package awsx

import (
	"context"
	"net/http"
	"reflect"
	"strings"
	"testing"
)

func TestParseRestoreHeader(t *testing.T) {
	tests := []struct {
		name        string
		header      string
		wantOngoing bool
		wantPresent bool
	}{
		{"ongoing", `ongoing-request="true"`, true, true},
		{"restored", `ongoing-request="false"`, false, true},
		{
			"restored with expiry",
			`ongoing-request="false", expiry-date="Fri, 21 Dec 2012 00:00:00 GMT"`,
			false, true,
		},
		{"empty", "", false, false},
		{"garbage", `expiry-date="Fri, 21 Dec 2012 00:00:00 GMT"`, false, false},
		{"unquoted value not matched", `ongoing-request=true`, false, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ongoing, present := parseRestoreHeader(tt.header)
			if ongoing != tt.wantOngoing || present != tt.wantPresent {
				t.Errorf("parseRestoreHeader(%q) = (%v, %v), want (%v, %v)",
					tt.header, ongoing, present, tt.wantOngoing, tt.wantPresent)
			}
		})
	}
}

func TestClassifyRestore(t *testing.T) {
	tests := []struct {
		class, restore string
		want           restoreState
	}{
		{"", "", stateStandard},
		// A restore header on a STANDARD object is still skipped
		// (Python checks the StorageClass key first).
		{"", `ongoing-request="true"`, stateStandard},
		{"GLACIER", `ongoing-request="true"`, stateInProgress},
		{"DEEP_ARCHIVE", `ongoing-request="false", expiry-date="x"`, stateRestored},
		// Restore header wins over the class check (Python order).
		{"GLACIER_IR", `ongoing-request="false"`, stateRestored},
		{"STANDARD_IA", "", stateNotGlacier},
		{"INTELLIGENT_TIERING", "", stateNotGlacier},
		{"GLACIER", "", stateCold},
		{"DEEP_ARCHIVE", "", stateCold},
	}
	for _, tt := range tests {
		if got := classifyRestore(tt.class, tt.restore); got != tt.want {
			t.Errorf("classifyRestore(%q, %q) = %v, want %v", tt.class, tt.restore, got, tt.want)
		}
	}
}

// glacierTestObjects is the ListObjectsV2 page used by the restore tests.
const glacierListXML = `<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <Name>b</Name><Prefix>arch/x/</Prefix><IsTruncated>false</IsTruncated>
  <Contents><Key>arch/x/cold1</Key><Size>10</Size><StorageClass>GLACIER</StorageClass></Contents>
  <Contents><Key>arch/x/retrieving</Key><Size>10</Size><StorageClass>GLACIER</StorageClass></Contents>
  <Contents><Key>arch/x/done</Key><Size>10</Size><StorageClass>DEEP_ARCHIVE</StorageClass></Contents>
  <Contents><Key>arch/x/warm</Key><Size>10</Size><StorageClass>STANDARD_IA</StorageClass></Contents>
  <Contents><Key>arch/x/Froster.allfiles.csv</Key><Size>10</Size><StorageClass>STANDARD_IA</StorageClass></Contents>
  <Contents><Key>arch/x/plain</Key><Size>10</Size><StorageClass>STANDARD</StorageClass></Contents>
  <Contents><Key>arch/x/sub/nested</Key><Size>10</Size><StorageClass>GLACIER</StorageClass></Contents>
  <Contents><Key>arch/x/racy</Key><Size>10</Size><StorageClass>GLACIER</StorageClass></Contents>
</ListBucketResult>`

// glacierHeadHandler answers HeadObject for the objects above. Note that,
// like real S3 (and boto3), STANDARD objects carry no x-amz-storage-class
// header.
func glacierHeadHandler(path string) *http.Response {
	head := func(class, restore string) *http.Response {
		h := map[string]string{"Content-Length": "10"}
		if class != "" {
			h["x-amz-storage-class"] = class
		}
		if restore != "" {
			h["x-amz-restore"] = restore
		}
		return httpResponse(200, "", h)
	}
	switch path {
	case "/b/arch/x/cold1":
		return head("GLACIER", "")
	case "/b/arch/x/retrieving":
		return head("GLACIER", `ongoing-request="true"`)
	case "/b/arch/x/done":
		return head("DEEP_ARCHIVE", `ongoing-request="false", expiry-date="Fri, 21 Dec 2029 00:00:00 GMT"`)
	case "/b/arch/x/warm":
		return head("STANDARD_IA", "")
	case "/b/arch/x/Froster.allfiles.csv":
		return head("STANDARD_IA", "")
	case "/b/arch/x/plain":
		return head("", "") // STANDARD: no storage class header
	case "/b/arch/x/racy":
		return head("GLACIER", "")
	}
	return nil
}

