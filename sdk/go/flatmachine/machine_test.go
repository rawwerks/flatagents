package flatmachine

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

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

func TestLoadMachine(t *testing.T) {
	dir := t.TempDir()

	profilesYAML := `
spec: flatprofiles
spec_version: "2.2.2"
data:
  model_profiles:
    fast:
      provider: openai
      name: gpt-4
      temperature: 0.6
  default: fast
`
	writeFile(t, dir, "profiles.yml", profilesYAML)

	writerYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: writer
  model: "fast"
  system: "Write marketing copy."
  user: "Write a tagline for {{ input.product }}"
`
	writeFile(t, dir, "writer.yml", writerYAML)

	criticYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: critic
  model: "fast"
  system: "Critique marketing copy."
  user: "Rate this tagline: {{ input.tagline }}"
  output:
    score:
      type: int
    feedback:
      type: str
`
	writeFile(t, dir, "critic.yml", criticYAML)

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: writer-critic-loop
  context:
    product: "{{ input.product }}"
    score: 0
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
        tagline: "{{ output.content }}"
      transitions:
        - to: review
    review:
      agent: critic
      input:
        tagline: "{{ context.tagline }}"
      output_to_context:
        score: "{{ output.score }}"
      transitions:
        - condition: "context.score >= 8"
          to: done
        - to: write
    done:
      type: final
      output:
        tagline: "{{ context.tagline }}"
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)

	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if machine.Name() != "writer-critic-loop" {
		t.Errorf("expected name 'writer-critic-loop', got %q", machine.Name())
	}
	if len(machine.Agents) != 2 {
		t.Errorf("expected 2 agents, got %d", len(machine.Agents))
	}
	if _, ok := machine.Agents["writer"]; !ok {
		t.Error("expected writer agent")
	}
	if _, ok := machine.Agents["critic"]; !ok {
		t.Error("expected critic agent")
	}
}

func TestInitialAndFinalStates(t *testing.T) {
	machine := &Machine{
		Config: types.MachineWrapper{
			Data: types.MachineData{
				Name: "test",
				States: map[string]types.StateDefinition{
					"start":  {Type: "initial"},
					"middle": {},
					"done":   {Type: "final"},
					"error":  {Type: "final"},
				},
			},
		},
	}

	initial, err := machine.InitialState()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if initial != "start" {
		t.Errorf("expected initial state 'start', got %q", initial)
	}

	finals := machine.FinalStates()
	if len(finals) != 2 {
		t.Errorf("expected 2 final states, got %d", len(finals))
	}

	if !machine.IsFinal("done") {
		t.Error("expected 'done' to be final")
	}
	if machine.IsFinal("middle") {
		t.Error("expected 'middle' not to be final")
	}
}

func TestNoInitialState(t *testing.T) {
	machine := &Machine{
		Config: types.MachineWrapper{
			Data: types.MachineData{
				Name: "test",
				States: map[string]types.StateDefinition{
					"middle": {},
				},
			},
		},
	}

	_, err := machine.InitialState()
	if err == nil {
		t.Error("expected error for missing initial state")
	}
}

// ---------------------------------------------------------------------------
// Expression engine tests
// ---------------------------------------------------------------------------

func TestSimpleExpressionEngine(t *testing.T) {
	engine := &SimpleExpressionEngine{}

	vars := map[string]interface{}{
		"context": map[string]interface{}{
			"score":   int64(8),
			"round":   int64(3),
			"current": "hel",
			"target":  "hello",
			"failed":  false,
		},
	}

	tests := []struct {
		expr     string
		expected bool
	}{
		{"context.score >= 8", true},
		{"context.score >= 9", false},
		{"context.score == 8", true},
		{"context.score != 7", true},
		{"context.round < 4", true},
		{"context.round > 4", false},
		{"context.score >= 8 and context.round < 4", true},
		{"context.score >= 9 or context.round < 4", true},
		{"context.score >= 9 or context.round > 4", false},
		{"not context.failed", true},
		{"context.current == context.target", false},
		{"context.current != context.target", true},
	}

	for _, tt := range tests {
		result, err := engine.Evaluate(tt.expr, vars)
		if err != nil {
			t.Errorf("Evaluate(%q): unexpected error: %v", tt.expr, err)
			continue
		}
		got := toBool(result)
		if got != tt.expected {
			t.Errorf("Evaluate(%q) = %v, want %v", tt.expr, got, tt.expected)
		}
	}
}

