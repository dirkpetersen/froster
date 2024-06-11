from froster import *
from config import *
from utils_froster_full_config import config_froster
from argparse import Namespace
import configparser
import os
import shutil
from unittest.mock import patch
import unittest


@patch('builtins.print')
class TestIndex(unittest.TestCase):
    '''Test the froster index command.'''

    # Method executed before every test
    def setUp(self):
        pass
        # init_froster(self)

    # Method executed after every test
    def tearDown(self):
        pass
        # deinit_froster(self)

    @patch('inquirer.text', side_effect=[NAME, EMAIL])
    def test_subcmd_index(self, mock_print, mock_text):
        self.assertTrue(config_froster(caller_name="index"))


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
