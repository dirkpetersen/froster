package app

import (
	"context"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/slurm"
	"github.com/dirkpetersen/froster/go/internal/tui"
)

// Delete implements `froster delete` (spec §2.1 subcmd_delete plus main()'s
// credentials gate).
func (a *App) Delete(ctx context.Context, args cli.DeleteArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	if err := s.credsGate(ctx); err != nil {
		return err
	}

	// Hidden --bucket: bucket deletion, debug-only in Python.
	if args.Bucket != "" {
		if args.Global.Debug {
			// DOCUMENTED GAP: aws.delete_bucket (empty + remove a bucket)
			// is not ported; awsx has no DeleteBucket yet.
			s.log.Logf("Error: bucket deletion is not implemented yet in go-froster")
			return exit1()
		}
		s.log.Logf("%s", "Error: Option not available")
		return exit1()
	}

	wf, err := s.workflow()
	if err != nil {
		return err
	}

	argv := a.Argv
	if len(folders) == 0 {
		rows := archiveRows(wf.DB.All(), false)
		if len(rows) == 0 {
			s.log.Logf("%s", "No archives available.")
			return nil
		}
		folder, ok, err := a.pickArchived(ctx, rows)
		if err != nil {
			return err
		}
		if !ok {
			return exit1() // Python: TableArchive cancelled → return False
		}
		folders = []string{folder}
		// Python appends the selection to sys.argv so a Slurm
		// re-execution carries it.
		argv = append(append([]string{}, argv...), folder)
	}

	if slurm.ShouldUse(args.Global.NoSlurm) {
		if args.Recursive && wf.DeleteCollision(folders) {
			return exit1()
		}
		return s.submitSlurm(ctx, "delete", folders, argv, "")
	}

	return wrapWorkflowErr(wf.Delete(ctx, folders, args.Recursive))
}

// archiveRows adapts DB entries to the TableArchive rows. Python passes
// [local_folder, s3_storage_class, profile] for delete and adds
// archive_mode for restore/mount; the Go table always shows all four
// columns (withMode selects nothing today, kept for clarity).
func archiveRows(entries []*archivedb.Entry, withMode bool) []tui.ArchiveRow {
	rows := make([]tui.ArchiveRow, 0, len(entries))
	for _, e := range entries {
		row := tui.ArchiveRow{
			LocalFolder:  e.LocalFolder,
			StorageClass: e.S3StorageClass,
			Profile:      e.Profile,
		}
		if withMode {
			row.ArchiveMode = e.ArchiveMode
		}
		rows = append(rows, row)
	}
	return rows
}
