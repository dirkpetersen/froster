from unittest.mock import patch
import unittest
import os
import shutil
import configparser
from froster import *
import warnings
warnings.filterwarnings("always", category=ResourceWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)


# Variables
NAME = "John Doe"
EMAIL = "john@doe.com"

AWS_REGION = "eu-west-1"
AWS_REGION_2 = "eu-west-2"
AWS_PROFILE = "froster-test"
AWS_PROFILE_2 = "froster-test-2"

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET = os.getenv('AWS_SECRET')

USER_SECTION = 'USER'
AWS_SECTION = 'AWS'
SHARED_SECTION = 'SHARED'
NIH_SECTION = 'NIH'
S3_SECTION = 'S3'

SHARED_DIR = '/tmp/shared_dir'


def init_froster(self):
    self.parser = parse_arguments()
    self.args = self.parser.parse_args()
    self.cfg = ConfigManager()
    self.arch = Archiver(self.args, self.cfg)
    self.aws = AWSBoto(self.args, self.cfg, self.arch)

    # Create the data directory
    os.makedirs(self.cfg.data_dir, exist_ok=True, mode=0o775)

    # Create the shared directory
    os.makedirs(SHARED_DIR, exist_ok=True, mode=0o775)


def deinit_froster(self):

    # Delete used directories
    if os.path.exists(self.cfg.aws_dir):
        shutil.rmtree(self.cfg.aws_dir)

    if os.path.exists(self.cfg.config_dir):
        shutil.rmtree(self.cfg.config_dir)

    if os.path.exists(self.cfg.data_dir):
        shutil.rmtree(self.cfg.data_dir)

    if os.path.exists(SHARED_DIR):
        shutil.rmtree(SHARED_DIR)

    # Delete initizalized objects
    del self.parser
    del self.args
    del self.cfg
    del self.arch
    del self.aws


def check_ini_file(self, ini_file, section, key, value):
    config = configparser.ConfigParser()
    config.read(ini_file)
    self.assertIn(section, config.sections())
    self.assertEqual(config.get(section, key), value)


@patch('builtins.print')
class TestConfigUser(unittest.TestCase):

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_set_user(self, mock_print, mock_input_text):
        '''Set the user and email in the configuration file.'''

        # Call set_user method
        self.assertTrue(self.cfg.set_user())

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
        if AWS_ACCESS_KEY_ID is None or AWS_SECRET is None:
            raise ValueError("AWS credentials are not set")

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws(self, mock_print, mock_input_list, mock_input_text):
        '''Set a new AWS profile with valid credentials.'''

        # Call set_aws method
        self.assertTrue(self.cfg.set_aws(self.aws))

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, 'wrong_access_key_id', 'wrong_secret'])
    def test_set_aws_invalid_credentials(self, mock_print, mock_input_list, mock_input_text):
        '''Set a new AWS profile with invalid credentials.'''

        # Set valid credentials
        self.assertFalse(self.cfg.set_aws(self.aws))

        config = configparser.ConfigParser()
        config.read(self.cfg.aws_credentials_file)
        self.assertNotIn(AWS_PROFILE, config.sections())

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, AWS_PROFILE, AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def test_set_aws_select_profile(self, mock_print, mock_input_list, mock_input_text):
        '''Select profile from AWS configuration file.'''
        # Call set_aws methon and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Call set_aws method and select an existing profile
        self.assertTrue(self.cfg.set_aws(self.aws))

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile', AWS_REGION_2])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE_2, AWS_ACCESS_KEY_ID, AWS_SECRET])
    @patch('inquirer.confirm', side_effect=['y'])
    def test_set_aws_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):
        '''Overwrite an existing AWS profile.'''

        # Call set_aws method and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Call set_aws method and overwrite the existing profile
        self.assertTrue(self.cfg.set_aws(self.aws))

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

    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new profile'])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, AWS_PROFILE])
    @patch('inquirer.confirm', side_effect=[False])
    def test_set_aws_do_not_overwrite_profile(self, mock_print, mock_input_list, mock_input_text, mock_input_confirm):
        '''Do not overwrite an existing AWS profile.'''
        # Call set_aws method and create a new profile
        self.assertTrue(self.cfg.set_aws(self.aws))

        # Call set_aws method and do not overwrite the existing profile
        self.assertFalse(self.cfg.set_aws(self.aws))

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

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.confirm', side_effect=[False, True])
    @patch('inquirer.prompt', return_value={'shared_dir': SHARED_DIR})
    def test_set_shared(self, mock_print, mock_input_confirm, mock_input_prompt):
        '''Set the shared flag to False and then to True in the configuration file.'''

        # Call set_shared method
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
    def test_set_shared_do_not_move_froster_archives(self, mock_print, mock_input_confirm, mock_input_prompt):
        '''Set the shared flag to True and do not move the froster_archives.json file.'''

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
    def test_set_shared_move_froster_archives(self, mock_print, mock_input_confirm, mock_input_prompt):
        '''Set the shared flag to True and move the froster_archives.json file.'''

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
    def test_set_shared_froster_archives_exist(self, mock_print, mock_input_confirm, mock_input_prompt):
        '''Set the shared flag to True when froster_archives.json file already exists in shared dir.'''

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
    def test_set_shared_froster_shared_config_exist(self, mock_print, mock_input_confirm, mock_input_prompt):
        '''Set the shared flag to True when froster_archives.json file already exists in shared dir.'''

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

    # Method executed before every test
    def setUp(self):
        init_froster(self)

    # Method executed after every test
    def tearDown(self):
        deinit_froster(self)

    @patch('inquirer.confirm', side_effect=[True, False])
    def test_set_nih(self, mock_print, mock_input_confirm):
        '''Set the NIH flag to True and then to False in the configuration file.'''

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'True')

        # Call set_user method
        self.assertTrue(self.cfg.set_nih())

        # Check that the configuration file was updated correctly
        check_ini_file(self, self.cfg.config_file,
                       NIH_SECTION, 'is_nih', 'False')


