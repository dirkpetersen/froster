package slurm

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeShim installs an executable fake command into dir.
func writeShim(t *testing.T, dir, name, content string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, name), []byte(content), 0o755); err != nil {
		t.Fatal(err)
	}
}

// shimDir creates a directory prepended to PATH for fake Slurm binaries.
func shimDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
	return dir
}

// installFakeSbatch installs an sbatch shim that captures the submitted
// script (read from stdin, as froster pipes it) and prints a job ID.
func installFakeSbatch(t *testing.T, dir string) (captureFile string) {
	t.Helper()
	captureFile = filepath.Join(dir, "captured-script.sh")
	writeShim(t, dir, "sbatch", fmt.Sprintf("#!/bin/sh\ncat > %q\necho 'Submitted batch job 12345'\n", captureFile))
	return captureFile
}

func TestInstalled(t *testing.T) {
	empty := t.TempDir()
	t.Setenv("PATH", empty)
	if Installed() {
		t.Error("Installed() = true with empty PATH")
	}
	writeShim(t, empty, "sbatch", "#!/bin/sh\n")
	if !Installed() {
		t.Error("Installed() = false with sbatch on PATH")
	}
}

func TestInsideJob(t *testing.T) {
	t.Setenv("SLURM_JOB_ID", "")
	if InsideJob() {
		t.Error("InsideJob() = true without SLURM_JOB_ID")
	}
	t.Setenv("SLURM_JOB_ID", "4242")
	if !InsideJob() {
		t.Error("InsideJob() = false with SLURM_JOB_ID set")
	}
}

func TestShouldUse(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("PATH", dir)
	t.Setenv("SLURM_JOB_ID", "")

	// No sbatch installed: never use Slurm.
	if ShouldUse(false) {
		t.Error("ShouldUse(false) = true without sbatch")
	}

	writeShim(t, dir, "sbatch", "#!/bin/sh\n")
	if !ShouldUse(false) {
		t.Error("ShouldUse(false) = false with sbatch installed")
	}
	if ShouldUse(true) {
		t.Error("ShouldUse(true) = true despite --no-slurm")
	}

	// Inside a Slurm job: never re-submit.
	t.Setenv("SLURM_JOB_ID", "4242")
	if ShouldUse(false) {
		t.Error("ShouldUse(false) = true inside a Slurm job")
	}
}

// fullOptions returns SubmitOptions exercising every directive.
func fullOptions(t *testing.T) SubmitOptions {
	t.Helper()
	folder := "/home/user/proj 1"
	return SubmitOptions{
		CmdType:    "archive",
		Label:      LabelForFolder(folder),
		ShortLabel: ShortLabelForFolder(folder),
		Cores:      4,
		MemGB:      64,
		Args:       []string{"archive", folder},
		OutputDir:  filepath.Join(t.TempDir(), "froster", "slurm"),
		Executable: "/opt/froster/bin/froster",
		Config: Config{
			Partition:     "batch",
			QOS:           "normal",
			WalltimeDays:  7,
			WalltimeHours: 0,
			Lscratch:      "--gres tmp:1024",
			LscratchMkdir: "mkdir-scratch.sh",
			LscratchRmdir: "rmdir-scratch.sh",
			LscratchRoot:  "/mnt/scratch",
			Email:         "user@example.com",
		},
	}
}

