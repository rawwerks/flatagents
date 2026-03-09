// Package types defines the shared data types for the flatagents Go SDK.
//
// These types mirror the TypeScript spec defined in flatagent.d.ts,
// flatmachine.d.ts, profiles.d.ts, and flatagents-runtime.d.ts.
package types

const SpecVersion = "2.2.2"

// ---------------------------------------------------------------------------
// FlatAgent types (flatagent.d.ts)
// ---------------------------------------------------------------------------

// AgentWrapper is the top-level container for a flatagent config file.
type AgentWrapper struct {
	Spec        string                 `yaml:"spec" json:"spec"`
	SpecVersion string                 `yaml:"spec_version" json:"spec_version"`
	Data        AgentData              `yaml:"data" json:"data"`
	Metadata    map[string]interface{} `yaml:"metadata,omitempty" json:"metadata,omitempty"`
}

// AgentData holds the agent's configuration.
// The Model field is flexible: it can be a string (profile name), an inline
// ModelConfig, or a ProfiledModelConfig (profile + overrides).
type AgentData struct {
	Name              string                 `yaml:"name,omitempty" json:"name,omitempty"`
	Model             ModelField             `yaml:"model" json:"model"`
	System            string                 `yaml:"system" json:"system"`
	User              string                 `yaml:"user" json:"user"`
	InstructionSuffix string                 `yaml:"instruction_suffix,omitempty" json:"instruction_suffix,omitempty"`
	Output            map[string]OutputField `yaml:"output,omitempty" json:"output,omitempty"`
	MCP               *MCPConfig             `yaml:"mcp,omitempty" json:"mcp,omitempty"`
	Tools             []ToolDefinition       `yaml:"tools,omitempty" json:"tools,omitempty"`
}

// ModelField handles the three forms of the model field:
//   - string: profile name
//   - map with "profile" key: ProfiledModelConfig
//   - map with "name"/"provider" keys: inline ModelConfig
type ModelField struct {
	// Raw holds the unparsed YAML value for custom unmarshaling.
	Raw interface{} `yaml:"-" json:"-"`

	// ProfileName is set when model is a plain string.
	ProfileName string `yaml:"-" json:"-"`

	// Config is set when model is an inline ModelConfig (no profile key).
	Config *ModelConfig `yaml:"-" json:"-"`

	// Profiled is set when model is a ProfiledModelConfig (has profile key).
	Profiled *ProfiledModelConfig `yaml:"-" json:"-"`
}

// IsString returns true if the model field is a profile name string.
func (m *ModelField) IsString() bool { return m.ProfileName != "" }

// IsProfiled returns true if the model field references a profile with optional overrides.
func (m *ModelField) IsProfiled() bool { return m.Profiled != nil }

// IsInline returns true if the model field is a full inline config.
func (m *ModelField) IsInline() bool { return m.Config != nil }

// UnmarshalYAML implements custom YAML unmarshaling for the polymorphic model field.
func (m *ModelField) UnmarshalYAML(unmarshal func(interface{}) error) error {
	// Try string first.
	var s string
	if err := unmarshal(&s); err == nil {
		m.ProfileName = s
		m.Raw = s
		return nil
	}

	// Try map.
	var raw map[string]interface{}
	if err := unmarshal(&raw); err != nil {
		return err
	}
	m.Raw = raw

	if _, ok := raw["profile"]; ok {
		// ProfiledModelConfig
		p := &ProfiledModelConfig{}
		if err := unmarshal(p); err != nil {
			return err
		}
		m.Profiled = p
	} else {
		// Inline ModelConfig
		c := &ModelConfig{}
		if err := unmarshal(c); err != nil {
			return err
		}
		m.Config = c
	}
	return nil
}

// ModelConfig defines inline LLM model parameters.
type ModelConfig struct {
	Name             string   `yaml:"name" json:"name"`
	Provider         string   `yaml:"provider,omitempty" json:"provider,omitempty"`
	Temperature      *float64 `yaml:"temperature,omitempty" json:"temperature,omitempty"`
	MaxTokens        *int     `yaml:"max_tokens,omitempty" json:"max_tokens,omitempty"`
	TopP             *float64 `yaml:"top_p,omitempty" json:"top_p,omitempty"`
	TopK             *int     `yaml:"top_k,omitempty" json:"top_k,omitempty"`
	FrequencyPenalty *float64 `yaml:"frequency_penalty,omitempty" json:"frequency_penalty,omitempty"`
	PresencePenalty  *float64 `yaml:"presence_penalty,omitempty" json:"presence_penalty,omitempty"`
	Seed             *int     `yaml:"seed,omitempty" json:"seed,omitempty"`
	BaseURL          string   `yaml:"base_url,omitempty" json:"base_url,omitempty"`
}

