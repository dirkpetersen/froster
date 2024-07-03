import subprocess
import sys
from time import sleep
import unittest
from unittest.mock import patch
from froster import *
from tests.config import *


class TestBasicFeatures(unittest.TestCase):
    '''Test the froster basic features.'''

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

        # Delete the created S3 bucket
        with \
                patch('sys.argv', ['froster', '--debug', 'delete', '--bucket', S3_BUCKET_NAME_CREDENTIALS_1]):
            main()

    def test_basic_features(self):
        '''- Test the froster basic features.'''

        try:
            # Create a dummy file
            folder_path = tempfile.mkdtemp(prefix='froster_')
            print(f"\nTemporary directory created at: {folder_path}")

            file_path = os.path.join(folder_path, 'dummy_file')
            with open(file_path, 'wb') as f:
                f.truncate(1)
            print(f"Dummy file created at: {file_path}")

            # Run the basic features commands and check if return value is 0, which means no issues detected while executing the command
            
            # NOTE: config command is tested into the setUpClass method
            
            with \
                    patch('sys.argv', ['froster', 'index', folder_path]):
                self.assertFalse(main())

            with \
                    patch('sys.argv', ['froster', 'archive', folder_path]):
                self.assertFalse(main())

            with \
                    patch('sys.argv', ['froster', 'delete', folder_path]):
                self.assertFalse(main())

        except Exception as e:
            print(f"Error: {e}")
        


if __name__ == '__main__':

    try:

        unittest.main(verbosity=2, failfast=True)

    except KeyboardInterrupt:
        print("\nTests interrupted by the user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print("\nAn error occurred during the tests execution: %s" % e)
        sys.exit(1)
