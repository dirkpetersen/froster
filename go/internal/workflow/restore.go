package workflow

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// RestoreOptions carries the restore-specific flags.
type RestoreOptions struct {
	Recursive bool
	// Days is the Glacier retention in days (parsed from the string
	// --days flag by the app layer).
	Days int32
	// RetrieveOpt is the retrieval tier: "Bulk", "Standard", "Expedited".
	RetrieveOpt string
	NoDownload  bool
	// NoSlurm disables the retry scheduling gate (--no-slurm). The gate
	// itself is `is_slurm_installed() and not noslurm` — it fires even
	// inside a Slurm job (spec §6.1).
	NoSlurm bool
}

// Restore reproduces Archiver.restore (spec §3.2): the recursive collision
// check, per-root DB lookup (with recursive-parent resolution), the
// leftover-files gate, the Glacier trigger/summary, the download+verify
// pipeline, and the triple Slurm retry scheduling for pending retrievals.
// It returns nil (exit 0) in the "come back later" case, like Python.
func (w *Workflow) Restore(ctx context.Context, folders []string, opts RestoreOptions) error {
	if opts.Recursive && w.RestoreCollision(folders) {
		return ErrReported
	}

	for _, folder := range folders {
		if _, err := os.Stat(folder); os.IsNotExist(err) {
			if err := os.MkdirAll(folder, 0o777); err != nil {
				w.echoErr(fmt.Sprintf("Error: %v", err))
				return ErrReported
			}
		}
		roots := w.walkRoots(folder)
		if !opts.Recursive && len(roots) > 1 {
			roots = roots[:1]
		}
		for _, root := range roots {
			entry := w.DB.Get(root)
			if entry == nil {
				w.echof("\nFolder %s is not archived", root)
				w.echo("No entry found in froster-archives.json\n")
				continue
			}

			// The gate refuses to download into a folder that still holds
			// real files (Python's confusingly named
			// _contains_non_froster_files returns True only when the top
			// level has no file outside dirmetafiles — a leftover
			// Froster.smallfiles.tar also blocks the restore).
			if w.hasNonMetaFiles(root) {
				// Trailing space after the folder name reproduces the
				// Python message verbatim.
				w.echof("\nWARNING: Folder %s ", root)
				w.echo("    contains files in addition to Froster meta data.\n")
				w.echo("Has this folder been deleted using \"froster delete\" command?.")
				w.echo("Please empty the folder before restoring.\n")
				continue
			}

			if w.restoreLocally(ctx, root, opts) {
				if opts.NoDownload {
					w.echo("\nFolder restored but not downloaded (--no-download flag set)\n")
					// DOCUMENTED DEVIATION: Python `return`s None here,
					// which main treats as failure → exit 1 even though
					// everything succeeded (spec §3.2). Go keeps the early
					// return (remaining folders are not processed, matching
					// Python) but exits 0.
					return nil
				}
				w.download(ctx, root)
			} else {
				// Glacier retrieval pending: schedule three delayed Slurm
				// retries (12/24/48 hours) when Slurm is available and
				// --no-slurm was not given. Note: Python passes the full
				// original folder list each time, once per pending root.
				if w.slurmInstalled() && !opts.NoSlurm && w.ScheduleRestore != nil {
					w.ScheduleRestore("now+12hours")
					w.ScheduleRestore("now+24hours")
					w.ScheduleRestore("now+48hours")
				}
			}
		}
	}
	return nil
}

func (w *Workflow) slurmInstalled() bool {
	return w.SlurmInstalled != nil && w.SlurmInstalled()
}

// hasNonMetaFiles reports whether the top level of folder contains any file
// outside DirMetaFiles (the negation of Python's
// _contains_non_froster_files return value).
func (w *Workflow) hasNonMetaFiles(folder string) bool {
	files, err := topFiles(folder)
	if err != nil {
		return false
	}
	for _, name := range files {
		if !isMetaFile(name) {
			return true
		}
	}
	return false
}

