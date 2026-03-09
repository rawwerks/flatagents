package profiles

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/memgrafter/flatagents/sdk/go/types"
)

func tempProfilesFile(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "profiles.yml")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("writing temp file: %v", err)
	}
	return path
}

func float64Ptr(f float64) *float64 { return &f }
func intPtr(i int) *int             { return &i }

func TestLoadFromFile(t *testing.T) {
	content := `
spec: flatprofiles
spec_version: "2.2.2"
data:
  model_profiles:
    fast-cheap:
      provider: cerebras
      name: zai-glm-4.6
      temperature: 0.6
      max_tokens: 2048
    smart-expensive:
      provider: anthropic
      name: claude-3-opus-20240229
      temperature: 0.3
      max_tokens: 4096
  default: fast-cheap
  # override: smart-expensive
`
	path := tempProfilesFile(t, content)
	mgr, err := LoadFromFile(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(mgr.Profiles()) != 2 {
		t.Errorf("expected 2 profiles, got %d", len(mgr.Profiles()))
	}
	if mgr.DefaultProfile() != "fast-cheap" {
		t.Errorf("expected default 'fast-cheap', got %q", mgr.DefaultProfile())
	}
	if mgr.OverrideProfile() != "" {
		t.Errorf("expected no override, got %q", mgr.OverrideProfile())
	}

	fast := mgr.GetProfile("fast-cheap")
	if fast == nil {
		t.Fatal("expected fast-cheap profile")
	}
	if fast.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", fast.Provider)
	}
	if fast.Name != "zai-glm-4.6" {
		t.Errorf("expected name 'zai-glm-4.6', got %q", fast.Name)
	}
}

func TestResolveStringProfile(t *testing.T) {
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{
			"fast": {
				Provider:    "cerebras",
				Name:        "zai-glm-4.6",
				Temperature: float64Ptr(0.6),
				MaxTokens:   intPtr(2048),
			},
		},
		Default: "fast",
	})

	// String model field = profile name lookup
	field := types.ModelField{ProfileName: "fast"}
	resolved, err := mgr.Resolve(field)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resolved.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", resolved.Provider)
	}
	if resolved.Name != "zai-glm-4.6" {
		t.Errorf("expected name 'zai-glm-4.6', got %q", resolved.Name)
	}
	if *resolved.Temperature != 0.6 {
		t.Errorf("expected temperature 0.6, got %f", *resolved.Temperature)
	}
}

func TestResolveProfiledWithOverrides(t *testing.T) {
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{
			"fast": {
				Provider:    "cerebras",
				Name:        "zai-glm-4.6",
				Temperature: float64Ptr(0.6),
				MaxTokens:   intPtr(2048),
			},
		},
	})

	// ProfiledModelConfig = profile + overrides
	field := types.ModelField{
		Profiled: &types.ProfiledModelConfig{
			Profile:     "fast",
			Temperature: float64Ptr(0.9),
			MaxTokens:   intPtr(200),
		},
	}
	resolved, err := mgr.Resolve(field)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resolved.Provider != "cerebras" {
		t.Errorf("expected provider 'cerebras', got %q", resolved.Provider)
	}
	// Temperature should be overridden
	if *resolved.Temperature != 0.9 {
		t.Errorf("expected temperature 0.9, got %f", *resolved.Temperature)
	}
	// MaxTokens should be overridden
	if *resolved.MaxTokens != 200 {
		t.Errorf("expected max_tokens 200, got %d", *resolved.MaxTokens)
	}
}

func TestResolveInlineConfig(t *testing.T) {
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{
			"fast": {
				Provider:    "cerebras",
				Name:        "zai-glm-4.6",
				Temperature: float64Ptr(0.6),
			},
		},
		Default: "fast",
	})

	// Inline config (no profile)
	field := types.ModelField{
		Config: &types.ModelConfig{
			Provider:    "openai",
			Name:        "gpt-4",
			Temperature: float64Ptr(0.3),
		},
	}
	resolved, err := mgr.Resolve(field)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Inline should override default
	if resolved.Provider != "openai" {
		t.Errorf("expected provider 'openai', got %q", resolved.Provider)
	}
	if resolved.Name != "gpt-4" {
		t.Errorf("expected name 'gpt-4', got %q", resolved.Name)
	}
	if *resolved.Temperature != 0.3 {
		t.Errorf("expected temperature 0.3, got %f", *resolved.Temperature)
	}
}