// ProfiledModelConfig references a named profile with optional overrides.
type ProfiledModelConfig struct {
	Profile          string   `yaml:"profile" json:"profile"`
	Name             string   `yaml:"name,omitempty" json:"name,omitempty"`
	Provider         string   `yaml:"provider,omitempty" json:"provider,omitempty"`
	Temperature      *float64 `yaml:"temperature,omitempty" json:"temperature,omitempty"`
	MaxTokens        *int     `yaml:"max_tokens,omitempty" json:"max_tokens,omitempty"`
	TopP             *float64 `yaml:"top_p,omitempty" json:"top_p,omitempty"`
	TopK             *int     `yaml:"top_k,omitempty" json:"top_k,omitempty"`
	FrequencyPenalty *float64 `yaml:"frequency_penalty,omitempty" json:"frequency_penalty,omitempty"`
	PresencePenalty  *float64 `yaml:"presence_penalty,omitempty" json:"presence_penalty,omitempty"`
	Seed             *int     `yaml:"seed,omitempty" json:"seed,omitempty"`
	BaseURL          string   `yaml:"base_url,omitempty" json:"base_url,omitempty"`
}

// Overrides returns a ModelConfig containing only the override fields
// (everything except the profile name).
func (p *ProfiledModelConfig) Overrides() ModelConfig {
	return ModelConfig{
		Name:             p.Name,
		Provider:         p.Provider,
		Temperature:      p.Temperature,
		MaxTokens:        p.MaxTokens,
		TopP:             p.TopP,
		TopK:             p.TopK,
		FrequencyPenalty: p.FrequencyPenalty,
		PresencePenalty:  p.PresencePenalty,
		Seed:             p.Seed,
		BaseURL:          p.BaseURL,
	}
}

// ToolDefinition defines a tool the agent can use.
type ToolDefinition struct {
	Type     string       `yaml:"type" json:"type"`
	Function ToolFunction `yaml:"function" json:"function"`
}

// ToolFunction describes a callable function for tool use.
type ToolFunction struct {
	Name        string                 `yaml:"name" json:"name"`
	Description string                 `yaml:"description,omitempty" json:"description,omitempty"`
	Parameters  map[string]interface{} `yaml:"parameters,omitempty" json:"parameters,omitempty"`
}

// MCPConfig defines MCP (Model Context Protocol) configuration.
type MCPConfig struct {
	Servers    map[string]MCPServerDef `yaml:"servers" json:"servers"`
	ToolFilter *ToolFilter             `yaml:"tool_filter,omitempty" json:"tool_filter,omitempty"`
	ToolPrompt string                  `yaml:"tool_prompt" json:"tool_prompt"`
}

// MCPServerDef defines an MCP server, either stdio or HTTP transport.
type MCPServerDef struct {
	// Stdio transport
	Command string            `yaml:"command,omitempty" json:"command,omitempty"`
	Args    []string          `yaml:"args,omitempty" json:"args,omitempty"`
	Env     map[string]string `yaml:"env,omitempty" json:"env,omitempty"`
	// HTTP transport
	ServerURL string            `yaml:"server_url,omitempty" json:"server_url,omitempty"`
	Headers   map[string]string `yaml:"headers,omitempty" json:"headers,omitempty"`
	Timeout   *int              `yaml:"timeout,omitempty" json:"timeout,omitempty"`
}

// ToolFilter defines allow/deny rules for tool filtering.
type ToolFilter struct {
	Allow []string `yaml:"allow,omitempty" json:"allow,omitempty"`
	Deny  []string `yaml:"deny,omitempty" json:"deny,omitempty"`
}

