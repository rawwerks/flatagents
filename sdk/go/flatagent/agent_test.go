package flatagent

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/memgrafter/flatagents/sdk/go/profiles"
	"github.com/memgrafter/flatagents/sdk/go/types"
)

func writeFile(t *testing.T, dir, name, content string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("writing %s: %v", name, err)
	}
	return path
}

func TestLoadAgent(t *testing.T) {
	dir := t.TempDir()
	agentYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: test-agent
  model:
    provider: openai
    name: gpt-4
    temperature: 0.3
  system: "You are a test agent."
  user: "Question: {{ input.question }}"
  output:
    answer:
      type: str
      description: "The answer"
`
	agentPath := writeFile(t, dir, "agent.yml", agentYAML)

	agent, err := Load(agentPath, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if agent.Name() != "test-agent" {
		t.Errorf("expected name 'test-agent', got %q", agent.Name())
	}
	if agent.ModelName() != "openai/gpt-4" {
		t.Errorf("expected model 'openai/gpt-4', got %q", agent.ModelName())
	}
	if !agent.HasOutputSchema() {
		t.Error("expected output schema")
	}
}

func TestLoadAgentWithProfiles(t *testing.T) {
	dir := t.TempDir()

	profilesYAML := `
spec: flatprofiles
spec_version: "2.2.2"
data:
  model_profiles:
    fast:
      provider: cerebras
      name: zai-glm-4.6
      temperature: 0.6
      max_tokens: 2048
  default: fast
`
	writeFile(t, dir, "profiles.yml", profilesYAML)

	agentYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: profiled-agent
  model: "fast"
  system: "System prompt."
  user: "User prompt."
`
	agentPath := writeFile(t, dir, "agent.yml", agentYAML)

	agent, err := Load(agentPath, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if agent.ResolvedModel.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", agent.ResolvedModel.Provider)
	}
	if agent.ResolvedModel.Name != "zai-glm-4.6" {
		t.Errorf("expected name 'zai-glm-4.6', got %q", agent.ResolvedModel.Name)
	}
}

