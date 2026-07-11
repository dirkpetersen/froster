package hotspots

import (
	"bufio"
	"strings"
)

// writeExcelRow writes one CSV row exactly like Python's
// csv.writer(f, dialect='excel') with the default QUOTE_MINIMAL quoting:
//
//   - fields are joined with ','   and terminated with "\r\n";
//   - a field is quoted only if it contains a comma, a double quote, or a
//     line-terminator character ('\r' or '\n'); embedded quotes are doubled;
//   - unlike encoding/csv, fields with leading/trailing whitespace or the
//     value `\.` are NOT quoted, and empty fields are written bare.
//
// encoding/csv cannot reproduce these rules byte-for-byte, hence this
// hand-rolled writer.
func writeExcelRow(w *bufio.Writer, fields []string) error {
	for i, f := range fields {
		if i > 0 {
			if err := w.WriteByte(','); err != nil {
				return err
			}
		}
		if !strings.ContainsAny(f, ",\"\r\n") {
			if _, err := w.WriteString(f); err != nil {
				return err
			}
			continue
		}
		if err := w.WriteByte('"'); err != nil {
			return err
		}
		for j := 0; j < len(f); j++ {
			if f[j] == '"' {
				if err := w.WriteByte('"'); err != nil {
					return err
				}
			}
			if err := w.WriteByte(f[j]); err != nil {
				return err
			}
		}
		if err := w.WriteByte('"'); err != nil {
			return err
		}
	}
	_, err := w.WriteString("\r\n")
	return err
}
