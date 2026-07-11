package awsx

import (
	"context"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// Integration test against a local Minio container. It exercises the
// plain S3 control-plane operations (buckets, object listing) end to end.
// Glacier restore and storage-class changes are NOT tested here — Minio
// does not implement RestoreObject or AWS storage classes; those paths are
// covered by the mocked-HTTP unit tests.
//
// The test is skipped when docker is unavailable or the container cannot
// be started (e.g. no network to pull the image, port already in use).

const (
	minioContainer = "froster-go-awsx-minio"
	minioPort      = "9301"
	minioEndpoint  = "http://127.0.0.1:" + minioPort
	minioUser      = "froster-minio-admin"
	minioPassword  = "froster-minio-secret"
)

func startMinio(t *testing.T) {
	t.Helper()

	if testing.Short() {
		t.Skip("skipping Minio integration test in -short mode")
	}
	if _, err := exec.LookPath("docker"); err != nil {
		t.Skip("docker not available; skipping Minio integration test")
	}
	if err := exec.Command("docker", "info").Run(); err != nil {
		t.Skip("docker daemon not reachable; skipping Minio integration test")
	}

	// Remove any leftover container from a previous run.
	exec.Command("docker", "rm", "-f", minioContainer).Run()

	out, err := exec.Command("docker", "run", "-d", "--name", minioContainer,
		"-p", minioPort+":9000",
		"-e", "MINIO_ROOT_USER="+minioUser,
		"-e", "MINIO_ROOT_PASSWORD="+minioPassword,
		"minio/minio", "server", "/data").CombinedOutput()
	if err != nil {
		t.Skipf("cannot start Minio container: %v (%s)", err, out)
	}
	t.Cleanup(func() {
		exec.Command("docker", "rm", "-f", minioContainer).Run()
	})

	// Wait for Minio to answer its health endpoint.
	deadline := time.Now().Add(60 * time.Second)
	for {
		resp, err := http.Get(minioEndpoint + "/minio/health/live")
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				return
			}
		}
		if time.Now().After(deadline) {
			t.Skipf("Minio did not become healthy in time (last error: %v)", err)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func newMinioClient(t *testing.T) *Client {
	t.Helper()

	dir := t.TempDir()
	credsFile := filepath.Join(dir, "credentials")
	creds := "[froster-minio-test]\n" +
		"aws_access_key_id = " + minioUser + "\n" +
		"aws_secret_access_key = " + minioPassword + "\n"
	if err := os.WriteFile(credsFile, []byte(creds), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("AWS_SHARED_CREDENTIALS_FILE", credsFile)
	t.Setenv("AWS_CONFIG_FILE", filepath.Join(dir, "config-does-not-exist"))
	t.Setenv("AWS_EC2_METADATA_DISABLED", "true")

	client, err := New(context.Background(), Options{
		Profile:  "froster-minio-test",
		Region:   "us-east-1",
		Endpoint: minioEndpoint,
		Provider: "Minio",
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return client
}

func TestMinioIntegration(t *testing.T) {
	startMinio(t)
	client := newMinioClient(t)
	ctx := context.Background()

	const bucket = "froster-go-awsx-test"

	// Bucket does not exist yet.
	exists, err := client.BucketExists(ctx, bucket)
	if err != nil {
		t.Fatalf("BucketExists: %v", err)
	}
	if exists {
		t.Fatalf("bucket %s unexpectedly exists", bucket)
	}

	// Create it (us-east-1: no LocationConstraint on the wire).
	if err := client.CreateBucket(ctx, bucket, "us-east-1"); err != nil {
		t.Fatalf("CreateBucket: %v", err)
	}

	exists, err = client.BucketExists(ctx, bucket)
	if err != nil || !exists {
		t.Fatalf("BucketExists after create = (%v, %v), want (true, nil)", exists, err)
	}

	buckets, err := client.ListBuckets(ctx)
	if err != nil {
		t.Fatalf("ListBuckets: %v", err)
	}
	found := false
	for _, b := range buckets {
		if b == bucket {
			found = true
		}
	}
	if !found {
		t.Fatalf("ListBuckets = %v, missing %s", buckets, bucket)
	}

	// Put a few objects directly (data plane is rclone's job in froster;
	// this only feeds the listing test).
	for _, key := range []string{"arch/p/one.dat", "arch/p/two.dat", "arch/q/other.dat"} {
		_, err := client.s3.PutObject(ctx, &s3.PutObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(key),
			Body:   strings.NewReader("froster test payload"),
		})
		if err != nil {
			t.Fatalf("PutObject(%s): %v", key, err)
		}
	}

	objects, err := client.ListObjects(ctx, bucket, "arch/p/")
	if err != nil {
		t.Fatalf("ListObjects: %v", err)
	}
	if len(objects) != 2 {
		t.Fatalf("ListObjects(arch/p/) returned %d objects, want 2: %+v", len(objects), objects)
	}
	for _, obj := range objects {
		if !strings.HasPrefix(obj.Key, "arch/p/") {
			t.Errorf("object %q outside requested prefix", obj.Key)
		}
		if obj.Size != int64(len("froster test payload")) {
			t.Errorf("object %q size = %d, want %d", obj.Key, obj.Size, len("froster test payload"))
		}
	}

	// All objects with an empty prefix.
	objects, err = client.ListObjects(ctx, bucket, "")
	if err != nil {
		t.Fatalf("ListObjects(all): %v", err)
	}
	if len(objects) != 3 {
		t.Fatalf("ListObjects(all) returned %d objects, want 3", len(objects))
	}
}
