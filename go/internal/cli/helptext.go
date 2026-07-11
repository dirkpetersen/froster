package cli

// Flag help strings, verbatim from go/testdata/cli-contract.json (which is
// dumped from the Python argparse tree in froster/froster.py). Do not edit by
// hand-tuning wording: contract_test.go asserts byte equality with the
// contract. Trailing whitespace inside some strings (e.g. helpArchiveNewer,
// helpRestoreRetrieveOpt) is intentional and present in the Python source.
//
// Exceptions:
//   - The global --cores/--mem help embeds the env-dependent computed default
//     and is therefore built with fmt.Sprintf in root.go (helpGlobalCoresFmt,
//     helpGlobalMemoryFmt).
//   - delete --bucket is argparse.SUPPRESS in Python ("==SUPPRESS==" in the
//     contract); the cobra flag is Hidden instead.
const (
	// global (root) flags
	helpGlobalCoresFmt       = "Number of cores to be allocated for the machine. (default=%d)"
	helpGlobalDebug          = "verbose output for all commands"
	helpGlobalDefaultProfile = "Select default profile"
	helpGlobalInfo           = "print froster and packages info"
	helpGlobalLogPrint       = "Print the log file to the screen"
	helpGlobalMemoryFmt      = "Amount of memory to be allocated for the machine in GB. (default=%d)"
	helpGlobalNoSlurm        = "do not submit a Slurm job, execute in the foreground."
	helpGlobalProfile        = "User this profile for the current session"
	helpGlobalVersion        = "print froster version"

	// archive
	helpArchiveForce     = "Force archiving of a folder that contains the .froster.md5sum file"
	helpArchiveLarger    = "Archive folders larger than <GiB>. This option\nworks in conjunction with --older <days>. If both\noptions are set froster will print a command that\nallows you to archive all matching folders at once."
	helpArchiveOlder     = "Archive folders that have not been accessed more than\n<days>. (optionally set --mtime to select folders that\nhave not been modified more than <days>). This option\nworks in conjunction with --larger <GiB>. If both\noptions are set froster will print a command that\nallows you to archive all matching folders at once."
	helpArchiveNewer     = "Archive folders that have been accessed within the last \n<days>. (optionally set --mtime to select folders that\nhave not been modified more than <days>). This option\nworks in conjunction with --larger <GiB>. If both \noptions are set froster will print a command that \nallows you to archive all matching folders at once."
	helpArchiveNIH       = "Search and Link Metadata from NIH Reporter"
	helpArchiveNIHRef    = "Use NIH Reporter reference for the current archive"
	helpArchiveMtime     = "Use modified file time (mtime) instead of accessed time (atime)"
	helpArchiveRecursive = "Archive the current folder and all sub-folders"
	helpArchiveReset     = "This will not download any data, but recusively reset a folder\nfrom previous (e.g. failed) archiving attempt.\nIt will delete .froster.md5sum and extract Froster.smallfiles.tar"
	helpArchiveNoTar     = "Do not move small files to tar file before archiving"
	helpArchiveDryRun    = "Execute a test archive without actually copying the data"

	// config
	helpConfigPrint  = "Print the current configuration"
	helpConfigReset  = "Delete the current configuration and start over"
	helpConfigImport = "Import a given configuration file"
	helpConfigExport = "Export the current configuration to the given directory"

	// delete
	helpDeleteRecursive = "Delete the current archived folder and all archived sub-folders"

	// index
	helpIndexForce       = "Force indexing"
	helpIndexPermissions = "Print read and write permissions for the provided folder(s)"
	helpIndexPwalkCopy   = "Directory where the pwalk CSV file should be copied to."

	// mount (and umount, which shares the flag set)
	helpMountAWS        = "Mount folder on new EC2 instance instead of local machine"
	helpMountList       = "List all mounted folders"
	helpMountMountPoint = "pick a custom mount point, this only works if you select a single folder."

	// restore
	helpRestoreAWS          = "Restore folder on new AWS EC2 instance instead of local machine"
	helpRestoreDays         = "Number of days to keep data in S3 One Zone-IA storage at $10/TiB/month (default: 30)"
	helpRestoreInstanceType = "The EC2 instance type is auto-selected, but you can pick any other type here"
	helpRestoreNoDownload   = "skip download to local storage after retrieval from Glacier"
	helpRestoreMonitor      = "Monitor EC2 server for cost and idle time."
	helpRestoreRetrieveOpt  = "More information at:\n    https://docs.aws.amazon.com/AmazonS3/latest/userguide/restoring-objects-retrieval-options.html\n    https://aws.amazon.com/s3/pricing/\n\nS3 GLACIER DEEP ARCHIVE or S3 INTELLIGENT-TIERING DEEP ARCHIVE ACCESS\n    Bulk:\n        - Within 48 hours retrieval            <-- default\n        - costs of $2.50 per TiB\n    Standard:\n        - Within 12 hours retrieval\n        - costs of $10 per TiB\n    Expedited:\n        - not supported \n\nS3 GLACIER FLEXIBLE RETRIEVAL or S3 INTELLIGENT-TIERING ARCHIVE ACCESS\n    Bulk:\n        - 5-12 hours retrieval\n        - costs of $2.50 per TiB\n    Standard:\n        - 3-5 hours retrieval\n        - costs of $10 per TiB\n    Expedited:\n        - 1-5 minutes retrieval\n        - costs of $30 per TiB\n\n\n    In addition to the retrieval cost, AWS will charge you about\n    $10/TiB/month for the duration you keep the data in S3.\n    (Costs in Summer 2024)"
	helpRestoreRecursive    = "Restore the current archived folder and all archived sub-folders"
	helpRestoreChangeTier   = "Change the storage tier of archived data without restoring it. Interactive TUI will guide tier selection."

	// update
	helpUpdateRclone = "Update rclone to latests version"
)

