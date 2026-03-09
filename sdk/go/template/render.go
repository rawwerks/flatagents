// Package template provides Jinja2-to-Go template translation and rendering
// for flatagents configurations.
//
// Flatagents configs use Jinja2 template syntax ({{ input.field }}). This
// package translates common Jinja2 patterns to Go text/template equivalents
// and renders them with the provided data.
package template

import (
	"fmt"
	"regexp"
	"strings"
	"text/template"
)

// jinja2ToGo translates a Jinja2 template string to Go text/template syntax.
//
// Supported translations:
//   - {{ expr }}           -> {{ .expr }}  (dot-prefix for variable access)
//   - {{ input.field }}    -> {{ .input.field }}
//   - {{ context.field }}  -> {{ .context.field }}
//   - {{ output.field }}   -> {{ .output.field }}
//   - {% if cond %}        -> {{ if .cond }}
//   - {% else %}           -> {{ else }}
//   - {% endif %}          -> {{ end }}
//   - {% for x in y %}     -> {{ range .y }}  (simplified)
//   - {% endfor %}         -> {{ end }}
//   - {{ x | default(v) }} -> {{ if .x }}{{ .x }}{{ else }}v{{ end }}
//   - {{ x | int }}        -> {{ .x }}  (Go handles type conversion differently)
func Translate(jinjaTemplate string) string {
	s := jinjaTemplate

	// Handle {% if expr %} blocks
	s = reIf.ReplaceAllStringFunc(s, translateIf)

	// Handle {% else %}
	s = strings.ReplaceAll(s, "{% else %}", "{{ else }}")

	// Handle {% endif %}
	s = strings.ReplaceAll(s, "{% endif %}", "{{ end }}")

	// Handle {% for item in collection %}
	s = reFor.ReplaceAllStringFunc(s, translateFor)

	// Handle {% endfor %}
	s = strings.ReplaceAll(s, "{% endfor %}", "{{ end }}")

	// Handle {{ expr | default(value) }} before general expression translation
	s = reDefault.ReplaceAllStringFunc(s, translateDefault)

	// Handle {{ expr | int }} and other simple filters (strip the filter)
	s = reSimpleFilter.ReplaceAllStringFunc(s, translateSimpleFilter)

	// Handle general {{ expr }} expressions
	s = reExpr.ReplaceAllStringFunc(s, translateExpr)

	return s
}

var (
	// reExpr matches {{ expr }} Jinja2 expressions.
	reExpr = regexp.MustCompile(`\{\{\s*(.+?)\s*\}\}`)

	// reIf matches {% if expr %}
	reIf = regexp.MustCompile(`\{%[-\s]*if\s+(.+?)\s*[-]?%\}`)

	// reFor matches {% for var in collection %}
	reFor = regexp.MustCompile(`\{%[-\s]*for\s+(\w+)\s+in\s+(.+?)\s*[-]?%\}`)

	// reDefault matches {{ expr | default(value) }}
	reDefault = regexp.MustCompile(`\{\{\s*(.+?)\s*\|\s*default\(([^)]*)\)\s*\}\}`)

	// reSimpleFilter matches {{ expr | filter }} for filters we strip
	reSimpleFilter = regexp.MustCompile(`\{\{\s*(.+?)\s*\|\s*(int|float|string|trim|lower|upper|length)\s*\}\}`)
)

// translateExpr translates a {{ expr }} expression.
func translateExpr(match string) string {
	inner := reExpr.FindStringSubmatch(match)
	if len(inner) < 2 {
		return match
	}
	expr := strings.TrimSpace(inner[1])

	// Already translated (starts with .)
	if strings.HasPrefix(expr, ".") {
		return match
	}

	// Go template control keywords -- don't prefix
	if strings.HasPrefix(expr, "if ") || strings.HasPrefix(expr, "else") ||
		strings.HasPrefix(expr, "end") || strings.HasPrefix(expr, "range ") ||
		strings.HasPrefix(expr, "with ") || strings.HasPrefix(expr, "define ") ||
		strings.HasPrefix(expr, "template ") || strings.HasPrefix(expr, "block ") {
		return match
	}

	// Handle arithmetic/concatenation expressions: context.round + 1
	// For these complex expressions, we use the index helper approach
	if strings.Contains(expr, " + ") || strings.Contains(expr, " - ") ||
		strings.Contains(expr, " * ") || strings.Contains(expr, " / ") {
		return fmt.Sprintf("{{ eval %q . }}", expr)
	}

	// Handle subscript access: context.target[context.current|length]
	// These are complex Jinja2 patterns -- pass through as eval
	if strings.Contains(expr, "[") {
		return fmt.Sprintf("{{ eval %q . }}", expr)
	}

	// Simple dotted access: prefix with .
	expr = addDotPrefix(expr)
	return fmt.Sprintf("{{ %s }}", expr)
}

// translateIf translates {% if expr %} to {{ if .expr }}.
func translateIf(match string) string {
	inner := reIf.FindStringSubmatch(match)
	if len(inner) < 2 {
		return match
	}
	expr := strings.TrimSpace(inner[1])
	expr = addDotPrefix(expr)
	return fmt.Sprintf("{{ if %s }}", expr)
}

