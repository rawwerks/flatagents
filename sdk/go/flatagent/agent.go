// Package flatagent implements FlatAgent config parsing and execution.
//
// A FlatAgent represents a single LLM call: model + prompts + output schema.
// The package handles loading YAML configs, resolving model profiles,
// rendering prompt templates, and invoking the LLM through a pluggable
// LLMProvider interface.
package flatagent

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/memgrafter/flatagents/sdk/go/profiles"
	tmpl "github.com/memgrafter/flatagents/sdk/go/template"
	"github.com/memgrafter/flatagents/sdk/go/types"
	"gopkg.in/yaml.v3"
)

// Agent holds a parsed flatagent configuration and provides methods
// for rendering prompts and executing LLM calls.
type Agent struct {
	// Config is the raw parsed config wrapper.
	Config types.AgentWrapper

	// ResolvedModel is the fully resolved model configuration
	// after profile cascade.
	ResolvedModel types.ModelConfig

	// ProfileManager handles profile resolution.
	ProfileManager *profiles.Manager

	// configDir is the directory containing the agent config file.
	configDir string
}

// LoadOptions configures how an agent is loaded.
type LoadOptions struct {
	// ProfilesFile is an explicit path to profiles.yml.
	// If empty, auto-discovery is used.
	ProfilesFile string

	// ProfilesData provides pre-loaded profiles data, taking precedence
	// over file-based loading.
	ProfilesData *profiles.ProfilesData
}

// Load loads a FlatAgent from a YAML config file.
func Load(configFile string, opts *LoadOptions) (*Agent, error) {
	data, err := os.ReadFile(configFile)
	if err != nil {
		return nil, fmt.Errorf("reading agent config: %w", err)
	}

	var wrapper types.AgentWrapper
	if err := yaml.Unmarshal(data, &wrapper); err != nil {
		return nil, fmt.Errorf("parsing agent YAML: %w", err)
	}

	configDir := filepath.Dir(configFile)
	if !filepath.IsAbs(configDir) {
		abs, err := filepath.Abs(configDir)
		if err == nil {
			configDir = abs
		}
	}

	return fromWrapper(wrapper, configDir, opts)
}

// LoadFromDict loads a FlatAgent from an in-memory config dict.
func LoadFromDict(config types.AgentWrapper, opts *LoadOptions) (*Agent, error) {
	cwd, _ := os.Getwd()
	return fromWrapper(config, cwd, opts)
}

func fromWrapper(wrapper types.AgentWrapper, configDir string, opts *LoadOptions) (*Agent, error) {
	// Validate spec
	if wrapper.Spec != "flatagent" {
		return nil, fmt.Errorf("invalid spec: expected 'flatagent', got '%s'", wrapper.Spec)
	}

	if opts == nil {
		opts = &LoadOptions{}
	}

	// Load profiles
	var mgr *profiles.Manager
	if opts.ProfilesData != nil {
		mgr = profiles.NewManager(opts.ProfilesData)
	} else {
		profilesPath := profiles.DiscoverFile(configDir, opts.ProfilesFile)
		if profilesPath != "" {
			var err error
			mgr, err = profiles.LoadFromFile(profilesPath)
			if err != nil {
				// Non-fatal: continue without profiles
				mgr = profiles.NewManager(nil)
			}
		} else {
			mgr = profiles.NewManager(nil)
		}
	}

	// Resolve model config through profiles
	resolved, err := mgr.Resolve(wrapper.Data.Model)
	if err != nil {
		return nil, fmt.Errorf("resolving model config: %w", err)
	}

	// Infer agent name from filename if not set
	if wrapper.Data.Name == "" {
		if meta, ok := wrapper.Metadata["name"]; ok {
			if name, ok := meta.(string); ok {
				wrapper.Data.Name = name
			}
		}
		if wrapper.Data.Name == "" {
			wrapper.Data.Name = "unnamed-agent"
		}
	}

	return &Agent{
		Config:         wrapper,
		ResolvedModel:  resolved,
		ProfileManager: mgr,
		configDir:      configDir,
	}, nil
}

// Name returns the agent's name.
func (a *Agent) Name() string {
	return a.Config.Data.Name
}

// ModelName returns the fully qualified model name (provider/name).
func (a *Agent) ModelName() string {
	return profiles.ModelName(a.ResolvedModel)
}