// OutputField defines a single field in the output schema.
type OutputField struct {
	Type        string                 `yaml:"type" json:"type"`
	Description string                 `yaml:"description,omitempty" json:"description,omitempty"`
	Enum        []string               `yaml:"enum,omitempty" json:"enum,omitempty"`
	Required    *bool                  `yaml:"required,omitempty" json:"required,omitempty"`
	Items       *OutputField           `yaml:"items,omitempty" json:"items,omitempty"`
	Properties  map[string]OutputField `yaml:"properties,omitempty" json:"properties,omitempty"`
}

// IsRequired returns whether the field is required (default true).
func (f OutputField) IsRequired() bool {
	if f.Required == nil {
		return true
	}
	return *f.Required
}

// ---------------------------------------------------------------------------
// FlatMachine types (flatmachine.d.ts)
// ---------------------------------------------------------------------------

// MachineWrapper is the top-level container for a flatmachine config file.
type MachineWrapper struct {
	Spec        string                 `yaml:"spec" json:"spec"`
	SpecVersion string                 `yaml:"spec_version" json:"spec_version"`
	Data        MachineData            `yaml:"data" json:"data"`
	Metadata    map[string]interface{} `yaml:"metadata,omitempty" json:"metadata,omitempty"`
}

// MachineData holds the machine's configuration.
type MachineData struct {
	Name             string                        `yaml:"name,omitempty" json:"name,omitempty"`
	ExpressionEngine string                        `yaml:"expression_engine,omitempty" json:"expression_engine,omitempty"`
	Context          map[string]interface{}         `yaml:"context,omitempty" json:"context,omitempty"`
	Agents           map[string]AgentRef            `yaml:"agents,omitempty" json:"agents,omitempty"`
	Machines         map[string]interface{}         `yaml:"machines,omitempty" json:"machines,omitempty"`
	States           map[string]StateDefinition     `yaml:"states" json:"states"`
	Settings         *MachineSettings               `yaml:"settings,omitempty" json:"settings,omitempty"`
	Persistence      *PersistenceConfig             `yaml:"persistence,omitempty" json:"persistence,omitempty"`
	Hooks            interface{}                    `yaml:"hooks,omitempty" json:"hooks,omitempty"`
}

// AgentRef is a polymorphic reference to an agent.
// It can be a string path, an inline AgentWrapper, or a typed adapter ref.
type AgentRef struct {
	// Path is set when the agent ref is a string file path.
	Path string `yaml:"-" json:"-"`

	// Inline is set when the ref is a full inline agent config.
	Inline *AgentWrapper `yaml:"-" json:"-"`

	// Typed is set when the ref is a typed adapter reference.
	Typed *AgentRefConfig `yaml:"-" json:"-"`
}

// UnmarshalYAML implements custom YAML unmarshaling for the polymorphic AgentRef.
func (a *AgentRef) UnmarshalYAML(unmarshal func(interface{}) error) error {
	// Try string first.
	var s string
	if err := unmarshal(&s); err == nil {
		a.Path = s
		return nil
	}

	// Try map.
	var raw map[string]interface{}
	if err := unmarshal(&raw); err != nil {
		return err
	}

	if _, ok := raw["type"]; ok {
		// Typed adapter ref
		cfg := &AgentRefConfig{}
		if err := unmarshal(cfg); err != nil {
			return err
		}
		a.Typed = cfg
	} else if _, ok := raw["spec"]; ok {
		// Inline agent config
		w := &AgentWrapper{}
		if err := unmarshal(w); err != nil {
			return err
		}
		a.Inline = w
	} else {
		// Fallback: treat as path if there's a single key, else inline
		w := &AgentWrapper{}
		if err := unmarshal(w); err != nil {
			return err
		}
		a.Inline = w
	}
	return nil
}

// AgentRefConfig is a typed adapter reference.
type AgentRefConfig struct {
	Type   string                 `yaml:"type" json:"type"`
	Ref    string                 `yaml:"ref,omitempty" json:"ref,omitempty"`
	Config map[string]interface{} `yaml:"config,omitempty" json:"config,omitempty"`
}

// MachineSettings holds optional machine settings.
type MachineSettings struct {
	MaxSteps         *int   `yaml:"max_steps,omitempty" json:"max_steps,omitempty"`
	ParallelFallback string `yaml:"parallel_fallback,omitempty" json:"parallel_fallback,omitempty"`
}

