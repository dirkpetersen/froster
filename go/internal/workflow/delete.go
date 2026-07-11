package workflow

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/transfer"
)

// Delete reproduces Archiver.delete (spec §2.2): the recursive collision
// check, then per-folder _delete_locally. Individual folder failures only
// print messages; the command still exits 0 (Python always returns True).
// No DB mutation ever happens on delete.
func (w *Workflow) Delete(ctx context.Context, folders []string, recursive bool) error {
	if recursive && w.DeleteCollision(folders) {
		return ErrReported
	}

	for _, folder := range folders {
		if recursive {
			for _, root := range w.walkRoots(folder) {
				w.deleteLocally(ctx, root)
			}
		} else {
			w.deleteLocally(ctx, folder)
		}
	}
	return nil
}

// deleteLocally reproduces Archiver._delete_locally (spec §2.3). All exits
// are silent successes from the command's point of view.
func (w *Workflow) deleteLocally(ctx context.Context, folder string) {
	w.echof("\nDELETING %s", folder)

	// Already deleted?
	manifest := filepath.Join(folder, WhereDidTheFilesGoFileName)
	if info, err := os.Stat(manifest); err == nil && info.Mode().IsRegular() {
		w.echo("    ...already deleted\n")
		return
	}

	entry := w.DB.Get(folder)
	if entry == nil {
		w.echof("\nFolder %s is not archived", folder)
		w.echo("No entry found in froster-archives.json\n")
		return
	}

	// Hashfile resolution: prefer .froster.md5sum, else the restored one.
	hashfile := filepath.Join(folder, MD5SumFileName)
	if _, err := os.Stat(hashfile); err != nil {
		hashfile = filepath.Join(folder, MD5SumRestoredFileName)
		if _, err := os.Stat(hashfile); err != nil {
			w.echof("There is no hashfile therefore cannot delete files in %s", folder)
			return
		}
	}

	// Python: archive_folder + folder.replace(local_folder, '') — note
	// str.replace removes every occurrence.
	s3Dest := entry.ArchiveFolder + strings.ReplaceAll(folder, entry.LocalFolder, "")

	// Verify against the remote before deleting anything.
	w.echo("\n    Verifying checksums...")
	if err := w.Engine.CheckMD5(ctx, hashfile, s3Dest, transfer.CheckOptions{MaxDepth: 1}); err != nil {
		// Python returns silently here (no deletion, exit code unaffected);
		// the underlying rclone failure went to stderr.
		w.rcloneErr("checksum", err)
		return
	}
	w.echo("        ...done")

	// Delete the top-level files, keeping the four metadata files.
	// Froster.smallfiles.tar IS deleted (it lives in the archive).
	files, err := topFiles(folder)
	if err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return
	}
	var deleted []string
	w.echo("\n    Deleting files...")
	for _, name := range files {
		if name == MD5SumFileName || name == MD5SumRestoredFileName ||
			name == AllfilesCSVFileName || name == WhereDidTheFilesGoFileName {
			continue
		}
		if err := os.Remove(filepath.Join(folder, name)); err != nil {
			w.echoErr(fmt.Sprintf("Error: %v", err))
			return
		}
		deleted = append(deleted, name)
	}
	w.echo("        ...done")

	// Write the manifest with the exact Python body (spec §2.3 step 8).
	if err := os.WriteFile(manifest, []byte(w.manifestBody(entry, folder, s3Dest, deleted)), 0o644); err != nil {
		w.echoErr(fmt.Sprintf("Error: %v", err))
		return
	}

	w.echo("\nDELETING SUCCESSFULLY COMPLETED\n")
	w.echof("    LOCAL DELETED FOLDER:   %s", folder)
	w.echof("    AWS S3 DESTINATION:     %s\n", s3Dest)
	w.echof("    Total files deleted:    %d\n", len(deleted))
	w.echof("    Manifest:               %s\n", manifest)
}

// manifestBody renders the Where-did-the-files-go.txt content exactly as
// Python writes it (spec §2.3 step 8), including the str(datetime.now())
// deletion date and the comma-joined first ten deleted files.
func (w *Workflow) manifestBody(entry *archivedb.Entry, folder, s3Dest string, deleted []string) string {
	firstTen := deleted
	if len(firstTen) > 10 {
		firstTen = firstTen[:10]
	}
	var b strings.Builder
	b.WriteString("The files in this folder have been moved to an AWS S3 archive!\n")
	fmt.Fprintf(&b, "Archive location: %s\n", s3Dest)
	fmt.Fprintf(&b, "\nLocal folder : %s\n", entry.LocalFolder)
	fmt.Fprintf(&b, "Provider: %s\n", entry.Provider)
	fmt.Fprintf(&b, "Endpoint: %s\n", entry.Endpoint)
	fmt.Fprintf(&b, "S3 storage class: %s\n", entry.S3StorageClass)
	fmt.Fprintf(&b, "Archive mode: %s\n", entry.ArchiveMode)
	fmt.Fprintf(&b, "Archive aws profile: %s\n", entry.Profile)
	fmt.Fprintf(&b, "Archiver user: %s\n", entry.User)
	fmt.Fprintf(&b, "Archiver email: %s\n", w.Email)
	fmt.Fprintf(&b, "froster-archives.json: %s\n", w.DB.Path())
	b.WriteString("Archive tool: https://github.com/dirkpetersen/froster\n")
	fmt.Fprintf(&b, "Restore command: froster restore %s\n", quoteDouble(folder))
	fmt.Fprintf(&b, "Deletion date: %s\n", pyDatetimeStr(w.now()))
	b.WriteString("\n\nFirst 10 files deleted this time:\n")
	b.WriteString(strings.Join(firstTen, ", "))
	b.WriteString("\n\nPlease see more metadata in Froster.allfiles.csv file")
	b.WriteString("\n\nYou can use \"visidata\" or \"vd\" tool to help you visualize Froster.allfiles.csv file\n")
	return b.String()
}
