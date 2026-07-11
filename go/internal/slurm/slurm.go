// Package slurm provides Slurm detection, batch-script generation and job
// submission for froster (see GO-ARCHITECTURE.md §6.7).
//
// It is a port of the Python Slurm class in froster/froster.py plus the
// module-level helpers is_slurm_installed / is_inside_slurm_job / use_slurm
// and Archiver._slurm_cmd. The generated batch script reproduces the Python
// template (same #SBATCH directives, same job names and output paths under
// the froster data dir's slurm/ subdirectory) so users' expectations and
// documentation continue to hold.
//
// Like Python, the job payload replays the original CLI arguments verbatim;
// re-submission inside the job is prevented by SLURM_JOB_ID detection in
// ShouldUse. (--no-slurm cannot be appended after the subcommand: global
// flags are root-local, matching argparse.)
//
// Resubmit-on-failure: like Python, the script carries "#SBATCH --requeue",
// which marks the job eligible for automatic requeueing by Slurm after node
// failure or preemption, and "--mail-type=FAIL,REQUEUE,END" so the user is
// notified. There is no trap or dependent-job chain in Python and none here.
// (For Glacier restores Python additionally schedules three delayed jobs via
// --begin=now+12hours/24hours/48hours; callers reproduce that by calling
// Submit three times with SubmitOptions.Begin set.)
package slurm

import (
	"fmt"
	"os"
	"os/exec"
)

// Installed reports whether Slurm is available, i.e. sbatch is on PATH.
// Mirrors Python is_slurm_installed().
func Installed() bool {
	_, err := exec.LookPath("sbatch")
	return err == nil
}

// InsideJob reports whether the current process is running inside a Slurm
// job (SLURM_JOB_ID is set). Mirrors Python is_inside_slurm_job().
func InsideJob() bool {
	return os.Getenv("SLURM_JOB_ID") != ""
}

// ShouldUse reports whether froster should submit the current operation as
// a Slurm batch job: Slurm is installed, the user did not pass --no-slurm,
// and we are not already inside a Slurm job. Mirrors Python use_slurm().
func ShouldUse(noSlurmFlag bool) bool {
	return Installed() && !noSlurmFlag && !InsideJob()
}

// Config carries the [SLURM] section of froster's config.ini plus the user
// email, i.e. everything the batch-script template needs beyond per-job
// options. Zero values mean "not configured" and the corresponding
// directives are omitted (Python emits literal "None" values in that case,
// which is a latent bug we deliberately do not reproduce).
type Config struct {
	// Partition is the Slurm partition (config key slurm_partition).
	Partition string
	// QOS is the Slurm quality of service (config key slurm_qos).
	QOS string
	// WalltimeDays and WalltimeHours form the --time directive as
	// "<days>-<hours>" (config keys slurm_walltime_days/_hours). If both
	// are zero the Python default "7-0" (7 days) is used.
	WalltimeDays  int
	WalltimeHours int
	// Lscratch holds extra sbatch flags requesting node-local scratch,
	// e.g. "--gres tmp:1024" (config key slurm_lscratch). Emitted verbatim
	// as an "#SBATCH <flags>" line.
	Lscratch string
	// LscratchMkdir is a site-specific command that provisions local
	// scratch, run at the start of the job (config key lscratch_mkdir).
	LscratchMkdir string
	// LscratchRmdir is a site-specific command that tears down local
	// scratch, run at the end of the job (config key lscratch_rmdir).
	LscratchRmdir string
	// LscratchRoot, if set, exports TMPDIR=<root>/${SLURM_JOB_ID} inside
	// the job (config key lscratch_root).
	LscratchRoot string
	// Email receives FAIL/REQUEUE/END notifications (config key email in
	// the [USER] section).
	Email string
}

// walltime returns the --time value, defaulting to Python's "7-0".
func (c Config) walltime() string {
	if c.WalltimeDays == 0 && c.WalltimeHours == 0 {
		return "7-0"
	}
	return fmt.Sprintf("%d-%d", c.WalltimeDays, c.WalltimeHours)
}
