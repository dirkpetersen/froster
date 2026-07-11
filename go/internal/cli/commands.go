package cli

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

// stubbedError is returned when a flag whose feature was intentionally
// dropped from go-froster (GO-ARCHITECTURE.md section 9) is used. The flags
// still parse so scripts fail with a clear message instead of a parse error.
func stubbedError(features ...string) error {
	list := strings.Join(features, ", ")
	return fmt.Errorf("%s is not yet implemented in go-froster.\n"+
		"This feature exists in Python froster (pip install froster==0.22.x).\n"+
		"See GO-ARCHITECTURE.md section 9 (Stubbed Features) for details", list)
}

// argumentsSection renders the positional-argument help (argparse shows a
// "positional arguments:" section; cobra has no equivalent, so we append it
// to the Long description).
func argumentsSection(name, help string) string {
	return "\nArguments:\n  " + name + "\n        " + strings.ReplaceAll(help, "\n", "\n        ")
}

func newCredentialsCmd(app App, global *GlobalArgs) *cobra.Command {
	return &cobra.Command{
		Use:     "credentials",
		Aliases: []string{"crd"},
		Short:   descCredentials,
		Long:    descCredentials,
		Args:    cobra.NoArgs,
		RunE: run(app, global, func(ctx context.Context, _ []string) error {
			return app.Credentials(ctx, CredentialsArgs{Global: *global})
		}),
	}
}

func newConfigCmd(app App, global *GlobalArgs) *cobra.Command {
	args := ConfigArgs{}
	cmd := &cobra.Command{
		Use:     "config",
		Aliases: []string{"cnf"},
		Short:   "Froster configuration bootstrap.",
		Long:    descConfig,
		Args:    cobra.NoArgs,
		RunE: run(app, global, func(ctx context.Context, _ []string) error {
			args.Global = *global
			return app.Config(ctx, args)
		}),
	}
	f := cmd.Flags()
	f.BoolVarP(&args.Print, "print", "p", false, helpConfigPrint)
	f.BoolVarP(&args.Reset, "reset", "r", false, helpConfigReset)
	f.StringVarP(&args.ImportConfig, "import", "i", "", helpConfigImport)
	f.StringVarP(&args.ExportConfig, "export", "e", "", helpConfigExport)
	return cmd
}

func newIndexCmd(app App, global *GlobalArgs) *cobra.Command {
	args := IndexArgs{}
	cmd := &cobra.Command{
		Use:     "index [folders ...]",
		Aliases: []string{"idx"},
		Short:   "Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file.",
		Long:    descIndex + "\n" + argumentsSection("folders", helpIndexFolders),
		Args:    cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			args.Global = *global
			args.Folders = folders
			return app.Index(ctx, args)
		}),
	}
	f := cmd.Flags()
	f.BoolVarP(&args.Force, "force", "f", false, helpIndexForce)
	f.BoolVarP(&args.Permissions, "permissions", "p", false, helpIndexPermissions)
	f.StringVarP(&args.PwalkCopy, "pwalk-copy", "y", "", helpIndexPwalkCopy)
	return cmd
}

func newArchiveCmd(app App, global *GlobalArgs) *cobra.Command {
	args := ArchiveArgs{}
	cmd := &cobra.Command{
		Use:     "archive [folders ...]",
		Aliases: []string{"arc"},
		Short:   "Archive a folder to S3/Glacier.",
		Long:    descArchive + "\n" + argumentsSection("folders", helpArchiveFolders),
		Args:    cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			args.Global = *global
			args.Folders = folders
			return app.Archive(ctx, args)
		}),
	}
	f := cmd.Flags()
	f.BoolVarP(&args.Force, "force", "f", false, helpArchiveForce)
	f.IntVarP(&args.Larger, "larger", "l", 0, helpArchiveLarger)
	f.IntVarP(&args.Older, "older", "o", 0, helpArchiveOlder)
	f.IntVarP(&args.Newer, "newer", "w", 0, helpArchiveNewer)
	f.BoolVarP(&args.NIH, "nih", "n", false, helpArchiveNIH)
	f.StringVarP(&args.NIHRef, "nih-ref", "i", "", helpArchiveNIHRef)
	f.BoolVarP(&args.AgeMtime, "mtime", "m", false, helpArchiveMtime)
	f.BoolVarP(&args.Recursive, "recursive", "r", false, helpArchiveRecursive)
	f.BoolVarP(&args.Reset, "reset", "s", false, helpArchiveReset)
	f.BoolVarP(&args.NoTar, "no-tar", "t", false, helpArchiveNoTar)
	f.BoolVarP(&args.DryRun, "dry-run", "d", false, helpArchiveDryRun)
	return cmd
}

func newDeleteCmd(app App, global *GlobalArgs) *cobra.Command {
	args := DeleteArgs{}
	cmd := &cobra.Command{
		Use:     "delete [folders ...]",
		Aliases: []string{"del"},
		Short:   "Remove data from a local filesystem folder that has been archived.",
		Long:    descDelete + "\n" + argumentsSection("folders", helpDeleteFolders),
		Args:    cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			args.Global = *global
			args.Folders = folders
			return app.Delete(ctx, args)
		}),
	}
	f := cmd.Flags()
	// Hidden like argparse.SUPPRESS in Python (bucket deletion, debug only).
	f.StringVarP(&args.Bucket, "bucket", "b", "", "")
	_ = f.MarkHidden("bucket")
	f.BoolVarP(&args.Recursive, "recursive", "r", false, helpDeleteRecursive)
	return cmd
}

