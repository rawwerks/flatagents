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
	"strconv"
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
			dataMap, ok := data.(map[string]interface{})
			if !ok {
				return fmt.Sprintf("<eval error: data is %T, not map>", data)
			}
			result, err := evalExpr(expr, dataMap)
			if err != nil {
				return fmt.Sprintf("<eval error: %s>", err)
			}
			return fmt.Sprintf("%v", result)
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

// ---------------------------------------------------------------------------
// Expression evaluator for arithmetic and subscript access
// ---------------------------------------------------------------------------

// evalExpr evaluates a Jinja2 expression that contains arithmetic operators
// (+, -, *, /) or subscript access (e.g., context.target[context.current|length]).
//
// It resolves dotted variable paths against the provided data map and computes
// the result. This is intentionally limited to the patterns that appear in
// flatagents/flatmachines configs.
func evalExpr(expr string, data map[string]interface{}) (interface{}, error) {
	expr = strings.TrimSpace(expr)

	// Handle subscript access: e.g., context.target[context.current|length]
	if bracketIdx := strings.Index(expr, "["); bracketIdx > 0 {
		return evalSubscript(expr, bracketIdx, data)
	}

	// Handle binary arithmetic: a + b, a - b, a * b, a / b
	for _, op := range []string{" + ", " - ", " * ", " / "} {
		if idx := strings.Index(expr, op); idx > 0 {
			leftExpr := strings.TrimSpace(expr[:idx])
			rightExpr := strings.TrimSpace(expr[idx+len(op):])

			leftVal, err := evalExpr(leftExpr, data)
			if err != nil {
				return nil, err
			}
			rightVal, err := evalExpr(rightExpr, data)
			if err != nil {
				return nil, err
			}

			lNum, lOk := toFloat(leftVal)
			rNum, rOk := toFloat(rightVal)
			if !lOk || !rOk {
				// String concatenation for +
				if op == " + " {
					return fmt.Sprintf("%v%v", leftVal, rightVal), nil
				}
				return nil, fmt.Errorf("cannot perform %q on non-numeric values: %v %s %v", op, leftVal, strings.TrimSpace(op), rightVal)
			}

			switch op {
			case " + ":
				r := lNum + rNum
				if isWholeNumber(r) {
					return int64(r), nil
				}
				return r, nil
			case " - ":
				r := lNum - rNum
				if isWholeNumber(r) {
					return int64(r), nil
				}
				return r, nil
			case " * ":
				r := lNum * rNum
				if isWholeNumber(r) {
					return int64(r), nil
				}
				return r, nil
			case " / ":
				if rNum == 0 {
					return nil, fmt.Errorf("division by zero")
				}
				r := lNum / rNum
				if isWholeNumber(r) {
					return int64(r), nil
				}
				return r, nil
			}
		}
	}

	// Base case: resolve a single value (variable path or literal)
	return resolveValue(expr, data)
}

// evalSubscript handles expressions like context.target[context.current|length].
func evalSubscript(expr string, bracketIdx int, data map[string]interface{}) (interface{}, error) {
	baseExpr := strings.TrimSpace(expr[:bracketIdx])
	rest := expr[bracketIdx+1:]
	closeBracket := strings.Index(rest, "]")
	if closeBracket < 0 {
		return nil, fmt.Errorf("unclosed bracket in expression: %s", expr)
	}
	indexExpr := strings.TrimSpace(rest[:closeBracket])

	baseVal, err := resolveValue(baseExpr, data)
	if err != nil {
		return nil, err
	}

	// Handle |length filter on index expression
	if strings.Contains(indexExpr, "|length") {
		parts := strings.SplitN(indexExpr, "|", 2)
		innerExpr := strings.TrimSpace(parts[0])
		innerVal, err := resolveValue(innerExpr, data)
		if err != nil {
			return nil, err
		}
		// Get length of the value
		idx := lengthOf(innerVal)
		return subscriptAccess(baseVal, idx)
	}

	// Try as numeric index
	indexVal, err := evalExpr(indexExpr, data)
	if err != nil {
		return nil, err
	}
	if n, ok := toFloat(indexVal); ok {
		return subscriptAccess(baseVal, int(n))
	}
	// Try as string key
	if s, ok := indexVal.(string); ok {
		if m, ok := baseVal.(map[string]interface{}); ok {
			return m[s], nil
		}
	}
	return nil, fmt.Errorf("cannot subscript %T with %T", baseVal, indexVal)
}

// subscriptAccess indexes into a string or slice by integer index.
func subscriptAccess(val interface{}, idx int) (interface{}, error) {
	switch v := val.(type) {
	case string:
		if idx < 0 || idx >= len(v) {
			return nil, fmt.Errorf("string index %d out of range (len=%d)", idx, len(v))
		}
		return string(v[idx]), nil
	case []interface{}:
		if idx < 0 || idx >= len(v) {
			return nil, fmt.Errorf("list index %d out of range (len=%d)", idx, len(v))
		}
		return v[idx], nil
	default:
		return nil, fmt.Errorf("cannot index %T with integer", val)
	}
}

// lengthOf returns the length of a string, slice, or map.
func lengthOf(val interface{}) int {
	switch v := val.(type) {
	case string:
		return len(v)
	case []interface{}:
		return len(v)
	case map[string]interface{}:
		return len(v)
	default:
		return 0
	}
}

// resolveValue resolves a single value: a dotted variable path or a literal.
func resolveValue(expr string, data map[string]interface{}) (interface{}, error) {
	expr = strings.TrimSpace(expr)

	// Numeric literal
	if n, err := strconv.ParseFloat(expr, 64); err == nil {
		if isWholeNumber(n) {
			return int64(n), nil
		}
		return n, nil
	}

	// Quoted string literal
	if len(expr) >= 2 {
		if (expr[0] == '"' && expr[len(expr)-1] == '"') ||
			(expr[0] == '\'' && expr[len(expr)-1] == '\'') {
			return expr[1 : len(expr)-1], nil
		}
	}

	// Boolean/null literals
	switch expr {
	case "true", "True":
		return true, nil
	case "false", "False":
		return false, nil
	case "null", "None", "nil", "none":
		return nil, nil
	}

	// Dotted variable path: context.score, output.tagline, etc.
	if strings.Contains(expr, ".") {
		return resolveDotted(expr, data)
	}

	// Simple variable
	if val, ok := data[expr]; ok {
		return val, nil
	}

	return nil, fmt.Errorf("unknown variable: %s", expr)
}

// resolveDotted resolves a dotted path like "context.score" against data.
func resolveDotted(path string, data map[string]interface{}) (interface{}, error) {
	parts := strings.Split(path, ".")
	if len(parts) == 0 {
		return nil, fmt.Errorf("empty path")
	}

	val, ok := data[parts[0]]
	if !ok {
		return nil, nil
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

// toFloat converts a value to float64 for arithmetic.
func toFloat(v interface{}) (float64, bool) {
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

// isWholeNumber returns true if a float64 has no fractional part.
func isWholeNumber(f float64) bool {
	return f == float64(int64(f))
}
