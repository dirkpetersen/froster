# Variables
import os
import random
import string
import tempfile

def random_string(length=4):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

NAME_1 = "bob"
NAME_2 = "alice"

EMAIL_1 = "bob@bob.com"
EMAIL_2 = "alice@alice.com"

PROVIDER_1 = "AWS"
PROVIDER_2 = "AWS"

PROFILE_1 = "profile bob"
PROFILE_2 = "profile alice"

AWS_CREDENTIALS_PROFILE_1 = "bob"
AWS_CREDENTIALS_PROFILE_2 = "alice"

AWS_REGION_1 = "eu-west-2"
AWS_REGION_2 = "eu-west-2"

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET = os.getenv('AWS_SECRET')

USER_SECTION = 'USER'
AWS_SECTION = 'AWS'
SHARED_SECTION = 'SHARED'
NIH_SECTION = 'NIH'
S3_SECTION = 'S3'

S3_BUCKET_NAME_CONFIG_1 = 'froster-unittest-config-' + random_string(4)
S3_BUCKET_NAME_CONFIG_2 = 'froster-unittest-config-' + random_string(4)

S3_BUCKET_NAME_INDEX_1 = 'froster-unittest-index-' + random_string(4)
S3_BUCKET_NAME_INDEX_2 = 'froster-unittest-index-' + random_string(4)

S3_BUCKET_NAME_CREDENTIALS_1 = 'froster-unittest-credentials-' + random_string(4)
S3_BUCKET_NAME_CREDENTIALS_2 = 'froster-unittest-credentials-' + random_string(4)

S3_ARCHIVE_DIR_1 = 'froster-bob'
S3_ARCHIVE_DIR_2 = 'froster-alice'

S3_STORAGE_CLASS_1 = 'DEEP_ARCHIVE'
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
