from froster import *
from config import *
from argparse import Namespace
import configparser
import os
import shutil
from unittest.mock import patch
import unittest


##################
# FUNCTION UTILS #
##################

def init_froster(self):
    '''Initialize the froster objects.'''

    self.cmd = Commands()
    self.parser = self.cmd.parse_arguments()
    self.args = self.parser.parse_args()
    self.cfg = ConfigManager()
    self.arch = Archiver(self.args, self.cfg)
    self.aws = AWSBoto(self.args, self.cfg, self.arch)

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


def deinit_froster(self):
    '''Deinitialize the froster objects.'''

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
        if S3_BUCKET_NAME_CONFIG in s3_buckets:
            self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_CONFIG)
        if S3_BUCKET_NAME_CONFIG_2 in s3_buckets:
            self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_CONFIG_2)


def check_ini_file(self, ini_file, section, key, value):
    '''Check the value of a key in a section of an ini file.'''

    config = configparser.ConfigParser()
    config.read(ini_file)
    self.assertIn(section, config.sections())
    self.assertEqual(config.get(section, key), value)

#################
# TESTS CLASSES #
#################

@patch('builtins.print')
class TestConfig(unittest.TestCase):
    '''Test the subcmd_confing method.'''

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):

        # Check if the AWS credentials are set
        if AWS_ACCESS_KEY_ID is None or AWS_SECRET is None:
            raise ValueError("AWS credentials are not set")

    # Method executed before every test
    def setUp(self):

        # Initialize the froster objects
        init_froster(self)

        # Make sure we have credentials to be able to delete buckets
        self.set_credentials()

        # Delete any existing buckets
        delete_buckets(self)

        # NOTE: This is a workaround. We needed to set the credentials to be able to delete possible buckets that
        # were created in previous tests. However, we don't want to set the credentials for the current test.
        # Therefore, we need to delete the credentials after deleting the buckets.

        # Deinitialize the froster objects
        deinit_froster(self)

        # Initialize the froster objects
        init_froster(self)



    # Method executed after every test
    def tearDown(self):

        # Delete any existing buckets
        delete_buckets(self)

        # Deinitialize the froster objects
        deinit_froster(self)

    @patch('builtins.print')
    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def set_credentials(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Set a new AWS profile with valid credentials.'''

        # Call set_aws method
        self.assertTrue(self.cfg.set_aws(self.aws))
        self.assertTrue(self.aws.check_credentials())


    # HELPER RUNS

    def helper_set_default_cli_arguments(self):
        '''- Set default cli arguments.'''

        self.cmd.args = Namespace(cores=4, debug=False, info=False, memory=64, noslurm=False, aws_profile='', version=False,
                                  subcmd='config', aws=False, monitor=False, nih=False, print=False, s3=False, shared=False, slurm=False, user=False)

    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.confirm', side_effect=[False, False])
    def helper_run_subcmd_config(self, mock_print, mock_text, mock_prompt, mock_list, mock_confirm):
        '''- Helper that sets full configuration'''

        # Check that nothing is set yet
        self.assertFalse(self.cfg.user_init)
        self.assertFalse(self.cfg.aws_init)
        self.assertFalse(self.cfg.nih_init)
        self.assertFalse(self.cfg.s3_init)

        # Mock the CLI default arguments
        self.helper_set_default_cli_arguments()

        # Mock the "froster config" command
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}, {'shared_dir': SHARED_DIR}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.confirm', side_effect=[True, False])
    def helper_run_subcmd_config_shared(self, mock_print, mock_text, mock_prompt, mock_list, mock_confirm):
        '''- Helper that sets full configuration with shared directory'''

        # Check that nothing is set yet
        self.assertFalse(self.cfg.user_init)
        self.assertFalse(self.cfg.aws_init)
        self.assertFalse(self.cfg.nih_init)
        self.assertFalse(self.cfg.s3_init)

        # Mock the CLI default arguments
        self.helper_set_default_cli_arguments()

        # Mock the "froster config" command
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR, NAME_2, EMAIL_2])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}, {'shared_dir': SHARED_DIR}, {'aws_dir': AWS_DEFAULT_PATH}, {'shared_dir': SHARED_DIR}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS, AWS_PROFILE, AWS_REGION])
    @patch('inquirer.confirm', side_effect=[True, False, True, True])
    def helper_run_subcmd_config_shared_existing_config(self, mock_print, mock_text, mock_prompt, mock_list, mock_confirm):
        '''- Helper that sets full configuration with a shared directory where there is already a shared configuration file'''

        # Check that nothing is set yet
        self.assertFalse(self.cfg.user_init)
        self.assertFalse(self.cfg.aws_init)
        self.assertFalse(self.cfg.nih_init)
        self.assertFalse(self.cfg.s3_init)

        # Mock the CLI default arguments
        self.helper_set_default_cli_arguments()

        # Mock the "froster config" command
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

        # Mock the "froster config" command again (now we have an existing shared configuration file)
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

    @patch('inquirer.text', side_effect=[NAME_2, EMAIL_2, AWS_PROFILE_2, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG_2, S3_ARCHIVE_DIR_2])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION_2, '+ Create new bucket', S3_STORAGE_CLASS_2])
    @patch('inquirer.confirm', side_effect=[True, False, False])
    def helper_run_subcmd_config_overwrite(self, mock_print, mock_text, mock_prompt, mock_list, mock_confirm):
        '''- Helper that sets full configuration and overwrites the current configuration'''

        # Mock the CLI default arguments
        self.helper_set_default_cli_arguments()

        # Mock the "froster config" command
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}, {'shared_dir': SHARED_DIR}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.confirm', side_effect=[True, True, False])
    def helper_run_subcmd_config_shared_move_froster_archives_json(self, mock_print, mock_text, mock_prompt, mock_list, mock_confirm):
        '''- Helper that sets full configuration with a shared directory and moves the froster-archives.json file'''

        # Check that nothing is set yet
        self.assertFalse(self.cfg.user_init)
        self.assertFalse(self.cfg.aws_init)
        self.assertFalse(self.cfg.nih_init)
        self.assertFalse(self.cfg.s3_init)

        # Mock the CLI default arguments
        self.helper_set_default_cli_arguments()

        # Assert that the froster-archives.json file is set to not shared path
        self.assertEqual(self.cfg.archive_json, os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name))

        # Assert that the froster-archives.json file does not exist yet
        self.assertTrue(not os.path.exists(self.cfg.archive_json))

        # Create a mock froster-archives.json file
        with open(self.cfg.archive_json, 'w') as f:
            f.write('Hello, world!')

        # Assert that the froster-archives.json file exists
        self.assertTrue(os.path.exists(self.cfg.archive_json))

        # Mock the "froster config" command
        self.assertTrue(self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws))

    @patch('inquirer.confirm', side_effect=[True, True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def helper_run_subcmd_config_shared_move_config_sections(self, mock_print, mock_confirm, mock_prompt):
        '''- Helper that sets full configuration and moves the config sections to the shared directory'''

        # Call set_shared method and set the shared flag to True
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

    # HELPER CHECKS

    def helper_check_subcmd_config(self):

        # Check that everything is set
        self.assertTrue(self.cfg.user_init)
        self.assertTrue(self.cfg.aws_init)
        self.assertTrue(self.cfg.nih_init)
        self.assertTrue(self.cfg.s3_init)

        # USER config checks
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL)

        # AWS config checks
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

        # SHARED config checks
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'False')

        # NIH config checks
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'False')

        # S3 config checks
        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS)

        # Check the bucket was created
        s3_buckets = self.aws.get_buckets()
        self.assertIn(S3_BUCKET_NAME_CONFIG, s3_buckets)

    def helper_check_subcmd_config_shared(self):

        # Check that everything is set
        self.assertTrue(self.cfg.user_init)
        self.assertTrue(self.cfg.aws_init)
        self.assertTrue(self.cfg.nih_init)
        self.assertTrue(self.cfg.s3_init)

        # USER config checks
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL)

        # AWS config checks
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

        # SHARED config checks
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', SHARED_CONFIG_FILE)

        # NIH config checks
        check_ini_file(self, self.cfg.shared_config_file,
                       NIH_SECTION, 'is_nih', 'False')

        # S3 config checks
        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS)

        # Check the bucket was created
        s3_buckets = self.aws.get_buckets()
        self.assertIn(S3_BUCKET_NAME_CONFIG, s3_buckets)

    def helper_check_subcmd_config_shared_existing_config(self):

        # Check that everything is set
        self.assertTrue(self.cfg.user_init)
        self.assertTrue(self.cfg.aws_init)
        self.assertTrue(self.cfg.nih_init)
        self.assertTrue(self.cfg.s3_init)

        # USER config checks
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME_2)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL_2)

        # AWS config checks
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

        # SHARED config checks
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', SHARED_CONFIG_FILE)

        # NIH config checks
        check_ini_file(self, self.cfg.shared_config_file,
                       NIH_SECTION, 'is_nih', 'False')

        # S3 config checks
        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS)

        # Check the bucket was created
        s3_buckets = self.aws.get_buckets()
        self.assertIn(S3_BUCKET_NAME_CONFIG, s3_buckets)

    def helper_check_subcmd_config_overwrite(self):

        # Check that everything is set
        self.assertTrue(self.cfg.user_init)
        self.assertTrue(self.cfg.aws_init)
        self.assertTrue(self.cfg.nih_init)
        self.assertTrue(self.cfg.s3_init)

        # USER config checks
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME_2)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL_2)

        # AWS config checks
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE_2)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION_2)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE_2,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE_2, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE_2, 'region', AWS_REGION_2)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE_2, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

        # SHARED config checks
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'False')

        # NIH config checks
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'False')

        # S3 config checks
        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG_2)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR_2)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS_2)

        # Check the bucket was created
        s3_buckets = self.aws.get_buckets()
        self.assertIn(S3_BUCKET_NAME_CONFIG_2, s3_buckets)

    def helper_check_subcmd_config_shared_move_froster_archives_json(self):

        self.helper_check_subcmd_config_shared()

        # Assert that the froster-archives.json is still in the user directory
        self.assertTrue(os.path.exists(os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)))

        # Assert that the froster-archives.json has been copied to the shared directory
        self.assertTrue(os.path.exists(os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)))

    # TESTS

    def test_subcmd_config(self, mock_print):
        '''- Set full configuration'''

        self.helper_run_subcmd_config(None)

        self.helper_check_subcmd_config()

    def test_subcmd_config_overwrite(self, mock_print,):
        '''- Set full configuration overwritting current configuration'''

        self.helper_run_subcmd_config(None)

        self.helper_check_subcmd_config()

        self.helper_run_subcmd_config_overwrite(None)

        self.helper_check_subcmd_config_overwrite()

    def test_subcmd_config_shared(self, mock_print):
        '''- Set full configuration with shared directory'''

        self.helper_run_subcmd_config(None)

        self.helper_check_subcmd_config()

    def test_subcmd_config_shared_existing_config(self, mock_print):
        '''- Set full configuration with shared directory where there is already a shared configuration file'''

        self.helper_run_subcmd_config_shared_existing_config(None)

        self.helper_check_subcmd_config_shared_existing_config()

    def test_subcmd_config_shared_move_froster_archives_json(self, mock_print):
        '''- Set full configuration with shared directory moving the froster-archives.json file'''

        self.helper_run_subcmd_config_shared_move_froster_archives_json(None)

        self.helper_check_subcmd_config_shared_move_froster_archives_json()

    def test_subcmd_config_shared_move_config(self, mock_print):
        '''- Set full configuration and move config to the shared directory config file'''

        # Not shared full configuration
        self.helper_run_subcmd_config(None)

        # Set share config so the config sections are moved to the shared directory
        self.helper_run_subcmd_config_shared_move_config_sections(None)

        # Check we are in the shared directory scenario
        self.helper_check_subcmd_config_shared()


@patch('builtins.print')
class TestConfigUser(unittest.TestCase):
    '''Test the set_user method.'''

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_set_user(self, mock_print, mock_text):
        '''- Set the user and email in the configuration file.'''

        # Check that the user is not set
        self.assertFalse(self.cfg.user_init)

        # Call set_user method
        self.assertTrue(self.cfg.set_user())

        # Check that the user is set
        self.assertTrue(self.cfg.user_init)

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL)


@patch('builtins.print')
class TestConfigAWS(unittest.TestCase):
    '''Test the set_aws method.'''

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):
        if AWS_ACCESS_KEY_ID is None or AWS_SECRET is None:
            raise ValueError("AWS credentials are not set")

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Set a new AWS profile with valid credentials.'''

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Call set_aws method
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, 'wrong_access_key_id', 'wrong_secret'])
    def test_set_aws_invalid_credentials(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Set a new AWS profile with invalid credentials.'''

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Set valid credentials
        self.assertFalse(self.cfg.set_aws(self.aws))

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Check that the configuration files were not updated
        config = configparser.ConfigParser()
        config.read(self.cfg.aws_credentials_file)
        self.assertNotIn(AWS_PROFILE, config.sections())

    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, AWS_PROFILE, AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_select_profile(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Select profile from AWS configuration file.'''

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Call set_aws methon and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Call set_aws method and select an existing profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile', AWS_REGION_2])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE_2, AWS_ACCESS_KEY_ID, AWS_SECRET])
    @patch('inquirer.confirm', side_effect=['y'])
    def test_set_aws_overwrite_profile(self, mock_print, mock_prompt, mock_list, mock_text, mock_confirm):
        '''- Overwrite an existing AWS profile.'''

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Call set_aws method and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Call set_aws method and overwrite the existing profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE_2)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION_2)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE_2,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE_2, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE_2, 'region', AWS_REGION_2)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE_2, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())

    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile'])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE])
    @patch('inquirer.confirm', side_effect=[False])
    def test_set_aws_do_not_overwrite_profile(self, mock_print, mock_prompt, mock_list, mock_text, mock_confirm):
        '''- Do not overwrite an existing AWS profile.'''

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Call set_aws method and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Call set_aws method and do not overwrite the existing profile
        self.assertFalse(self.cfg.set_aws(self.aws))

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_profile', AWS_PROFILE)

        check_ini_file(self, self.cfg.config_file,
                       AWS_SECTION, 'aws_region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_credentials_file, AWS_PROFILE,
                       'aws_access_key_id', AWS_ACCESS_KEY_ID)

        check_ini_file(self, self.cfg.aws_credentials_file,
                       AWS_PROFILE, 'aws_secret_access_key', AWS_SECRET)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'region', AWS_REGION)

        check_ini_file(self, self.cfg.aws_config_file,
                       AWS_PROFILE, 'output', 'json')

        self.assertTrue(self.aws.check_credentials())


