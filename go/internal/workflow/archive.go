package workflow

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// ArchiveOptions carries the archive-specific flags.
type ArchiveOptions struct {
	Recursive bool
	NoTar     bool
	Force     bool
	NIHRef    string // --nih-ref value stored as nih_project
}

// archiveStatus is the tri-state result of archiveLocally, mirroring
// Python's True / False / None returns.
type archiveStatus int

const (
	archiveOK archiveStatus = iota
	archiveFailed
	archiveSkipped
)

// Archive reproduces Archiver.archive (spec §1.3): the recursive collision
// check, the per-folder _archive_locally sequence, and the single DB entry
// per top-level folder. It returns ErrReported when the run had failures
// (Python: return False → exit 1); all messages are printed here.
func (w *Workflow) Archive(ctx context.Context, folders []string, opts ArchiveOptions) error {
	overallSuccess := true

	if opts.Recursive && w.ArchiveCollision(folders) {
		return ErrReported
	}

	for _, folder := range folders {
		s3Dest := w.s3Dest(folder)

		// anySuccess tracks whether at least one (sub)folder was archived,
		// deciding the DB write below.
		anySuccess := false
		failed := false
		archiveMode := archivedb.ModeSingle

		if opts.Recursive {
			archiveMode = archivedb.ModeRecursive
			for _, root := range w.walkRoots(folder) {
				status := w.archiveLocally(ctx, root, w.s3Dest(root), !opts.NoTar, opts.Force)
				switch status {
				case archiveOK:
					anySuccess = true
				case archiveFailed:
					failed = true
					overallSuccess = false
					w.echoErr(fmt.Sprintf("\nError occurred during archive of %s. Skipping remaining subfolders for %s.\n", root, folder))
				case archiveSkipped:
					// tolerated, like Python's None
				}
				if failed {
					break
				}
			}
		} else {
			// Single mode covers only the top-level files (subdirectories
			// are silently ignored — Python quirk Q8, no warning printed).
			switch w.archiveLocally(ctx, folder, s3Dest, !opts.NoTar, opts.Force) {
			case archiveOK:
				anySuccess = true
			case archiveFailed:
				failed = true
				overallSuccess = false
				w.echoErr(fmt.Sprintf("\nError occurred during archive of %s.\n", folder))
			}
		}

		// DB write: one entry per top-level folder; subfolders never get
		// their own entries (spec §1.3 step 6).
		//
		// DOCUMENTED DEVIATION (Python bug Q6): Python gates this write on
		// the result of the *last* walked subfolder only, so a recursive
		// archive whose final subfolder is empty (skipped) silently loses
		// its DB entry despite successful uploads. Go writes the entry
		// whenever at least one folder was archived and no failure
		// occurred.
		if anySuccess && !failed {
			timestamp := archivedb.FormatTimestamp(w.now())
			entry := &archivedb.Entry{
				LocalFolder:      folder,
				ArchiveFolder:    s3Dest,
				S3StorageClass:   w.StorageClass,
				Profile:          w.Credentials, // the credentials profile name (quirk Q9)
				Provider:         w.Provider,
				Endpoint:         w.Endpoint,
				ArchiveMode:      archiveMode,
				Timestamp:        timestamp,
				TimestampArchive: timestamp,
				User:             w.User,
				NIHProject:       opts.NIHRef,
			}
			if err := w.DB.Upsert(entry); err != nil {
				w.echoErr(fmt.Sprintf("Error: cannot update %s: %v", w.DB.Path(), err))
				overallSuccess = false
			}
		}
	}

	if !overallSuccess {
		return ErrReported
	}
	return nil
}