// translateFor translates {% for var in collection %} to {{ range .collection }}.
func translateFor(match string) string {
	inner := reFor.FindStringSubmatch(match)
	if len(inner) < 3 {
		return match
	}
	collection := strings.TrimSpace(inner[2])
	collection = addDotPrefix(collection)
	return fmt.Sprintf("{{ range %s }}", collection)
}

// translateDefault translates {{ expr | default(value) }}.
func translateDefault(match string) string {
	inner := reDefault.FindStringSubmatch(match)
	if len(inner) < 3 {
		return match
	}
	expr := addDotPrefix(strings.TrimSpace(inner[1]))
	defVal := strings.TrimSpace(inner[2])
	// Remove surrounding quotes from default value for Go template
	defVal = strings.Trim(defVal, "\"'")
	return fmt.Sprintf("{{ default %s %q }}", expr, defVal)
}

// translateSimpleFilter translates {{ expr | filter }} by stripping the filter.
func translateSimpleFilter(match string) string {
	inner := reSimpleFilter.FindStringSubmatch(match)
	if len(inner) < 2 {
		return match
	}
	expr := addDotPrefix(strings.TrimSpace(inner[1]))
	return fmt.Sprintf("{{ %s }}", expr)
}

// addDotPrefix adds a dot prefix to the first identifier in an expression
// if it's a known variable (input, context, output, item, doc, model, tools, etc.)
func addDotPrefix(expr string) string {
	// Handle "not expr"
	if strings.HasPrefix(expr, "not ") {
		rest := strings.TrimPrefix(expr, "not ")
		return "not " + addDotPrefix(rest)
	}

	// Handle "expr and expr", "expr or expr"
	for _, op := range []string{" and ", " or "} {
		if idx := strings.Index(expr, op); idx > 0 {
			left := addDotPrefix(expr[:idx])
			right := addDotPrefix(expr[idx+len(op):])
			return left + op + right
		}
	}

	// Handle comparison operators
	for _, op := range []string{" >= ", " <= ", " != ", " == ", " > ", " < "} {
		if idx := strings.Index(expr, op); idx > 0 {
			left := addDotPrefix(strings.TrimSpace(expr[:idx]))
			right := addDotPrefixIfVar(strings.TrimSpace(expr[idx+len(op):]))
			return left + op + right
		}
	}

	// Simple identifier or dotted access
	return addDotPrefixIfVar(expr)
}

// addDotPrefixIfVar adds a dot prefix if the string starts with a known variable.
func addDotPrefixIfVar(s string) string {
	s = strings.TrimSpace(s)
	if s == "" || s == "true" || s == "false" || s == "null" || s == "nil" || s == "none" {
		return s
	}
	// Number literal
	if len(s) > 0 && (s[0] >= '0' && s[0] <= '9') {
		return s
	}
	// Quoted string literal
	if len(s) > 0 && (s[0] == '"' || s[0] == '\'') {
		return s
	}
	// Already dot-prefixed
	if strings.HasPrefix(s, ".") {
		return s
	}

	// Known top-level variables that need dot prefix
	knownVars := []string{
		"input.", "context.", "output.", "item.", "doc.",
		"model.", "tools.", "tools_prompt",
		"input", "context", "output", "item", "doc",
		"model", "tools",
	}
	for _, v := range knownVars {
		if strings.HasPrefix(s, v) {
			return "." + s
		}
	}

	return s
}

// Render translates a Jinja2 template string and executes it with the given data.
// The data map is available as the root context (e.g., data["input"] -> {{ .input }}).
func Render(jinjaTemplate string, data map[string]interface{}) (string, error) {
	goTmpl := Translate(jinjaTemplate)

	funcMap := template.FuncMap{
		"default": func(val interface{}, def string) interface{} {
			if val == nil || val == "" {
				return def
			}
			return val
		},
		"eval": func(expr string, data interface{}) string {
			// Simplified eval for arithmetic/subscript expressions.
			// In production, this would use a proper expression evaluator.
			return expr
		},
	}

	tmpl, err := template.New("").Funcs(funcMap).Parse(goTmpl)
	if err != nil {
		return "", fmt.Errorf("parsing Go template (translated from Jinja2): %w\n  original: %s\n  translated: %s", err, jinjaTemplate, goTmpl)
	}

	var buf strings.Builder
	if err := tmpl.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("executing template: %w", err)
	}

	return buf.String(), nil
}

// RenderMap renders all string values in a map through the template engine.
// Non-string values are passed through unchanged.
func RenderMap(templates map[string]interface{}, data map[string]interface{}) (map[string]interface{}, error) {
	result := make(map[string]interface{}, len(templates))
	for k, v := range templates {
		switch val := v.(type) {
		case string:
			rendered, err := Render(val, data)
			if err != nil {
				return nil, fmt.Errorf("rendering template for key '%s': %w", k, err)
			}
			result[k] = rendered
		default:
			result[k] = v
			_ = val
		}
	}
	return result, nil
}
