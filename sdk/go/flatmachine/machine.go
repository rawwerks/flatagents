// Package flatmachine implements FlatMachine config parsing and state machine execution.
//
// A FlatMachine orchestrates multiple agents through a state machine:
// states, transitions, conditions, and loops. It manages context flow,
// template rendering, and expression evaluation between states.
package flatmachine

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/memgrafter/flatagents/sdk/go/flatagent"
	"github.com/memgrafter/flatagents/sdk/go/profiles"
	tmpl "github.com/memgrafter/flatagents/sdk/go/template"
	"github.com/memgrafter/flatagents/sdk/go/types"
	"gopkg.in/yaml.v3"
)

// Machine holds a parsed flatmachine configuration and provides
// methods for executing the state machine.
type Machine struct {
	// Config is the raw parsed config wrapper.
	Config types.MachineWrapper

	// Agents maps agent names to loaded Agent instances.
	Agents map[string]*flatagent.Agent

	// ProfileManager handles profile resolution.
	ProfileManager *profiles.Manager

	// configDir is the directory containing the machine config file.
	configDir string
}

// LoadOptions configures how a machine is loaded.
type LoadOptions struct {
	// ProfilesFile is an explicit path to profiles.yml.
	ProfilesFile string

	// ProfilesData provides pre-loaded profiles data.
	ProfilesData *profiles.ProfilesData
}

// Load loads a FlatMachine from a YAML config file.
func Load(configFile string, opts *LoadOptions) (*Machine, error) {
	data, err := os.ReadFile(configFile)
	if err != nil {
		return nil, fmt.Errorf("reading machine config: %w", err)
	}

	var wrapper types.MachineWrapper
	if err := yaml.Unmarshal(data, &wrapper); err != nil {
		return nil, fmt.Errorf("parsing machine YAML: %w", err)
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

// LoadFromDict loads a FlatMachine from an in-memory config.
func LoadFromDict(config types.MachineWrapper, opts *LoadOptions) (*Machine, error) {
	cwd, _ := os.Getwd()
	return fromWrapper(config, cwd, opts)
}

func fromWrapper(wrapper types.MachineWrapper, configDir string, opts *LoadOptions) (*Machine, error) {
	if wrapper.Spec != "flatmachine" {
		return nil, fmt.Errorf("invalid spec: expected 'flatmachine', got '%s'", wrapper.Spec)
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
				mgr = profiles.NewManager(nil)
			}
		} else {
			mgr = profiles.NewManager(nil)
		}
	}

	// Load referenced agents
	agents := make(map[string]*flatagent.Agent)
	for name, ref := range wrapper.Data.Agents {
		agent, err := loadAgentRef(ref, configDir, mgr)
		if err != nil {
			return nil, fmt.Errorf("loading agent '%s': %w", name, err)
		}
		if agent != nil {
			agents[name] = agent
		}
	}

	return &Machine{
		Config:         wrapper,
		Agents:         agents,
		ProfileManager: mgr,
		configDir:      configDir,
	}, nil
}

// loadAgentRef loads an agent from a polymorphic AgentRef.
func loadAgentRef(ref types.AgentRef, configDir string, mgr *profiles.Manager) (*flatagent.Agent, error) {
	if ref.Path != "" {
		agentPath := ref.Path
		if !filepath.IsAbs(agentPath) {
			agentPath = filepath.Join(configDir, agentPath)
		}
		return flatagent.Load(agentPath, &flatagent.LoadOptions{
			ProfilesData: &profiles.ProfilesData{
				ModelProfiles: mgr.Profiles(),
				Default:       mgr.DefaultProfile(),
				Override:      mgr.OverrideProfile(),
			},
		})
	}
	if ref.Inline != nil {
		return flatagent.LoadFromDict(*ref.Inline, &flatagent.LoadOptions{
			ProfilesData: &profiles.ProfilesData{
				ModelProfiles: mgr.Profiles(),
				Default:       mgr.DefaultProfile(),
				Override:      mgr.OverrideProfile(),
			},
		})
	}
	// Typed adapter refs are not loaded as agents here; they need external resolution.
	return nil, nil
}