func TestExpressionEmptyIsTrue(t *testing.T) {
	engine := &SimpleExpressionEngine{}
	result, err := engine.Evaluate("", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !toBool(result) {
		t.Error("empty expression should be true")
	}
}

func TestExpressionStringLiterals(t *testing.T) {
	engine := &SimpleExpressionEngine{}
	vars := map[string]interface{}{
		"context": map[string]interface{}{
			"status": "done",
		},
	}

	result, err := engine.Evaluate(`context.status == "done"`, vars)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !toBool(result) {
		t.Error("expected true for string equality")
	}
}

func TestExpressionNullComparison(t *testing.T) {
	engine := &SimpleExpressionEngine{}
	vars := map[string]interface{}{
		"context": map[string]interface{}{
			"val": nil,
		},
	}

	result, err := engine.Evaluate("context.val == null", vars)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !toBool(result) {
		t.Error("expected null == null to be true")
	}

	result2, err := engine.Evaluate("context.val != null", vars)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if toBool(result2) {
		t.Error("expected null != null to be false")
	}
}

func TestExpressionBooleanLiterals(t *testing.T) {
	engine := &SimpleExpressionEngine{}
	vars := map[string]interface{}{
		"context": map[string]interface{}{
			"approved": true,
		},
	}

	result, err := engine.Evaluate("context.approved == true", vars)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !toBool(result) {
		t.Error("expected true")
	}
}

func TestExpressionMissingField(t *testing.T) {
	engine := &SimpleExpressionEngine{}
	vars := map[string]interface{}{
		"context": map[string]interface{}{},
	}

	// Missing field should return nil, not error
	result, err := engine.Evaluate("context.nonexistent == null", vars)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !toBool(result) {
		t.Error("missing field should equal null")
	}
}

// ---------------------------------------------------------------------------
// Machine run tests (with mock provider)
// ---------------------------------------------------------------------------

// mockProvider is a simple LLM provider for testing.
type mockProvider struct {
	responses []types.AgentResult
	callCount int
}

func (m *mockProvider) Call(messages []types.Message, opts types.LLMCallOptions) (*types.AgentResult, error) {
	if m.callCount >= len(m.responses) {
		return nil, fmt.Errorf("mock provider: no more responses (call %d)", m.callCount)
	}
	result := m.responses[m.callCount]
	m.callCount++
	return &result, nil
}

func TestRunSimpleMachine(t *testing.T) {
	// A simple machine: start -> action_state -> done
	dir := t.TempDir()

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: simple-machine
  context:
    greeting: ""
  states:
    start:
      type: initial
      transitions:
        - to: greet
    greet:
      action: set_greeting
      transitions:
        - to: done
    done:
      type: final
      output:
        result: "{{ context.greeting }}"
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	// Custom hooks that handle the action
	hooks := &testHooks{
		onAction: func(action string, ctx map[string]interface{}) (map[string]interface{}, error) {
			if action == "set_greeting" {
				ctx["greeting"] = "Hello, World!"
			}
			return ctx, nil
		},
	}

	result, err := machine.Run(map[string]interface{}{}, RunOptions{
		Hooks: hooks,
	})
	if err != nil {
		t.Fatalf("running machine: %v", err)
	}

	if result.FinalState != "done" {
		t.Errorf("expected final state 'done', got %q", result.FinalState)
	}
	if result.Output["result"] != "Hello, World!" {
		t.Errorf("expected greeting 'Hello, World!', got %v", result.Output["result"])
	}
}

func TestRunMachineWithAgent(t *testing.T) {
	dir := t.TempDir()

	profilesYAML := `
spec: flatprofiles
spec_version: "2.2.2"
data:
  model_profiles:
    test:
      provider: test
      name: test-model
  default: test
`
	writeFile(t, dir, "profiles.yml", profilesYAML)

	agentYAML := `
spec: flatagent
spec_version: "2.2.2"
data:
  name: greeter
  model: "test"
  system: "You greet people."
  user: "Greet {{ input.name }}"
`
	writeFile(t, dir, "greeter.yml", agentYAML)

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: greet-machine
  context:
    name: "{{ input.name }}"
  agents:
    greeter: ./greeter.yml
  states:
    start:
      type: initial
      transitions:
        - to: greet
    greet:
      agent: greeter
      input:
        name: "{{ context.name }}"
      output_to_context:
        greeting: "{{ output.content }}"
      transitions:
        - to: done
    done:
      type: final
      output:
        greeting: "{{ context.greeting }}"
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	provider := &mockProvider{
		responses: []types.AgentResult{
			{Content: "Hello, Alice!", Output: map[string]interface{}{"content": "Hello, Alice!"}},
		},
	}

	result, err := machine.Run(
		map[string]interface{}{"name": "Alice"},
		RunOptions{Provider: provider},
	)
	if err != nil {
		t.Fatalf("running machine: %v", err)
	}

	if result.FinalState != "done" {
		t.Errorf("expected final state 'done', got %q", result.FinalState)
	}
	if result.Output["greeting"] != "Hello, Alice!" {
		t.Errorf("expected greeting 'Hello, Alice!', got %v", result.Output["greeting"])
	}
}

func TestRunMachineWithConditionalTransitions(t *testing.T) {
	dir := t.TempDir()

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: conditional-machine
  context:
    score: 0
    round: 0
  states:
    start:
      type: initial
      transitions:
        - to: check
    check:
      action: increment
      transitions:
        - condition: "context.round >= 3"
          to: done
        - to: check
    done:
      type: final
      output:
        rounds: "{{ context.round }}"
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	hooks := &testHooks{
		onAction: func(action string, ctx map[string]interface{}) (map[string]interface{}, error) {
			if action == "increment" {
				round, _ := toFloat64(ctx["round"])
				ctx["round"] = int64(round) + 1
			}
			return ctx, nil
		},
	}

	result, err := machine.Run(map[string]interface{}{}, RunOptions{Hooks: hooks})
	if err != nil {
		t.Fatalf("running machine: %v", err)
	}

	if result.FinalState != "done" {
		t.Errorf("expected final state 'done', got %q", result.FinalState)
	}
	if result.Steps != 4 { // start->check, check(1)->check, check(2)->check, check(3)->done
		t.Errorf("expected 4 steps, got %d", result.Steps)
	}
}

func TestRunMachineMaxSteps(t *testing.T) {
	dir := t.TempDir()

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: infinite-loop
  context: {}
  states:
    start:
      type: initial
      transitions:
        - to: loop
    loop:
      action: noop
      transitions:
        - to: loop
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	_, err = machine.Run(map[string]interface{}{}, RunOptions{MaxSteps: 5})
	if err == nil {
		t.Error("expected error for exceeding max steps")
	}
}

func TestRunMachineOnError(t *testing.T) {
	dir := t.TempDir()

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: error-machine
  context: {}
  states:
    start:
      type: initial
      transitions:
        - to: risky
    risky:
      action: fail_action
      on_error: error_state
      transitions:
        - to: done
    error_state:
      type: final
      output:
        error: "{{ context.last_error }}"
    done:
      type: final
      output:
        success: true
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	hooks := &testHooks{
		onAction: func(action string, ctx map[string]interface{}) (map[string]interface{}, error) {
			if action == "fail_action" {
				return nil, fmt.Errorf("something went wrong")
			}
			return ctx, nil
		},
	}

	result, err := machine.Run(map[string]interface{}{}, RunOptions{Hooks: hooks})
	if err != nil {
		t.Fatalf("running machine: %v", err)
	}

	if result.FinalState != "error_state" {
		t.Errorf("expected final state 'error_state', got %q", result.FinalState)
	}
}

func TestRunMachineContextTemplates(t *testing.T) {
	dir := t.TempDir()

	machineYAML := `
spec: flatmachine
spec_version: "2.2.2"
data:
  name: context-test
  context:
    name: "{{ input.user_name }}"
    greeting: ""
  states:
    start:
      type: initial
      transitions:
        - to: done
    done:
      type: final
      output:
        name: "{{ context.name }}"
`
	machinePath := writeFile(t, dir, "machine.yml", machineYAML)
	machine, err := Load(machinePath, nil)
	if err != nil {
		t.Fatalf("loading machine: %v", err)
	}

	result, err := machine.Run(map[string]interface{}{
		"user_name": "Charlie",
	}, RunOptions{})
	if err != nil {
		t.Fatalf("running machine: %v", err)
	}

	if result.Output["name"] != "Charlie" {
		t.Errorf("expected name 'Charlie', got %v", result.Output["name"])
	}
}

func TestInvalidMachineSpec(t *testing.T) {
	config := types.MachineWrapper{
		Spec: "wrong",
		Data: types.MachineData{},
	}
	_, err := LoadFromDict(config, nil)
	if err == nil {
		t.Error("expected error for invalid spec")
	}
}

// testHooks is a test helper that lets tests override individual hook methods.
type testHooks struct {
	types.NoOpHooks
	onAction func(string, map[string]interface{}) (map[string]interface{}, error)
}

func (h *testHooks) OnAction(action string, ctx map[string]interface{}) (map[string]interface{}, error) {
	if h.onAction != nil {
		return h.onAction(action, ctx)
	}
	return ctx, nil
}