// StateDefinition defines a state in the machine.
type StateDefinition struct {
	Type            string                 `yaml:"type,omitempty" json:"type,omitempty"`
	Agent           string                 `yaml:"agent,omitempty" json:"agent,omitempty"`
	Machine         interface{}            `yaml:"machine,omitempty" json:"machine,omitempty"`
	Action          string                 `yaml:"action,omitempty" json:"action,omitempty"`
	Execution       *ExecutionConfig       `yaml:"execution,omitempty" json:"execution,omitempty"`
	OnError         interface{}            `yaml:"on_error,omitempty" json:"on_error,omitempty"`
	WaitFor         string                 `yaml:"wait_for,omitempty" json:"wait_for,omitempty"`
	Input           map[string]interface{} `yaml:"input,omitempty" json:"input,omitempty"`
	OutputToContext map[string]interface{} `yaml:"output_to_context,omitempty" json:"output_to_context,omitempty"`
	Output          map[string]interface{} `yaml:"output,omitempty" json:"output,omitempty"`
	Transitions     []Transition           `yaml:"transitions,omitempty" json:"transitions,omitempty"`
	ToolLoop        interface{}            `yaml:"tool_loop,omitempty" json:"tool_loop,omitempty"`
	Sampling        string                 `yaml:"sampling,omitempty" json:"sampling,omitempty"`
	Foreach         string                 `yaml:"foreach,omitempty" json:"foreach,omitempty"`
	As              string                 `yaml:"as,omitempty" json:"as,omitempty"`
	Key             string                 `yaml:"key,omitempty" json:"key,omitempty"`
	Mode            string                 `yaml:"mode,omitempty" json:"mode,omitempty"`
	Timeout         *int                   `yaml:"timeout,omitempty" json:"timeout,omitempty"`
	Launch          interface{}            `yaml:"launch,omitempty" json:"launch,omitempty"`
	LaunchInput     map[string]interface{} `yaml:"launch_input,omitempty" json:"launch_input,omitempty"`
}

// ToolLoopConfig holds tool loop guardrails (when tool_loop is a map).
type ToolLoopConfig struct {
	MaxToolCalls *int     `yaml:"max_tool_calls,omitempty" json:"max_tool_calls,omitempty"`
	MaxTurns     *int     `yaml:"max_turns,omitempty" json:"max_turns,omitempty"`
	AllowedTools []string `yaml:"allowed_tools,omitempty" json:"allowed_tools,omitempty"`
	DeniedTools  []string `yaml:"denied_tools,omitempty" json:"denied_tools,omitempty"`
	ToolTimeout  *int     `yaml:"tool_timeout,omitempty" json:"tool_timeout,omitempty"`
	TotalTimeout *int     `yaml:"total_timeout,omitempty" json:"total_timeout,omitempty"`
	MaxCost      *float64 `yaml:"max_cost,omitempty" json:"max_cost,omitempty"`
}

// ToolLoopDefaults returns a ToolLoopConfig with spec default values.
func ToolLoopDefaults() ToolLoopConfig {
	maxToolCalls := 50
	maxTurns := 20
	toolTimeout := 30
	totalTimeout := 600
	return ToolLoopConfig{
		MaxToolCalls: &maxToolCalls,
		MaxTurns:     &maxTurns,
		ToolTimeout:  &toolTimeout,
		TotalTimeout: &totalTimeout,
	}
}

// ExecutionConfig configures the execution strategy for an agent call.
type ExecutionConfig struct {
	Type          string    `yaml:"type" json:"type"`
	Backoffs      []float64 `yaml:"backoffs,omitempty" json:"backoffs,omitempty"`
	Jitter        *float64  `yaml:"jitter,omitempty" json:"jitter,omitempty"`
	NSamples      *int      `yaml:"n_samples,omitempty" json:"n_samples,omitempty"`
	KMargin       *float64  `yaml:"k_margin,omitempty" json:"k_margin,omitempty"`
	MaxCandidates *int      `yaml:"max_candidates,omitempty" json:"max_candidates,omitempty"`
}

// Transition defines a conditional transition between states.
type Transition struct {
	Condition string `yaml:"condition,omitempty" json:"condition,omitempty"`
	To        string `yaml:"to" json:"to"`
}

