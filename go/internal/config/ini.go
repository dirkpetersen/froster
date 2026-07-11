package config

import (
	"bytes"
	"strings"

	ini "gopkg.in/ini.v1"
)

// loadOptions returns go-ini options tuned to match Python's configparser:
//
//   - InsensitiveKeys: configparser lowercases option names via optionxform
//     on both read and write; section names stay case-sensitive.
//   - IgnoreInlineComment: configparser has inline comments disabled by
//     default ("value ; not a comment" is part of the value).
//   - AllowPythonMultilineValues: indented continuation lines belong to the
//     previous key's value (configparser semantics; also used by
//     ~/.aws/config's nested "s3" value).
//   - PreserveSurroundedQuote: configparser treats quotes as literal value
//     characters and never strips them.
//
// Differences that remain (all strictly more permissive than configparser):
//
//   - Duplicate keys/sections: configparser (strict=True) raises an error;
//     go-ini keeps the last value.
//   - '%' interpolation: configparser's BasicInterpolation would expand or
//     reject '%' sequences; go-ini treats them literally.
func loadOptions() ini.LoadOptions {
	return ini.LoadOptions{
		InsensitiveKeys:            true,
		IgnoreInlineComment:        true,
		AllowPythonMultilineValues: true,
		PreserveSurroundedQuote:    true,
	}
}

// normalizeMultilineValues rewrites every multi-line value in f the way
// configparser normalizes them at parse time: each physical line of the
// value is stripped of surrounding whitespace and the lines are re-joined
// with "\n". (go-ini keeps the continuation indentation; configparser does
// not.) Doing this at load time keeps rewrites stable: the emitter re-indents
// continuation lines with a tab exactly once, like configparser.write().
func normalizeMultilineValues(f *ini.File) {
	for _, sec := range f.Sections() {
		for _, key := range sec.Keys() {
			v := key.Value()
			if strings.Contains(v, "\n") {
				key.SetValue(normalizeMultiline(v))
			}
		}
	}
}

func normalizeMultiline(v string) string {
	lines := strings.Split(v, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimSpace(line)
	}
	return strings.Join(lines, "\n")
}

// marshalINI serializes f byte-for-byte the way Python's
// configparser.ConfigParser.write() would, with one deliberate exception:
// comments present in the source file are preserved (configparser drops
// them). Format details reproduced:
//
//   - "key = value" with exactly one space around '=' and no alignment
//     padding; empty values produce a trailing space ("key = ").
//   - Option names written in lowercase.
//   - A blank line after every section, including the last one.
//   - Multi-line values written with continuation lines indented by a tab
//     ("key = \n\tcontinuation"), as configparser.write() does via
//     value.replace("\n", "\n\t").
func marshalINI(f *ini.File) []byte {
	var buf bytes.Buffer

	for _, sec := range f.Sections() {
		keys := sec.Keys()

		if sec.Name() == ini.DefaultSection && len(keys) == 0 {
			// go-ini always materializes an (empty) default section;
			// configparser only writes [DEFAULT] when it has entries.
			continue
		}

		writeComment(&buf, sec.Comment)
		buf.WriteString("[")
		buf.WriteString(sec.Name())
		buf.WriteString("]\n")

		for _, key := range keys {
			writeComment(&buf, key.Comment)
			buf.WriteString(strings.ToLower(key.Name()))
			buf.WriteString(" = ")
			buf.WriteString(strings.ReplaceAll(key.Value(), "\n", "\n\t"))
			buf.WriteString("\n")
		}

		buf.WriteString("\n")
	}

	return buf.Bytes()
}

// writeComment emits a stored go-ini comment (which may span multiple
// lines), making sure every line carries a comment prefix.
func writeComment(buf *bytes.Buffer, comment string) {
	if comment == "" {
		return
	}
	for _, line := range strings.Split(comment, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if !strings.HasPrefix(line, "#") && !strings.HasPrefix(line, ";") {
			line = "# " + line
		}
		buf.WriteString(line)
		buf.WriteString("\n")
	}
}

// parseConfigparserBool interprets a value the way configparser.getboolean
// does: 1/yes/true/on are true; 0/no/false/off are false (case-insensitive).
// Any other value is reported as not-ok.
func parseConfigparserBool(v string) (value, ok bool) {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "yes", "true", "on":
		return true, true
	case "0", "no", "false", "off":
		return false, true
	default:
		return false, false
	}
}

// pythonBool renders a boolean the way Python's str(bool) does, which is
// what froster writes into config.ini ("True"/"False").
func pythonBool(b bool) string {
	if b {
		return "True"
	}
	return "False"
}