// Name returns the machine's name.
func (m *Machine) Name() string {
	return m.Config.Data.Name
}

// InitialState returns the name of the initial state.
func (m *Machine) InitialState() (string, error) {
	for name, state := range m.Config.Data.States {
		if state.Type == "initial" {
			return name, nil
		}
	}
	return "", fmt.Errorf("no initial state found in machine '%s'", m.Name())
}

// FinalStates returns the names of all final states.
func (m *Machine) FinalStates() []string {
	var finals []string
	for name, state := range m.Config.Data.States {
		if state.Type == "final" {
			finals = append(finals, name)
		}
	}
	return finals
}

// IsFinal returns true if the given state is a final state.
func (m *Machine) IsFinal(stateName string) bool {
	state, ok := m.Config.Data.States[stateName]
	if !ok {
		return false
	}
	return state.Type == "final"
}

// ---------------------------------------------------------------------------
// Expression evaluation (simple mode)
// ---------------------------------------------------------------------------

// ExpressionEngine evaluates condition expressions.
type ExpressionEngine interface {
	Evaluate(expr string, vars map[string]interface{}) (interface{}, error)
}

// SimpleExpressionEngine implements the "simple" expression mode using
// basic string-based evaluation for common comparison patterns.
type SimpleExpressionEngine struct{}

// Evaluate evaluates a simple expression string.
// Supports: ==, !=, >=, <=, >, <, and, or, not, field access.
func (e *SimpleExpressionEngine) Evaluate(expr string, vars map[string]interface{}) (interface{}, error) {
	expr = strings.TrimSpace(expr)
	if expr == "" {
		return true, nil
	}

	// Handle "and" / "or" operators (lowest precedence)
	if parts, ok := splitBoolOp(expr, " and "); ok {
		for _, part := range parts {
			val, err := e.Evaluate(part, vars)
			if err != nil {
				return nil, err
			}
			if !toBool(val) {
				return false, nil
			}
		}
		return true, nil
	}
	if parts, ok := splitBoolOp(expr, " or "); ok {
		for _, part := range parts {
			val, err := e.Evaluate(part, vars)
			if err != nil {
				return nil, err
			}
			if toBool(val) {
				return true, nil
			}
		}
		return false, nil
	}

	// Handle "not" prefix
	if strings.HasPrefix(expr, "not ") {
		val, err := e.Evaluate(strings.TrimPrefix(expr, "not "), vars)
		if err != nil {
			return nil, err
		}
		return !toBool(val), nil
	}

	// Handle comparison operators
	for _, op := range []string{">=", "<=", "!=", "==", ">", "<"} {
		if idx := strings.Index(expr, " "+op+" "); idx > 0 {
			leftExpr := strings.TrimSpace(expr[:idx])
			rightExpr := strings.TrimSpace(expr[idx+len(op)+2:])

			left, err := e.resolveValue(leftExpr, vars)
			if err != nil {
				return nil, err
			}
			right, err := e.resolveValue(rightExpr, vars)
			if err != nil {
				return nil, err
			}

			return compare(left, right, op)
		}
	}

	// No operator -- resolve as a value and return its truthiness
	val, err := e.resolveValue(expr, vars)
	if err != nil {
		return nil, err
	}
	return val, nil
}

// resolveValue resolves a value expression (literal or variable access).
func (e *SimpleExpressionEngine) resolveValue(expr string, vars map[string]interface{}) (interface{}, error) {
	expr = strings.TrimSpace(expr)

	// Boolean literals
	if expr == "true" || expr == "True" {
		return true, nil
	}
	if expr == "false" || expr == "False" {
		return false, nil
	}
	if expr == "null" || expr == "None" || expr == "nil" || expr == "none" {
		return nil, nil
	}

	// Quoted string literal
	if (strings.HasPrefix(expr, "\"") && strings.HasSuffix(expr, "\"")) ||
		(strings.HasPrefix(expr, "'") && strings.HasSuffix(expr, "'")) {
		return expr[1 : len(expr)-1], nil
	}

	// Numeric literal
	if n, err := strconv.ParseFloat(expr, 64); err == nil {
		// Return int if it's a whole number
		if n == float64(int64(n)) {
			return int64(n), nil
		}
		return n, nil
	}

	// Dotted variable access: context.score, output.field, etc.
	if strings.Contains(expr, ".") {
		return resolveDotted(expr, vars)
	}

	// Simple variable
	if val, ok := vars[expr]; ok {
		return val, nil
	}

	return nil, fmt.Errorf("unknown variable: %s", expr)
}

