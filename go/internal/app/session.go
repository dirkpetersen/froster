package app

import (
	"context"
	"fmt"
	"os"

	"github.com/dirkpetersen/froster/go/internal/archivedb"
	"github.com/dirkpetersen/froster/go/internal/awsx"
	"github.com/dirkpetersen/froster/go/internal/cli"
	"github.com/dirkpetersen/froster/go/internal/config"
	"github.com/dirkpetersen/froster/go/internal/logging"
	"github.com/dirkpetersen/froster/go/internal/slurm"
	"github.com/dirkpetersen/froster/go/internal/transfer"
	"github.com/dirkpetersen/froster/go/internal/workflow"
)

// session is the per-invocation state: resolved paths, parsed config, the
// selected profile, and lazily built AWS/transfer clients. It mirrors the
// ConfigManager+AWSBoto+Rclone objects Python constructs in main().
type session struct {
	app    *App
	global cli.GlobalArgs

	paths    config.Paths
	cfg      *config.Config
	log      *logging.Logger
	profile  string // canonical "profile <name>", or "" when unconfigured
	prof     config.Profile
	region   string
	endpoint string

	aws *awsx.Client // set by credsGate
}

// newSession loads config.ini, resolves the profile (--profile beats
// [DEFAULT_PROFILE]) and the region/endpoint from ~/.aws, and prepares the
// logger.
func (a *App) newSession(global cli.GlobalArgs) (*session, error) {
	paths, err := config.DefaultPaths()
	if err != nil {
		return nil, err
	}
	cfg, err := config.Load(paths)
	if err != nil {
		return nil, err
	}

	logger := logging.New(paths.LogFile(), global.Debug || os.Getenv("DEBUG") == "1")

	profile, err := cfg.ResolveProfile(global.Profile)
	if err != nil {
		// Python: log(f'\nError: "{profile}" does not exist in the
		// configuration file (remember case sensitive)\n'); sys.exit(1)
		logger.Logf("\nError: %v\n", err)
		return nil, exit1()
	}

	s := &session{
		app:     a,
		global:  global,
		paths:   paths,
		cfg:     cfg,
		log:     logger,
		profile: profile,
	}
	if profile != "" {
		prof, err := cfg.Profile(profile)
		if err != nil {
			logger.Logf("\nError: %v\n", err)
			return nil, exit1()
		}
		s.prof = prof
		aws := paths.AWS()
		s.region = aws.Region(prof.Credentials)
		s.endpoint = aws.Endpoint(prof.Credentials)
	}
	return s, nil
}

// awsClient builds (once) the awsx control-plane client for the session
// profile.
func (s *session) awsClient(ctx context.Context) (*awsx.Client, error) {
	if s.aws != nil {
		return s.aws, nil
	}
	client, err := awsx.New(ctx, awsx.Options{
		Profile:  s.prof.Credentials,
		Region:   s.region,
		Endpoint: s.endpoint,
		Provider: s.prof.Provider,
	})
	if err != nil {
		return nil, err
	}
	s.aws = client
	return client, nil
}

// listBuckets performs the credential probe (Python check_credentials:
// s3_client.list_buckets() must succeed).
func (s *session) listBuckets(ctx context.Context) error {
	client, err := s.awsClient(ctx)
	if err != nil {
		return err
	}
	_, err = client.ListBuckets(ctx)
	return err
}

// credsGate reproduces main()'s credentials gate for archive/restore/
// delete/mount (spec §0.7): ListBuckets must succeed, otherwise the
// invalid-credentials block is printed and the process exits 1.
func (s *session) credsGate(ctx context.Context) error {
	failed := s.profile == ""
	if !failed {
		failed = s.listBuckets(ctx) != nil
	}
	if !failed {
		return nil
	}
	if s.profile == "" {
		// check_credentials' own no-profile message comes first.
		s.log.Logf("%s", "\nError: No profile found. Please configure an S3 profile using the command:")
		s.log.Logf("%s", "    froster config\n")
	} else {
		s.log.Logf("%s", "\nError: Invalid credentials.")
		s.log.Logf("  Profile: %s", s.profile)
		s.log.Logf("  Provider: %s", s.prof.Provider)
		s.log.Logf("  Credentials: %s", s.prof.Credentials)
		s.log.Logf("  Endpoint: %s\n", s.endpoint)
	}
	s.log.Logf("%s", "\nYou can configure the credentials using the command:")
	s.log.Logf("%s", "    froster config\n")
	return exit1()
}

