from unittest.mock import patch
import unittest
import os
import shutil
import configparser
from froster import *
import warnings
warnings.filterwarnings("always", category=ResourceWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)


NAME = "John Doe"
EMAIL = "john@doe.com"
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET = os.getenv('AWS_SECRET')
AWS_REGION = "eu-west-1"
AWS_REGION_2 = "eu-west-2"
AWS_PROFILE = "froster-test"
AWS_PROFILE_2 = "froster-test-2"

USER_SECTION = 'USER'
AWS_SECTION = 'AWS'
SHARED_SECTION = 'SHARED'
NIH_SECTION = 'NIH'
S3_SECTION = 'S3'

SHARED_DIR = '/tmp/shared_dir'


def init_froster(cls):
    cls.parser = parse_arguments()
    cls.args = cls.parser.parse_args()
    cls.cfg = ConfigManager()
    cls.arch = Archiver(cls.args, cls.cfg)
    cls.aws = AWSBoto(cls.args, cls.cfg, cls.arch)

    remove_froster_files(cls.cfg)


def check_ini_file(self, ini_file, section, key, value):
    config = configparser.ConfigParser()
    config.read(ini_file)
    self.assertIn(section, config.sections())
    self.assertEqual(config.get(section, key), value)


def remove_froster_files(cfg):
    # Delete configuration file if exists
    if hasattr(cfg, 'config_file') and os.path.exists(cfg.config_file):
        os.remove(cfg.config_file)

    # Delete AWS credential file if exists
    if hasattr(cfg, 'aws_credentials_file') and os.path.exists(cfg.aws_credentials_file):
        os.remove(cfg.aws_credentials_file)

    # Delete AWS config file if exists
    if hasattr(cfg, 'aws_config_file') and os.path.exists(cfg.aws_config_file):
        os.remove(cfg.aws_config_file)

    if os.path.exists(cfg.data_dir):
        shutil.rmtree(cfg.data_dir)

    if os.path.exists(SHARED_DIR):
        shutil.rmtree(SHARED_DIR)


@patch('builtins.print')
class TestConfigUser(unittest.TestCase):

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):
        init_froster(cls)

    # Method executed after every test
    def tearDown(self):
        remove_froster_files(self.cfg)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_set_user(self, mock_print, mock_input_text):

        # Call set_user method
        self.cfg.set_user()

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'name', NAME)
        check_ini_file(self, self.cfg.config_file,
                       USER_SECTION, 'email', EMAIL)


@patch('builtins.print')
class TestConfigAWS(unittest.TestCase):

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):
        init_froster(cls)

    # Method executed before every test
    def setUp(self):

        if AWS_ACCESS_KEY_ID is None or AWS_SECRET is None:
            raise ValueError("AWS credentials are not set")

    # Method executed after every test
    def tearDown(self):
        remove_froster_files(self.cfg)

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_new_profile(self, mock_print, mock_input_list, mock_input_text):

        # Call set_aws method
        self.cfg.set_aws(self.aws)

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, AWS_PROFILE, AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_select_profile(self, mock_print, mock_input_list, mock_input_text):

        # Call set_aws methon and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and select an existing profile
        self.cfg.set_aws(self.aws)

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile', AWS_REGION_2])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE_2, AWS_ACCESS_KEY_ID, AWS_SECRET])
    @patch('inquirer.confirm', side_effect=['y'])
    def test_set_aws_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):

        # Call set_aws method and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and overwrite the existing profile
        self.cfg.set_aws(self.aws)

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile'])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE])
    @patch('inquirer.confirm', side_effect=[False])
    def test_set_aws_do_not_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):

        # Call set_aws method and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and do not overwrite the existing profile
        self.cfg.set_aws(self.aws)

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


@patch('builtins.print')
class TestConfigShared(unittest.TestCase):

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):
        # Init froster
        init_froster(cls)

        # Create the data directory
        os.makedirs(cls.cfg.data_dir, exist_ok=True, mode=0o775)

        # Create the shared directory
        os.makedirs(SHARED_DIR, exist_ok=True, mode=0o775)

    # Method executed after every test
    def tearDown(self):
        remove_froster_files(self.cfg)

    @patch('inquirer.confirm', side_effect=[False])
    def test_set_shared_do_not_share(self, mock_print, mock_input_confirm):

        # Call set_shared method
        self.cfg.set_shared()

        # Check that the configuration files were updated correctly
        check_ini_file(self, self.cfg.config_file,
                       SHARED_SECTION, 'is_shared', 'False')

    @patch('inquirer.confirm', side_effect=[True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared(self, mock_print, mock_input_confirm, mock_input_prompt):

        # Call set_shared method
        self.cfg.set_shared()

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
    def test_set_shared_do_not_move_froster_archives(self, mock_print, mock_input_confirm, mock_input_prompt):

        # Create a dummy froster_archives.json file
        archive_json_file = os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)
        with open(archive_json_file, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.cfg.set_shared()

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
    def test_set_shared_move_froster_archives(self, mock_print, mock_input_confirm, mock_input_prompt):

        # Create a dummy froster_archives.json file
        archive_json_file = os.path.join(
            self.cfg.data_dir, self.cfg.archive_json_file_name)
        with open(archive_json_file, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.cfg.set_shared()

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
    def test_set_shared_froster_archives_already_exist(self, mock_print, mock_input_confirm, mock_input_prompt):

        # Create a dummy froster_archives.json file in the shared directory
        archive_json_file_shared = os.path.join(
            SHARED_DIR, self.cfg.archive_json_file_name)
        with open(archive_json_file_shared, 'w') as f:
            f.write('Hello, world!')

        # Call set_shared method
        self.cfg.set_shared()

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

    
if __name__ == '__main__':
    print()
    if False:
        unittest.main(verbosity=2)
    else:
        suite = unittest.TestSuite()
        suite.addTest(TestConfigShared(
            'test_set_shared_froster_archives_already_exist'))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
    print()