func TestSubmit(t *testing.T) {
	dir := shimDir(t)
	captureFile := installFakeSbatch(t, dir)
	// Fake sinfo so the partition-capping path is deterministic (caps are
	// well above the requested 4 cores / 64 GiB).
	writeShim(t, dir, "sinfo", `#!/bin/sh
case "$*" in
  *%m*) printf 'MEMORY\n256000\n128000\n' ;;
  *)    printf 'HOSTNAMES CPUS\nnode1 64\nnode2 64\n' ;;
esac
`)

	opts := fullOptions(t)
	jobID, err := Submit(context.Background(), opts)
	if err != nil {
		t.Fatalf("Submit: %v", err)
	}
	if jobID != "12345" {
		t.Errorf("jobID = %q, want %q", jobID, "12345")
	}

	if _, err := os.Stat(opts.OutputDir); err != nil {
		t.Errorf("output dir not created: %v", err)
	}

	raw, err := os.ReadFile(captureFile)
	if err != nil {
		t.Fatalf("sbatch shim did not capture a script: %v", err)
	}
	script := string(raw)
	lines := strings.Split(strings.TrimRight(script, "\n"), "\n")

	if lines[0] != "#!/bin/bash" {
		t.Errorf("shebang = %q, want #!/bin/bash", lines[0])
	}

	// All #SBATCH directives must directly follow the shebang (Python
	// reorders them to the top).
	seenPayload := false
	for _, line := range lines[1:] {
		if strings.HasPrefix(line, "#SBATCH") {
			if seenPayload {
				t.Errorf("#SBATCH line after payload: %q", line)
			}
		} else {
			seenPayload = true
		}
	}

	wantDirectives := []string{
		"#SBATCH --gres tmp:1024",
		"#SBATCH --job-name=froster:archive:proj 1",
		"#SBATCH --cpus-per-task=4",
		"#SBATCH --mem=65536",
		"#SBATCH --requeue",
		"#SBATCH --output=" + filepath.Join(opts.OutputDir, "froster-archive@+home+user+proj_1") + "-%J.out",
		"#SBATCH --mail-type=FAIL,REQUEUE,END",
		"#SBATCH --mail-user=user@example.com",
		"#SBATCH --time=7-0",
		"#SBATCH --partition=batch",
		"#SBATCH --qos=normal",
	}
	for _, want := range wantDirectives {
		if !strings.Contains(script, want+"\n") {
			t.Errorf("script missing directive %q\nscript:\n%s", want, script)
		}
	}

	// Payload order: scratch setup, TMPDIR export, verbatim self-reexec,
	// scratch teardown last.
	wantPayload := []string{
		"mkdir-scratch.sh",
		"export TMPDIR=/mnt/scratch/${SLURM_JOB_ID}",
		"/opt/froster/bin/froster archive '/home/user/proj 1'",
		"rmdir-scratch.sh",
	}
	payload := lines[len(lines)-len(wantPayload):]
	for i, want := range wantPayload {
		if payload[i] != want {
			t.Errorf("payload[%d] = %q, want %q", i, payload[i], want)
		}
	}
	if lines[len(lines)-1] != "rmdir-scratch.sh" {
		t.Errorf("last line = %q, want lscratch teardown", lines[len(lines)-1])
	}
}

func TestSubmitMinimalConfig(t *testing.T) {
	dir := shimDir(t)
	captureFile := installFakeSbatch(t, dir)

	opts := SubmitOptions{
		CmdType:    "index",
		Label:      LabelForFolder("/data/set1"),
		ShortLabel: "set1",
		Cores:      8,
		MemGB:      64,
		Args:       []string{"index", "/data/set1"},
		OutputDir:  t.TempDir(),
		Executable: "/usr/bin/froster",
	}
	if _, err := Submit(context.Background(), opts); err != nil {
		t.Fatalf("Submit: %v", err)
	}
	script := string(mustRead(t, captureFile))

	// Unconfigured optional directives must be omitted entirely (Python
	// would emit literal "None" values here; we deliberately do not).
	for _, banned := range []string{"--partition", "--qos", "--mail-user", "--begin", "--gres", "None"} {
		if strings.Contains(script, banned) {
			t.Errorf("script contains %q despite empty config\nscript:\n%s", banned, script)
		}
	}
	// Defaults still apply.
	for _, want := range []string{
		"#SBATCH --time=7-0",
		"#SBATCH --mem=65536",
		"#SBATCH --job-name=froster:index:set1",
		"/usr/bin/froster index /data/set1",
	} {
		if !strings.Contains(script, want+"\n") {
			t.Errorf("script missing %q\nscript:\n%s", want, script)
		}
	}
}

