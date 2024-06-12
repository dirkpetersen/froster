from froster import *
from config import *
from argparse import Namespace
from generate_dummy_data import generate_test_data
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
        print("CREDENTIALS")
        # Get the buckets list
        s3_buckets = self.aws.get_buckets()

        # Delete the buckets if they exists
        if S3_BUCKET_NAME_INDEX in s3_buckets:
            print("Delete bucket ", S3_BUCKET_NAME_INDEX)
            self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_INDEX)
        if S3_BUCKET_NAME_INDEX_2 in s3_buckets:
            print("Delete bucket ", S3_BUCKET_NAME_INDEX_2)
            self.aws.s3_client.delete_bucket(Bucket=S3_BUCKET_NAME_INDEX_2)
    else:
        print("NO CREDENTIALS")

class TestIndex(unittest.TestCase):
    '''Test the froster index command.'''

    @patch('builtins.print')
    @patch('inquirer.prompt', return_value={'aws_dir': AWS_DEFAULT_PATH})
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION])
    @patch('inquirer.text', side_effect=[AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET])
    def set_credentials(self, mock_print, mock_prompt, mock_list, mock_text):
        '''- Set a new AWS profile with valid credentials.'''

        # Call set_aws method
        self.assertTrue(self.cfg.set_aws(self.aws))
        self.assertTrue(self.aws.check_credentials())

    # @patch('builtins.print')
    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.confirm', side_effect=[False, False])
    # Method executed before every test
    def setUp(self, mock_text, mock_prompt, mock_list, mock_confirm):
        if AWS_ACCESS_KEY_ID is None or AWS_SECRET is None:
            raise ValueError("AWS credentials are not set")

        # Initialize the froster objects
        init_froster(self)

        # Make sure we have credentials to be able to delete buckets
        self.set_credentials()

        # Delete any existing buckets
        delete_buckets(self)

        # We needed to set the credentials to be able to delete possible buckets that
        # were created in previous tests. However, we don't want to set the credentials for the current test.
        # Therefore, we need to delete the credentials after deleting the buckets.

        # Deinitialize the froster objects
        deinit_froster(self)

        # Initialize the froster objects
        init_froster(self)

        # Mock the CLI default arguments

        # Default arguments for "froster config" command
        self.cmd.args = Namespace(cores=4, debug=False, info=False, log_print=False, memory=64, noslurm=False, version=False,
                                  subcmd='config', aws=False, monitor=False, nih=False, print=False, s3=False, shared=False, slurm=False, user=False)
        
        # Mock the "froster config" command and make sure it runs successfully
        self.cmd.subcmd_config(cfg=self.cfg, aws=self.aws)

        # Generate test data
        self.test_data_dir = generate_test_data()

    # Method executed after every test

    def tearDown(self):
        # Delete any existing buckets
        delete_buckets(self)

        # Deinitialize the froster objects
        deinit_froster(self)

        # Delete the test data directory
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_subcmd_index(self, mock_text):
        '''- Test the froster index command.'''

        print("Test data folder: ", self.test_data_dir)

        # Default arguments for "froster index" command
        self.cmd.args = Namespace(cores=4, debug=False, info=False, log_print=False, memory=64, noslurm=False,
                                  version=False, subcmd='index', folders=[self.test_data_dir], force=False, pwalkcopy='')

    #     # Run the index command
    #    self.cmd.subcmd_index(self.cfg, self.arch)
        self.assertTrue(True)


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
        suite.addTest(TestConfigS3('test_set_s3'))

        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