// archiveLocally reproduces Archiver._archive_locally (spec §1.4).
func (w *Workflow) archiveLocally(ctx context.Context, folder, s3Dest string, isTar, isForce bool) archiveStatus {
	hashfile := filepath.Join(folder, MD5SumFileName)

	if isForce {
		// Reset the folder first, then continue archiving.
		if err := w.resetFolder(folder, false); err != nil {
			return archiveFailed
		}
	} else if _, err := os.Stat(hashfile); err == nil {
		// A hash file from a previous attempt exists: report and refuse.
		entry := w.DB.Get(folder)
		checksumOK := w.Engine.CheckMD5(ctx, hashfile, s3Dest, transfer.CheckOptions{MaxDepth: 1}) == nil

		switch {
		case entry != nil && checksumOK:
			w.echof("\nThe folder %s is already archived in S3 bucket.\n", folder)
			w.echof("%s\n", pyDictRepr(entry))
		case entry != nil && !checksumOK:
			w.echof("\nThe folder %s is already archived in our database but checksums do not match in the S3 bucket.\n", folder)
			w.echof("%s\n", pyDictRepr(entry))
			// "us" (sic) reproduces the Python message verbatim.
			w.echo("\nIf you want to force the archiving process again on this folder, please us the -f or --force flag\n")
		default:
			w.echof("\nThe hashfile \".froster.md5sum\" already exists in %s from a previous archiving process attempt.", folder)
			w.echo("\nIf you want to force the archiving process again on this folder, please us the -f or --force flag\n")
		}
		return archiveFailed
	}

	// Empty-folder skip: no file/symlink outside the metadata set (a
	// present Froster.smallfiles.tar counts as content, spec §1.4 step 4).
	entries, err := os.ReadDir(folder)
	if err != nil {
		if os.IsNotExist(err) {
			w.echof("\nError: Folder %s not found during check.\n", folder)
		} else {
			w.echof("\nError scanning folder %s: %v\n", folder, err)
		}
		return archiveFailed
	}
	// Python's predicate (froster.py:4152-4156) is
	// entry.is_file(follow_symlinks=False) or entry.is_symlink(): only
	// regular files and symlinks count. Special files (sockets, FIFOs,
	// devices) must NOT count — otherwise a folder containing only a live
	// socket would be "archived" (header-only CSV), registered in the DB,
	// and a later froster delete would remove the socket.
	hasContent := false
	for _, e := range entries {
		if e.IsDir() || isMetaFile(e.Name()) {
			continue
		}
		if e.Type().IsRegular() || e.Type()&os.ModeSymlink != 0 {
			hasContent = true
			break
		}
	}
	if !hasContent {
		w.echof("\nFolder %s contains no files or symlinks to archive (only subdirectories and/or metadata), skipping.\n", folder)
		return archiveSkipped
	}

	w.echof("\nARCHIVING %s", folder)

	if isTar {
		w.echo("\n    Generating Froster.allfiles.csv and tar small files...")
	} else {
		w.echo("\n    Generating Froster.allfiles.csv...")
	}
	if err := w.genAllfilesAndTar(folder, w.thresholdKiB(), isTar); err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return archiveFailed
	}
	w.echo("        ...done")

	w.echo("\n    Generating checksums...\n")
	if err := w.genMD5Sums(folder, MD5SumFileName); err != nil {
		if err != errEmptyMD5 {
			w.echoErr(fmt.Sprintf("Error: %v", err))
		}
		return archiveFailed
	}
	w.echo("        ...done")

	excludes := []string{MD5SumFileName, MD5SumRestoredFileName, AllfilesCSVFileName, WhereDidTheFilesGoFileName}

	// Upload Froster.allfiles.csv on its own; on AWS it goes to
	// INTELLIGENT_TIERING instead of the profile storage class.
	w.echo("\n    Uploading Froster.allfiles.csv file...")
	csvOpts := transfer.CopyOptions{
		MaxDepth: 1,
		Links:    true,
		Exclude:  excludes, // inert for a single-file source, kept for parity
	}
	if w.Provider == "AWS" {
		csvOpts.StorageClass = "INTELLIGENT_TIERING"
	}
	if _, err := w.Engine.Copy(ctx, filepath.Join(folder, AllfilesCSVFileName), s3Dest, csvOpts); err != nil {
		w.echo("        ...FAILED\n")
		w.rcloneErr("copy", err)
		return archiveFailed
	}
	w.echo("        ...done")

	// Main upload: top level only, symlinks as .rclonelink, metadata files
	// excluded (the tar IS uploaded).
	w.echo("\n    Uploading files...")
	if _, err := w.Engine.Copy(ctx, folder, s3Dest, transfer.CopyOptions{
		MaxDepth:           1,
		Links:              true,
		Exclude:            excludes,
		Transfers:          w.Cores,
		Checkers:           w.Cores / 2,
		MultiThreadStreams: 4,
	}); err != nil {
		w.echo("        ...FAILED\n")
		w.rcloneErr("copy", err)
		return archiveFailed
	}
	w.echo("        ...done")

	w.echo("\n    Verifying checksums...")
	checkers := w.Cores / 2
	if checkers < 1 {
		checkers = 1
	}
	if err := w.Engine.CheckMD5(ctx, hashfile, s3Dest, transfer.CheckOptions{MaxDepth: 1, Checkers: checkers}); err != nil {
		w.echo("        ...FAILED\n")
		w.rcloneErr("checksum", err)
		return archiveFailed
	}
	w.echo("        ...done")

	w.echo("\nARCHIVING SUCCESSFULLY COMPLETED\n")
	w.echof("    PROVIDER:           %s", quoteDouble(w.Provider))
	w.echof("    PROFILE:            %s", quoteDouble(w.Profile))
	w.echof("    ENDPOINT:           %s", quoteDouble(w.Endpoint))
	w.echof("    LOCAL SOURCE:       %s", quoteDouble(folder))
	w.echof("    S3 DESTINATION:     %s\n", quoteDouble(s3Dest))

	return archiveOK
}

