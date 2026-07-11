package awsx

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

// mockTransport implements aws.HTTPClient and routes every request to a
// test-provided handler. No network I/O ever happens.
type mockTransport struct {
	t *testing.T
	// handler returns the canned response for a request. Returning nil
	// fails the test (unexpected request).
	handler func(req *http.Request) *http.Response
	// requests records every request seen, with the body already read,
	// so tests can assert on wire-level details.
	requests []capturedRequest
}

type capturedRequest struct {
	Method string
	Path   string
	Query  string
	Header http.Header
	Body   string
}

func (m *mockTransport) Do(req *http.Request) (*http.Response, error) {
	var body []byte
	if req.Body != nil {
		var err error
		body, err = io.ReadAll(req.Body)
		if err != nil {
			m.t.Fatalf("reading request body: %v", err)
		}
		req.Body.Close()
	}
	m.requests = append(m.requests, capturedRequest{
		Method: req.Method,
		Path:   req.URL.Path,
		Query:  req.URL.RawQuery,
		Header: req.Header.Clone(),
		Body:   string(body),
	})

	resp := m.handler(req)
	if resp == nil {
		m.t.Fatalf("unexpected request: %s %s?%s", req.Method, req.URL.Path, req.URL.RawQuery)
	}
	resp.Request = req
	return resp, nil
}

// find returns the first captured request matching method and path, or nil.
func (m *mockTransport) find(method, path string) *capturedRequest {
	for i := range m.requests {
		if m.requests[i].Method == method && m.requests[i].Path == path {
			return &m.requests[i]
		}
	}
	return nil
}

// countRequests returns how many captured requests match method and path.
func (m *mockTransport) countRequests(method, path string) int {
	n := 0
	for _, r := range m.requests {
		if r.Method == method && r.Path == path {
			n++
		}
	}
	return n
}

// httpResponse builds a canned *http.Response with optional headers.
func httpResponse(status int, body string, headers map[string]string) *http.Response {
	h := http.Header{}
	h.Set("Content-Type", "application/xml")
	for k, v := range headers {
		h.Set(k, v)
	}
	return &http.Response{
		StatusCode: status,
		Header:     h,
		Body:       io.NopCloser(bytes.NewReader([]byte(body))),
	}
}

// s3ErrorResponse builds an S3-style XML error response.
func s3ErrorResponse(status int, code, message string) *http.Response {
	body := `<?xml version="1.0" encoding="UTF-8"?>
<Error><Code>` + code + `</Code><Message>` + message + `</Message><RequestId>req-1</RequestId></Error>`
	return httpResponse(status, body, nil)
}

const testProfile = "froster-test-profile"

// newTestClient builds a Client whose HTTP layer is fully mocked. It also
// isolates credential resolution: a temporary shared-credentials file
// provides the profile, and env vars stop the SDK from touching ~/.aws,
// IMDS, or SSO.
func newTestClient(t *testing.T, handler func(req *http.Request) *http.Response) (*Client, *mockTransport) {
	t.Helper()

	dir := t.TempDir()
	credsFile := filepath.Join(dir, "credentials")
	creds := "[" + testProfile + "]\n" +
		"aws_access_key_id = AKIAMOCKMOCKMOCKMOCK\n" +
		"aws_secret_access_key = mock-secret-key\n"
	if err := os.WriteFile(credsFile, []byte(creds), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AWS_SHARED_CREDENTIALS_FILE", credsFile)
	t.Setenv("AWS_CONFIG_FILE", filepath.Join(dir, "config-does-not-exist"))
	t.Setenv("AWS_EC2_METADATA_DISABLED", "true")

	mt := &mockTransport{t: t, handler: handler}
	client, err := New(context.Background(), Options{
		Profile:  testProfile,
		Region:   "us-west-2",
		Provider: "AWS",
		// A custom endpoint enables path-style addressing, which keeps
		// request paths predictable (/bucket/key) for the mock router.
		Endpoint:   "https://s3.mock.local",
		HTTPClient: mt,
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return client, mt
}