// s3Config assembles the transfer.S3Config for the session profile from
// ~/.aws/credentials, mirroring the RCLONE_S3_* environment Python builds
// (spec §0.5). Missing keys reproduce the Python error and exit 1.
func (s *session) s3Config() (transfer.S3Config, error) {
	aws := s.paths.AWS()
	accessKey := aws.Credential(s.prof.Credentials, "aws_access_key_id")
	secretKey := aws.Credential(s.prof.Credentials, "aws_secret_access_key")
	if accessKey == "" || secretKey == "" {
		s.log.Logf("%s", "\nError: No credentials found for Rclone to use.")
		return transfer.S3Config{}, exit1()
	}
	return transfer.S3Config{
		Provider:        s.prof.Provider,
		Endpoint:        s.endpoint,
		Region:          s.region,
		AccessKeyID:     accessKey,
		SecretAccessKey: secretKey,
		StorageClass:    s.prof.StorageClass,
	}, nil
}

// openDB opens the (possibly shared) archive database.
func (s *session) openDB() (*archivedb.DB, error) {
	db, err := archivedb.Load(s.cfg.ArchiveJSON())
	if err != nil {
		// DOCUMENTED DEVIATION: Python logs "Cannot read {path}, file
		// corrupt?" and silently pretends the DB is empty; Go refuses to
		// continue against a corrupt archive database.
		s.log.Logf("Error: %v", err)
		return nil, exit1()
	}
	return db, nil
}

// workflow builds a fully wired Workflow (engine + DB) for the data
// commands.
func (s *session) workflow() (*workflow.Workflow, error) {
	s3cfg, err := s.s3Config()
	if err != nil {
		return nil, err
	}
	db, err := s.openDB()
	if err != nil {
		return nil, err
	}
	w := &workflow.Workflow{
		Log:          s.log,
		Stderr:       s.app.stderr(),
		Engine:       transfer.New(s3cfg),
		DB:           db,
		Provider:     s.prof.Provider,
		Profile:      s.profile,
		Credentials:  s.prof.Credentials,
		Endpoint:     s.endpoint,
		Bucket:       s.prof.BucketName,
		ArchiveDir:   s.prof.ArchiveDir,
		StorageClass: s.prof.StorageClass,
		Email:        s.cfg.Email(),
		User:         config.Whoami(),
		Cores:        s.global.Cores,
	}
	w.MountFn = w.DefaultMountFn(s3cfg)
	w.SlurmInstalled = slurm.Installed
	return w, nil
}

// bareWorkflow builds a Workflow without S3/DB wiring, for commands that
// need neither (index, umount).
func (s *session) bareWorkflow() *workflow.Workflow {
	return &workflow.Workflow{
		Log:    s.log,
		Stderr: s.app.stderr(),
		Cores:  s.global.Cores,
	}
}

// slurmConfig assembles the [SLURM] batch settings plus the user email.
func (s *session) slurmConfig() slurm.Config {
	return slurm.Config{
		Partition:     s.cfg.SlurmPartition(),
		QOS:           s.cfg.SlurmQOS(),
		WalltimeDays:  int(s.cfg.SlurmWalltimeDays()),
		WalltimeHours: int(s.cfg.SlurmWalltimeHours()),
		Lscratch:      s.cfg.SlurmLscratch(),
		LscratchMkdir: s.cfg.LscratchMkdir(),
		LscratchRmdir: s.cfg.LscratchRmdir(),
		LscratchRoot:  s.cfg.LscratchRoot(),
		Email:         s.cfg.Email(),
	}
}

// submitSlurm submits the current froster invocation as a Slurm batch job
// (Python Archiver._slurm_cmd + Slurm.submit_job) and prints the SLURM JOB
// info block (spec §6.1). argv is the CLI argument list to replay
// (normally the original command line, with interactively selected folders
// appended by the caller).
func (s *session) submitSlurm(ctx context.Context, cmdType string, folders, argv []string, scheduled string) error {
	opts := slurm.SubmitOptions{
		CmdType:    cmdType,
		Label:      slurm.LabelForFolder(folders[0]),
		ShortLabel: slurm.ShortLabelForFolder(folders[0]),
		Cores:      s.global.Cores,
		MemGB:      s.global.Memory,
		Args:       argv,
		OutputDir:  s.paths.SlurmDir(),
		Begin:      scheduled,
		Debug:      s.global.Debug,
		Config:     s.slurmConfig(),
	}
	jobID, err := slurm.Submit(ctx, opts)
	if err != nil {
		fmt.Fprintf(s.app.stderr(), "Error: %v\n", err)
		return exit1()
	}

	s.log.Logf("%s", "\nSLURM JOB\n")
	s.log.Logf("  ID: %s", jobID)
	s.log.Logf("  Type: %s", cmdType)
	s.log.Logf("  Check status: %q", "squeue -j "+jobID)
	s.log.Logf("  Check output: %q", "tail -n 100 -f "+opts.OutputFile(jobID))
	s.log.Logf("  Cancel the job: %q\n", "scancel "+jobID)
	return nil
}