func TestSubmitBegin(t *testing.T) {
	dir := shimDir(t)
	captureFile := installFakeSbatch(t, dir)

	opts := fullOptions(t)
	opts.CmdType = "restore"
	opts.Begin = "now+12hours"
	opts.Config.Partition = "" // skip sinfo capping path
	if _, err := Submit(context.Background(), opts); err != nil {
		t.Fatalf("Submit: %v", err)
	}
	script := string(mustRead(t, captureFile))
	if !strings.Contains(script, "#SBATCH --begin=now+12hours\n") {
		t.Errorf("script missing --begin directive:\n%s", script)
	}
}

func TestSubmitArgsReplayedVerbatim(t *testing.T) {
	dir := shimDir(t)
	captureFile := installFakeSbatch(t, dir)

	opts := fullOptions(t)
	opts.Config.Partition = ""
	opts.Args = []string{"--no-slurm", "archive", "/data/x"}
	if _, err := Submit(context.Background(), opts); err != nil {
		t.Fatalf("Submit: %v", err)
	}
	script := string(mustRead(t, captureFile))
	// Args are replayed verbatim: an explicit --no-slurm stays exactly
	// where the caller put it (before the subcommand) and is not
	// duplicated or moved.
	if !strings.Contains(script, "froster --no-slurm archive /data/x\n") {
		t.Errorf("verbatim replay missing\nscript:\n%s", script)
	}
	if got := strings.Count(script, "--no-slurm"); got != 1 {
		t.Errorf("--no-slurm appears %d times, want 1\nscript:\n%s", got, script)
	}
}

func TestSubmitResourceCapping(t *testing.T) {
	dir := shimDir(t)
	captureFile := installFakeSbatch(t, dir)
	writeShim(t, dir, "sinfo", `#!/bin/sh
case "$*" in
  *%m*) printf 'MEMORY\n256000\n128000\n' ;;
  *)    printf 'HOSTNAMES CPUS\nnode1 64\nnode2 64\n' ;;
esac
`)

	opts := fullOptions(t)
	opts.Cores = 999  // > 128 total CPUs in partition
	opts.MemGB = 1000 // 1024000 MB > 128000 MB smallest node
	if _, err := Submit(context.Background(), opts); err != nil {
		t.Fatalf("Submit: %v", err)
	}
	script := string(mustRead(t, captureFile))
	if !strings.Contains(script, "#SBATCH --cpus-per-task=128\n") {
		t.Errorf("cores not capped to partition total:\n%s", script)
	}
	if !strings.Contains(script, "#SBATCH --mem=128000\n") {
		t.Errorf("memory not capped to smallest node:\n%s", script)
	}
}

func TestSubmitSbatchFailure(t *testing.T) {
	dir := shimDir(t)
	writeShim(t, dir, "sbatch", "#!/bin/sh\necho 'sbatch: error: Batch job submission failed' >&2\nexit 1\n")

	opts := fullOptions(t)
	opts.Config.Partition = ""
	_, err := Submit(context.Background(), opts)
	if err == nil || !strings.Contains(err.Error(), "Batch job submission failed") {
		t.Errorf("err = %v, want sbatch stderr included", err)
	}
}

func TestSubmitInvalidGenericResource(t *testing.T) {
	dir := shimDir(t)
	writeShim(t, dir, "sbatch", "#!/bin/sh\necho 'sbatch: error: Invalid generic resource (gres) specification' >&2\nexit 1\n")

	opts := fullOptions(t)
	opts.Config.Partition = ""
	_, err := Submit(context.Background(), opts)
	if err == nil || !strings.Contains(err.Error(), "slurm_lscratch") {
		t.Errorf("err = %v, want slurm_lscratch hint", err)
	}
}

func TestSubmitDebugKeepsScript(t *testing.T) {
	dir := shimDir(t)
	installFakeSbatch(t, dir)
	t.Chdir(t.TempDir())

	opts := fullOptions(t)
	opts.Config.Partition = ""
	opts.Debug = true
	if _, err := Submit(context.Background(), opts); err != nil {
		t.Fatalf("Submit: %v", err)
	}
	if _, err := os.Stat("submitted-12345.sh"); err != nil {
		t.Errorf("debug script copy missing: %v", err)
	}
}

