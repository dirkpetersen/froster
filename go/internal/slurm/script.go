package slurm

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

// SubmitOptions describes one froster batch job. CmdType, Label/ShortLabel,
// Cores, MemGB, Args and OutputDir are required; the rest is optional.
type SubmitOptions struct {
	// CmdType is the froster subcommand being wrapped ("index", "archive",
	// "delete", "restore"). It appears in the job name and output file.
	CmdType string
	// Label is the long label used in the output file name, derived from
	// the target folder (see LabelForFolder).
	Label string
	// ShortLabel is the short label used in the job name, usually the
	// basename of the target folder (see ShortLabelForFolder).
	ShortLabel string
	// JobName overrides the default job name
	// "froster:<CmdType>:<ShortLabel>" when non-empty.
	JobName string
	// Cores maps to --cpus-per-task (froster's global --cores flag).
	Cores int
	// MemGB is the requested memory in GiB (froster's global --mem flag);
	// it is emitted as --mem=<MemGB*1024> (megabytes), matching Python.
	MemGB int
	// Args are the froster CLI arguments (without the program name) to
	// re-run inside the job. --no-slurm is appended automatically unless
	// already present, so the job executes in the foreground.
	Args []string
	// OutputDir is the directory for job output files, normally
	// ~/.local/share/froster/slurm (ConfigManager.slurm_dir in Python).
	// It is created if missing.
	OutputDir string
	// Begin, if set, adds "#SBATCH --begin=<Begin>" to delay the job
	// start, e.g. "now+12hours" (used for scheduled Glacier-restore
	// retries) or an ISO timestamp.
	Begin string
	// Executable is the froster binary to re-invoke inside the job.
	// Defaults to os.Executable().
	Executable string
	// Debug keeps a copy of the submitted script as
	// submitted-<jobid>.sh in the current working directory, matching
	// Python's --debug behavior.
	Debug bool
	// Config carries the site Slurm configuration.
	Config Config
}

// jobName returns the --job-name value, Python:
// "froster:{cmd_type}:{shortlabel}".
func (o *SubmitOptions) jobName() string {
	if o.JobName != "" {
		return o.JobName
	}
	return fmt.Sprintf("froster:%s:%s", o.CmdType, o.ShortLabel)
}

// outputPattern returns the --output value, Python:
// "{slurm_dir}/froster-{cmd_type}@{label}-%J.out".
func (o *SubmitOptions) outputPattern() string {
	return filepath.Join(o.OutputDir, fmt.Sprintf("froster-%s@%s", o.CmdType, o.Label)) + "-%J.out"
}

// OutputFile returns the concrete job output file path for a submitted job
// ID, i.e. the --output pattern with %J resolved. Useful for "check output:
// tail -f <file>" hints after submission.
func (o *SubmitOptions) OutputFile(jobID string) string {
	return strings.ReplaceAll(o.outputPattern(), "%J", jobID)
}

// LabelForFolder derives the output-file label from the target folder path,
// matching Python Archiver._slurm_cmd: the hotspot file name for the folder
// (path with '/' replaced by '+') with spaces replaced by '_'.
func LabelForFolder(folder string) string {
	return strings.NewReplacer("/", "+", " ", "_").Replace(folder)
}

// ShortLabelForFolder derives the job-name label from the target folder
// path, matching Python (os.path.basename of the first folder).
func ShortLabelForFolder(folder string) string {
	return filepath.Base(folder)
}

// buildScript renders the batch script. cores and memMB are the (possibly
// partition-capped) resource values.
//
// The layout matches Python Slurm.sbatch() after _reorder_sbatch_lines():
// shebang first, then every #SBATCH directive in insertion order, then the
// payload lines, then the lscratch teardown command.
func buildScript(o *SubmitOptions, cores, memMB int) (string, error) {
	exe := o.Executable
	if exe == "" {
		var err error
		exe, err = os.Executable()
		if err != nil {
			return "", fmt.Errorf("slurm: resolving froster executable: %w", err)
		}
	}

	cfg := o.Config

	// #SBATCH directives, in the exact order Python adds them
	// (Slurm.__init__ adds the lscratch request; submit_job adds the rest).
	var directives []string
	add := func(format string, a ...any) {
		directives = append(directives, fmt.Sprintf(format, a...))
	}
	if cfg.Lscratch != "" {
		add("#SBATCH %s", cfg.Lscratch)
	}
	add("#SBATCH --job-name=%s", o.jobName())
	add("#SBATCH --cpus-per-task=%d", cores)
	add("#SBATCH --mem=%d", memMB)
	if o.Begin != "" {
		add("#SBATCH --begin=%s", o.Begin)
	}
	add("#SBATCH --requeue")
	add("#SBATCH --output=%s", o.outputPattern())
	add("#SBATCH --mail-type=FAIL,REQUEUE,END")
	if cfg.Email != "" {
		add("#SBATCH --mail-user=%s", cfg.Email)
	}
	add("#SBATCH --time=%s", cfg.walltime())
	if cfg.Partition != "" {
		add("#SBATCH --partition=%s", cfg.Partition)
	}
	if cfg.QOS != "" {
		add("#SBATCH --qos=%s", cfg.QOS)
	}

	// Payload: local-scratch setup, then froster re-invoking itself.
	var payload []string
	if cfg.LscratchMkdir != "" {
		payload = append(payload, cfg.LscratchMkdir)
	}
	if cfg.LscratchRoot != "" {
		payload = append(payload, fmt.Sprintf("export TMPDIR=%s/${SLURM_JOB_ID}", cfg.LscratchRoot))
	}

	args := o.Args
	if !slices.Contains(args, "--no-slurm") {
		args = append(slices.Clone(args), "--no-slurm")
	}
	cmd := make([]string, 0, len(args)+1)
	cmd = append(cmd, shellQuote(exe))
	for _, a := range args {
		cmd = append(cmd, shellQuote(a))
	}
	payload = append(payload, strings.Join(cmd, " "))

	var b strings.Builder
	b.WriteString("#!/bin/bash\n")
	for _, line := range directives {
		b.WriteString(line)
		b.WriteByte('\n')
	}
	for _, line := range payload {
		b.WriteString(line)
		b.WriteByte('\n')
	}
	if cfg.LscratchRmdir != "" {
		b.WriteString(cfg.LscratchRmdir)
		b.WriteByte('\n')
	}
	return b.String(), nil
}

// shellUnsafe matches any character outside shlex.quote's safe set
// ([\w@%+=:,./-]); a string containing one must be single-quoted.
var shellUnsafe = regexp.MustCompile(`[^\w@%+=:,./-]`)

// shellQuote quotes s for POSIX shell, matching Python's shlex.quote.
func shellQuote(s string) string {
	if s == "" {
		return "''"
	}
	if !shellUnsafe.MatchString(s) {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", `'"'"'`) + "'"
}