// resolveDotted resolves a dotted path like "context.score" against variables.
func resolveDotted(path string, vars map[string]interface{}) (interface{}, error) {
	parts := strings.Split(path, ".")
	if len(parts) == 0 {
		return nil, fmt.Errorf("empty path")
	}

	val, ok := vars[parts[0]]
	if !ok {
		return nil, nil // Unknown root returns nil
	}

	for _, part := range parts[1:] {
		if val == nil {
			return nil, nil
		}
		switch v := val.(type) {
		case map[string]interface{}:
			val, ok = v[part]
			if !ok {
				return nil, nil
			}
		case map[interface{}]interface{}:
			val, ok = v[part]
			if !ok {
				return nil, nil
			}
		default:
			return nil, nil
		}
	}
	return val, nil
}

// compare performs a comparison between two values.
func compare(left, right interface{}, op string) (bool, error) {
	// Handle nil comparisons
	if left == nil || right == nil {
		switch op {
		case "==":
			return left == right, nil
		case "!=":
			return left != right, nil
		default:
			return false, nil
		}
	}

	// Try numeric comparison
	lNum, lOk := toFloat64(left)
	rNum, rOk := toFloat64(right)
	if lOk && rOk {
		switch op {
		case "==":
			return lNum == rNum, nil
		case "!=":
			return lNum != rNum, nil
		case ">=":
			return lNum >= rNum, nil
		case "<=":
			return lNum <= rNum, nil
		case ">":
			return lNum > rNum, nil
		case "<":
			return lNum < rNum, nil
		}
	}

	// String comparison
	lStr := fmt.Sprintf("%v", left)
	rStr := fmt.Sprintf("%v", right)
	switch op {
	case "==":
		return lStr == rStr, nil
	case "!=":
		return lStr != rStr, nil
	case ">=":
		return lStr >= rStr, nil
	case "<=":
		return lStr <= rStr, nil
	case ">":
		return lStr > rStr, nil
	case "<":
		return lStr < rStr, nil
	}

	return false, fmt.Errorf("unsupported operator: %s", op)
}

// toFloat64 attempts to convert a value to float64.
func toFloat64(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case string:
		f, err := strconv.ParseFloat(n, 64)
		return f, err == nil
	}
	return 0, false
}

// toBool converts a value to boolean.
func toBool(v interface{}) bool {
	if v == nil {
		return false
	}
	switch b := v.(type) {
	case bool:
		return b
	case int:
		return b != 0
	case int64:
		return b != 0
	case float64:
		return b != 0
	case string:
		return b != "" && b != "false" && b != "0"
	}
	return true
}

