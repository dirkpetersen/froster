package slurm

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"os/exec"
	"strings"
)

// squeueFormat is the exact output format Python uses
// (Slurm.squeue_output_format): quoted CSV with one row per job.
const squeueFormat = `"%i","%j","%t","%M","%L","%D","%C","%m","%b","%R"`

// Job is one row of `squeue --me` output, mirroring the columns of Python's
// squeue output format string.
type Job struct {
	ID          string // %i JOBID
	Name        string // %j NAME (e.g. "froster:archive:proj1")
	State       string // %t ST (compact state, e.g. "R", "PD")
	TimeUsed    string // %M TIME
	TimeLeft    string // %L TIME_LEFT
	Nodes       string // %D NODES
	CPUs        string // %C CPUS
	MinMemory   string // %m MIN_MEMORY
	TRESPerNode string // %b TRES_PER_NODE (gres, e.g. local scratch)
	Reason      string // %R NODELIST(REASON)
}

// Squeue lists the current user's Slurm jobs, mirroring Python
// Slurm.squeue() (`squeue --me -o <format>`).
func Squeue(ctx context.Context) ([]Job, error) {
	var stdout, stderr bytes.Buffer
	cmd := exec.CommandContext(ctx, "squeue", "--me", "-o", squeueFormat)
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("slurm: running squeue: %v: %s", err, strings.TrimSpace(stderr.String()))
	}
	return parseSqueueOutput(stdout.String())
}

// parseSqueueOutput parses the quoted-CSV squeue output. The first row is
// the header (JOBID, NAME, ...) and is skipped.
func parseSqueueOutput(out string) ([]Job, error) {
	r := csv.NewReader(strings.NewReader(strings.TrimSpace(out)))
	r.FieldsPerRecord = -1 // tolerate short rows
	records, err := r.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("slurm: parsing squeue output: %w", err)
	}
	if len(records) <= 1 {
		return nil, nil // header only, or no output: no jobs
	}
	jobs := make([]Job, 0, len(records)-1)
	for _, rec := range records[1:] {
		var j Job
		fields := []*string{
			&j.ID, &j.Name, &j.State, &j.TimeUsed, &j.TimeLeft,
			&j.Nodes, &j.CPUs, &j.MinMemory, &j.TRESPerNode, &j.Reason,
		}
		for i, f := range fields {
			if i < len(rec) {
				*f = rec[i]
			}
		}
		jobs = append(jobs, j)
	}
	return jobs, nil
}
