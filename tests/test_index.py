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


class TestIndex(unittest.TestCase):
    '''Test the froster index command.'''

    # Method executed once before all tests
    @classmethod
    @patch('sys.argv', ['froster', 'config'])
    @patch('inquirer.text', side_effect=[NAME, EMAIL, AWS_PROFILE, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CONFIG, S3_ARCHIVE_DIR])
    @patch('inquirer.prompt', side_effect=[{'aws_dir': AWS_DEFAULT_PATH}])
    @patch('inquirer.list_input', side_effect=['+ Create new profile', AWS_REGION, '+ Create new bucket', S3_STORAGE_CLASS])
    @patch('inquirer.confirm', side_effect=[False, False])
    @patch('builtins.print')
    def setUpClass(cls, mock_text, mock_prompt, mock_list, mock_confirm, mock_print):

        main()

    # Method executed once after all tests
    @classmethod
    @patch('builtins.print')
    def tearDownClass(cls, mock_print):

        with patch('sys.argv', ['froster', '--debug', 'delete', '--bucket', S3_BUCKET_NAME_CONFIG]):
            main()

        with patch('sys.argv', ['froster', '--debug', 'delete', '--bucket', S3_BUCKET_NAME_CONFIG_2]):
            main()

    # Method executed before every test
    @patch('builtins.print')
    def setUp(self, mock_print):

        # Generate test data
        self.test_data_dir = generate_test_data()

    # Method executed after every test
    @patch('builtins.print')
    def tearDown(self, mock_print):
        '''- Clean up test data and S3 buckets.'''

        # Delete the test data directory if exist
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    @patch('builtins.print')
    def test_subcmd_index(self, mock_print):
        '''- Test the froster index command.'''

        with patch('sys.argv', ['froster', 'index', self.test_data_dir]):
            self.assertTrue(main())


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
