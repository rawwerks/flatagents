package types

import (
	"testing"

	"gopkg.in/yaml.v3"
)

func TestModelFieldUnmarshalString(t *testing.T) {
	input := `"fast-cheap"`
	var mf ModelField
	if err := yaml.Unmarshal([]byte(input), &mf); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !mf.IsString() {
		t.Error("expected IsString() to be true")
	}
	if mf.ProfileName != "fast-cheap" {
		t.Errorf("expected ProfileName 'fast-cheap', got %q", mf.ProfileName)
	}
}

func TestModelFieldUnmarshalInline(t *testing.T) {
	input := `
provider: openai
name: gpt-4
temperature: 0.3
`
	var mf ModelField
	if err := yaml.Unmarshal([]byte(input), &mf); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !mf.IsInline() {
		t.Error("expected IsInline() to be true")
	}
	if mf.Config.Name != "gpt-4" {
		t.Errorf("expected Name 'gpt-4', got %q", mf.Config.Name)
	}
	if mf.Config.Provider != "openai" {
		t.Errorf("expected Provider 'openai', got %q", mf.Config.Provider)
	}
	if mf.Config.Temperature == nil || *mf.Config.Temperature != 0.3 {
		t.Error("expected Temperature 0.3")
	}
}

func TestModelFieldUnmarshalProfiled(t *testing.T) {
	input := `
profile: fast-cheap
temperature: 0.9
`
	var mf ModelField
	if err := yaml.Unmarshal([]byte(input), &mf); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !mf.IsProfiled() {
		t.Error("expected IsProfiled() to be true")
	}
	if mf.Profiled.Profile != "fast-cheap" {
		t.Errorf("expected Profile 'fast-cheap', got %q", mf.Profiled.Profile)
	}
	if mf.Profiled.Temperature == nil || *mf.Profiled.Temperature != 0.9 {
		t.Error("expected Temperature 0.9")
	}
}

func TestAgentWrapperParse(t *testing.T) {
	input := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: critic
  model:
    provider: cerebras
    name: zai-glm-4.6
    temperature: 0.5
  system: |
    Act as a ruthless critic.
  user: |
    Question: {{ input.question }}
  output:
    critique:
      type: str
      description: "Specific errors found"
    severity:
      type: str
      enum: ["High", "Medium", "Low"]
metadata:
  description: "Critiques draft answers"
  tags: ["reflection", "qa"]
`
	var w AgentWrapper
	if err := yaml.Unmarshal([]byte(input), &w); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if w.Spec != "flatagent" {
		t.Errorf("expected spec 'flatagent', got %q", w.Spec)
	}
	if w.SpecVersion != "2.2.2" {
		t.Errorf("expected spec_version '2.2.2', got %q", w.SpecVersion)
	}
	if w.Data.Name != "critic" {
		t.Errorf("expected name 'critic', got %q", w.Data.Name)
	}
	if !w.Data.Model.IsInline() {
		t.Error("expected inline model config")
	}
	if w.Data.Model.Config.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", w.Data.Model.Config.Provider)
	}
	if len(w.Data.Output) != 2 {
		t.Errorf("expected 2 output fields, got %d", len(w.Data.Output))
	}
	critique := w.Data.Output["critique"]
	if critique.Type != "str" {
		t.Errorf("expected critique type 'str', got %q", critique.Type)
	}
	severity := w.Data.Output["severity"]
	if len(severity.Enum) != 3 {
		t.Errorf("expected 3 enum values, got %d", len(severity.Enum))
	}
}

func TestMachineWrapperParse(t *testing.T) {
	input := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: writer-critic-loop
  context:
    product: "{{ input.product }}"
    score: 0
    round: 0
  agents:
    writer: ./writer.yml
    critic: ./critic.yml
  states:
    start:
      type: initial
      transitions:
        - to: write
    write:
      agent: writer
      input:
        product: "{{ context.product }}"
      output_to_context:
        tagline: "{{ output.tagline }}"
      transitions:
        - to: review
    review:
      agent: critic
      transitions:
        - condition: "context.score >= 8"
          to: done
        - to: write
    done:
      type: final
      output:
        tagline: "{{ context.tagline }}"
`
	var w MachineWrapper
	if err := yaml.Unmarshal([]byte(input), &w); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if w.Spec != "flatmachine" {
		t.Errorf("expected spec 'flatmachine', got %q", w.Spec)
	}
	if w.Data.Name != "writer-critic-loop" {
		t.Errorf("expected name 'writer-critic-loop', got %q", w.Data.Name)
	}
	if len(w.Data.Agents) != 2 {
		t.Errorf("expected 2 agents, got %d", len(w.Data.Agents))
	}
	if w.Data.Agents["writer"].Path != "./writer.yml" {
		t.Errorf("expected writer path './writer.yml', got %q", w.Data.Agents["writer"].Path)
	}
	if len(w.Data.States) != 4 {
		t.Errorf("expected 4 states, got %d", len(w.Data.States))
	}
	review := w.Data.States["review"]
	if len(review.Transitions) != 2 {
		t.Errorf("expected 2 transitions in review, got %d", len(review.Transitions))
	}
	if review.Transitions[0].Condition != "context.score >= 8" {
		t.Errorf("unexpected condition: %q", review.Transitions[0].Condition)
	}
}

