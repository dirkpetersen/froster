from froster import *
from config import *
from argparse import Namespace
import configparser
import os
import shutil
from unittest.mock import patch
import unittest

import warnings
warnings.filterwarnings("always", category=ResourceWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)


patch('builtins.print')


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

        # Delete any existing buckets
        delete_buckets(self)

    # Method executed after every test
    def tearDown(self):

        # Delete any existing buckets
        delete_buckets(self)

        # Deinitialize the froster objects
        deinit_froster(self)

    # HELPER RUNS

    def helper_set_default_cli_arguments(self):
        '''- Set default cli arguments.'''


if __name__ == '__main__':

    if False:
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
