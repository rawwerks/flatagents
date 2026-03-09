package template

import (
	"fmt"
	"strings"
	"testing"
)

func TestTranslateSimpleVariable(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"{{ input.name }}", "{{ .input.name }}"},
		{"{{ context.score }}", "{{ .context.score }}"},
		{"{{ output.tagline }}", "{{ .output.tagline }}"},
	}

	for _, tt := range tests {
		got := Translate(tt.input)
		if got != tt.expected {
			t.Errorf("Translate(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestTranslatePreservesText(t *testing.T) {
	input := "Hello world, no templates here."
	got := Translate(input)
	if got != input {
		t.Errorf("Translate(%q) = %q, want unchanged", input, got)
	}
}

func TestTranslateIfElse(t *testing.T) {
	input := "{% if input.feedback %}has feedback{% else %}no feedback{% endif %}"
	got := Translate(input)
	if !strings.Contains(got, "{{ if .input.feedback }}") {
		t.Errorf("expected translated if, got %q", got)
	}
	if !strings.Contains(got, "{{ else }}") {
		t.Errorf("expected {{ else }}, got %q", got)
	}
	if !strings.Contains(got, "{{ end }}") {
		t.Errorf("expected {{ end }}, got %q", got)
	}
}

func TestTranslateFor(t *testing.T) {
	input := "{% for tool in tools %}{{ tool.name }}{% endfor %}"
	got := Translate(input)
	if !strings.Contains(got, "{{ range .tools }}") {
		t.Errorf("expected range translation, got %q", got)
	}
	if !strings.Contains(got, "{{ end }}") {
		t.Errorf("expected end, got %q", got)
	}
}

func TestRenderSimple(t *testing.T) {
	tpl := "Hello {{ input.name }}!"
	data := map[string]interface{}{
		"input": map[string]interface{}{
			"name": "Alice",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "Hello Alice!" {
		t.Errorf("Render = %q, want 'Hello Alice!'", got)
	}
}

func TestRenderNestedAccess(t *testing.T) {
	tpl := "Product: {{ context.product }}, Score: {{ context.score }}"
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"product": "Widget",
			"score":   "8",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := "Product: Widget, Score: 8"
	if got != expected {
		t.Errorf("Render = %q, want %q", got, expected)
	}
}

func TestRenderMultiline(t *testing.T) {
	tpl := `Question: {{ input.question }}
Draft: {{ input.draft }}`
	data := map[string]interface{}{
		"input": map[string]interface{}{
			"question": "What is Go?",
			"draft":    "Go is a programming language.",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "What is Go?") {
		t.Errorf("expected question in output, got %q", got)
	}
	if !strings.Contains(got, "Go is a programming language.") {
		t.Errorf("expected draft in output, got %q", got)
	}
}

func TestRenderMapValues(t *testing.T) {
	templates := map[string]interface{}{
		"product":  "{{ context.product }}",
		"tagline":  "{{ context.tagline }}",
		"static":   42,
	}
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"product": "Widget",
			"tagline": "Best widget ever",
		},
	}
	got, err := RenderMap(templates, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got["product"] != "Widget" {
		t.Errorf("expected product 'Widget', got %v", got["product"])
	}
	if got["tagline"] != "Best widget ever" {
		t.Errorf("expected tagline 'Best widget ever', got %v", got["tagline"])
	}
	if got["static"] != 42 {
		t.Errorf("expected static 42, got %v", got["static"])
	}
}

func TestRenderDefault(t *testing.T) {
	tpl := `{{ input.target_score | default(10) }}`
	data := map[string]interface{}{
		"input": map[string]interface{}{},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "10" {
		t.Errorf("Render = %q, want '10'", got)
	}
}

func TestRenderDefaultWithValue(t *testing.T) {
	tpl := `{{ input.target_score | default(10) }}`
	data := map[string]interface{}{
		"input": map[string]interface{}{
			"target_score": "8",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "8" {
		t.Errorf("Render = %q, want '8'", got)
	}
}

func TestRenderIfBlock(t *testing.T) {
	tpl := "{% if input.feedback %}Feedback: {{ input.feedback }}{% else %}No feedback{% endif %}"

	// With feedback
	data := map[string]interface{}{
		"input": map[string]interface{}{
			"feedback": "Good work",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got, "Good work") {
		t.Errorf("expected feedback in output, got %q", got)
	}

	// Without feedback
	data2 := map[string]interface{}{
		"input": map[string]interface{}{},
	}
	got2, err := Render(tpl, data2)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(got2, "No feedback") {
		t.Errorf("expected 'No feedback', got %q", got2)
	}
}

func TestTranslateFilterStrip(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"{{ context.round | int }}", "{{ .context.round }}"},
		{"{{ context.name | lower }}", "{{ .context.name }}"},
	}
	for _, tt := range tests {
		got := Translate(tt.input)
		if got != tt.expected {
			t.Errorf("Translate(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

func TestAddDotPrefixPreservesLiterals(t *testing.T) {
	// Numbers and strings should not get dot-prefixed
	tests := []struct {
		input    string
		expected string
	}{
		{"42", "42"},
		{`"hello"`, `"hello"`},
		{"true", "true"},
		{"false", "false"},
		{"null", "null"},
	}
	for _, tt := range tests {
		got := addDotPrefixIfVar(tt.input)
		if got != tt.expected {
			t.Errorf("addDotPrefixIfVar(%q) = %q, want %q", tt.input, got, tt.expected)
		}
	}
}

// ---------------------------------------------------------------------------
// eval expression tests
// ---------------------------------------------------------------------------

func TestEvalArithmetic(t *testing.T) {
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"round": int64(3),
			"score": int64(7),
		},
	}

	tests := []struct {
		expr     string
		expected string
	}{
		{"context.round + 1", "4"},
		{"context.score - 2", "5"},
		{"context.round * 2", "6"},
		{"context.score + context.round", "10"},
	}

	for _, tt := range tests {
		got, err := evalExpr(tt.expr, data)
		if err != nil {
			t.Errorf("evalExpr(%q): unexpected error: %v", tt.expr, err)
			continue
		}
		gotStr := fmt.Sprintf("%v", got)
		if gotStr != tt.expected {
			t.Errorf("evalExpr(%q) = %v, want %s", tt.expr, got, tt.expected)
		}
	}
}

func TestRenderArithmeticTemplate(t *testing.T) {
	// This is the pattern from the writer_critic example:
	//   round: "{{ (context.round | int) + 1 }}"
	// After filter stripping it becomes:
	//   round: "{{ context.round + 1 }}"
	tpl := "{{ context.round + 1 }}"
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"round": int64(2),
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "3" {
		t.Errorf("Render(%q) = %q, want '3'", tpl, got)
	}
}

func TestRenderArithmeticWithStringNumber(t *testing.T) {
	// Context values from prior template renders may be strings
	tpl := "{{ context.round + 1 }}"
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"round": "5",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "6" {
		t.Errorf("Render(%q) = %q, want '6'", tpl, got)
	}
}

func TestEvalSubscriptStringIndex(t *testing.T) {
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"target":  "hello",
			"current": "hel",
		},
	}

	// context.target[context.current|length] should give 'l' (index 3)
	got, err := evalExpr("context.target[context.current|length]", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "l" {
		t.Errorf("evalExpr subscript = %v, want 'l'", got)
	}
}

func TestEvalDivision(t *testing.T) {
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"total": int64(10),
		},
	}
	got, err := evalExpr("context.total / 2", data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	gotStr := fmt.Sprintf("%v", got)
	if gotStr != "5" {
		t.Errorf("evalExpr division = %v, want 5", got)
	}
}

func TestEvalDivisionByZero(t *testing.T) {
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"val": int64(10),
		},
	}
	_, err := evalExpr("context.val / 0", data)
	if err == nil {
		t.Error("expected error for division by zero")
	}
}

func TestEvalLiteralResolution(t *testing.T) {
	data := map[string]interface{}{}

	tests := []struct {
		expr     string
		expected interface{}
	}{
		{"42", int64(42)},
		{"3.14", 3.14},
		{`"hello"`, "hello"},
		{"true", true},
		{"false", false},
	}

	for _, tt := range tests {
		got, err := resolveValue(tt.expr, data)
		if err != nil {
			t.Errorf("resolveValue(%q): %v", tt.expr, err)
			continue
		}
		if got != tt.expected {
			t.Errorf("resolveValue(%q) = %v (%T), want %v (%T)", tt.expr, got, got, tt.expected, tt.expected)
		}
	}
}

func TestRenderSubscriptTemplate(t *testing.T) {
	// This pattern appears in the helloworld machine config:
	//   expected_char: "{{ context.target[context.current|length] }}"
	tpl := "{{ context.target[context.current|length] }}"
	data := map[string]interface{}{
		"context": map[string]interface{}{
			"target":  "hello",
			"current": "he",
		},
	}
	got, err := Render(tpl, data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "l" {
		t.Errorf("Render subscript = %q, want 'l'", got)
	}
}