// restoreLocally reproduces Archiver._restore_locally (spec §3.3). It
// returns true when the folder is ready to download (not Glacier, or fully
// thawed) and false when Glacier retrievals are pending or the trigger
// failed.
func (w *Workflow) restoreLocally(ctx context.Context, folder string, opts RestoreOptions) bool {
	w.echof("\nRESTORING %s\n", quoteDouble(folder))

	entry := w.DB.Get(folder)
	info, err := entry.BucketInfo(folder)
	if err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return false
	}

	if !info.Glacier {
		w.echo("...no glacier restore needed\n")
		return true
	}

	if w.Glacier == nil {
		w.echoErr("Error: no AWS client available for Glacier restore")
		return false
	}
	res, err := w.Glacier.TriggerGlacierRestore(info.Bucket, info.Prefix, opts.Days, opts.RetrieveOpt)
	if err != nil {
		// Python prints the failure ("Access denied ..." / "Restore
		// request for {key} failed.") and continues with five empty lists.
		w.echoErr(fmt.Sprintf("Error: %v", err))
		res = GlacierResult{}
	}
	for _, key := range res.NotSupported {
		w.echof("%s: No Expedited retrieval in DEEP_ARCHIVE storage class.", key)
	}

	w.echof("    Triggered Glacier retrievals: %d", len(res.Triggered))
	w.echof("    Currently retrieving from Glacier: %d", len(res.InProgress))
	w.echof("    Retrieved from Glacier: %d", len(res.Restored))
	w.echof("    Not in Glacier: %d", len(res.NotGlacier))
	w.echof("    Restore option not supported: %d\n", len(res.NotSupported))

	if len(res.Triggered) > 0 || len(res.InProgress) > 0 {
		w.echo("\n    Glacier retrievals pending. Depending on the storage class and restore mode run this command again in:\n")
		w.echo("        Expedited mode: ~ 5 minutes (DEEP_ARCHIVE not supported)")
		w.echo("        Standard mode: ~ 12 hours")
		w.echo("        Bulk mode: ~ 48 hours\n")
		w.echo("        NOTE: You can check more accurate times in the AWS S3 console\n")
		return false
	}
	return true
}

// download reproduces Archiver._download (spec §3.4 step 1): rclone copy
// from the archive prefix (MaxDepth 1, no --links) into the folder, then
// checksum verification and untarring via restoreVerify. Verification runs
// even when the download reported FAILED, matching Python.
func (w *Workflow) download(ctx context.Context, folder string) {
	entry := w.DB.Get(folder)
	if entry == nil {
		w.echof("\nFolder %s is not registered as archived", folder)
		return
	}
	info, err := entry.BucketInfo(folder)
	if err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return
	}

	source := ":s3:" + info.Bucket + "/" + info.Prefix

	w.echo("Downloading files...")
	if _, err := w.Engine.Copy(ctx, source, folder, transfer.CopyOptions{MaxDepth: 1}); err != nil {
		w.echo("    ...FAILED\n")
		w.rcloneErr("copy", err)
	} else {
		w.echo("    ...done\n")
	}

	w.restoreVerify(ctx, source, folder)
}

// restoreVerify reproduces Archiver._restore_verify (spec §3.4 step 2):
// generate .froster-restored.md5sum, verify it against the remote, untar
// Froster.smallfiles.tar, remove the deletion manifest, and print the
// completion message.
func (w *Workflow) restoreVerify(ctx context.Context, source, target string) {
	w.echo("\n    Generating checksums...\n")
	if err := w.genMD5Sums(target, MD5SumRestoredFileName); err != nil {
		// Python quirk Q10: an empty hash file (e.g. an empty subfolder of
		// a recursive archive) is deleted and the restore of this folder
		// stops silently; overall exit stays 0.
		if err != errEmptyMD5 {
			w.echoErr(fmt.Sprintf("Error: %v", err))
		}
		return
	}
	w.echo("    ...done")

	hashfile := filepath.Join(target, MD5SumRestoredFileName)
	checkers := w.Cores / 2
	if checkers < 1 {
		checkers = 1
	}
	w.echo("\nVerifying checksums...")
	if err := w.Engine.CheckMD5(ctx, hashfile, source, transfer.CheckOptions{MaxDepth: 1, Checkers: checkers}); err != nil {
		w.echo("    ...FAILED\n")
		w.rcloneErr("checksum", err)
		return
	}
	w.echo("    ...done")

	// Untar only after checksum verification succeeded; the tar is
	// deleted afterwards. The trailing space matches Python.
	tarPath := filepath.Join(target, SmallfilesTarFileName)
	if _, err := os.Lstat(tarPath); err == nil {
		w.echo("\nUntarring Froster.smallfiles.tar... ")
		if err := untar(tarPath, target); err != nil {
			w.echoErr(fmt.Sprintf("Error: %v", err))
			return
		}
		if err := os.Remove(tarPath); err != nil {
			w.echoErr(fmt.Sprintf("Error: %v", err))
			return
		}
		w.echo("    ...done\n")
	}

	// Remove the deletion manifest, silently.
	manifest := filepath.Join(target, WhereDidTheFilesGoFileName)
	if _, err := os.Lstat(manifest); err == nil {
		_ = os.Remove(manifest)
	}

	w.echof("RESTORATION OF %s COMPLETED SUCCESSFULLY\n", target)
}