func TestTriggerGlacierRestore(t *testing.T) {
	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		switch {
		case req.Method == "GET" && req.URL.Path == "/b" &&
			req.URL.Query().Get("list-type") == "2":
			return httpResponse(200, glacierListXML, nil)
		case req.Method == "HEAD":
			return glacierHeadHandler(req.URL.Path)
		case req.Method == "POST" && req.URL.Query().Has("restore"):
			if req.URL.Path == "/b/arch/x/racy" {
				// Someone else triggered this restore first.
				return s3ErrorResponse(409, "RestoreAlreadyInProgress",
					"Object restore is already in progress")
			}
			return httpResponse(202, "", nil)
		}
		return nil
	})

	res, err := client.TriggerGlacierRestore(context.Background(), "b", "arch/x/", 30, TierBulk)
	if err != nil {
		t.Fatalf("TriggerGlacierRestore: %v", err)
	}

	if want := []string{"arch/x/cold1"}; !reflect.DeepEqual(res.Triggered, want) {
		t.Errorf("Triggered = %v, want %v", res.Triggered, want)
	}
	// racy raced into RestoreAlreadyInProgress and must be counted as
	// in-progress, not fail the whole sweep.
	if want := []string{"arch/x/retrieving", "arch/x/racy"}; !reflect.DeepEqual(res.InProgress, want) {
		t.Errorf("InProgress = %v, want %v", res.InProgress, want)
	}
	if want := []string{"arch/x/done"}; !reflect.DeepEqual(res.Restored, want) {
		t.Errorf("Restored = %v, want %v", res.Restored, want)
	}
	// Froster.allfiles.csv is excluded from NotGlacier (Python parity).
	if want := []string{"arch/x/warm"}; !reflect.DeepEqual(res.NotGlacier, want) {
		t.Errorf("NotGlacier = %v, want %v", res.NotGlacier, want)
	}
	if len(res.NotSupported) != 0 {
		t.Errorf("NotSupported = %v, want empty", res.NotSupported)
	}

	// The nested subfolder object must not even be HeadObject'ed.
	if r := mt.find("HEAD", "/b/arch/x/sub/nested"); r != nil {
		t.Error("HeadObject was called for a subfolder object")
	}

	// The restore request must carry Days and Tier.
	restoreReq := mt.find("POST", "/b/arch/x/cold1")
	if restoreReq == nil {
		t.Fatal("no RestoreObject request for arch/x/cold1")
	}
	if !strings.Contains(restoreReq.Body, "<Days>30</Days>") {
		t.Errorf("restore request body missing Days: %s", restoreReq.Body)
	}
	if !strings.Contains(restoreReq.Body, "<Tier>Bulk</Tier>") {
		t.Errorf("restore request body missing Tier: %s", restoreReq.Body)
	}
}

func TestTriggerGlacierRestoreExpeditedDeepArchive(t *testing.T) {
	listXML := `<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <Name>b</Name><Prefix>arch/x/</Prefix><IsTruncated>false</IsTruncated>
  <Contents><Key>arch/x/deep</Key><Size>10</Size><StorageClass>DEEP_ARCHIVE</StorageClass></Contents>
  <Contents><Key>arch/x/glac</Key><Size>10</Size><StorageClass>GLACIER</StorageClass></Contents>
</ListBucketResult>`

	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		switch {
		case req.Method == "GET" && req.URL.Path == "/b":
			return httpResponse(200, listXML, nil)
		case req.Method == "HEAD" && req.URL.Path == "/b/arch/x/deep":
			return httpResponse(200, "", map[string]string{"x-amz-storage-class": "DEEP_ARCHIVE"})
		case req.Method == "HEAD" && req.URL.Path == "/b/arch/x/glac":
			return httpResponse(200, "", map[string]string{"x-amz-storage-class": "GLACIER"})
		case req.Method == "POST" && req.URL.Query().Has("restore"):
			return httpResponse(202, "", nil)
		}
		return nil
	})

	res, err := client.TriggerGlacierRestore(context.Background(), "b", "arch/x/", 7, TierExpedited)
	if err != nil {
		t.Fatalf("TriggerGlacierRestore: %v", err)
	}
	// Expedited is not available for DEEP_ARCHIVE: refused, not triggered.
	if want := []string{"arch/x/deep"}; !reflect.DeepEqual(res.NotSupported, want) {
		t.Errorf("NotSupported = %v, want %v", res.NotSupported, want)
	}
	if want := []string{"arch/x/glac"}; !reflect.DeepEqual(res.Triggered, want) {
		t.Errorf("Triggered = %v, want %v", res.Triggered, want)
	}
	if mt.find("POST", "/b/arch/x/deep") != nil {
		t.Error("RestoreObject must not be called for DEEP_ARCHIVE with Expedited tier")
	}
	glacReq := mt.find("POST", "/b/arch/x/glac")
	if glacReq == nil {
		t.Fatal("no RestoreObject request for arch/x/glac")
	}
	if !strings.Contains(glacReq.Body, "<Tier>Expedited</Tier>") {
		t.Errorf("restore request body missing Expedited tier: %s", glacReq.Body)
	}
}

func TestRestoreStatus(t *testing.T) {
	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		switch {
		case req.Method == "GET" && req.URL.Path == "/b":
			return httpResponse(200, glacierListXML, nil)
		case req.Method == "HEAD":
			return glacierHeadHandler(req.URL.Path)
		}
		return nil
	})

	res, err := client.RestoreStatus(context.Background(), "b", "arch/x/")
	if err != nil {
		t.Fatalf("RestoreStatus: %v", err)
	}
	// Status-only sweep: cold objects are reported, never triggered.
	if want := []string{"arch/x/cold1", "arch/x/racy"}; !reflect.DeepEqual(res.NotTriggered, want) {
		t.Errorf("NotTriggered = %v, want %v", res.NotTriggered, want)
	}
	if want := []string{"arch/x/retrieving"}; !reflect.DeepEqual(res.InProgress, want) {
		t.Errorf("InProgress = %v, want %v", res.InProgress, want)
	}
	if want := []string{"arch/x/done"}; !reflect.DeepEqual(res.Restored, want) {
		t.Errorf("Restored = %v, want %v", res.Restored, want)
	}
	if want := []string{"arch/x/warm"}; !reflect.DeepEqual(res.NotGlacier, want) {
		t.Errorf("NotGlacier = %v, want %v", res.NotGlacier, want)
	}
}