// splitBoolOp splits an expression on a boolean operator, respecting nesting.
func splitBoolOp(expr, op string) ([]string, bool) {
	idx := strings.Index(expr, op)
	if idx < 0 {
		return nil, false
	}

	// Simple split for now (doesn't handle parentheses)
	var parts []string
	remaining := expr
	for {
		idx = strings.Index(remaining, op)
		if idx < 0 {
			parts = append(parts, remaining)
			break
		}
		parts = append(parts, remaining[:idx])
		remaining = remaining[idx+len(op):]
	}
	return parts, len(parts) > 1
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

// RunOptions configures machine execution.
type RunOptions struct {
	// Hooks provides extension points for machine execution.
	Hooks types.MachineHooks

	// Provider is the LLM provider used for agent calls.
	Provider types.LLMProvider

	// MaxSteps limits the number of state transitions (safety valve).
	// Defaults to 100 if not set in config or here.
	MaxSteps int
}

// RunResult holds the output of a machine execution.
type RunResult struct {
	// Output is the final output from the terminal state.
	Output map[string]interface{}

	// Context is the final context after execution.
	Context map[string]interface{}

	// FinalState is the name of the state where execution ended.
	FinalState string

	// Steps is the number of state transitions performed.
	Steps int
}

// Run executes the state machine with the given input.
func (m *Machine) Run(input map[string]interface{}, opts RunOptions) (*RunResult, error) {
	if opts.Hooks == nil {
		opts.Hooks = types.NoOpHooks{}
	}

	maxSteps := opts.MaxSteps
	if maxSteps <= 0 {
		if m.Config.Data.Settings != nil && m.Config.Data.Settings.MaxSteps != nil {
			maxSteps = *m.Config.Data.Settings.MaxSteps
		} else {
			maxSteps = 100
		}
	}

	// Initialize context from config templates
	ctx := make(map[string]interface{})
	if m.Config.Data.Context != nil {
		data := map[string]interface{}{
			"input": input,
		}
		for k, v := range m.Config.Data.Context {
			switch val := v.(type) {
			case string:
				rendered, err := tmpl.Render(val, data)
				if err != nil {
					return nil, fmt.Errorf("rendering context key '%s': %w", k, err)
				}
				ctx[k] = rendered
			default:
				ctx[k] = v
				_ = val
			}
		}
	}

	// Hook: on_machine_start
	var err error
	ctx, err = opts.Hooks.OnMachineStart(ctx)
	if err != nil {
		return nil, fmt.Errorf("on_machine_start hook: %w", err)
	}

	// Find initial state
	currentState, err := m.InitialState()
	if err != nil {
		return nil, err
	}

	engine := &SimpleExpressionEngine{}
	step := 0

	for step < maxSteps {
		stateDef, ok := m.Config.Data.States[currentState]
		if !ok {
			return nil, fmt.Errorf("state '%s' not found", currentState)
		}

		// Hook: on_state_enter
		ctx, err = opts.Hooks.OnStateEnter(currentState, ctx)
		if err != nil {
			return nil, fmt.Errorf("on_state_enter hook for '%s': %w", currentState, err)
		}

		// Check if this is a final state
		if stateDef.Type == "final" {
			// Render output
			var output map[string]interface{}
			if stateDef.Output != nil {
				data := map[string]interface{}{
					"context": ctx,
					"input":   input,
				}
				output, err = tmpl.RenderMap(stateDef.Output, data)
				if err != nil {
					return nil, fmt.Errorf("rendering final output for '%s': %w", currentState, err)
				}
			}

			// Hook: on_machine_end
			outputI, err := opts.Hooks.OnMachineEnd(ctx, output)
			if err != nil {
				return nil, fmt.Errorf("on_machine_end hook: %w", err)
			}
			if o, ok := outputI.(map[string]interface{}); ok {
				output = o
			}

			return &RunResult{
				Output:     output,
				Context:    ctx,
				FinalState: currentState,
				Steps:      step,
			}, nil
		}

		// Execute state action
		var stateOutput map[string]interface{}

		if stateDef.Action != "" {
			// Hook: on_action
			ctx, err = opts.Hooks.OnAction(stateDef.Action, ctx)
			if err != nil {
				errState := handleError(stateDef, err)
				if errState != "" {
					currentState = errState
					step++
					continue
				}
				return nil, fmt.Errorf("action '%s' in state '%s': %w", stateDef.Action, currentState, err)
			}
		} else if stateDef.Agent != "" {
			// Execute agent
			agent, ok := m.Agents[stateDef.Agent]
			if !ok {
				return nil, fmt.Errorf("agent '%s' not found for state '%s'", stateDef.Agent, currentState)
			}
			if opts.Provider == nil {
				return nil, fmt.Errorf("LLM provider required for agent state '%s' but not provided", currentState)
			}

			// Render input
			agentInput := make(map[string]interface{})
			if stateDef.Input != nil {
				data := map[string]interface{}{
					"context": ctx,
					"input":   input,
				}
				agentInput, err = tmpl.RenderMap(stateDef.Input, data)
				if err != nil {
					return nil, fmt.Errorf("rendering input for agent '%s' in state '%s': %w", stateDef.Agent, currentState, err)
				}
			}

			result, err := agent.Call(opts.Provider, agentInput)
			if err != nil {
				errState := handleError(stateDef, err)
				if errState != "" {
					ctx["last_error"] = err.Error()
					ctx["last_error_type"] = fmt.Sprintf("%T", err)
					currentState = errState
					step++
					continue
				}
				return nil, fmt.Errorf("executing agent '%s' in state '%s': %w", stateDef.Agent, currentState, err)
			}
			if result.Error != nil {
				errState := handleError(stateDef, result.Error)
				if errState != "" {
					ctx["last_error"] = result.Error.Message
					ctx["last_error_type"] = result.Error.Type
					currentState = errState
					step++
					continue
				}
				return nil, fmt.Errorf("agent '%s' returned error in state '%s': %s", stateDef.Agent, currentState, result.Error.Message)
			}

			stateOutput = result.Output
			if stateOutput == nil && result.Content != "" {
				stateOutput = map[string]interface{}{"content": result.Content}
			}
		}

		// Map output to context
		if stateDef.OutputToContext != nil && stateOutput != nil {
			data := map[string]interface{}{
				"context": ctx,
				"output":  stateOutput,
				"input":   input,
			}
			rendered, err := tmpl.RenderMap(stateDef.OutputToContext, data)
			if err != nil {
				return nil, fmt.Errorf("rendering output_to_context for '%s': %w", currentState, err)
			}
			for k, v := range rendered {
				ctx[k] = v
			}
		}

		// Hook: on_state_exit
		_, err = opts.Hooks.OnStateExit(currentState, ctx, stateOutput)
		if err != nil {
			return nil, fmt.Errorf("on_state_exit hook for '%s': %w", currentState, err)
		}

		// Evaluate transitions
		nextState := ""
		if stateDef.Transitions != nil {
			vars := map[string]interface{}{
				"context": ctx,
				"input":   input,
				"output":  stateOutput,
			}
			for _, t := range stateDef.Transitions {
				if t.Condition == "" {
					// Default transition (no condition)
					nextState = t.To
					break
				}
				result, err := engine.Evaluate(t.Condition, vars)
				if err != nil {
					return nil, fmt.Errorf("evaluating condition '%s' in state '%s': %w", t.Condition, currentState, err)
				}
				if toBool(result) {
					nextState = t.To
					break
				}
			}
		}

		if nextState == "" {
			return nil, fmt.Errorf("no valid transition from state '%s'", currentState)
		}

		// Hook: on_transition
		nextState, err = opts.Hooks.OnTransition(currentState, nextState, ctx)
		if err != nil {
			return nil, fmt.Errorf("on_transition hook from '%s' to '%s': %w", currentState, nextState, err)
		}

		currentState = nextState
		step++
	}

	return nil, fmt.Errorf("machine exceeded max_steps (%d)", maxSteps)
}

// handleError checks the on_error configuration and returns the error state name,
// or empty string if the error should propagate.
func handleError(stateDef types.StateDefinition, err error) string {
	if stateDef.OnError == nil {
		return ""
	}

	switch v := stateDef.OnError.(type) {
	case string:
		return v
	case map[string]interface{}:
		// Check for specific error type mapping
		errType := fmt.Sprintf("%T", err)
		if state, ok := v[errType]; ok {
			if s, ok := state.(string); ok {
				return s
			}
		}
		// Fall back to default
		if state, ok := v["default"]; ok {
			if s, ok := state.(string); ok {
				return s
			}
		}
	}
	return ""
}

// ConfigDir returns the directory containing the machine config file.
func (m *Machine) ConfigDir() string {
	return m.configDir
}
