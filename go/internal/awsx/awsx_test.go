package awsx

import (
	"context"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestCheckCredentials(t *testing.T) {
	const identityXML = `<?xml version="1.0" encoding="UTF-8"?>
<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
  <GetCallerIdentityResult>
    <Arn>arn:aws:iam::123456789012:user/froster</Arn>
    <UserId>AIDAEXAMPLE</UserId>
    <Account>123456789012</Account>
  </GetCallerIdentityResult>
  <ResponseMetadata><RequestId>req-1</RequestId></ResponseMetadata>
</GetCallerIdentityResponse>`

	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		if req.Method == "POST" && strings.Contains(req.Header.Get("Content-Type"), "x-www-form-urlencoded") {
			return httpResponse(200, identityXML, nil)
		}
		return nil
	})

	id, err := client.CheckCredentials(context.Background())
	if err != nil {
		t.Fatalf("CheckCredentials: %v", err)
	}
	want := CallerIdentity{
		Account: "123456789012",
		Arn:     "arn:aws:iam::123456789012:user/froster",
		UserID:  "AIDAEXAMPLE",
	}
	if id != want {
		t.Errorf("CheckCredentials = %+v, want %+v", id, want)
	}
}

func TestListBuckets(t *testing.T) {
	const listXML = `<?xml version="1.0" encoding="UTF-8"?>
<ListAllMyBucketsResult>
  <Owner><ID>owner</ID></Owner>
  <Buckets>
    <Bucket><Name>froster-b1</Name><CreationDate>2026-01-01T00:00:00.000Z</CreationDate></Bucket>
    <Bucket><Name>other</Name><CreationDate>2026-01-01T00:00:00.000Z</CreationDate></Bucket>
  </Buckets>
</ListAllMyBucketsResult>`

	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		if req.Method == "GET" && req.URL.Path == "/" {
			return httpResponse(200, listXML, nil)
		}
		return nil
	})

	buckets, err := client.ListBuckets(context.Background())
	if err != nil {
		t.Fatalf("ListBuckets: %v", err)
	}
	if want := []string{"froster-b1", "other"}; !reflect.DeepEqual(buckets, want) {
		t.Errorf("ListBuckets = %v, want %v", buckets, want)
	}
}

func TestErrorWrappingIncludesProfile(t *testing.T) {
	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		return s3ErrorResponse(403, "AccessDenied", "Access Denied")
	})

	_, err := client.ListBuckets(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "(AWS profile: "+testProfile+")") {
		t.Errorf("error %q does not mention the AWS profile", err)
	}
	if !strings.Contains(err.Error(), "AccessDenied") {
		t.Errorf("error %q does not preserve the AWS error code", err)
	}
}

func TestBucketExists(t *testing.T) {
	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		if req.Method != "HEAD" {
			return nil
		}
		switch req.URL.Path {
		case "/present":
			return httpResponse(200, "", nil)
		case "/missing":
			return httpResponse(404, "", nil)
		}
		return nil
	})

	exists, err := client.BucketExists(context.Background(), "present")
	if err != nil || !exists {
		t.Errorf("BucketExists(present) = (%v, %v), want (true, nil)", exists, err)
	}
	exists, err = client.BucketExists(context.Background(), "missing")
	if err != nil || exists {
		t.Errorf("BucketExists(missing) = (%v, %v), want (false, nil)", exists, err)
	}
}

func TestCreateBucketRegionAware(t *testing.T) {
	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		switch {
		case req.Method == "PUT" && req.URL.Query().Has("encryption"):
			return httpResponse(200, "", nil)
		case req.Method == "PUT":
			return httpResponse(200, "", map[string]string{"Location": req.URL.Path})
		}
		return nil
	})

	// Non-default region: LocationConstraint required.
	if err := client.CreateBucket(context.Background(), "b-eu", "eu-west-1"); err != nil {
		t.Fatalf("CreateBucket(eu-west-1): %v", err)
	}
	createReq := mt.find("PUT", "/b-eu")
	if createReq == nil {
		t.Fatal("no CreateBucket request for b-eu")
	}
	if !strings.Contains(createReq.Body, "<LocationConstraint>eu-west-1</LocationConstraint>") {
		t.Errorf("CreateBucket body missing LocationConstraint: %q", createReq.Body)
	}

	// us-east-1 must NOT send a LocationConstraint (S3 rejects it).
	if err := client.CreateBucket(context.Background(), "b-use1", "us-east-1"); err != nil {
		t.Fatalf("CreateBucket(us-east-1): %v", err)
	}
	createReq = mt.find("PUT", "/b-use1")
	if createReq == nil {
		t.Fatal("no CreateBucket request for b-use1")
	}
	if strings.Contains(createReq.Body, "LocationConstraint") {
		t.Errorf("CreateBucket for us-east-1 must not send LocationConstraint: %q", createReq.Body)
	}

	// Provider AWS: default AES256 encryption is applied (Python parity).
	found := false
	for _, r := range mt.requests {
		if r.Method == "PUT" && strings.Contains(r.Query, "encryption") && r.Path == "/b-eu" {
			if !strings.Contains(r.Body, "AES256") {
				t.Errorf("PutBucketEncryption body missing AES256: %q", r.Body)
			}
			found = true
		}
	}
	if !found {
		t.Error("no PutBucketEncryption request for provider AWS")
	}
}

