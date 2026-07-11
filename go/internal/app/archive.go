package app

import (
	"context"
	"fmt"

	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/slurm"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// Archive implements `froster archive` (spec §1.1 subcmd_archive plus
// main()'s credentials gate).
func (a *App) Archive(ctx context.Context, args cli.ArchiveArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	// main() gates credentials before subcmd_archive, --reset included.
	if err := s.credsGate(ctx); err != nil {
		return err
	}

	if args.Older > 0 && args.Newer > 0 {
		fmt.Fprint(a.stderr(), "\nError: Cannot use both --older and --newer flags together.\n\n")
		return exit1()
	}

	wf, err := s.workflow()
	if err != nil {
		return err
	}

	if args.Reset {
		return wf.ResetFolders(folders, args.Recursive)
	}

	if len(folders) == 0 {
		return a.archiveSelectHotspots(ctx, s, wf, args)
	}
	return a.archiveFolders(ctx, s, wf, args, folders, a.Argv)
}

// archiveFolders runs the NIH gate, the Slurm gate, and the archive itself
// (Archiver.archive order: collision → NIH → Slurm → local, spec §1.3).
// argv is the command line replayed into a Slurm job.
func (a *App) archiveFolders(ctx context.Context, s *session, wf *workflow.Workflow, args cli.ArchiveArgs, folders, argv []string) error {
	// NIH grant linking requires the interactive grant-search screen.
	// DOCUMENTED GAP: the NIH grant TUI is not ported yet; a preselected
	// --nih-ref works, interactive selection does not.
	if s.cfg.IsNIH() || (args.NIH && args.NIHRef == "") {
		return fmt.Errorf("interactive NIH grant search is not implemented yet in go-froster; " +
			"pass the grant reference explicitly with --nih-ref <ref>")
	}

	if slurm.ShouldUse(args.Global.NoSlurm) {
		// The collision check happens before submission, as in Python.
		if args.Recursive && wf.ArchiveCollision(folders) {
			return exit1()
		}
		return s.submitSlurm(ctx, "archive", folders, argv, "")
	}

	return wrapWorkflowErr(wf.Archive(ctx, folders, workflow.ArchiveOptions{
		Recursive: args.Recursive,
		NoTar:     args.NoTar,
		Force:     args.Force,
		NIHRef:    args.NIHRef,
	}))
}