// Positional-argument help strings, verbatim from the contract. Cobra has no
// first-class positional help, so these are rendered in each command's Long
// text under an "Arguments:" heading.
const (
	helpArchiveFolders = "folders you would like to archive (separated by space), the last folder in this list is the target"
	helpDeleteFolders  = "folders (separated by space) from which you would like to delete files, you can only delete files that have been archived"
	helpIndexFolders   = "Folders you would like to index (separated by space), using the pwalk file system crawler"
	helpMountFolders   = "archived folders (separated by space) which you would like to mount."
	helpRestoreFolders = "folders you would like to to restore (separated by space)"
)

// Subcommand descriptions, matching the argparse subparser description texts
// in froster/froster.py (whitespace normalized for cobra's Long field).
const (
	descCredentials = "Check the current profile has valid credentials."
	descConfig      = "Froster configuration bootstrap. This command will guide you through the\nconfiguration of Froster. You can also import and export configurations."
	descIndex       = "Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file\nthat lists the largest folders. As this process is compute intensive the\nindex job will be automatically submitted to Slurm if the Slurm tools are\nfound."
	descArchive     = "Select from a list of large folders, that has been created by 'froster index', and\narchive a folder to S3/Glacier. Once you select a folder the archive job will be\nautomatically submitted to Slurm. You can also automate this process"
	descDelete      = "Remove data from a local filesystem folder that has been confirmed to\nbe archived (through checksum verification). Use this instead of deleting manually"
	descMount       = "Mount or unmount the remote S3 or Glacier storage in your local file system\nat the location of the original folder."
	descUmount      = "Mount or unmount the remote S3 or Glacier storage in your local file system\nat the location of the original folder."
	descRestore     = "Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need\nto download all data to local storage after the restore is complete.\nJust use the mount sub command."
	descUpdate      = "Check for froster updates"
	descTest        = "Test basic functionality of Froster"
)

// Root command description, matching the argparse main parser description.
const descRoot = "A user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems"