func TestCheckBucketAccess(t *testing.T) {
	aclXML := func(permission string) string {
		return `<?xml version="1.0" encoding="UTF-8"?>
<AccessControlPolicy>
  <Owner><ID>owner</ID></Owner>
  <AccessControlList>
    <Grant>
      <Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="CanonicalUser"><ID>owner</ID></Grantee>
      <Permission>` + permission + `</Permission>
    </Grant>
  </AccessControlList>
</AccessControlPolicy>`
	}

	client, _ := newTestClient(t, func(req *http.Request) *http.Response {
		if req.Method == "GET" && req.URL.Query().Has("acl") {
			switch req.URL.Path {
			case "/owned":
				return aclResponse(aclXML("FULL_CONTROL"))
			case "/readable":
				return aclResponse(aclXML("READ"))
			case "/forbidden":
				return s3ErrorResponse(403, "AccessDenied", "Access Denied")
			}
		}
		return nil
	})

	tests := []struct {
		bucket    string
		readwrite bool
		want      bool
		wantErr   bool
	}{
		{"owned", true, true, false},
		{"owned", false, false, false}, // FULL_CONTROL is not READ (Python parity)
		{"readable", false, true, false},
		{"readable", true, false, false},
		{"forbidden", false, false, true},
	}
	for _, tt := range tests {
		got, err := client.CheckBucketAccess(context.Background(), tt.bucket, tt.readwrite)
		if got != tt.want || (err != nil) != tt.wantErr {
			t.Errorf("CheckBucketAccess(%s, readwrite=%v) = (%v, %v), want (%v, err=%v)",
				tt.bucket, tt.readwrite, got, err, tt.want, tt.wantErr)
		}
	}
}

func aclResponse(xml string) *http.Response {
	return httpResponse(200, xml, nil)
}

func TestListObjectsPagination(t *testing.T) {
	page1 := `<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <Name>b</Name><Prefix>p/</Prefix>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>tok-1</NextContinuationToken>
  <Contents><Key>p/one</Key><Size>1</Size><StorageClass>STANDARD</StorageClass></Contents>
  <Contents><Key>p/two</Key><Size>2</Size><StorageClass>GLACIER</StorageClass></Contents>
</ListBucketResult>`
	page2 := `<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
  <Name>b</Name><Prefix>p/</Prefix>
  <IsTruncated>false</IsTruncated>
  <Contents><Key>p/three</Key><Size>3</Size><StorageClass>DEEP_ARCHIVE</StorageClass></Contents>
</ListBucketResult>`

	client, mt := newTestClient(t, func(req *http.Request) *http.Response {
		if req.Method == "GET" && req.URL.Path == "/b" {
			if req.URL.Query().Get("continuation-token") == "tok-1" {
				return httpResponse(200, page2, nil)
			}
			return httpResponse(200, page1, nil)
		}
		return nil
	})

	objects, err := client.ListObjects(context.Background(), "b", "p/")
	if err != nil {
		t.Fatalf("ListObjects: %v", err)
	}
	want := []Object{
		{Key: "p/one", Size: 1, StorageClass: "STANDARD"},
		{Key: "p/two", Size: 2, StorageClass: "GLACIER"},
		{Key: "p/three", Size: 3, StorageClass: "DEEP_ARCHIVE"},
	}
	if !reflect.DeepEqual(objects, want) {
		t.Errorf("ListObjects = %+v, want %+v", objects, want)
	}
	if n := mt.countRequests("GET", "/b"); n != 2 {
		t.Errorf("expected 2 list pages, got %d requests", n)
	}
	// Both requests must carry the prefix.
	for _, r := range mt.requests {
		if !strings.Contains(r.Query, "prefix=p") {
			t.Errorf("list request missing prefix: %q", r.Query)
		}
	}
}

func TestNewRequiresProfile(t *testing.T) {
	_, err := New(context.Background(), Options{})
	if err == nil || !strings.Contains(err.Error(), "profile") {
		t.Errorf("New without profile: err = %v, want profile error", err)
	}
}

func TestNewUnknownProfileMentionsProfile(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("AWS_SHARED_CREDENTIALS_FILE", filepath.Join(dir, "credentials"))
	t.Setenv("AWS_CONFIG_FILE", filepath.Join(dir, "config"))

	_, err := New(context.Background(), Options{Profile: "no-such-profile", Region: "us-west-2"})
	if err == nil {
		t.Fatal("expected error for unknown profile")
	}
	if !strings.Contains(err.Error(), "(AWS profile: no-such-profile)") {
		t.Errorf("error %q does not mention the AWS profile", err)
	}
}

func TestListProfiles(t *testing.T) {
	dir := t.TempDir()
	credsFile := filepath.Join(dir, "credentials")
	content := "[default]\naws_access_key_id = a\naws_secret_access_key = b\n\n" +
		"[minio-lab]\naws_access_key_id = c\naws_secret_access_key = d\n"
	if err := os.WriteFile(credsFile, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AWS_SHARED_CREDENTIALS_FILE", credsFile)

	profiles, err := ListProfiles()
	if err != nil {
		t.Fatalf("ListProfiles: %v", err)
	}
	if want := []string{"default", "minio-lab"}; !reflect.DeepEqual(profiles, want) {
		t.Errorf("ListProfiles = %v, want %v", profiles, want)
	}

	ok, err := ProfileExists("minio-lab")
	if err != nil || !ok {
		t.Errorf("ProfileExists(minio-lab) = (%v, %v), want (true, nil)", ok, err)
	}
	ok, err = ProfileExists("nope")
	if err != nil || ok {
		t.Errorf("ProfileExists(nope) = (%v, %v), want (false, nil)", ok, err)
	}

	// A missing credentials file is not an error.
	t.Setenv("AWS_SHARED_CREDENTIALS_FILE", filepath.Join(dir, "does-not-exist"))
	profiles, err = ListProfiles()
	if err != nil || profiles != nil {
		t.Errorf("ListProfiles(missing file) = (%v, %v), want (nil, nil)", profiles, err)
	}
}
