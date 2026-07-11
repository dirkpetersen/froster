package workflow

import (
	"testing"
	"time"
)

func TestPyDatetimeStr(t *testing.T) {
	cases := []struct {
		t    time.Time
		want string
	}{
		{time.Date(2026, 7, 10, 23, 40, 25, 780537000, time.UTC), "2026-07-10 23:40:25.780537"},
		{time.Date(2026, 1, 2, 3, 4, 5, 1000, time.UTC), "2026-01-02 03:04:05.000001"},
		// Python omits the fraction entirely for microsecond == 0.
		{time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC), "2026-01-02 03:04:05"},
	}
	for _, c := range cases {
		if got := pyDatetimeStr(c.t); got != c.want {
			t.Errorf("pyDatetimeStr(%v) = %q, want %q", c.t, got, c.want)
		}
	}
}

func TestPyRoundRepr(t *testing.T) {
	cases := []struct {
		x       float64
		ndigits int
		want    string
	}{
		{0.0021374, 3, "0.002"},    // golden index summary: 0.002 TiB
		{2.0, 3, "2.0"},            // str(round(2.0, 3)) == '2.0'
		{0.2465753, 1, "0.2"},      // 90/365 years
		{15.0, 1, "15.0"},          // 5475/365
		{1.2328767, 1, "1.2"},      // 450/365
		{0.0, 3, "0.0"},            // str(0.0)
		{123.456789, 3, "123.457"}, // plain rounding
	}
	for _, c := range cases {
		if got := pyRoundRepr(c.x, c.ndigits); got != c.want {
			t.Errorf("pyRoundRepr(%v, %d) = %q, want %q", c.x, c.ndigits, got, c.want)
		}
	}
}

func TestCleanPath(t *testing.T) {
	dir := t.TempDir()
	// Trailing slash is stripped.
	if got := CleanPath(dir + "/"); got != dir {
		t.Errorf("CleanPath(%q) = %q, want %q", dir+"/", got, dir)
	}
	// Missing paths resolve their existing prefix (realpath semantics).
	missing := dir + "/does/not/exist"
	if got := CleanPath(missing); got != missing {
		t.Errorf("CleanPath(%q) = %q, want %q", missing, got, missing)
	}
	// Empty stays empty (mountpoint default handling relies on this).
	if got := CleanPath(""); got != "" {
		t.Errorf("CleanPath(\"\") = %q", got)
	}
}