// PersistenceConfig configures checkpoint persistence.
type PersistenceConfig struct {
	Enabled      bool     `yaml:"enabled" json:"enabled"`
	Backend      string   `yaml:"backend" json:"backend"`
	DBPath       string   `yaml:"db_path,omitempty" json:"db_path,omitempty"`
	CheckpointOn []string `yaml:"checkpoint_on,omitempty" json:"checkpoint_on,omitempty"`
}

// ---------------------------------------------------------------------------
// Runtime types (flatagents-runtime.d.ts)
// ---------------------------------------------------------------------------

// AgentResult is the universal result contract for agent execution.
type AgentResult struct {
	Output       map[string]interface{} `json:"output,omitempty"`
	Content      string                 `json:"content,omitempty"`
	Usage        *UsageInfo             `json:"usage,omitempty"`
	Cost         *CostInfo              `json:"cost,omitempty"`
	Metadata     map[string]interface{} `json:"metadata,omitempty"`
	FinishReason string                 `json:"finish_reason,omitempty"`
	Error        *AgentError            `json:"error,omitempty"`
	RateLimit    *RateLimitState        `json:"rate_limit,omitempty"`
	ProviderData *ProviderData          `json:"provider_data,omitempty"`
}

// UsageInfo holds token usage information.
type UsageInfo struct {
	InputTokens     int `json:"input_tokens,omitempty"`
	OutputTokens    int `json:"output_tokens,omitempty"`
	TotalTokens     int `json:"total_tokens,omitempty"`
	CacheReadTokens int `json:"cache_read_tokens,omitempty"`
	CacheWriteTokens int `json:"cache_write_tokens,omitempty"`
}

// CostInfo holds per-field cost breakdown.
type CostInfo struct {
	Input      float64 `json:"input,omitempty"`
	Output     float64 `json:"output,omitempty"`
	CacheRead  float64 `json:"cache_read,omitempty"`
	CacheWrite float64 `json:"cache_write,omitempty"`
	Total      float64 `json:"total,omitempty"`
}

// AgentError describes an error from an agent call.
type AgentError struct {
	Code       string `json:"code,omitempty"`
	Type       string `json:"type,omitempty"`
	Message    string `json:"message"`
	StatusCode int    `json:"status_code,omitempty"`
	Retryable  bool   `json:"retryable,omitempty"`
}

func (e *AgentError) Error() string { return e.Message }

// RateLimitState holds normalized rate limit information.
type RateLimitState struct {
	Limited    bool              `json:"limited"`
	RetryAfter *float64          `json:"retry_after,omitempty"`
	Windows    []RateLimitWindow `json:"windows,omitempty"`
}

// RateLimitWindow describes a single rate limit window.
type RateLimitWindow struct {
	Name      string   `json:"name"`
	Resource  string   `json:"resource"`
	Remaining *int     `json:"remaining,omitempty"`
	Limit     *int     `json:"limit,omitempty"`
	ResetsIn  *float64 `json:"resets_in,omitempty"`
	ResetAt   *float64 `json:"reset_at,omitempty"`
}

// ProviderData holds provider-specific metadata.
type ProviderData struct {
	Provider   string            `json:"provider,omitempty"`
	Model      string            `json:"model,omitempty"`
	RequestID  string            `json:"request_id,omitempty"`
	RawHeaders map[string]string `json:"raw_headers,omitempty"`
}

// Message represents a chat message in the LLM conversation.
type Message struct {
	Role       string     `json:"role"`
	Content    string     `json:"content"`
	ToolCallID string     `json:"tool_call_id,omitempty"`
	ToolCalls  []ToolCall `json:"tool_calls,omitempty"`
}

// ToolCall represents a tool call from the LLM.
type ToolCall struct {
	ID       string           `json:"id"`
	Type     string           `json:"type"`
	Function ToolCallFunction `json:"function"`
}

// ToolCallFunction holds the function name and arguments (JSON string) for a tool call.
type ToolCallFunction struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

