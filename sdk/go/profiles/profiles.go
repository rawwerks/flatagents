// Package profiles implements model profile loading and resolution for flatagents.
//
// Model profiles provide reusable model configurations that agents can reference
// by name. This enables centralized model management and easy switching between
// configurations (e.g., development vs production, fast vs quality).
//
// Resolution order (low to high priority):
//  1. default profile from profiles.yml (fallback when agent has no model config)
//  2. Named profile from agent's model: "profile-name"
//  3. Inline overrides from agent's model: { profile: "name", temperature: 0.5 }
//  4. override profile from profiles.yml (trumps all agent configs)
package profiles

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/memgrafter/flatagents/sdk/go/types"
	"gopkg.in/yaml.v3"
)

// ProfilesWrapper is the top-level container for a profiles.yml file.
type ProfilesWrapper struct {
	Spec        string                 `yaml:"spec"`
	SpecVersion string                 `yaml:"spec_version"`
	Data        ProfilesData           `yaml:"data"`
	Metadata    map[string]interface{} `yaml:"metadata,omitempty"`
}

// ProfilesData holds profile definitions and settings.
type ProfilesData struct {
	ModelProfiles map[string]types.ModelConfig `yaml:"model_profiles"`
	Default       string                       `yaml:"default,omitempty"`
	Override      string                       `yaml:"override,omitempty"`
}

// Manager manages model profiles and resolves model configurations.
type Manager struct {
	profiles        map[string]types.ModelConfig
	defaultProfile  string
	overrideProfile string
}

// NewManager creates a new profile manager from a ProfilesData struct.
func NewManager(data *ProfilesData) *Manager {
	m := &Manager{
		profiles: make(map[string]types.ModelConfig),
	}
	if data != nil {
		m.profiles = data.ModelProfiles
		if m.profiles == nil {
			m.profiles = make(map[string]types.ModelConfig)
		}
		m.defaultProfile = data.Default
		m.overrideProfile = data.Override
	}
	return m
}

// LoadFromFile loads profiles from a YAML file and returns a Manager.
func LoadFromFile(path string) (*Manager, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading profiles file: %w", err)
	}

	var wrapper ProfilesWrapper
	if err := yaml.Unmarshal(data, &wrapper); err != nil {
		return nil, fmt.Errorf("parsing profiles YAML: %w", err)
	}

	if wrapper.Spec != "" && wrapper.Spec != "flatprofiles" {
		return nil, fmt.Errorf("invalid profiles spec: expected 'flatprofiles', got '%s'", wrapper.Spec)
	}

	return NewManager(&wrapper.Data), nil
}

// DiscoverFile looks for profiles.yml in the given directory.
// If explicitPath is non-empty, it is returned as-is.
// Returns empty string if no file is found.
func DiscoverFile(configDir, explicitPath string) string {
	if explicitPath != "" {
		return explicitPath
	}
	candidate := filepath.Join(configDir, "profiles.yml")
	if _, err := os.Stat(candidate); err == nil {
		return candidate
	}
	return ""
}

// GetProfile returns a profile by name, or nil if not found.
func (m *Manager) GetProfile(name string) *types.ModelConfig {
	cfg, ok := m.profiles[name]
	if !ok {
		return nil
	}
	return &cfg
}

// Profiles returns all loaded profiles.
func (m *Manager) Profiles() map[string]types.ModelConfig {
	return m.profiles
}

// DefaultProfile returns the name of the default profile.
func (m *Manager) DefaultProfile() string {
	return m.defaultProfile
}

// OverrideProfile returns the name of the override profile.
func (m *Manager) OverrideProfile() string {
	return m.overrideProfile
}

// Resolve resolves a ModelField through the profile cascade:
//  1. Start with default profile (if set)
//  2. Apply named profile (if model is string or has 'profile' key)
//  3. Merge inline overrides (if model is dict)
//  4. Apply override profile (trumps all)
//
// Returns the fully resolved ModelConfig.
func (m *Manager) Resolve(field types.ModelField) (types.ModelConfig, error) {
	result := types.ModelConfig{}

	// 1. Apply default profile
	if m.defaultProfile != "" {
		if def := m.GetProfile(m.defaultProfile); def != nil {
			result = *def
		}
	}

	// 2. Handle agent's model config
	switch {
	case field.IsString():
		// String = profile name lookup
		profileCfg := m.GetProfile(field.ProfileName)
		if profileCfg != nil {
			mergeModelConfig(&result, profileCfg)
		} else if result.Name == "" {
			return result, fmt.Errorf("model profile '%s' not found and no default configured", field.ProfileName)
		}

	case field.IsProfiled():
		// Profile reference with optional overrides
		profileCfg := m.GetProfile(field.Profiled.Profile)
		if profileCfg != nil {
			mergeModelConfig(&result, profileCfg)
		} else if result.Name == "" {
			return result, fmt.Errorf("model profile '%s' not found and no default configured", field.Profiled.Profile)
		}
		// Apply inline overrides
		overrides := field.Profiled.Overrides()
		mergeModelConfig(&result, &overrides)

	case field.IsInline():
		// Inline config -- merge directly
		mergeModelConfig(&result, field.Config)
	}

	// 3. Apply override profile (trumps all)
	if m.overrideProfile != "" {
		if ovr := m.GetProfile(m.overrideProfile); ovr != nil {
			mergeModelConfig(&result, ovr)
		}
	}

	return result, nil
}

// mergeModelConfig merges src into dst, only overwriting non-zero fields.
func mergeModelConfig(dst, src *types.ModelConfig) {
	if src.Name != "" {
		dst.Name = src.Name
	}
	if src.Provider != "" {
		dst.Provider = src.Provider
	}
	if src.Temperature != nil {
		dst.Temperature = src.Temperature
	}
	if src.MaxTokens != nil {
		dst.MaxTokens = src.MaxTokens
	}
	if src.TopP != nil {
		dst.TopP = src.TopP
	}
	if src.TopK != nil {
		dst.TopK = src.TopK
	}
	if src.FrequencyPenalty != nil {
		dst.FrequencyPenalty = src.FrequencyPenalty
	}
	if src.PresencePenalty != nil {
		dst.PresencePenalty = src.PresencePenalty
	}
	if src.Seed != nil {
		dst.Seed = src.Seed
	}
	if src.BaseURL != "" {
		dst.BaseURL = src.BaseURL
	}
}

// ModelName returns the fully-qualified model name (provider/name).
func ModelName(cfg types.ModelConfig) string {
	if cfg.Provider != "" && cfg.Name != "" {
		return cfg.Provider + "/" + cfg.Name
	}
	return cfg.Name
}
