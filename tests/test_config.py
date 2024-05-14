import tracemalloc
import configparser
import os
import unittest
from unittest.mock import patch
import warnings
from froster.froster import *


@patch('builtins.print')
class TestConfig(unittest.TestCase):

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

    @staticmethod
    def remove_ini_files(cfg):
        # Delete configuration file if exists
        if os.path.exists(cfg.config_file):
            os.remove(cfg.config_file)

        # Delete AWS credential file if exists
        if os.path.exists(cfg.aws_credentials_file):
            os.remove(cfg.aws_credentials_file)

        # Delete AWS config file if exists
        if os.path.exists(cfg.aws_config_file):
            os.remove(cfg.aws_config_file)

    def check_ini_file(self, ini_file, section, key, value):
        config = configparser.ConfigParser()
        config.read(ini_file)
        self.assertIn(section, config.sections())
        self.assertEqual(config.get(section, key), value)

    # Method executed only once before all tests
    @classmethod
    def setUpClass(cls):
        cls.parser = parse_arguments()
        cls.args = cls.parser.parse_args()
        cls.cfg = ConfigManager()
        cls.arch = Archiver(cls.args, cls.cfg)
        cls.aws = AWSBoto(cls.args, cls.cfg, cls.arch)

        cls.remove_ini_files(cls.cfg)

    # Method executed after every test
    def tearDown(self):
        self.remove_ini_files(self.cfg)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_set_user(self, mock_print, mock_input_text):

        # Call set_user method
        self.cfg.set_user()

        # Check that the configuration file was updated correctly
        self.check_ini_file(self.cfg.config_file,
                            self.USER_SECTION, 'name', self.NAME)
        self.check_ini_file(self.cfg.config_file,
                            self.USER_SECTION, 'email', self.EMAIL)

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_new_profile(self, mock_print, mock_input_list, mock_input_text):

        # Call set_user method
        self.cfg.set_aws(self.aws)

        # Check that the configuration files were updated correctly
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_profile', self.AWS_PROFILE)
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_region', self.AWS_REGION)

        self.check_ini_file(self.cfg.aws_credentials_file, self.AWS_PROFILE,
                            'aws_access_key_id', self.AWS_ACCESS_KEY_ID)
        self.check_ini_file(self.cfg.aws_credentials_file,
                            self.AWS_PROFILE, 'aws_secret_access_key', self.AWS_SECRET)

        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'region', self.AWS_REGION)
        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'output', 'json')

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, AWS_PROFILE, AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_select_profile(self, mock_print, mock_input_list, mock_input_text):

        # Call set_aws methon and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and select an existing profile
        self.cfg.set_aws(self.aws)

        # Check that the configuration files were updated correctly
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_profile', self.AWS_PROFILE)
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_region', self.AWS_REGION)

        self.check_ini_file(self.cfg.aws_credentials_file, self.AWS_PROFILE,
                            'aws_access_key_id', self.AWS_ACCESS_KEY_ID)
        self.check_ini_file(self.cfg.aws_credentials_file,
                            self.AWS_PROFILE, 'aws_secret_access_key', self.AWS_SECRET)

        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'region', self.AWS_REGION)
        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'output', 'json')

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile', AWS_REGION_2])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE_2, AWS_ACCESS_KEY_ID, AWS_SECRET])
    @patch('inquirer.confirm', side_effect=['y'])
    def test_set_aws_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):

        # Call set_aws method and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and overwrite the existing profile
        self.cfg.set_aws(self.aws)

        # Check that the configuration files were updated correctly
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_profile', self.AWS_PROFILE_2)
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_region', self.AWS_REGION_2)

        self.check_ini_file(self.cfg.aws_credentials_file, self.AWS_PROFILE_2,
                            'aws_access_key_id', self.AWS_ACCESS_KEY_ID)
        self.check_ini_file(self.cfg.aws_credentials_file,
                            self.AWS_PROFILE_2, 'aws_secret_access_key', self.AWS_SECRET)

        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE_2, 'region', self.AWS_REGION_2)
        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE_2, 'output', 'json')

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile'])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE])
    @patch('inquirer.confirm', side_effect=[False])
    def test_set_aws_do_not_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):

        self.assertFalse(os.path.exists(self.cfg.aws_credentials_file))

        # Call set_aws method and create a new profile
        self.cfg.set_aws(self.aws)

        # Call set_aws method and do not overwrite the existing profile
        self.cfg.set_aws(self.aws)

        # Check that the configuration files were updated correctly
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_profile', self.AWS_PROFILE)
        self.check_ini_file(self.cfg.config_file,
                            self.AWS_SECTION, 'aws_region', self.AWS_REGION)

        self.check_ini_file(self.cfg.aws_credentials_file, self.AWS_PROFILE,
                            'aws_access_key_id', self.AWS_ACCESS_KEY_ID)
        self.check_ini_file(self.cfg.aws_credentials_file,
                            self.AWS_PROFILE, 'aws_secret_access_key', self.AWS_SECRET)

        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'region', self.AWS_REGION)
        self.check_ini_file(self.cfg.aws_config_file,
                            self.AWS_PROFILE, 'output', 'json')


if __name__ == '__main__':
    print()
    warnings.filterwarnings("ignore", category=ResourceWarning)
    unittest.main(verbosity=2)
    print()
