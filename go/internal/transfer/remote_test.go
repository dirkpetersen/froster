package transfer

import (
	"strings"
	"testing"
)

func TestConnStringLocalPassthrough(t *testing.T) {
	got, err := ConnString("/tmp/some/dir", S3Config{})
	if err != nil {
		t.Fatalf("ConnString: %v", err)
	}
	if got != "/tmp/some/dir" {
		t.Errorf("local path changed: %q", got)
	}
}

func TestConnStringS3(t *testing.T) {
	cfg := S3Config{
		Provider:        "AWS",
		Region:          "us-west-2",
		AccessKeyID:     "AKIAEXAMPLE",
		SecretAccessKey: "secret",
		StorageClass:    "DEEP_ARCHIVE",
	}
	got, err := ConnString(":s3:mybucket/froster/prefix", cfg)
	if err != nil {
		t.Fatalf("ConnString: %v", err)
	}
	want := ":s3,provider=AWS,region=us-west-2,location_constraint=us-west-2," +
		"access_key_id=AKIAEXAMPLE,secret_access_key=secret,storage_class=DEEP_ARCHIVE:mybucket/froster/prefix"
	if got != want {
		t.Errorf("got  %q\nwant %q", got, want)
	}
}

func TestConnStringQuotesEndpoint(t *testing.T) {
	cfg := S3Config{
		Provider:        "Minio",
		Endpoint:        "http://127.0.0.1:9101",
		AccessKeyID:     "k",
		SecretAccessKey: "s",
	}
	got, err := ConnString(":s3:bucket", cfg)
	if err != nil {
		t.Fatalf("ConnString: %v", err)
	}
	if !strings.Contains(got, `endpoint="http://127.0.0.1:9101"`) {
		t.Errorf("endpoint with colons not quoted: %q", got)
	}
}

func TestConnStringCephForcesNoCheckBucket(t *testing.T) {
	cfg := S3Config{Provider: "Ceph", AccessKeyID: "k", SecretAccessKey: "s"}
	got, err := ConnString(":s3:bucket/p", cfg)
	if err != nil {
		t.Fatalf("ConnString: %v", err)
	}
	if !strings.Contains(got, "no_check_bucket=true") {
		t.Errorf("Ceph provider must set no_check_bucket: %q", got)
	}
}

func TestConnStringEnvAuth(t *testing.T) {
	got, err := ConnString(":s3:bucket", S3Config{Provider: "AWS", EnvAuth: true})
	if err != nil {
		t.Fatalf("ConnString with EnvAuth: %v", err)
	}
	if !strings.Contains(got, "env_auth=true") {
		t.Errorf("EnvAuth not propagated: %q", got)
	}
	if strings.Contains(got, "access_key_id") {
		t.Errorf("unexpected static credentials: %q", got)
	}
}

func TestConnStringMissingCredentials(t *testing.T) {
	if _, err := ConnString(":s3:bucket", S3Config{Provider: "AWS"}); err == nil {
		t.Error("expected error for missing credentials")
	}
}

func TestQuoteConnValue(t *testing.T) {
	cases := map[string]string{
		"plain":            "plain",
		"has,comma":        `"has,comma"`,
		"has:colon":        `"has:colon"`,
		`has"quote`:        `"has""quote"`,
		"http://host:9000": `"http://host:9000"`,
	}
	for in, want := range cases {
		if got := quoteConnValue(in); got != want {
			t.Errorf("quoteConnValue(%q) = %q, want %q", in, got, want)
		}
	}
}