@patch('builtins.print')
class TestConfigShared(unittest.TestCase):
    '''Test the set_shared method.'''

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.confirm', side_effect=[False, True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to False and then to True in the configuration file.'''

        # Call set_shared method and set the shared flag to False
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'False')

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

    @patch('inquirer.confirm', side_effect=[True, False])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared_do_not_move_froster_archives(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to True and do not move the froster_archives.json file.'''

        # Create a dummy froster_archives.json file
        archive_json_file = os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)
        with open(archive_json_file, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

        # Check that the froster_archives.json is still in the data directory
        self.assertTrue(os.path.exists(archive_json_file))

        # Check that the froster_archives.json file was not copied to the shared directory
        self.assertFalse(os.path.exists(os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)))

    @patch('inquirer.confirm', side_effect=[True, True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared_move_froster_archives(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to True and move the froster_archives.json file.'''

        # Create a dummy froster_archives.json file
        archive_json_file = os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)
        with open(archive_json_file, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

        # Check that the froster_archives.json is still in the data directory (as we only copy the file)
        self.assertTrue(os.path.exists(os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)))

        # Check that the froster_archives.json file was copied to the shared directory
        self.assertTrue(os.path.exists(os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)))

    @patch('inquirer.confirm', side_effect=[True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared_froster_archives_exist(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to True when froster_archives.json file already exists in shared dir.'''

        # Create a dummy froster_archives.json file in the shared directory
        archive_json_file_shared = os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)
        with open(archive_json_file_shared, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

        # Check that the froster_archives.json is not in the data directory
        self.assertFalse(os.path.exists(os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)))

        # Check that the froster_archives.json file is still in the shared directory
        self.assertTrue(os.path.exists(os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)))

    @patch('inquirer.confirm', side_effect=[True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared_froster_shared_config_exist(self, mock_print, mock_confirm, mock_prompt):
        '''- Set the shared flag to True when froster_archives.json file already exists in shared dir.'''

        # Create a dummy froster_archives.json file in the shared directory
        archive_json_file_shared = os.path.join(
            SHARED_DIR, self.cfg.shared_config_file_name)
        with open(archive_json_file_shared, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'True')

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_dir', SHARED_DIR)

        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'shared_config_file', os.path.join(
                           SHARED_DIR, self.cfg.shared_config_file_name))

        # Check that the shared_config.ini file is still in the shared directory
        self.assertTrue(os.path.exists(archive_json_file_shared))


@patch('builtins.print')
class TestConfigNIH(unittest.TestCase):
    '''Test the set_nih method.'''

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.confirm', side_effect=[True, False])
    def test_set_nih(self, mock_print, mock_confirm):
        '''- Set the NIH flag to True and then to False.'''

        # Check that the nih_init is not set
        self.assertFalse(self.cfg.nih_init)

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the nih_init is set
        self.assertTrue(self.cfg.nih_init)

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'True')

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the nih_init is still set
        self.assertTrue(self.cfg.nih_init)

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'False')

    @patch('inquirer.confirm', side_effect=[True, True, False])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_nih_when_shared_config(self, mock_print, mock_confirm, mock_promp):
        '''- Set the NIH flag to True and then to False when shared configuration.'''

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.shared_config_file,
                       NIH_SECTION, 'is_nih', 'True')

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.shared_config_file,
                       NIH_SECTION, 'is_nih', 'False')


@patch('builtins.print')
class TestConfigS3(unittest.TestCase):
    '''Test the set_s3 method.'''

    # Method executed before every test
    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    @patch('builtins.print')
    def setUp(self, mock_print, mock_prompt, mock_input_list, mock_input_text):

        init_froster(self)

        # Set valid credentials
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Delete any existing buckets
        delete_buckets(self)


    # Method executed after every test
    def tearDown(self):

        # Delete any existing buckets
        delete_buckets(self)

        deinit_froster(self)

    @patch('inquirer.list_input', side_effect=['+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.text', side_effect=[S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    def test_set_s3(self, mock_print, mock_list, mock_text):
        '''- Set a new S3 bucket.'''

        # Assert S3 is not set
        self.assertFalse(self.cfg.s3_init)

        # Call set_s3 method
        self.assertTrue(self.cfg.set_s3(self.aws))

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS)

        # Check that the s3_init is set
        self.assertTrue(self.cfg.s3_init)

        # Get the buckets list
        s3_buckets = self.aws.get_buckets()

        # Check the bucket was created
        self.assertIn(S3_BUCKET_NAME_CONFIG, s3_buckets)

    def test_set_s3_aws_not_init(self, mock_print):
        '''- set_s3 method returns False if AWS credentials are not set.'''

        # Mock the aws_init variable
        self.cfg.aws_init = False

        # Call set_s3 method
        self.assertFalse(self.cfg.set_s3(self.aws))

        # Check that the aws_init is not set
        self.assertFalse(self.cfg.aws_init)

        # Check that the s3_init is not set
        self.assertFalse(self.cfg.s3_init)

        # Restore the aws_init variable
        self.cfg.aws_init = True

    def test_set_s3_invalid_aws_credentials(self, mock_print):
        '''- set_s3 method returns False if AWS credentials are invalid.'''

        # Manually change to a profile not set
        self.cfg.aws_profile = AWS_PROFILE_2

        # Check that the aws_init is set
        self.assertTrue(self.cfg.aws_init)

        # Check that the s3_init is not set
        self.assertFalse(self.cfg.s3_init)

        # Call set_s3 method
        self.assertFalse(self.cfg.set_s3(self.aws))

        # Check that the aws_init is still set
        self.assertTrue(self.cfg.aws_init)

        # Check that the s3_init is not set
        self.assertFalse(self.cfg.s3_init)

        # Restore the changed profile
        self.cfg.aws_profile = AWS_PROFILE

    @patch('inquirer.list_input', side_effect=['+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.text', side_effect=[S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.confirm', side_effect=[True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_s3_when_shared_config(self, mock_print, mock_list, mock_text, mock_confirm, mock_prompt):
        '''- Set a new S3 bucket when shared configuration.'''

        # Call set_shared method
        self.assertTrue(self.cfg.set_shared())

        # Call set_s3 method
        self.assertTrue(self.cfg.set_s3(self.aws))

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR)

        check_ini_file(self, self.cfg.shared_config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS)

        # Check that the s3_init is set
        self.assertTrue(self.cfg.s3_init)

        # Get the buckets list
        s3_buckets = self.aws.get_buckets()

        # Check the bucket was created
        self.assertIn(S3_BUCKET_NAME_CONFIG, s3_buckets)

    @patch('inquirer.list_input', side_effect=['+ Create new bucket', S3_STORAGE_CLASS, S3_BUCKET_NAME_CONFIG, S3_STORAGE_CLASS_2])
    @patch('inquirer.text', side_effect=[S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR, S3_ARCHIVE_DIR_2])
    def test_set_s3_select_bucket(self, mock_print, mock_list, mock_text):
        '''- Select S3 bucket.'''

        # Call set_s3 method
        self.assertTrue(self.cfg.set_s3(self.aws))

        # Call set_s3 method
        self.assertTrue(self.cfg.set_s3(self.aws))

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'bucket_name', S3_BUCKET_NAME_CONFIG)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'archive_dir', S3_ARCHIVE_DIR_2)

        check_ini_file(self, self.cfg.config_file,
                       S3_SECTION, 'storage_class', S3_STORAGE_CLASS_2)

        # Delete the bucket
        self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_CONFIG)

        # Get the buckets list
        s3_buckets = self.aws.get_buckets()

        # Check the bucket was created
        self.assertNotIn(S3_BUCKET_NAME_CONFIG, s3_buckets)


if __name__ == '__main__':

    if True:
        unittest.main(verbosity=2)
    else:
        suite = unittest.TestSuite()
        # FULL CONFIGURATION
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfig))

        # PARTIAL CONFIGURATION
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigUser))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigAWS))
        # suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestConfigShared))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigNIH))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigS3))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigSlurm))

        # BASIC TEST CASE FOR EVERY TEST
        # suite.addTest(TestConfig('test_subcmd_config'))
        # suite.addTest(TestConfigUser('test_set_user'))
        # suite.addTest(TestConfigAWS('test_set_aws'))
        # suite.addTest(TestConfigShared('test_set_shared'))
        # suite.addTest(TestConfigNIH('test_set_nih'))
        # suite.addTest(TestConfigS3('test_set_s3'))

        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
