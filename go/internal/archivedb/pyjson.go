package archivedb

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf16"
)

// This file implements a JSON writer whose output is byte-identical to
// Python's json.dump(data, file, indent=4) — the exact call the Python
// froster uses to write froster-archives.json (froster/froster.py,
// Archiver._archive_json_add_entry). Matching the formatting keeps diffs
// minimal when Python and Go clients share one DB file (shared-config mode).
//
// Python formatting rules reproduced here:
//   - 4-space indent, one key per line, ": " after keys, "," + newline
//     between items, no trailing newline after the closing brace.
//   - ensure_ascii=True: every rune outside 0x20..0x7E is escaped as
//     \uXXXX (surrogate pairs above the BMP); the shortcuts \" \\ \b \t
//     \n \f \r are used where they exist. Note that 0x7F (DEL) is escaped.
//   - Empty objects and arrays are written inline as "{}" and "[]".

const pyIndent = "    "

// pyEscapeString writes s as a Python-json.dump-compatible JSON string
// literal (including the surrounding quotes) to buf.
func pyEscapeString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\b':
			buf.WriteString(`\b`)
		case '\t':
			buf.WriteString(`\t`)
		case '\n':
			buf.WriteString(`\n`)
		case '\f':
			buf.WriteString(`\f`)
		case '\r':
			buf.WriteString(`\r`)
		default:
			if r >= 0x20 && r < 0x7f {
				buf.WriteRune(r)
			} else if r > 0xffff {
				hi, lo := utf16.EncodeRune(r)
				fmt.Fprintf(buf, `\u%04x\u%04x`, hi, lo)
			} else {
				fmt.Fprintf(buf, `\u%04x`, r)
			}
		}
	}
	buf.WriteByte('"')
}

// pyWriteRaw transcodes an arbitrary JSON value (held as raw bytes, e.g. an
// unknown entry key preserved from a Python-written file) into Python
// json.dump(indent=4) formatting at the given indent depth. Object key
// order and number literals are preserved exactly as they appear in raw.
func pyWriteRaw(buf *bytes.Buffer, raw json.RawMessage, depth int) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := pyTranscodeValue(buf, dec, depth); err != nil {
		return err
	}
	// Reject trailing garbage after the first value.
	if _, err := dec.Token(); err == nil {
		return fmt.Errorf("archivedb: trailing data after JSON value")
	}
	return nil
}

// pyTranscodeValue consumes one JSON value from dec and writes it in Python
// style. depth is the nesting depth of the value itself (its opening token
// is assumed already indented by the caller).
func pyTranscodeValue(buf *bytes.Buffer, dec *json.Decoder, depth int) error {
	tok, err := dec.Token()
	if err != nil {
		return fmt.Errorf("archivedb: invalid JSON value: %w", err)
	}
	return pyTranscodeToken(buf, dec, tok, depth)
}

func pyTranscodeToken(buf *bytes.Buffer, dec *json.Decoder, tok json.Token, depth int) error {
	switch t := tok.(type) {
	case json.Delim:
		switch t {
		case '{':
			return pyTranscodeObject(buf, dec, depth)
		case '[':
			return pyTranscodeArray(buf, dec, depth)
		default:
			return fmt.Errorf("archivedb: unexpected JSON delimiter %q", t)
		}
	case string:
		pyEscapeString(buf, t)
	case json.Number:
		buf.WriteString(t.String())
	case bool:
		if t {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case nil:
		buf.WriteString("null")
	default:
		return fmt.Errorf("archivedb: unexpected JSON token %v", tok)
	}
	return nil
}

func pyTranscodeObject(buf *bytes.Buffer, dec *json.Decoder, depth int) error {
	inner := strings.Repeat(pyIndent, depth+1)
	first := true
	for dec.More() {
		keyTok, err := dec.Token()
		if err != nil {
			return fmt.Errorf("archivedb: invalid JSON object key: %w", err)
		}
		key, ok := keyTok.(string)
		if !ok {
			return fmt.Errorf("archivedb: non-string JSON object key %v", keyTok)
		}
		if first {
			buf.WriteString("{\n")
			first = false
		} else {
			buf.WriteString(",\n")
		}
		buf.WriteString(inner)
		pyEscapeString(buf, key)
		buf.WriteString(": ")
		if err := pyTranscodeValue(buf, dec, depth+1); err != nil {
			return err
		}
	}
	if _, err := dec.Token(); err != nil { // consume '}'
		return fmt.Errorf("archivedb: unterminated JSON object: %w", err)
	}
	if first {
		buf.WriteString("{}") // Python writes empty dicts inline
		return nil
	}
	buf.WriteString("\n")
	buf.WriteString(strings.Repeat(pyIndent, depth))
	buf.WriteString("}")
	return nil
}

func pyTranscodeArray(buf *bytes.Buffer, dec *json.Decoder, depth int) error {
	inner := strings.Repeat(pyIndent, depth+1)
	first := true
	for dec.More() {
		if first {
			buf.WriteString("[\n")
			first = false
		} else {
			buf.WriteString(",\n")
		}
		buf.WriteString(inner)
		if err := pyTranscodeValue(buf, dec, depth+1); err != nil {
			return err
		}
	}
	if _, err := dec.Token(); err != nil { // consume ']'
		return fmt.Errorf("archivedb: unterminated JSON array: %w", err)
	}
	if first {
		buf.WriteString("[]") // Python writes empty lists inline
		return nil
	}
	buf.WriteString("\n")
	buf.WriteString(strings.Repeat(pyIndent, depth))
	buf.WriteString("]")
	return nil
}