func newMountCmd(app App, global *GlobalArgs) *cobra.Command {
	args := MountArgs{}
	cmd := &cobra.Command{
		Use:   "mount [folders ...]",
		Short: "Mount the remote S3 or Glacier storage in your local file system.",
		Long:  descMount + "\n" + argumentsSection("folders", helpMountFolders),
		Args:  cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			if args.AWS {
				return stubbedError("'mount --aws'")
			}
			args.Global = *global
			args.Folders = folders
			return app.Mount(ctx, args)
		}),
	}
	addMountFlags(cmd, &args.AWS, &args.List, &args.MountPoint)
	return cmd
}

// newUmountCmd builds the umount command.
//
// Deviation from the Python implementation (behavior-preserving): in argparse,
// `umount` is an *alias* of the `mount` subparser and main() inspects argv to
// decide whether to mount or unmount. Cobra reports the canonical name of the
// invoked alias awkwardly for that trick, so umount is its own command with
// the same flag set. User-visible behavior is identical: `froster umount
// <folder>` unmounts, and both `froster mount --help` and `froster umount
// --help` work. contract_test.go maps the contract's mount alias "umount" to
// this command.
func newUmountCmd(app App, global *GlobalArgs) *cobra.Command {
	args := UmountArgs{}
	cmd := &cobra.Command{
		Use:   "umount [folders ...]",
		Short: "Unmount the remote S3 or Glacier storage from your local file system.",
		Long:  descUmount + "\n" + argumentsSection("folders", helpMountFolders),
		Args:  cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			args.Global = *global
			args.Folders = folders
			return app.Umount(ctx, args)
		}),
	}
	// Same flags as mount: the Python parser is shared, so all of them must
	// keep parsing under umount even where the unmount path ignores them.
	addMountFlags(cmd, &args.AWS, &args.List, &args.MountPoint)
	return cmd
}

func addMountFlags(cmd *cobra.Command, aws *bool, list *bool, mountPoint *string) {
	f := cmd.Flags()
	f.BoolVarP(aws, "aws", "a", false, helpMountAWS)
	f.BoolVarP(list, "list", "l", false, helpMountList)
	f.StringVarP(mountPoint, "mount-point", "m", "", helpMountMountPoint)
}

func newRestoreCmd(app App, global *GlobalArgs) *cobra.Command {
	args := RestoreArgs{}
	cmd := &cobra.Command{
		Use:     "restore [folders ...]",
		Aliases: []string{"rst"},
		Short:   "Restore data from AWS Glacier.",
		Long:    descRestore + "\n" + argumentsSection("folders", helpRestoreFolders),
		Args:    cobra.ArbitraryArgs,
		RunE: run(app, global, func(ctx context.Context, folders []string) error {
			// Dropped features (GO-ARCHITECTURE.md section 9): the flags
			// parse, but using them reports a clear error.
			var stubbed []string
			if args.AWS {
				stubbed = append(stubbed, "'restore --aws'")
			}
			if args.Monitor {
				stubbed = append(stubbed, "'restore --monitor'")
			}
			if args.InstanceType != "" {
				stubbed = append(stubbed, "'restore --instance-type'")
			}
			if len(stubbed) > 0 {
				return stubbedError(stubbed...)
			}
			args.Global = *global
			args.Folders = folders
			if args.ChangeTier {
				return app.ChangeTier(ctx, args)
			}
			return app.Restore(ctx, args)
		}),
	}
	f := cmd.Flags()
	f.BoolVarP(&args.AWS, "aws", "a", false, helpRestoreAWS)
	// --days is a string on purpose: argparse stores it without type=int.
	f.StringVarP(&args.Days, "days", "d", "30", helpRestoreDays)
	f.StringVarP(&args.InstanceType, "instance-type", "i", "", helpRestoreInstanceType)
	f.BoolVarP(&args.NoDownload, "no-download", "l", false, helpRestoreNoDownload)
	f.BoolVarP(&args.Monitor, "monitor", "m", false, helpRestoreMonitor)
	f.StringVarP(&args.RetrieveOpt, "retrieve-opt", "o", "Bulk", helpRestoreRetrieveOpt)
	f.BoolVarP(&args.Recursive, "recursive", "r", false, helpRestoreRecursive)
	f.BoolVarP(&args.ChangeTier, "change-tier", "t", false, helpRestoreChangeTier)
	return cmd
}

func newUpdateCmd(app App, global *GlobalArgs) *cobra.Command {
	args := UpdateArgs{}
	cmd := &cobra.Command{
		Use:     "update",
		Aliases: []string{"upd"},
		Short:   descUpdate,
		Long:    descUpdate,
		Args:    cobra.NoArgs,
		RunE: run(app, global, func(ctx context.Context, _ []string) error {
			args.Global = *global
			return app.Update(ctx, args)
		}),
	}
	cmd.Flags().BoolVarP(&args.Rclone, "rclone", "r", false, helpUpdateRclone)
	return cmd
}

func newTestCmd(app App, global *GlobalArgs) *cobra.Command {
	return &cobra.Command{
		Use:     "test",
		Aliases: []string{"tst"},
		Short:   descTest,
		Long:    descTest,
		Args:    cobra.NoArgs,
		RunE: run(app, global, func(ctx context.Context, _ []string) error {
			return app.Test(ctx, TestArgs{Global: *global})
		}),
	}
}
