package app

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/awsx"
	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/tui"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// Restore implements `froster restore` (spec §3.1 subcmd_restore plus
// main()'s credentials gate). The --change-tier route is dispatched by the
// CLI layer to ChangeTier.
func (a *App) Restore(ctx context.Context, args cli.RestoreArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	if err := s.credsGate(ctx); err != nil {
		return err
	}

	wf, err := s.workflow()
	if err != nil {
		return err
	}

	argv := a.Argv
	if len(folders) == 0 {
		rows := archiveRows(wf.DB.All(), true)
		if len(rows) == 0 {
			s.log.Logf("%s", "No archives available.")
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
		argv = append(append([]string{}, argv...), folder)
	}

	// --days reaches boto as a string in Python (no type=int); parse it
	// here. DOCUMENTED DEVIATION: a non-numeric value fails up front with
	// a clear message instead of blowing up per-object inside boto.
	days, err := strconv.Atoi(strings.TrimSpace(args.Days))
	if err != nil {
		s.log.Logf("\nError: invalid --days value %q: not a number\n", args.Days)
		return exit1()
	}

	aws, err := s.awsClient(ctx)
	if err != nil {
		s.log.Logf("Error: %v", err)
		return exit1()
	}
	wf.Glacier = &glacierAdapter{ctx: ctx, client: aws}
	wf.ScheduleRestore = func(scheduled string) {
		if err := s.submitSlurm(ctx, "restore", folders, argv, scheduled); err != nil {
			fmt.Fprintf(a.stderr(), "Error: scheduling restore retry (%s) failed\n", scheduled)
		}
	}

	return wrapWorkflowErr(wf.Restore(ctx, folders, workflow.RestoreOptions{
		Recursive:   args.Recursive,
		Days:        int32(days),
		RetrieveOpt: args.RetrieveOpt,
		NoDownload:  args.NoDownload,
		NoSlurm:     args.Global.NoSlurm,
	}))
}

// glacierAdapter narrows awsx.Client to the workflow.GlacierClient
// interface (binding the context, which the workflow API omits).
type glacierAdapter struct {
	ctx    context.Context
	client *awsx.Client
}

func (g *glacierAdapter) TriggerGlacierRestore(bucket, prefix string, days int32, tier string) (workflow.GlacierResult, error) {
	res, err := g.client.TriggerGlacierRestore(g.ctx, bucket, prefix, days, tier)
	return workflow.GlacierResult{
		Triggered:    res.Triggered,
		InProgress:   res.InProgress,
		Restored:     res.Restored,
		NotGlacier:   res.NotGlacier,
		NotSupported: res.NotSupported,
	}, err
}

// ChangeTier implements `froster restore --change-tier`
// (Commands._change_storage_tier).
func (a *App) ChangeTier(ctx context.Context, args cli.RestoreArgs) error {
	s, err := a.newSession(args.Global)
	if err != nil {
		return err
	}
	folders := cleanPaths(args.Folders)

	if err := s.credsGate(ctx); err != nil {
		return err
	}

	db, err := s.openDB()
	if err != nil {
		return err
	}

	if len(folders) == 0 {
		rows := archiveRows(db.All(), true)
		if len(rows) == 0 {
			s.log.Logf("%s", "No archives available.")
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

	aws, err := s.awsClient(ctx)
	if err != nil {
		s.log.Logf("Error: %v", err)
		return exit1()
	}

	for _, folder := range folders {
		entry := db.Get(folder)
		if entry == nil {
			s.log.Logf("\nError: Folder %s is not archived\n", folder)
			return exit1()
		}

		currentTier := entry.S3StorageClass
		if currentTier == "GLACIER" || currentTier == "DEEP_ARCHIVE" {
			s.log.Logf("\nError: Cannot change storage tier from %s", currentTier)
			s.log.Logf("%s", "Moving data FROM Glacier or Deep Archive is not allowed.")
			s.log.Logf("%s", "Please restore the data first if you need to change its storage tier.\n")
			return exit1()
		}

		remote, err := archivedb.ParseRemote(entry.ArchiveFolder)
		if err != nil {
			s.log.Logf("Error: %v", err)
			return exit1()
		}

		s.log.Logf("\nAnalyzing archived folder: %s", folder)
		s.log.Logf("  Current tier: %s", currentTier)
		s.log.Logf("  Bucket: %s", remote.Bucket)
		s.log.Logf("  Prefix: %s", remote.Prefix)
		s.log.Logf("%s", "\n  Counting objects...")

		objects, err := aws.ListObjects(ctx, remote.Bucket, remote.Prefix)
		if err != nil {
			s.log.Logf("Error: %v", err)
			return exit1()
		}
		var totalSize int64
		for _, o := range objects {
			totalSize += o.Size
		}
		s.log.Logf("    Found %d objects, %.2f GiB\n", len(objects), float64(totalSize)/(1<<30))

		newTier, err := tui.SelectStorageTier(ctx, tui.TierSelectorOptions{
			CurrentTier:    currentTier,
			Folder:         folder,
			TotalSizeBytes: totalSize,
			ObjectCount:    int64(len(objects)),
		})
		if err != nil {
			return err
		}
		if newTier == "" {
			s.log.Logf("%s", "\nStorage tier change cancelled\n")
			return exit1()
		}

		if _, err := aws.ChangeStorageClass(ctx, remote.Bucket, remote.Prefix, newTier, currentTier); err != nil {
			s.log.Logf("Error: %v", err)
			s.log.Logf("%s", "\nStorage tier change failed\n")
			return exit1()
		}

		// Update the database. DOCUMENTED DEVIATION: for a subfolder of a
		// recursive archive Python re-keys the parent entry under the
		// subfolder path (duplicating it); Go updates the parent entry in
		// place (keyed by its own local_folder).
		entry.S3StorageClass = newTier
		if err := db.Upsert(entry); err != nil {
			s.log.Logf("Error: %v", err)
			return exit1()
		}

		s.log.Logf("%s", "\nSuccessfully changed storage tier")
		s.log.Logf("  Database updated: %s\n", db.Path())
	}
	return nil
}
