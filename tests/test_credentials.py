import sys
import unittest
from unittest.mock import patch
from froster import *
from tests.config import *


class TestCredentials(unittest.TestCase):
    '''Test the froster credentials command.'''

    # Method executed once before all tests
    @classmethod
    def setUpClass(cls):
        '''- Set up class.'''

        # Setup the froster configuration by mocking user input
        with \
                patch('sys.argv', ['froster', 'config']), \
                patch('inquirer.text', side_effect=[NAME_1, EMAIL_1, PROFILE_1, AWS_CREDENTIALS_PROFILE_1, AWS_ACCESS_KEY_ID, AWS_SECRET, S3_BUCKET_NAME_CREDENTIALS_1, S3_ARCHIVE_DIR_1]), \
                patch('inquirer.confirm', side_effect=[False, False, True, False]), \
                patch('inquirer.list_input', side_effect=['+ Create new profile', PROVIDER_1, '+ Create new credentials', AWS_REGION_1, '+ Create new bucket', S3_STORAGE_CLASS_1]):
            main()

    # Method executed once after all tests
    @classmethod
    def tearDownClass(cls):
        '''- Tear down class.'''

        # Delete the S3 buckets
        with \
                patch('sys.argv', ['froster', '--debug', 'delete', '--bucket', S3_BUCKET_NAME_CREDENTIALS_1]), \
                patch('builtins.print') as mock_print:
            main()

        with \
                patch('sys.argv', ['froster', '--debug', 'delete', '--bucket', S3_BUCKET_NAME_CREDENTIALS_2]), \
                patch('builtins.print') as mock_print:
            main()

    def test_subcmd_credentials(self):
        '''- Test the froster credentials command.'''

        # Run the index command and check if sys.exit(0), which means no issues detected while executing the command
        with \
                patch('sys.argv', ['froster', 'credentials']):
            self.assertFalse(main())


if __name__ == '__main__':

    try:
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

    except KeyboardInterrupt:
        print("\nTests interrupted by the user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print("\nAn error occurred during the tests execution: %s" % e)
        sys.exit(1)
