package app

import (
	"context"
	"os"

	"github.com/dirkpetersen/froster/go/internal/cli"
)

// Mount implements `froster mount` (spec §4.1 subcmd_mount plus main()'s
// credentials gate).
func (a *App) Mount(ctx context.Context, args cli.MountArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	// main() gates credentials before subcmd_mount — even for --list.
	if err := s.credsGate(ctx); err != nil {
		return err
	}

	wf, err := s.workflow()
	if err != nil {
		return err
	}

	if args.List {
		wf.PrintCurrentMounts()
		return nil
	}

	if args.MountPoint != "" {
		if info, err := os.Stat(args.MountPoint); err != nil || !info.IsDir() {
			s.log.Logf("\nError: Folder %q does not exist.\n", args.MountPoint)
			return exit1()
		}
		if len(folders) > 1 {
			s.log.Logf("%s", "\nError: Cannot mount multiple folders to a single mountpoint.")
			s.log.Logf("%s", "Check the mount command usage with \"froster mount --help\"\n")
			return exit1()
		}
	}

	if len(folders) == 0 {
		rows := archiveRows(wf.DB.All(), true)
		if len(rows) == 0 {
			s.log.Logf("%s", "\nNo archives available.\n")
			return nil
		}
		folder, ok, err := a.pickArchived(ctx, rows)
		if err != nil {
			return err
		}
		if !ok {
			return exit1()
		}
		folders = []string{folder}
	}

	return wrapWorkflowErr(wf.Mount(ctx, folders, args.MountPoint))
}

// Umount implements `froster umount` as *intended*. NOTE: the shipped
// Python umount always crashes with a TypeError before doing anything
// (spec §4.2); go-froster implements the documented intended behavior
// (documented deviation).
func (a *App) Umount(ctx context.Context, args cli.UmountArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	// umount skips the credentials gate (spec §0.7).
	wf := s.bareWorkflow()

	if args.List {
		wf.PrintCurrentMounts()
		return nil
	}

	mounts := wf.Mounts()
	if len(mounts) == 0 {
		s.log.Logf("%s", "\nNOTE: No rclone mounts on this computer.\n")
		return nil
	}

	if len(folders) == 0 {
		picked, ok, err := a.pickString(ctx, "Mountpoint", mounts)
		if err != nil {
			return err
		}
		if !ok {
			// Python would crash on an empty selection (IndexError →
			// print_error → exit 1); exit 1 without the traceback.
			return exit1()
		}
		folders = []string{picked}
	}

	return wrapWorkflowErr(wf.Umount(folders))
}
