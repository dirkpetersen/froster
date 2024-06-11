# Variables
import os
import tempfile


NAME = "Bob"
NAME_2 = "Alice"
EMAIL = "bob@bob.com"
EMAIL_2 = "alice@alice.com"

AWS_DEFAULT_PATH = os.path.join(tempfile.gettempdir(), '.aws')
AWS_REGION = "eu-west-1"
AWS_REGION_2 = "eu-west-2"
AWS_PROFILE = "froster-unittest-bob"
AWS_PROFILE_2 = "froster-unittest-alice"

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET = os.getenv('AWS_SECRET')

USER_SECTION = 'USER'
AWS_SECTION = 'AWS'
SHARED_SECTION = 'SHARED'
NIH_SECTION = 'NIH'
S3_SECTION = 'S3'

S3_ARCHIVE_DIR = 'froster_bob'
S3_ARCHIVE_DIR_2 = 'froster_alice'
S3_STORAGE_CLASS = 'DEEP_ARCHIVE'
S3_STORAGE_CLASS_2 = 'GLACIER'

SLURM_WALLTIME_DAYS = 8
SLURM_WALLTIME_HOURS = 1
SLURM_PARTITION = 'test_partition'
SLURM_QOS = 'test_qos'

SLURM_LOCAL_SCRATCH = 'test_lscratch'
SLURM_SCRIPT_SCRATCH = 'test_script_scratch'
SLURM_SCRIPT_TEARS_DOWN = 'test_script_tears_down'
SLURM_ROOT = 'test_root'

SHARED_DIR = os.path.join(tempfile.gettempdir(), 'shared_dir')
SHARED_CONFIG_FILE = os.path.join(SHARED_DIR, 'shared_config.ini')