func TestParseJobID(t *testing.T) {
	tests := []struct {
		out     string
		want    string
		wantErr bool
	}{
		{"Submitted batch job 12345\n", "12345", false},
		{"Submitted batch job 987654321 \n", "987654321", false},
		{"", "", true},
		{"sbatch: something went wrong\n", "", true},
	}
	for _, tt := range tests {
		got, err := parseJobID(tt.out)
		if (err != nil) != tt.wantErr {
			t.Errorf("parseJobID(%q) err = %v, wantErr %v", tt.out, err, tt.wantErr)
			continue
		}
		if got != tt.want {
			t.Errorf("parseJobID(%q) = %q, want %q", tt.out, got, tt.want)
		}
	}
}

func TestLabelForFolder(t *testing.T) {
	if got := LabelForFolder("/home/user/my proj"); got != "+home+user+my_proj" {
		t.Errorf("LabelForFolder = %q, want +home+user+my_proj", got)
	}
	if got := ShortLabelForFolder("/home/user/my proj"); got != "my proj" {
		t.Errorf("ShortLabelForFolder = %q, want %q", got, "my proj")
	}
}

func TestOutputFile(t *testing.T) {
	opts := SubmitOptions{CmdType: "archive", Label: "+data+x", OutputDir: "/home/u/.local/share/froster/slurm"}
	want := "/home/u/.local/share/froster/slurm/froster-archive@+data+x-777.out"
	if got := opts.OutputFile("777"); got != want {
		t.Errorf("OutputFile = %q, want %q", got, want)
	}
}

func TestShellQuote(t *testing.T) {
	tests := []struct{ in, want string }{
		{"simple", "simple"},
		{"/path/to/file.txt", "/path/to/file.txt"},
		{"--no-slurm", "--no-slurm"},
		{"has space", "'has space'"},
		{"", "''"},
		{"it's", `'it'"'"'s'`},
		{"a;b", "'a;b'"},
	}
	for _, tt := range tests {
		if got := shellQuote(tt.in); got != tt.want {
			t.Errorf("shellQuote(%q) = %q, want %q", tt.in, got, tt.want)
		}
	}
}

func TestSqueue(t *testing.T) {
	dir := shimDir(t)
	writeShim(t, dir, "squeue", `#!/bin/sh
printf '%s\n' '"JOBID","NAME","ST","TIME","TIME_LEFT","NODES","CPUS","MIN_MEMORY","TRES_PER_NODE","NODELIST(REASON)"'
printf '%s\n' '"101","froster:archive:proj1","R","1:23","6-22:36:37","1","4","64G","N/A","node001"'
printf '%s\n' '"102","froster:restore:proj2","PD","0:00","7-00:00:00","1","4","64G","N/A","(Priority)"'
`)
	jobs, err := Squeue(context.Background())
	if err != nil {
		t.Fatalf("Squeue: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("len(jobs) = %d, want 2", len(jobs))
	}
	want := Job{
		ID: "101", Name: "froster:archive:proj1", State: "R", TimeUsed: "1:23",
		TimeLeft: "6-22:36:37", Nodes: "1", CPUs: "4", MinMemory: "64G",
		TRESPerNode: "N/A", Reason: "node001",
	}
	if jobs[0] != want {
		t.Errorf("jobs[0] = %+v, want %+v", jobs[0], want)
	}
	if jobs[1].ID != "102" || jobs[1].State != "PD" || jobs[1].Reason != "(Priority)" {
		t.Errorf("jobs[1] = %+v", jobs[1])
	}
}

func TestSqueueNoJobs(t *testing.T) {
	dir := shimDir(t)
	writeShim(t, dir, "squeue", `#!/bin/sh
printf '%s\n' '"JOBID","NAME","ST","TIME","TIME_LEFT","NODES","CPUS","MIN_MEMORY","TRES_PER_NODE","NODELIST(REASON)"'
`)
	jobs, err := Squeue(context.Background())
	if err != nil {
		t.Fatalf("Squeue: %v", err)
	}
	if len(jobs) != 0 {
		t.Errorf("len(jobs) = %d, want 0", len(jobs))
	}
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return b
}