func TestLoadAgentProfiledWithOverrides(t *testing.T) {
	dir := t.TempDir()

	profilesYAML := `
spec: flatprofiles
spec_version: "2.2.2"
data:
  model_profiles:
    fast:
      provider: cerebras
      name: zai-glm-4.6
      temperature: 0.6
      max_tokens: 2048
`
	writeFile(t, dir, "profiles.yml", profilesYAML)

	agentYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: overridden-agent
  model:
    profile: "fast"
    max_tokens: 200
  system: "System."
  user: "User."
`
	agentPath := writeFile(t, dir, "agent.yml", agentYAML)

	agent, err := Load(agentPath, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if agent.ResolvedModel.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", agent.ResolvedModel.Provider)
	}
	if *agent.ResolvedModel.MaxTokens != 200 {
		t.Errorf("expected max_tokens 200, got %d", *agent.ResolvedModel.MaxTokens)
	}
}

func TestRenderPrompts(t *testing.T) {
	agent := &Agent{
		Config: types.AgentWrapper{
			Spec:        "flatagent",
			SpecVersion: "2.2.2",
			Data: types.AgentData{
				Name:   "test",
				System: "You analyze {{ input.thing }}.",
				User:   "Analyze: {{ input.query }}",
			},
		},
	}

	input := map[string]interface{}{
		"thing": "code",
		"query": "func main() {}",
	}

	sys, err := agent.RenderSystemPrompt(input)
	if err != nil {
		t.Fatalf("rendering system prompt: %v", err)
	}
	if sys != "You analyze code." {
		t.Errorf("system prompt = %q", sys)
	}

	usr, err := agent.RenderUserPrompt(input)
	if err != nil {
		t.Fatalf("rendering user prompt: %v", err)
	}
	if usr != "Analyze: func main() {}" {
		t.Errorf("user prompt = %q", usr)
	}
}

func TestRenderPromptWithSuffix(t *testing.T) {
	agent := &Agent{
		Config: types.AgentWrapper{
			Data: types.AgentData{
				User:              "Question: {{ input.q }}",
				InstructionSuffix: "Be concise.",
			},
		},
	}

	input := map[string]interface{}{"q": "What is Go?"}
	usr, err := agent.RenderUserPrompt(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if usr != "Question: What is Go?\n\nBe concise." {
		t.Errorf("unexpected prompt: %q", usr)
	}
}

func TestBuildMessages(t *testing.T) {
	agent := &Agent{
		Config: types.AgentWrapper{
			Data: types.AgentData{
				System: "You are helpful.",
				User:   "Say hello to {{ input.name }}",
			},
		},
	}

	msgs, err := agent.BuildMessages(map[string]interface{}{"name": "Bob"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(msgs) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(msgs))
	}
	if msgs[0].Role != "system" {
		t.Errorf("expected system role, got %q", msgs[0].Role)
	}
	if msgs[1].Content != "Say hello to Bob" {
		t.Errorf("unexpected user content: %q", msgs[1].Content)
	}
}

func TestBuildCallOptions(t *testing.T) {
	temp := 0.7
	maxTok := 2048
	agent := &Agent{
		ResolvedModel: types.ModelConfig{
			Provider:    "openai",
			Name:        "gpt-4",
			Temperature: &temp,
			MaxTokens:   &maxTok,
		},
		Config: types.AgentWrapper{
			Data: types.AgentData{
				Output: map[string]types.OutputField{
					"answer": {Type: "str"},
				},
			},
		},
	}

	opts := agent.BuildCallOptions()
	if opts.Model != "openai/gpt-4" {
		t.Errorf("expected model 'openai/gpt-4', got %q", opts.Model)
	}
	if *opts.Temperature != 0.7 {
		t.Errorf("expected temperature 0.7, got %f", *opts.Temperature)
	}
	if *opts.MaxTokens != 2048 {
		t.Errorf("expected max_tokens 2048, got %d", *opts.MaxTokens)
	}
	if opts.ResponseFormat == nil || opts.ResponseFormat.Type != "json_object" {
		t.Error("expected json_object response format when output schema is set")
	}
}

func TestBuildCallOptionsNoJSONForTools(t *testing.T) {
	agent := &Agent{
		ResolvedModel: types.ModelConfig{
			Provider: "openai",
			Name:     "gpt-4",
		},
		Config: types.AgentWrapper{
			Data: types.AgentData{
				Output: map[string]types.OutputField{
					"answer": {Type: "str"},
				},
				Tools: []types.ToolDefinition{
					{Type: "function", Function: types.ToolFunction{Name: "search"}},
				},
			},
		},
	}

	opts := agent.BuildCallOptions()
	if opts.ResponseFormat != nil {
		t.Error("expected no json_object format when tools are present")
	}
	if len(opts.Tools) != 1 {
		t.Errorf("expected 1 tool, got %d", len(opts.Tools))
	}
}

func TestLoadFromDict(t *testing.T) {
	config := types.AgentWrapper{
		Spec:        "flatagent",
		SpecVersion: "2.2.2",
		Data: types.AgentData{
			Name: "dict-agent",
			Model: types.ModelField{
				Config: &types.ModelConfig{
					Provider: "openai",
					Name:     "gpt-4",
				},
			},
			System: "Test system.",
			User:   "Test user.",
		},
	}

	agent, err := LoadFromDict(config, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if agent.Name() != "dict-agent" {
		t.Errorf("expected name 'dict-agent', got %q", agent.Name())
	}
}

func TestInvalidSpec(t *testing.T) {
	config := types.AgentWrapper{
		Spec: "wrong",
		Data: types.AgentData{},
	}
	_, err := LoadFromDict(config, nil)
	if err == nil {
		t.Error("expected error for invalid spec")
	}
}

func TestStripMarkdownJSON(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{`{"key": "val"}`, `{"key": "val"}`},
		{"```json\n{\"key\": \"val\"}\n```", `{"key": "val"}`},
		{"```\n{\"key\": \"val\"}\n```", `{"key": "val"}`},
	}
	for _, tt := range tests {
		got := stripMarkdownJSON(tt.input)
		if got != tt.expected {
			t.Errorf("stripMarkdownJSON(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestLoadAgentWithExplicitProfilesData(t *testing.T) {
	config := types.AgentWrapper{
		Spec:        "flatagent",
		SpecVersion: "2.2.2",
		Data: types.AgentData{
			Name:   "explicit-profiles",
			Model:  types.ModelField{ProfileName: "my-profile"},
			System: "System.",
			User:   "User.",
		},
	}

	temp := 0.5
	opts := &LoadOptions{
		ProfilesData: &profiles.ProfilesData{
			ModelProfiles: map[string]types.ModelConfig{
				"my-profile": {
					Provider:    "anthropic",
					Name:        "claude-3",
					Temperature: &temp,
				},
			},
		},
	}

	agent, err := LoadFromDict(config, opts)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if agent.ResolvedModel.Provider != "anthropic" {
		t.Errorf("expected provider 'anthropic', got %q", agent.ResolvedModel.Provider)
	}
	if agent.ModelName() != "anthropic/claude-3" {
		t.Errorf("expected model name 'anthropic/claude-3', got %q", agent.ModelName())
	}
}