// RenderSystemPrompt renders the system prompt with the given input data.
func (a *Agent) RenderSystemPrompt(input map[string]interface{}) (string, error) {
	data := map[string]interface{}{
		"input": input,
	}
	return tmpl.Render(a.Config.Data.System, data)
}

// RenderUserPrompt renders the user prompt with the given input data.
// If an instruction_suffix is configured, it is appended after the rendered prompt.
func (a *Agent) RenderUserPrompt(input map[string]interface{}) (string, error) {
	data := map[string]interface{}{
		"input": input,
	}
	rendered, err := tmpl.Render(a.Config.Data.User, data)
	if err != nil {
		return "", err
	}
	if a.Config.Data.InstructionSuffix != "" {
		rendered = rendered + "\n\n" + a.Config.Data.InstructionSuffix
	}
	return rendered, nil
}

// BuildMessages constructs the message list for an LLM call.
func (a *Agent) BuildMessages(input map[string]interface{}) ([]types.Message, error) {
	systemPrompt, err := a.RenderSystemPrompt(input)
	if err != nil {
		return nil, fmt.Errorf("rendering system prompt: %w", err)
	}
	userPrompt, err := a.RenderUserPrompt(input)
	if err != nil {
		return nil, fmt.Errorf("rendering user prompt: %w", err)
	}

	return []types.Message{
		{Role: "system", Content: systemPrompt},
		{Role: "user", Content: userPrompt},
	}, nil
}

// BuildCallOptions constructs LLMCallOptions from the resolved model config.
func (a *Agent) BuildCallOptions() types.LLMCallOptions {
	cfg := a.ResolvedModel
	opts := types.LLMCallOptions{
		Model:            a.ModelName(),
		Temperature:      cfg.Temperature,
		MaxTokens:        cfg.MaxTokens,
		TopP:             cfg.TopP,
		TopK:             cfg.TopK,
		FrequencyPenalty: cfg.FrequencyPenalty,
		PresencePenalty:  cfg.PresencePenalty,
		Seed:             cfg.Seed,
		BaseURL:          cfg.BaseURL,
	}

	// Include tool definitions if present
	if len(a.Config.Data.Tools) > 0 {
		opts.Tools = a.Config.Data.Tools
	}

	// Use JSON response format if output schema is defined and no tools
	if len(a.Config.Data.Output) > 0 && len(opts.Tools) == 0 {
		opts.ResponseFormat = &types.ResponseFormat{Type: "json_object"}
	}

	return opts
}

// Call executes the agent with the given input using the provided LLM provider.
// It renders prompts, builds messages, invokes the LLM, and parses the output.
func (a *Agent) Call(provider types.LLMProvider, input map[string]interface{}) (*types.AgentResult, error) {
	messages, err := a.BuildMessages(input)
	if err != nil {
		return nil, fmt.Errorf("building messages: %w", err)
	}

	opts := a.BuildCallOptions()
	result, err := provider.Call(messages, opts)
	if err != nil {
		return nil, fmt.Errorf("calling LLM: %w", err)
	}

	// Parse output schema from content if applicable
	if len(a.Config.Data.Output) > 0 && result.Content != "" && result.Output == nil {
		content := stripMarkdownJSON(result.Content)
		var parsed map[string]interface{}
		if err := json.Unmarshal([]byte(content), &parsed); err == nil {
			result.Output = parsed
		} else {
			result.Output = map[string]interface{}{"_raw": result.Content}
		}
	}

	return result, nil
}

// stripMarkdownJSON removes markdown code fences from a JSON string.
// LLMs sometimes wrap JSON in ```json ... ``` blocks.
func stripMarkdownJSON(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```json") {
		s = strings.TrimPrefix(s, "```json")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	} else if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		s = strings.TrimSuffix(s, "```")
		s = strings.TrimSpace(s)
	}
	return s
}

// OutputSchema returns the agent's output schema.
func (a *Agent) OutputSchema() map[string]types.OutputField {
	return a.Config.Data.Output
}

// HasOutputSchema returns true if the agent has an output schema defined.
func (a *Agent) HasOutputSchema() bool {
	return len(a.Config.Data.Output) > 0
}

// ConfigDir returns the directory containing the agent config file.
func (a *Agent) ConfigDir() string {
	return a.configDir
}