func TestOutputFieldRequired(t *testing.T) {
	// Default is required
	f := OutputField{Type: "str"}
	if !f.IsRequired() {
		t.Error("expected default required to be true")
	}

	// Explicit false
	b := false
	f2 := OutputField{Type: "str", Required: &b}
	if f2.IsRequired() {
		t.Error("expected explicit false")
	}
}

func TestToolLoopDefaults(t *testing.T) {
	d := ToolLoopDefaults()
	if *d.MaxToolCalls != 50 {
		t.Errorf("expected MaxToolCalls 50, got %d", *d.MaxToolCalls)
	}
	if *d.MaxTurns != 20 {
		t.Errorf("expected MaxTurns 20, got %d", *d.MaxTurns)
	}
	if *d.ToolTimeout != 30 {
		t.Errorf("expected ToolTimeout 30, got %d", *d.ToolTimeout)
	}
	if *d.TotalTimeout != 600 {
		t.Errorf("expected TotalTimeout 600, got %d", *d.TotalTimeout)
	}
}

func TestNoOpHooks(t *testing.T) {
	h := NoOpHooks{}
	ctx := map[string]interface{}{"key": "val"}

	out, err := h.OnMachineStart(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out["key"] != "val" {
		t.Error("expected context passed through")
	}

	_, err = h.OnMachineEnd(ctx, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	to, err := h.OnTransition("a", "b", ctx)
	if err != nil || to != "b" {
		t.Error("expected transition to pass through")
	}
}

func TestAgentErrorImplementsError(t *testing.T) {
	e := &AgentError{Message: "something failed", Code: "rate_limit"}
	var err error = e
	if err.Error() != "something failed" {
		t.Errorf("expected error message, got %q", err.Error())
	}
}

func TestMCPConfigParse(t *testing.T) {
	input := `
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/docs"]
tool_filter:
  allow: ["filesystem:read_file"]
  deny: ["filesystem:write_file"]
tool_prompt: |
  You have tools.
`
	var cfg MCPConfig
	if err := yaml.Unmarshal([]byte(input), &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(cfg.Servers) != 1 {
		t.Errorf("expected 1 server, got %d", len(cfg.Servers))
	}
	fs := cfg.Servers["filesystem"]
	if fs.Command != "npx" {
		t.Errorf("expected command 'npx', got %q", fs.Command)
	}
	if len(fs.Args) != 3 {
		t.Errorf("expected 3 args, got %d", len(fs.Args))
	}
	if cfg.ToolFilter == nil {
		t.Fatal("expected tool_filter to be set")
	}
	if len(cfg.ToolFilter.Allow) != 1 {
		t.Errorf("expected 1 allow rule, got %d", len(cfg.ToolFilter.Allow))
	}
	if len(cfg.ToolFilter.Deny) != 1 {
		t.Errorf("expected 1 deny rule, got %d", len(cfg.ToolFilter.Deny))
	}
}
