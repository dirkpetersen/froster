package awsx

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
)

const copyOKXML = `<?xml version="1.0" encoding="UTF-8"?>
<CopyObjectResult><LastModified>2026-01-01T00:00:00.000Z</LastModified><ETag>"etag"</ETag></CopyObjectResult>`

func TestChangeStorageClassRefusesGlacierSource(t *testing.T) {
	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		return nil // no request may ever be made
	})

	for _, current := range []string{"GLACIER", "DEEP_ARCHIVE"} {
		_, err := client.ChangeStorageClass(context.Background(), "b", "arch/y/", "STANDARD_IA", current)
		if !errors.Is(err, ErrGlacierSource) {
			t.Errorf("currentClass=%s: err = %v, want ErrGlacierSource", current, err)
		}
	}
	if len(mt.requests) != 0 {
		t.Errorf("expected no AWS requests, got %d", len(mt.requests))
	}
}

func TestChangeStorageClass(t *testing.T) {
	listXML := `<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <Name>b</Name><Prefix>arch/y/</Prefix><IsTruncated>false</IsTruncated>
  <Contents><Key>arch/y/a</Key><Size>100</Size><StorageClass>INTELLIGENT_TIERING</StorageClass></Contents>
  <Contents><Key>arch/y/.froster.md5sum</Key><Size>10</Size><StorageClass>STANDARD</StorageClass></Contents>
  <Contents><Key>arch/y/already</Key><Size>50</Size><StorageClass>STANDARD_IA</StorageClass></Contents>
  <Contents><Key>arch/y/frozen</Key><Size>200</Size><StorageClass>GLACIER</StorageClass></Contents>
  <Contents><Key>arch/y/thawed</Key><Size>300</Size><StorageClass>DEEP_ARCHIVE</StorageClass></Contents>
  <Contents><Key>arch/y/flaky</Key><Size>30</Size><StorageClass>INTELLIGENT_TIERING</StorageClass></Contents>
</ListBucketResult>`

	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		switch {
		case req.Method == "GET" && req.URL.Path == "/b":
			return httpResponse(200, listXML, nil)
		case req.Method == "HEAD" && req.URL.Path == "/b/arch/y/frozen":
			// Cold, never restored: must be refused, not copied.
			return httpResponse(200, "", map[string]string{"x-amz-storage-class": "GLACIER"})
		case req.Method == "HEAD" && req.URL.Path == "/b/arch/y/thawed":
			// Restored copy available: re-tiering is allowed.
			return httpResponse(200, "", map[string]string{
				"x-amz-storage-class": "DEEP_ARCHIVE",
				"x-amz-restore":       `ongoing-request="false", expiry-date="Fri, 21 Dec 2029 00:00:00 GMT"`,
			})
		case req.Method == "PUT" && req.Header.Get("x-amz-copy-source") != "":
			if req.URL.Path == "/b/arch/y/flaky" {
				return s3ErrorResponse(400, "InvalidRequest", "copy failed")
			}
			return httpResponse(200, copyOKXML, nil)
		}
		return nil
	})

	res, err := client.ChangeStorageClass(context.Background(), "b", "arch/y/", "STANDARD_IA", "INTELLIGENT_TIERING")
	if err != nil {
		t.Fatalf("ChangeStorageClass: %v", err)
	}

	// a + thawed copied; md5sum (metadata), already (target class),
	// frozen (cold glacier), flaky (copy error) skipped.
	if res.TotalObjects != 6 {
		t.Errorf("TotalObjects = %d, want 6", res.TotalObjects)
	}
	if res.ChangedObjects != 2 {
		t.Errorf("ChangedObjects = %d, want 2", res.ChangedObjects)
	}
	if res.SkippedObjects != 4 {
		t.Errorf("SkippedObjects = %d, want 4", res.SkippedObjects)
	}
	if want := int64(100 + 10 + 50 + 200 + 300 + 30); res.TotalSizeBytes != want {
		t.Errorf("TotalSizeBytes = %d, want %d", res.TotalSizeBytes, want)
	}

	// Copy of arch/y/a must carry the tier-change headers.
	copyReq := mt.find("PUT", "/b/arch/y/a")
	if copyReq == nil {
		t.Fatal("no CopyObject request for arch/y/a")
	}
	if got := copyReq.Header.Get("x-amz-storage-class"); got != "STANDARD_IA" {
		t.Errorf("x-amz-storage-class = %q, want STANDARD_IA", got)
	}
	if got := copyReq.Header.Get("x-amz-metadata-directive"); got != "COPY" {
		t.Errorf("x-amz-metadata-directive = %q, want COPY", got)
	}
	if src := copyReq.Header.Get("x-amz-copy-source"); !strings.Contains(src, "b/arch/y/a") {
		t.Errorf("x-amz-copy-source = %q, want it to reference b/arch/y/a", src)
	}

	// Refused/skipped objects must never be copied.
	for _, path := range []string{"/b/arch/y/frozen", "/b/arch/y/already", "/b/arch/y/.froster.md5sum"} {
		if mt.find("PUT", path) != nil {
			t.Errorf("CopyObject must not be called for %s", path)
		}
	}
	// Restored glacier object was copied.
	if mt.find("PUT", "/b/arch/y/thawed") == nil {
		t.Error("CopyObject expected for restored object arch/y/thawed")
	}
	// Objects outside glacier tiers must not be HeadObject'ed.
	if mt.find("HEAD", "/b/arch/y/a") != nil {
		t.Error("HeadObject must not be called for non-glacier objects")
	}
}