# @patch('builtins.print')
# class TestConfigS3(unittest.TestCase):

#     # Method executed only once before all tests
#     @classmethod
#     def setUpClass(cls):
#         init_froster(cls)

#     # Method executed after every test
#     def tearDown(self):
#         deinit_froster(self.cfg)

#     def test_set_s3_aws_not_init(self, mock_print):
#         """
#         Checks set_s3 method returns False if AWS credentials are not set.
#         """
#         self.assertFalse(self.cfg.set_s3(self.aws))

#     @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
#     @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
#     def test_set_s3_invalid_aws_credentials(self, mock_print, mock_input_list, mock_input_text):
#         """
#         Checks set_s3 method returns False if AWS credentials are invalid.
#         """

#         # Set valid credentials
#         self.cfg.set_aws(self.aws)

#         # Check valid credentials
#         self.assertTrue(self.aws.check_credentials())

#         # Set invalid credentials by manually modifying the ~/.aws/credentials file
#         config = configparser.ConfigParser()
#         config.read(self.cfg.aws_credentials_file)
#         config.set(AWS_PROFILE, 'aws_access_key_id', '1234')
#         with open(self.cfg.aws_credentials_file, 'w') as configfile:
#             config.write(configfile)

#         # Check invalid credentials
#         self.assertTrue(self.aws.check_credentials())

#         # Call set_s3 method
#         self.assertFalse(self.cfg.set_s3(self.aws))

    # @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', 'DEEP_ARCHIVE'])
    # @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, 'froster-githubactions-test', 'froster'])
    # def test_set_s3(self, mock_print, mock_input_list, mock_input_text):
    #     """
    #     Create new AWS S3 bucket
    #     """

    #     # Set valid credentials
    #     self.cfg.set_aws(self.aws)

    #     # Call set_s3 method
    #     self.assertFalse(self.cfg.set_s3(self.aws))


if __name__ == '__main__':

    if True:
        unittest.main(verbosity=2)
    else:
        suite = unittest.TestSuite()
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigUser))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigAWS))
        suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestConfigShared))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigNIH))
        # suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigS3))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)

        # suite.addTest(TestConfigAWS('test_set_aws_invalid_credentials'))