// MachineSnapshot is the wire format for checkpoints.
type MachineSnapshot struct {
	ExecutionID       string                 `json:"execution_id"`
	MachineName       string                 `json:"machine_name"`
	SpecVersion       string                 `json:"spec_version"`
	CurrentState      string                 `json:"current_state"`
	Context           map[string]interface{} `json:"context"`
	Step              int                    `json:"step"`
	CreatedAt         string                 `json:"created_at"`
	Event             string                 `json:"event,omitempty"`
	Output            map[string]interface{} `json:"output,omitempty"`
	TotalAPICalls     int                    `json:"total_api_calls,omitempty"`
	TotalCost         float64                `json:"total_cost,omitempty"`
	ParentExecutionID string                 `json:"parent_execution_id,omitempty"`
	PendingLaunches   []LaunchIntent         `json:"pending_launches,omitempty"`
	WaitingChannel    string                 `json:"waiting_channel,omitempty"`
	ConfigHash        string                 `json:"config_hash,omitempty"`
}

// LaunchIntent records a pending machine launch (outbox pattern).
type LaunchIntent struct {
	ExecutionID string                 `json:"execution_id"`
	Machine     string                 `json:"machine"`
	Input       map[string]interface{} `json:"input"`
	Launched    bool                   `json:"launched"`
}

// ---------------------------------------------------------------------------
// LLM Provider interface
// ---------------------------------------------------------------------------

// LLMProvider is the interface users implement to plug in any LLM backend.
// The SDK does not ship a concrete provider -- users bring their own.
type LLMProvider interface {
	// Call sends messages to the LLM and returns the result.
	// opts contains model parameters (temperature, max_tokens, tools, etc.).
	Call(messages []Message, opts LLMCallOptions) (*AgentResult, error)
}

// LLMCallOptions carries per-call parameters for the LLM provider.
type LLMCallOptions struct {
	Model            string           `json:"model,omitempty"`
	Temperature      *float64         `json:"temperature,omitempty"`
	MaxTokens        *int             `json:"max_tokens,omitempty"`
	TopP             *float64         `json:"top_p,omitempty"`
	TopK             *int             `json:"top_k,omitempty"`
	FrequencyPenalty *float64         `json:"frequency_penalty,omitempty"`
	PresencePenalty  *float64         `json:"presence_penalty,omitempty"`
	Seed             *int             `json:"seed,omitempty"`
	BaseURL          string           `json:"base_url,omitempty"`
	Tools            []ToolDefinition `json:"tools,omitempty"`
	ResponseFormat   *ResponseFormat  `json:"response_format,omitempty"`
}

// ResponseFormat specifies the desired response format.
type ResponseFormat struct {
	Type string `json:"type"` // "json_object" or "text"
}

// ---------------------------------------------------------------------------
// Hooks interface
// ---------------------------------------------------------------------------

// MachineHooks provides extension points for machine execution.
// All methods are optional -- implement only what you need.
type MachineHooks interface {
	OnMachineStart(ctx map[string]interface{}) (map[string]interface{}, error)
	OnMachineEnd(ctx map[string]interface{}, output interface{}) (interface{}, error)
	OnStateEnter(state string, ctx map[string]interface{}) (map[string]interface{}, error)
	OnStateExit(state string, ctx map[string]interface{}, output interface{}) (interface{}, error)
	OnTransition(from, to string, ctx map[string]interface{}) (string, error)
	OnError(state string, err error, ctx map[string]interface{}) (string, error)
	OnAction(action string, ctx map[string]interface{}) (map[string]interface{}, error)
}

// NoOpHooks is a default hooks implementation that does nothing.
// Embed this in your hooks struct to only override the methods you need.
type NoOpHooks struct{}

func (n NoOpHooks) OnMachineStart(ctx map[string]interface{}) (map[string]interface{}, error) {
	return ctx, nil
}
func (n NoOpHooks) OnMachineEnd(ctx map[string]interface{}, output interface{}) (interface{}, error) {
	return output, nil
}
func (n NoOpHooks) OnStateEnter(state string, ctx map[string]interface{}) (map[string]interface{}, error) {
	return ctx, nil
}
func (n NoOpHooks) OnStateExit(state string, ctx map[string]interface{}, output interface{}) (interface{}, error) {
	return output, nil
}
func (n NoOpHooks) OnTransition(from, to string, ctx map[string]interface{}) (string, error) {
	return to, nil
}
func (n NoOpHooks) OnError(state string, err error, ctx map[string]interface{}) (string, error) {
	return "", err
}
func (n NoOpHooks) OnAction(action string, ctx map[string]interface{}) (map[string]interface{}, error) {
	return ctx, nil
}
