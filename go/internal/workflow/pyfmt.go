package workflow

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"
)

// pyDatetimeStr renders t like Python's str(datetime.datetime.now()):
// "YYYY-MM-DD HH:MM:SS[.ffffff]" — microsecond precision, and the
// fractional part omitted entirely when the microseconds are zero.
func pyDatetimeStr(t time.Time) string {
	s := t.Format("2006-01-02 15:04:05")
	if us := t.Nanosecond() / 1000; us != 0 {
		s += fmt.Sprintf(".%06d", us)
	}
	return s
}

// pyRoundRepr renders Python's str(round(x, ndigits)): round-half-to-even
// at the given decimal position, then the shortest float repr — which for
// integer-valued floats includes a trailing ".0" (str(2.0) == "2.0").
func pyRoundRepr(x float64, ndigits int) string {
	pow := math.Pow(10, float64(ndigits))
	rounded := math.RoundToEven(x*pow) / pow
	s := strconv.FormatFloat(rounded, 'f', -1, 64)
	if !strings.ContainsAny(s, ".eE") {
		s += ".0"
	}
	return s
}
