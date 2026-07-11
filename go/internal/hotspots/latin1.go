package hotspots

import (
	"bufio"
	"io"
)

// latin1Reader transcodes an ISO-8859-1 byte stream to UTF-8, reproducing
// froster's unconditional `iconv -f ISO-8859-1 -t UTF-8` step. Every byte
// sequence is valid ISO-8859-1, so the transformation never fails: bytes
// < 0x80 pass through, bytes >= 0x80 become the two-byte UTF-8 encoding of
// the same code point (0x80..0x9F map to the C1 control code points, as
// iconv does).
//
// The deliberate consequence — identical to Python — is that input that
// was already multi-byte UTF-8 comes out mojibake'd (each byte
// reinterpreted as a Latin-1 character). See the package documentation.
type latin1Reader struct {
	src *bufio.Reader
}

func newLatin1Reader(r io.Reader) *latin1Reader {
	return &latin1Reader{src: bufio.NewReaderSize(r, 32*1024)}
}

// Read implements io.Reader. It may return (0, nil) if len(p) == 1 and the
// next input byte needs two output bytes; callers (bufio, encoding/csv)
// always supply larger buffers.
func (r *latin1Reader) Read(p []byte) (int, error) {
	n := 0
	for n < len(p) {
		b, err := r.src.ReadByte()
		if err != nil {
			if n > 0 {
				return n, nil
			}
			return 0, err
		}
		if b < 0x80 {
			p[n] = b
			n++
			continue
		}
		if n+2 > len(p) {
			// Not enough room for a two-byte sequence; leave the byte for
			// the next call.
			_ = r.src.UnreadByte()
			break
		}
		p[n] = 0xC0 | b>>6
		p[n+1] = 0x80 | b&0x3F
		n += 2
	}
	return n, nil
}
