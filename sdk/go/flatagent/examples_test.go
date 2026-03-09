package flatagent

import (
	"os"
	"path/filepath"
	"testing"
)

// TestParseExampleAgentConfigs parses real agent YAML files from sdk/examples/
// to verify the Go SDK correctly handles production config patterns.

func findExamplesDir() string {
	// Walk up from test directory to find sdk/examples
	candidates := []string{
		"../../examples",              // sdk/go -> sdk/examples
		"../../../sdk/examples",       // if running from a different cwd
	}
	for _, c := range candidates {
		abs, err := filepath.Abs(c)
		if err != nil {
			continue
		}
		if info, err := os.Stat(abs); err == nil && info.IsDir() {
			return abs
		}
	}
	return ""
}

func TestParseHelloWorldAgent(t *testing.T) {
	exDir := findExamplesDir()
	if exDir == "" {
		t.Skip("sdk/examples directory not found")
	}

	agentPath := filepath.Join(exDir, "helloworld", "config", "agent.yml")
	if _, err := os.Stat(agentPath); os.IsNotExist(err) {
		t.Skipf("helloworld agent not found at %s", agentPath)
	}

	agent, err := Load(agentPath, nil)
	if err != nil {
		t.Fatalf("loading helloworld agent: %v", err)
	}

	if agent.Name() != "hello-world-agent" {
		t.Errorf("expected name 'hello-world-agent', got %q", agent.Name())
	}

	// This agent uses profile "extra-params-demo" with max_tokens override
	if !agent.Config.Data.Model.IsProfiled() {
		t.Error("expected profiled model config")
	}
	if agent.Config.Data.Model.Profiled.Profile != "extra-params-demo" {
		t.Errorf("expected profile 'extra-params-demo', got %q", agent.Config.Data.Model.Profiled.Profile)
	}

	// Test prompt rendering
	input := map[string]interface{}{
		"target":  "hello",
		"current": "hel",
	}
	usr, err := agent.RenderUserPrompt(input)
	if err != nil {
		t.Fatalf("rendering user prompt: %v", err)
	}
	if usr == "" {
		t.Error("expected non-empty user prompt")
	}
}

func TestParseWriterCriticAgents(t *testing.T) {
	exDir := findExamplesDir()
	if exDir == "" {
		t.Skip("sdk/examples directory not found")
	}

	configDir := filepath.Join(exDir, "writer_critic", "config")

	tests := []struct {
		file     string
		name     string
		hasModel bool
	}{
		{"writer.yml", "writer", true},
		{"critic.yml", "critic", true},
	}

	for _, tt := range tests {
		t.Run(tt.file, func(t *testing.T) {
			path := filepath.Join(configDir, tt.file)
			if _, err := os.Stat(path); os.IsNotExist(err) {
				t.Skipf("file not found: %s", path)
			}

			agent, err := Load(path, nil)
			if err != nil {
				t.Fatalf("loading %s: %v", tt.file, err)
			}

			if agent.Name() != tt.name {
				t.Errorf("expected name %q, got %q", tt.name, agent.Name())
			}

			// These agents use string model references (profile names)
			if !agent.Config.Data.Model.IsString() {
				t.Error("expected string model (profile name)")
			}
		})
	}
}

func TestParseHelloWorldProfiles(t *testing.T) {
	exDir := findExamplesDir()
	if exDir == "" {
		t.Skip("sdk/examples directory not found")
	}

	profilesPath := filepath.Join(exDir, "helloworld", "config", "profiles.yml")
	if _, err := os.Stat(profilesPath); os.IsNotExist(err) {
		t.Skipf("profiles not found at %s", profilesPath)
	}

	// Load agent with profiles
	agentPath := filepath.Join(exDir, "helloworld", "config", "agent.yml")
	agent, err := Load(agentPath, nil)
	if err != nil {
		t.Fatalf("loading agent: %v", err)
	}

	// The resolved model should have provider from the profile
	if agent.ResolvedModel.Provider == "" {
		t.Error("expected resolved provider from profile")
	}
	if agent.ResolvedModel.Name == "" {
		t.Error("expected resolved model name from profile")
	}
}
