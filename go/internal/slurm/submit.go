package slurm

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
)

// Submit generates the batch script for opts, submits it with sbatch (via
// stdin, as Python does) and returns the parsed job ID.
//
// When a partition is configured, the requested cores and memory are capped
// to the partition's total CPUs and the cluster's smallest per-node memory,
// queried best-effort via sinfo (Python does the same; if sinfo fails the
// requested values are kept unchanged).
//
// With opts.Debug set, a copy of the submitted script is written to
// submitted-<jobid>.sh in the current working directory, matching Python's
// --debug behavior.
func Submit(ctx context.Context, opts SubmitOptions) (jobID string, err error) {
	if opts.CmdType == "" {
		return "", errors.New("slurm: SubmitOptions.CmdType is required")
	}
	if opts.OutputDir == "" {
		return "", errors.New("slurm: SubmitOptions.OutputDir is required")
	}
	if len(opts.Args) == 0 {
		return "", errors.New("slurm: SubmitOptions.Args is required")
	}

	// Python creates cfg.slurm_dir with mode 0o775 in Slurm.__init__.
	if err := os.MkdirAll(opts.OutputDir, 0o775); err != nil {
		return "", fmt.Errorf("slurm: creating output dir: %w", err)
	}

	cores, memMB := opts.Cores, opts.MemGB*1024
	if opts.Config.Partition != "" {
		if total, err := partitionTotalCPUs(ctx, opts.Config.Partition); err == nil && cores > total {
			cores = total
		}
		if maxMB, err := maxMemoryPerNodeMB(ctx); err == nil && memMB > maxMB {
			memMB = maxMB
		}
	}

	script, err := buildScript(&opts, cores, memMB)
	if err != nil {
		return "", err
	}

	cmd := exec.CommandContext(ctx, "sbatch")
	cmd.Stdin = strings.NewReader(script)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if strings.Contains(msg, "Invalid generic resource") {
			// Same hint Python prints for this sbatch failure.
			return "", fmt.Errorf("slurm: invalid generic resource request; please change configuration of slurm_lscratch: %s", msg)
		}
		if msg == "" {
			return "", fmt.Errorf("slurm: running sbatch: %w", err)
		}
		return "", fmt.Errorf("slurm: running sbatch: %s", msg)
	}

	jobID, err = parseJobID(stdout.String())
	if err != nil {
		return "", err
	}

	if opts.Debug {
		// Best effort, like Python's debug copy (submitted-<jobid>.sh in cwd).
		_ = os.WriteFile("submitted-"+jobID+".sh", []byte(script), 0o644)
	}

	return jobID, nil
}

// parseJobID extracts the job ID from sbatch output, e.g.
// "Submitted batch job 12345". Python takes the last whitespace-separated
// token and parses it as an integer; we do the same.
func parseJobID(out string) (string, error) {
	fields := strings.Fields(out)
	if len(fields) == 0 {
		return "", fmt.Errorf("slurm: empty sbatch output")
	}
	last := fields[len(fields)-1]
	if _, err := strconv.Atoi(last); err != nil {
		return "", fmt.Errorf("slurm: unexpected sbatch output %q", strings.TrimSpace(out))
	}
	return last, nil
}

// partitionTotalCPUs sums the CPUs of all nodes in a partition, mirroring
// Python Slurm.get_total_cpus ('sinfo -N -p <partition> --format="%n %c"').
func partitionTotalCPUs(ctx context.Context, partition string) (int, error) {
	out, err := sinfoOutput(ctx, "-N", "-p", partition, "--format=%n %c")
	if err != nil {
		return 0, err
	}
	total := 0
	for i, line := range strings.Split(out, "\n") {
		if i == 0 || strings.TrimSpace(line) == "" { // skip header and blanks
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		cpus, err := strconv.Atoi(strings.Trim(fields[1], `"'`))
		if err != nil {
			return 0, fmt.Errorf("slurm: parsing sinfo CPUs %q: %w", line, err)
		}
		total += cpus
	}
	if total == 0 {
		return 0, errors.New("slurm: sinfo reported no nodes")
	}
	return total, nil
}

// maxMemoryPerNodeMB returns the smallest per-node memory (MB) across the
// cluster, mirroring Python Slurm.get_max_memory_per_node_in_mb
// ("sinfo -N -o '%m'", min over nodes).
func maxMemoryPerNodeMB(ctx context.Context) (int, error) {
	out, err := sinfoOutput(ctx, "-N", "-o", "%m")
	if err != nil {
		return 0, err
	}
	minMB := 0
	for i, line := range strings.Split(out, "\n") {
		if i == 0 || strings.TrimSpace(line) == "" {
			continue
		}
		mb, err := strconv.Atoi(strings.TrimSpace(line))
		if err != nil {
			return 0, fmt.Errorf("slurm: parsing sinfo memory %q: %w", line, err)
		}
		if minMB == 0 || mb < minMB {
			minMB = mb
		}
	}
	if minMB == 0 {
		return 0, errors.New("slurm: sinfo reported no node memory")
	}
	return minMB, nil
}

func sinfoOutput(ctx context.Context, args ...string) (string, error) {
	var stdout, stderr bytes.Buffer
	cmd := exec.CommandContext(ctx, "sinfo", args...)
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("slurm: running sinfo: %v: %s", err, strings.TrimSpace(stderr.String()))
	}
	return stdout.String(), nil
}