func TestResolveCascadeOrder(t *testing.T) {
	// Test the full cascade: default -> profile -> inline overrides -> override
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{
			"default-profile": {
				Provider:    "default-provider",
				Name:        "default-model",
				Temperature: float64Ptr(0.5),
				MaxTokens:   intPtr(1000),
			},
			"named-profile": {
				Provider:    "named-provider",
				Name:        "named-model",
				Temperature: float64Ptr(0.7),
			},
			"override-profile": {
				Provider: "override-provider",
				Name:     "override-model",
			},
		},
		Default:  "default-profile",
		Override: "override-profile",
	})

	field := types.ModelField{
		Profiled: &types.ProfiledModelConfig{
			Profile:     "named-profile",
			Temperature: float64Ptr(0.9), // inline override
		},
	}
	resolved, err := mgr.Resolve(field)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Override profile trumps all for provider and name
	if resolved.Provider != "override-provider" {
		t.Errorf("expected override provider, got %q", resolved.Provider)
	}
	if resolved.Name != "override-model" {
		t.Errorf("expected override model, got %q", resolved.Name)
	}
	// MaxTokens comes from default (not set in named or override)
	if resolved.MaxTokens == nil || *resolved.MaxTokens != 1000 {
		t.Error("expected MaxTokens 1000 from default")
	}
}

func TestResolveUnknownProfileErrors(t *testing.T) {
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{},
	})

	field := types.ModelField{ProfileName: "nonexistent"}
	_, err := mgr.Resolve(field)
	if err == nil {
		t.Error("expected error for unknown profile")
	}
}

func TestResolveDefaultFallback(t *testing.T) {
	// When named profile not found but default exists, should use default
	mgr := NewManager(&ProfilesData{
		ModelProfiles: map[string]types.ModelConfig{
			"default-one": {
				Provider: "fallback-provider",
				Name:     "fallback-model",
			},
		},
		Default: "default-one",
	})

	field := types.ModelField{ProfileName: "nonexistent"}
	resolved, err := mgr.Resolve(field)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resolved.Provider != "fallback-provider" {
		t.Errorf("expected fallback provider, got %q", resolved.Provider)
	}
}

func TestModelName(t *testing.T) {
	cfg := types.ModelConfig{Provider: "openai", Name: "gpt-4"}
	if ModelName(cfg) != "openai/gpt-4" {
		t.Errorf("expected 'openai/gpt-4', got %q", ModelName(cfg))
	}

	cfg2 := types.ModelConfig{Name: "gpt-4"}
	if ModelName(cfg2) != "gpt-4" {
		t.Errorf("expected 'gpt-4', got %q", ModelName(cfg2))
	}
}

func TestDiscoverFile(t *testing.T) {
	dir := t.TempDir()

	// No file exists
	result := DiscoverFile(dir, "")
	if result != "" {
		t.Errorf("expected empty string, got %q", result)
	}

	// Explicit path takes precedence
	result = DiscoverFile(dir, "/explicit/path.yml")
	if result != "/explicit/path.yml" {
		t.Errorf("expected explicit path, got %q", result)
	}

	// Create profiles.yml
	path := filepath.Join(dir, "profiles.yml")
	if err := os.WriteFile(path, []byte("spec: flatprofiles"), 0644); err != nil {
		t.Fatal(err)
	}
	result = DiscoverFile(dir, "")
	if result != path {
		t.Errorf("expected %q, got %q", path, result)
	}
}

func TestInvalidSpec(t *testing.T) {
	content := `
spec: wrong-spec
data:
  model_profiles: {}
`
	path := tempProfilesFile(t, content)
	_, err := LoadFromFile(path)
	if err == nil {
		t.Error("expected error for invalid spec")
	}
}
