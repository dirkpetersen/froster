import sys
from froster import *
from config import *
from argparse import Namespace
import os
import shutil
from unittest.mock import patch


import warnings
warnings.filterwarnings("always", category=ResourceWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)

# VARIABLES
S3_BUCKET_NAME = "froster-unittest"
S3_BUCKET_NAME = "froster-unittest-2"

class FrosterConfiguration():

    def init_froster_objects(self):
        '''Initialize the froster objects.'''

        self.cmd = Commands()
        self.parser = self.cmd.parse_arguments()
        self.args = self.parser.parse_args()
        self.cfg = ConfigManager()
        self.arch = Archiver(self.args, self.cfg)
        self.aws = AWSBoto(self.args, self.cfg, self.arch)

        return True

    def create_fresh_directories(self):
        '''Reset the directories.'''

        # Create a fresh data directory
        if hasattr(self.cfg, 'data_dir') and os.path.exists(self.cfg.data_dir):
            shutil.rmtree(self.cfg.data_dir)
        os.makedirs(self.cfg.data_dir, exist_ok=True, mode=0o775)

        # Create a fresh config directory
        if hasattr(self.cfg, 'config_dir') and os.path.exists(self.cfg.config_dir):
            shutil.rmtree(self.cfg.config_dir)
        os.makedirs(self.cfg.config_dir, exist_ok=True, mode=0o775)

        # Create a fresh shared directory
        if os.path.exists(SHARED_DIR):
            shutil.rmtree(SHARED_DIR)
        os.makedirs(SHARED_DIR, exist_ok=True, mode=0o775)

        # Create a fresh aws directory
        if os.path.exists(AWS_DEFAULT_PATH):
            shutil.rmtree(AWS_DEFAULT_PATH)
        os.makedirs(AWS_DEFAULT_PATH, exist_ok=True, mode=0o775)


    def delete_directories(self):
        '''Delete the directories.'''

        if hasattr(self, 'cfg'):
            if hasattr(self.cfg, 'aws_dir') and os.path.exists(self.cfg.aws_dir):
                shutil.rmtree(self.cfg.aws_dir)

            if hasattr(self.cfg, 'config_dir') and os.path.exists(self.cfg.config_dir):
                shutil.rmtree(self.cfg.config_dir)

            if hasattr(self.cfg, 'data_dir') and os.path.exists(self.cfg.data_dir):
                shutil.rmtree(self.cfg.data_dir)

        if os.path.exists(SHARED_DIR):
            shutil.rmtree(SHARED_DIR)

        if os.path.exists(AWS_DEFAULT_PATH):
            shutil.rmtree(AWS_DEFAULT_PATH)


    def deinit_froster_objects(self):
        '''Deinitialize the froster objects.'''

        # Delete initizalized objects
        if hasattr(self, 'parser'):
            del self.parser
        if hasattr(self, 'args'):
            del self.args
        if hasattr(self, 'cfg'):
            del self.cfg
        if hasattr(self, 'arch'):
            del self.arch
        if hasattr(self, 'aws'):
            del self.aws


    def delete_buckets(self):
        '''Delete created S3 buckets if they exists.'''

        if self.aws.check_credentials():

            # Get the buckets list
            s3_buckets = self.aws.get_buckets()

            # Delete the buckets if they exists
            if S3_BUCKET_NAME in s3_buckets:
                self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME)
            if S3_BUCKET_NAME_2 in s3_buckets:
                self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_2)

    def set_default_cli_arguments(self):
        '''- Set default cli arguments.'''

        self.cmd.args = Namespace(cores=4, debug=False, info=False, memory=64, noslurm=False, aws_profile='', version=False,
                                subcmd='config', aws=False, monitor=False, nih=False, print=False, s3=False, shared=False, slurm=False, user=False)


    @patch('builtins.print')
    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def set_user(self, mock_print, mock_text):
        '''- Set the user and email in the configuration file.'''
    
        # Call set_user method
        return self.cfg.set_user()

    @patch('builtins.print')
    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def set_aws(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Set a new AWS profile with valid credentials.'''

        # Call set_aws method
        return self.cfg.set_aws(self.aws)

    @patch('builtins.print')
    @patch('inquirer.confirm', side_effect=[True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def set_shared(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to False and then to True in the configuration file.'''

        # Call set_shared method
        return self.cfg.set_shared()
    
    @patch('builtins.print')
    @patch('inquirer.confirm', side_effect=[False])
    def set_nih(self, mock_print, mock_confirm):
        '''- Set the NIH flag to True and then to False.'''

        # Call set_user method
        return self.cfg.set_nih()

    @patch('builtins.print')
    @patch('inquirer.list_input', side_effect=['+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.text', side_effect=[S3_BUCKET_NAME, S3_ARCHIVE_DIR])
    def set_s3(self, mock_print, mock_list, mock_text):
        '''- Set a new S3 bucket.'''

        # Call set_s3 method
        if not self.cfg.set_s3(self.aws):
            return False

        # Get the buckets list
        s3_buckets = self.aws.get_buckets()

        if S3_BUCKET_NAME not in s3_buckets:
            return False
        else:
            return True



def config_froster(caller_name="utils_froster_full_config"):
    global S3_BUCKET_NAME
    S3_BUCKET_NAME = S3_BUCKET_NAME + caller_name

    global S3_BUCKET_NAME_2
    S3_BUCKET_NAME_2 = S3_BUCKET_NAME_2 + "-" + caller_name
    
    froster = FrosterConfiguration()

    froster.init_froster_objects()

    froster.create_fresh_directories()

    froster.set_default_cli_arguments()

    if not froster.set_user():
        print("Error: set_user failed\n")
        return False

    if not froster.set_aws():
        print("Error: set_aws failed\n")
        return False

    if not froster.set_shared():
        print("Error: set_shared failed\n")
        return False

    if not froster.set_nih():
        print("Error: set_nih failed\n")
        return False

    froster.delete_buckets()

    if not froster.set_s3():
        print("Error: set_s3 failed\n")
        return False
    
    print("Configuration successful\n")

    return True

if __name__ == "__main__":
    config_froster()