// ResetFolders reproduces `froster archive --reset` (subcmd_archive step 2 +
// reset_folder, spec §1.8). Per-folder failures are reported but the
// command still succeeds, like Python (whose per-folder results are
// discarded).
func (w *Workflow) ResetFolders(folders []string, recursive bool) error {
	for _, folder := range folders {
		_ = w.resetFolder(folder, recursive)
	}
	return nil
}

// resetFolder untars Froster.smallfiles.tar back into place and removes
// the four metadata files (Python Archiver.reset_folder).
//
// DOCUMENTED DEVIATION (latent Python bug): Python's `return True` sits
// inside the walk loop, so at most ONE directory is ever reset even with
// recursive=True. Go resets every subdirectory when recursive is set.
func (w *Workflow) resetFolder(folder string, recursive bool) error {
	roots := w.walkRoots(folder)
	if !recursive && len(roots) > 1 {
		roots = roots[:1]
	}
	for _, root := range roots {
		w.echof("\nResetting folder %s...", quoteDouble(root))

		tarPath := filepath.Join(root, SmallfilesTarFileName)
		if _, err := os.Lstat(tarPath); err == nil {
			// Python prints the label with end='' before extracting and
			// "done." after; without partial-line printing the combined
			// line is emitted once the extraction succeeded.
			if err := untar(tarPath, root); err != nil {
				w.echoErr(fmt.Sprintf("Error: %v", err))
				return err
			}
			if err := os.Remove(tarPath); err != nil {
				w.echoErr(fmt.Sprintf("Error: %v", err))
				return err
			}
			w.echo("    Untarring Froster.smallfiles.tar... done.")
		}

		for _, name := range DirMetaFiles {
			delfile := filepath.Join(root, name)
			outcome := "nothing to remove"
			if _, err := os.Lstat(delfile); err == nil {
				if err := os.Remove(delfile); err != nil {
					w.echoErr(fmt.Sprintf("Error: %v", err))
					return err
				}
				outcome = "done"
			}
			w.echof("    Removing %s... %s", name, outcome)
		}

		w.echof("...folder %s reset successfully\n", root)
	}
	return nil
}

// quoteDouble renders s inside double quotes without escaping, matching
// Python f-string interpolation like f'"{x}"'. (fmt %q would escape.)
func quoteDouble(s string) string { return `"` + s + `"` }
