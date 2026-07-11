package app

import (
	"context"
	"fmt"
	"os"
	"syscall"

	"golang.org/x/sys/unix"

	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/slurm"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// Index implements `froster index` (subcmd_index + Archiver.index). Index
// skips the credentials gate (spec §0.7).
func (a *App) Index(ctx context.Context, args cli.IndexArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	if len(folders) == 0 {
		s.log.Logf("%s", "\nError: Folder not provided. Check the index command usage with \"froster index --help\"\n")
		return exit1()
	}

	if args.Permissions {
		a.printPathsRWInfo(s, folders)
		return nil
	}

	if args.PwalkCopy != "" {
		if info, err := os.Stat(args.PwalkCopy); err != nil || !info.IsDir() {
			s.log.Logf("\nError: Folder \"%s\" does not exist.\n", args.PwalkCopy)
			return exit1()
		}
	}

	for _, folder := range folders {
		if info, err := os.Stat(folder); err != nil || !info.IsDir() {
			s.log.Logf("\nError: The folder %s does not exist.\n", folder)
			return exit1()
		}
	}

	wf := s.bareWorkflow()

	// Archiver.index: dependency check, then the Slurm gate for the whole
	// run, then local indexing.
	if wf.IndexCollision(folders) {
		return exit1()
	}
	if slurm.ShouldUse(args.Global.NoSlurm) {
		return s.submitSlurm(ctx, "index", folders, a.Argv, "")
	}

	return wrapWorkflowErr(wf.Index(folders, workflow.IndexOptions{
		Force:       args.Force,
		PwalkCopy:   args.PwalkCopy,
		HotspotsDir: s.cfg.HotspotsDir(),
	}))
}

// printPathsRWInfo reproduces Archiver.print_paths_rw_info (`froster index
// --permissions`).
func (a *App) printPathsRWInfo(s *session, paths []string) {
	if len(paths) == 0 {
		fmt.Fprint(a.stderr(), "\nError: No file paths provided.\n\n")
		return
	}

	for _, path := range paths {
		var st syscall.Stat_t
		if err := syscall.Lstat(path, &st); err != nil {
			continue // Python: skip missing paths
		}

		uid := os.Getuid()
		gid := os.Getgid()
		isOwner := int(st.Uid) == uid

		isGroupMember := int(st.Gid) == gid
		if !isGroupMember {
			if groups, err := os.Getgroups(); err == nil {
				for _, g := range groups {
					if g == int(st.Gid) {
						isGroupMember = true
						break
					}
				}
			}
		}

		perm := st.Mode
		hasOwnerRead := perm&unix.S_IRUSR != 0
		hasGroupRead := perm&unix.S_IRGRP != 0
		is444 := perm&0o444 == 0o444
		canRead := (isOwner && hasOwnerRead) || (isGroupMember && hasGroupRead) || is444

		hasOwnerWrite := perm&unix.S_IWUSR != 0
		hasGroupWrite := perm&unix.S_IWGRP != 0
		is666or777 := perm&0o666 == 0o666 || perm&0o777 == 0o777
		canWrite := (isOwner && hasOwnerWrite) || (isGroupMember && hasGroupWrite) || is666or777

		s.log.Logf("\nFile: %s", path)
		s.log.Logf("\nis_owner: %s", pyBool(isOwner))
		s.log.Logf("has_owner_read_permission: %s", pyBool(hasOwnerRead))
		s.log.Logf("has_owner_write_permission: %s", pyBool(hasOwnerWrite))
		s.log.Logf("\nis_group_member: %s", pyBool(isGroupMember))
		s.log.Logf("has_group_read_permission: %s", pyBool(hasGroupRead))
		s.log.Logf("has_group_write_permission: %s", pyBool(hasGroupWrite))
		s.log.Logf("\nis_444: %s", pyBool(is444))
		s.log.Logf("is_666_or_777: %s", pyBool(is666or777))
		s.log.Logf("\ncan_read: %s", pyBool(canRead))
		s.log.Logf("can_write: %s\n", pyBool(canWrite))
	}
}

// pyBool renders a bool like Python's str(bool).
func pyBool(b bool) string {
	if b {
		return "True"
	}
	return "False"
}
