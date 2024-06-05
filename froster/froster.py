#! /usr/bin/env python3

"""
    Froster automates much of the challenging tasks when
    archiving many Terabytes of data on large (HPC) systems.
"""

# internal modules
from textual.widgets import DataTable, Footer, Button
from textual.widgets import Label, Input, LoadingIndicator
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical
from textual.app import App, ComposeResult
from textual import on, work
import psutil
import botocore
import boto3
import duckdb
import requests
import inquirer
import sys
import os
import argparse
import json
import configparser
import csv
import platform
import asyncio
import stat
import datetime
import tarfile
import textwrap
import tarfile
import time
import platform
import concurrent.futures
import hashlib
import fnmatch
import io
import math
import shlex
import shutil
import tempfile
import subprocess
import itertools
import socket
import inspect
import getpass
import pwd
import grp
import stat
import re
import traceback
import pkg_resources
from pathlib import Path


class ConfigManager:
    ''' Froster configuration manager

    This class manages the configuration of Froster.
    It reads and writes the configuration file.'''

    def __init__(self):
        try:
            ''' Initialize the ConfigManager object

            This function initializes the ConfigManager object with default values.
            Then it reads the configuration file (if exists) and populates the object variables.
            It follows the XDG Base Directory conventions:
            https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
            '''

            # Initialize the filename variables that are needed elsewhere
            self.archive_json_file_name = 'froster-archives.json'
            self.shared_config_file_name = 'shared_config.ini'

            # Initialize the variables that check if specific configuration sections have been initialized
            self.user_init = False
            self.aws_init = False
            self.nih_init = False
            self.s3_init = False
            self.configuration_done = False

            # Whoami
            self.whoami = getpass.getuser()

            # Expand the ~ symbols to user's home directory
            self.home_dir = os.path.expanduser('~')

            # Froster's home directory
            self.froster_dir = os.path.join(sys.prefix)

            # Froster's binary directory
            self.bin_dir = os.path.join(self.froster_dir, 'bin')

            # Froster's data directory
            xdg_data_home = os.environ.get('XDG_DATA_HOME')

            if xdg_data_home:
                self.data_dir = os.path.join(xdg_data_home, 'froster')
            else:
                self.data_dir = os.path.join(
                    self.home_dir, '.local', 'share', 'froster')

            self.slurm_dir = os.path.join(self.data_dir, 'slurm')

            # Froster's configuration directory
            xdg_config_home = os.environ.get('XDG_CONFIG_HOME')

            if xdg_config_home:
                self.config_dir = os.path.join(xdg_config_home, 'froster')
            else:
                self.config_dir = os.path.join(
                    self.home_dir, '.config', 'froster')

            # Froster's configuration file
            self.config_file = os.path.join(self.config_dir, 'config.ini')

            # Froster's archive json file
            self.archive_json = os.path.join(
                self.data_dir, self.archive_json_file_name)

            # Froster's default shared configuration
            self.is_shared = False

            # Basic setup, focus the indexer on larger folders and file sizes
            self.max_small_file_size_kib = 1024
            self.min_index_folder_size_gib = 1
            self.min_index_folder_size_avg_mib = 10
            self.max_hotspots_display_entries = 5000

            # Froster's ssh default key name
            self.ssh_key_name = 'froster-ec2'

            # Hotspots dir
            self.hotspots_dir = os.path.join(self.data_dir, 'hotspots')

            # Check if there is a ~/.config/froster/config.ini file and populate the variables
            if os.path.exists(self.config_file):

                # Create a ConfigParser object
                config = configparser.ConfigParser()

                # Populate self variables using local config.ini file
                config.read(self.config_file)

                # User configuration
                self.name = config.get('USER', 'name', fallback=None)
                self.email = config.get('USER', 'email', fallback=None)

                # Check if user configuration is complete
                if self.name and self.email:
                    self.user_init = True

                # AWS directory
                self.aws_dir = config.get(
                    'AWS', 'aws_dir', fallback=os.path.join(self.home_dir, '.aws'))

                # AWS config file
                self.aws_config_file = os.path.join(self.aws_dir, 'config')

                # AWS credentials file
                self.aws_credentials_file = os.path.join(
                    self.aws_dir, 'credentials')

                # AWS profile
                self.aws_profile = config.get(
                    'AWS', 'aws_profile', fallback=None)

                # AWS region
                self.aws_region = config.get(
                    'AWS', 'aws_region', fallback=None)

                # Check if aws configuration is complete
                if self.aws_profile and self.aws_region:
                    self.aws_init = True

                # Last timestamp we checked for an updated
                self.update_check_timestamp = config.get(
                    'UPDATE', 'timestamp', fallback=None)

                # Shared configuration
                self.is_shared = config.getboolean(
                    'SHARED', 'is_shared', fallback=False)

                if self.is_shared:

                    self.shared_dir = config.get(
                        'SHARED', 'shared_dir', fallback=None)

                    self.shared_config_file = os.path.join(
                        self.shared_dir,  self.shared_config_file_name)

                    self.archive_json = os.path.join(
                        self.shared_dir, self.archive_json_file_name)

                    self.shared_hotspots_dir = os.path.join(
                        self.shared_dir, 'hotspots')

                    # Change config file if this is a shared configuration
                    config.read(self.shared_config_file)

                # NIH configuration
                self.is_nih = config.getboolean('NIH', 'is_nih', fallback=None)

                # Set nih init flag
                self.nih_init = True if self.is_nih is not None else False

                # Current S3 Bucket name
                self.bucket_name = config.get(
                    'S3', 'bucket_name', fallback=None)

                # Archive directoy inside AWS S3 bucket
                self.archive_dir = config.get(
                    'S3', 'archive_dir', fallback=None)

                # Store aws s3 storage class in the config object
                self.storage_class = config.get(
                    'S3', 'storage_class', fallback=None)

                # Check if s3 configuration is complete
                if self.bucket_name and self.archive_dir and self.storage_class:
                    self.s3_init = True

                # Slurm configuration
                self.slurm_walltime_days = config.get(
                    'SLURM', 'slurm_walltime_days', fallback=None)

                self.slurm_walltime_hours = config.get(
                    'SLURM', 'slurm_walltime_hours', fallback=None)

                self.slurm_partition = config.get(
                    'SLURM', 'slurm_partition', fallback=None)

                self.slurm_qos = config.get(
                    'SLURM', 'slurm_qos', fallback=None)

                self.slurm_lscratch = config.get(
                    'SLURM', 'slurm_lscratch', fallback=None)

                self.lscratch_mkdir = config.get(
                    'SLURM', 'lscratch_mkdir', fallback=None)

                self.lscratch_rmdir = config.get(
                    'SLURM', 'lscratch_rmdir', fallback=None)

                self.lscratch_root = config.get(
                    'SLURM', 'lscratch_root', fallback=None)

                # Cloud configuration
                self.ses_verify_requests_sent = config.get(
                    'CLOUD', 'ses_verify_requests_sent', fallback=[])

                self.ec2_last_instance = config.get(
                    'CLOUD', 'ec2_last_instance', fallback=None)

            if self.user_init and self.aws_init and self.s3_init and self.nih_init:
                self.configuration_done = True

        except Exception:
            print_error()

    def __repr__(self):
        ''' Return a string representation of the object'''
        try:
            return "<{klass} @{id:x} {attrs}>".format(
                klass=self.__class__.__name__,
                id=id(self) & 0xFFFFFF,
                attrs=" ".join("{}={!r}\n".format(k, v)
                               for k, v in self.__dict__.items()),
            )
        except Exception:
            print_error()

    def add_systemd_cron_job(self, cmd, minute, hour='*'):

        try:
            # Troubleshoot with:
            #
            # journalctl -f --user-unit froster-monitor.service
            # journalctl -f --user-unit froster-monitor.timer
            # journalctl --since "5 minutes ago" | grep froster-monitor

            SERVICE_CONTENT = textwrap.dedent(f"""
            [Unit]
            Description=Run Froster-Monitor Cron Job

            [Service]
            Type=simple
            ExecStart={cmd}

            [Install]
            WantedBy=default.target
            """)

            TIMER_CONTENT = textwrap.dedent(f"""
            [Unit]
            Description=Run Froster-Monitor Cron Job hourly

            [Timer]
            Persistent=true
            OnCalendar=*-*-* {hour}:{minute}:00
            #RandomizedDelaySec=300
            #FixedRandomDelay=true
            #OnBootSec=180
            #OnUnitActiveSec=3600
            Unit=froster-monitor.service

            [Install]
            WantedBy=timers.target
            """)

            # Ensure the directory exists
            user_systemd_dir = os.path.expanduser("~/.config/systemd/user/")
            os.makedirs(user_systemd_dir, exist_ok=True, mode=0o775)

            SERVICE_PATH = os.path.join(
                user_systemd_dir, "froster-monitor.service")
            TIMER_PATH = os.path.join(
                user_systemd_dir, "froster-monitor.timer")

            # Create service and timer files
            with open(SERVICE_PATH, "w") as service_file:
                service_file.write(SERVICE_CONTENT)

            with open(TIMER_PATH, "w") as timer_file:
                timer_file.write(TIMER_CONTENT)

            # Reload systemd and enable/start timer
            os.chdir(user_systemd_dir)
            os.system("systemctl --user daemon-reload")
            os.system("systemctl --user enable froster-monitor.service")
            os.system("systemctl --user enable froster-monitor.timer")
            os.system("systemctl --user start froster-monitor.timer")

            print("Systemd froster-monitor.timer cron job started!")
            return True

        except Exception:
            print_error("Could not add systemd scheduler job")
            return False

    def assure_permissions_and_group(self, directory):
        '''Assure correct permissions and groupID of a directory'''

        try:
            if not os.path.isdir(directory):
                raise ValueError(
                    f'{inspect.currentframe().f_code.co_name}: tried to fix permissions of a non-directory "{directory}"')

            # Get the group ID of the directory
            dir_stat = os.stat(directory)
            dir_gid = dir_stat.st_gid

            # Change the permissions of the directory to 0o2775
            os.chmod(directory, 0o2775)

            # Iterate over all files and directories in the directory and its subdirectories
            for root, dirs, files in os.walk(directory):
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    # Change the permissions of the subdirectory to 0o2775
                    os.chmod(dir_path, 0o2775)

                for file in files:
                    path = os.path.join(root, file)

                    # Get the file extension
                    _, extension = os.path.splitext(path)

                    # If the file is a .pem file
                    if extension == '.pem':
                        # Change the permissions to 400
                        os.chmod(path, 0o400)
                    else:
                        # Change the permissions to 664
                        os.chmod(path, 0o664)

                    # Change the group ID to the same as the directory
                    os.chown(path, -1, dir_gid)

        except Exception:
            print_error(f"Could not fix permissions of directory: {directory}")

    def __inquirer_check_bucket_name(self, answers, current):
        '''Check if the bucket name is correct'''

        if not current.startswith("froster-"):
            raise inquirer.errors.ValidationError(
                "", reason="Wrong bucket name. E.g.: froster-")

        if not len(current) > 8:
            raise inquirer.errors.ValidationError(
                "", reason="Bucket name too short. E.g.: froster-")

        return True

    def __inquirer_check_email_format(self, answers, current):
        '''Check if the email format is correct'''

        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if re.match(pattern, current) is None:
            raise inquirer.errors.ValidationError(
                "", reason="Wrong email format. E.g.: xxx@yyy.zzz")
        return True

    def __inquirer_check_is_number(self, answers, current):
        '''Check if the input is a number'''

        pattern = r"^[0-9]+$"
        if re.match(pattern, current) is None:
            raise inquirer.errors.ValidationError(
                "", reason="Must be a number")
        return True

    def __inquirer_check_required(self, answers, current):
        '''Check input is set'''

        if not current:
            raise inquirer.errors.ValidationError(
                "", reason="Field is required")
        return True

    def __inquirer_check_path_exists(self, answers, current):
        '''Check if the path exists'''
        if not os.path.exists(os.path.expanduser(current)):
            raise inquirer.errors.ValidationError(
                "", reason="Path does not exist")
        return True

    def print_config(self):
        '''Print the configuration files'''

        try:
            if os.path.exists(self.config_file):
                print(f'\n*** LOCAL CONFIGURATION AT: {self.config_file}\n')
                with open(self.config_file, 'r') as f:
                    print(f.read())

                if self.is_shared and os.path.exists(self.shared_config_file):
                    print(
                        f'*** SHARED CONFIGURATION AT: {self.shared_config_file}\n')
                    with open(self.shared_config_file, 'r') as f:
                        print(f.read())
            else:
                print(f'\n*** NO CONFIGURATION FOUND ***')
                print('\nYou can configure froster using the command:')
                print('    froster config')
        except Exception:
            print_error()

    def ses_verify_requests_sent(self, email_list):
        '''Set the ses verify requests sent email list in configuration file'''
        try:
            if not email_list:
                raise ValueError('No email list provided')

            # Write the config object to the config file
            self.__set_configuration_entry(
                'CLOULD', 'ses_verify_requests_sent', email_list)

        except Exception:
            print_error()

    def set_aws(self, aws: 'AWSBoto'):
        '''Set the AWS configuration'''

        try:
            print(f'\n*** AWS CONFIGURATION ***\n')

            # Ask user to enter the path to a aws credentials directory

            if os.path.exists(os.path.join(self.home_dir, '.aws')):
                default_aws_dir = os.path.join(self.home_dir, '.aws')
            else:
                default_aws_dir = None

            aws_dir_question = [
                inquirer.Path(
                    'aws_dir',
                    message=f'Enter the path to aws credentials directory (default: {default_aws_dir})',
                    default=default_aws_dir,
                    validate=self.__inquirer_check_path_exists)
            ]

            # Get the answer from the user
            aws_dir_answer = inquirer.prompt(
                aws_dir_question)

            # Get the AWS directory
            aws_dir = os.path.expanduser(aws_dir_answer['aws_dir'])

            # Set the new AWS directory at AWS Boto3
            aws.set_aws_directory(aws_dir)

            # Set the new AWS Directory
            self.aws_dir = aws_dir

            # Set the new AWS config file
            self.aws_config_file = os.path.join(self.aws_dir, 'config')

            # Set the new AWS credentials file
            self.aws_credentials_file = os.path.join(
                self.aws_dir, 'credentials')

            # Get list of current AWS profiles under {$AWS_DIR}/credentials
            aws_profiles = aws.get_profiles()

            # Add an option to create a new profile
            aws_profiles.append('+ Create new profile')

            # Ask user to choose an existing aws profile or create a new one
            aws_profile = inquirer.list_input("Choose your aws profile",
                                              choices=aws_profiles)

            # Check if user wants to create a new aws profile
            if aws_profile == '+ Create new profile':

                # Get new profile name
                aws_new_profile_name = inquirer.text(
                    message="Enter new profile name", validate=self.__inquirer_check_required)

                # If new profile name already exists, then prompt user if we should overwrite it
                if aws_new_profile_name in aws_profiles:
                    is_overwrite = inquirer.confirm(
                        message=f'WARNING: Do you want to overwrite profile {aws_new_profile_name}?', default=False)

                    if not is_overwrite:
                        # If user does not want to overwrite the profile, then return
                        return False

                # Get aws access key id
                aws_access_key_id = inquirer.text(
                    message="AWS Access Key ID", validate=self.__inquirer_check_required)

                # Get aws secret access key
                aws_secret_access_key = inquirer.text(
                    message="AWS Secret Access Key", validate=self.__inquirer_check_required)

                # Check if the provided aws credentials are valid
                print("\nChecking AWS credentials...")

                if aws.check_credentials(aws_access_key_id=aws_access_key_id,
                                         aws_secret_access_key=aws_secret_access_key):
                    print('    ...AWS credentials are valid\n')
                else:
                    print('    ...AWS credentials are NOT valid\n')
                    print('\nYou can configure aws credentials using the command:')
                    print('    froster config --aws\n')
                    return False

                # Get list of AWS regions
                aws_regions = aws.get_regions()

                # Ask user to choose a region
                region = inquirer.list_input("Choose your region",
                                             choices=aws_regions)

                print("\nChecking region...")
                if aws.check_credentials(aws_access_key_id=aws_access_key_id,
                                         aws_secret_access_key=aws_secret_access_key,
                                         aws_region_name=region):
                    print('    ...region is valid\n')
                else:
                    print('    ...region is NOT valid\n')
                    print(
                        '\nYou can configure aws credentials and region using the command:')
                    print('    froster config --aws\n')
                    return False

                # Create new profile in ~/.aws/credentials
                self.__set_aws_credentials(aws_profile_name=aws_new_profile_name,
                                           aws_access_key_id=aws_access_key_id,
                                           aws_secret_access_key=aws_secret_access_key)

                # Create new profile in ~/.aws/config
                self.__set_aws_config(aws_profile_name=aws_new_profile_name,
                                      region=region)

            else:
                # EXISTING PROFILE CONFIGURATION

                # Check if the provided aws credentials are valid
                print("\nChecking AWS credentials...")

                if aws.check_credentials(aws_profile=aws_profile):
                    print('    ...AWS credentials are valid\n')
                else:
                    print('    ...AWS credentials are NOT valid\n')
                    print('\nConfigure new aws credentials using the command:')
                    print('    froster config --aws\n')
                    return False

                # Check the seletected profile region
                aws_profile_region = self.__set_aws_get_config_region(
                    aws_profile=aws_profile)

                # Get list of AWS regions
                aws_regions = aws.get_regions()

                # Ask user to choose a region
                region = inquirer.list_input("Choose your region",
                                             default=aws_profile_region,
                                             choices=aws_regions)

                print("\nChecking region...")
                if aws.check_credentials(aws_profile=aws_profile,
                                         aws_region_name=region):
                    print('    ...region is valid\n')
                else:
                    print('    ...region is NOT valid\n')
                    print(
                        '\nYou can configure aws credentials and region using the command:')
                    print('    froster config --aws\n')

                    return False

                if region != aws_profile_region:
                    # Update region in the config file
                    self.__set_aws_config(aws_profile_name=aws_profile,
                                          region=region)

            # Get the profile name
            if aws_profile == '+ Create new profile':
                profile_name = aws_new_profile_name
            else:
                profile_name = aws_profile

            # Store aws dir in the config file
            self.__set_configuration_entry('AWS', 'aws_dir', aws_dir)

            # Store aws profile in the config file
            self.__set_configuration_entry('AWS', 'aws_profile', profile_name)

            # Store aws region in the config file
            self.__set_configuration_entry('AWS', 'aws_region', region)

            # Set the AWS profile in the boto3 session
            aws.set_session(profile_name, region)

            # Set aws init flag
            self.aws_init = True

            print(f'*** AWS CONFIGURATION DONE ***\n')

            return True

        except Exception:
            print_error()
            return False

    def __set_aws_config(self, aws_profile_name, region):
        ''' Update the AWS config of the given profile'''

        try:
            if not aws_profile_name:
                raise ValueError('No AWS profile provided')

            if not region:
                raise ValueError('No region provided')

            # If it does not exist, create aws directory
            os.makedirs(self.aws_dir, exist_ok=True, mode=0o775)

            # Create a aws config ConfigParser object
            aws_config = configparser.ConfigParser()

            # If exists, read the aws config file
            if os.path.exists(self.aws_config_file):
                aws_config.read(self.aws_config_file)

            # If it does not exist, create a new profile in the aws config file
            if not aws_config.has_section(aws_profile_name):
                aws_config.add_section(aws_profile_name)

            # Write the profile with the new region
            aws_config[aws_profile_name]['region'] = region

            # Write the profile with the new output format
            aws_config[aws_profile_name]['output'] = 'json'

            # Write the config object to the config file
            with open(self.aws_config_file, 'w') as f:
                aws_config.write(f)

            # Asure the permissions of the config file
            os.chmod(self.aws_config_file, 0o600)

        except Exception:
            print_error()

    def __set_aws_credentials(self,
                              aws_profile_name,
                              aws_access_key_id,
                              aws_secret_access_key):
        ''' Update the AWS credentials of the given profile'''

        try:
            if not aws_profile_name:
                raise ValueError('No AWS profile provided')

            if not aws_access_key_id:
                raise ValueError('No AWS access key id provided')

            if not aws_secret_access_key:
                raise ValueError('No AWS secret access key provided')

            # If it does not exist, create aws directory
            os.makedirs(self.aws_dir, exist_ok=True, mode=0o775)

            # Create a aws credentials ConfigParser object
            aws_credentials = configparser.ConfigParser()

            # if exists, read the aws credentials file
            if hasattr(self, 'aws_credentials_file') and os.path.exists(self.aws_credentials_file):
                aws_credentials.read(self.aws_credentials_file)

            # Update the region of the profile
            if not aws_credentials.has_section(aws_profile_name):
                aws_credentials.add_section(aws_profile_name)

            # Write the profile with the new access key id
            aws_credentials[aws_profile_name]['aws_access_key_id'] = aws_access_key_id

            # Write the profile with the new secret access key
            aws_credentials[aws_profile_name]['aws_secret_access_key'] = aws_secret_access_key

            # Write the config object to the config file
            with open(self.aws_credentials_file, 'w') as f:
                aws_credentials.write(f)

            # Asure the permissions of the credentials file
            os.chmod(self.aws_credentials_file, 0o600)

        except Exception:
            print_error()

    def __set_aws_get_config_region(self, aws_profile):
        '''Set the AWS region for the given profile'''

        try:
            if not aws_profile:
                raise ValueError('No AWS profile provided')

            # Check if aws credentials file exists
            if not os.path.exists(self.aws_config_file):
                raise ValueError('AWS config file does not exist')

            # Create a ConfigParser object
            config = configparser.ConfigParser()

            # Read the aws config file
            if hasattr(self, 'aws_config_file') and os.path.exists(self.aws_config_file):
                config.read(self.aws_config_file)

            # Return the region if it exists
            if config.has_section(aws_profile) and config.has_option(aws_profile, 'region'):
                return config.get(aws_profile, 'region')

            # Return None otherwise
            return None

        except Exception:
            print_error()
            return None

    def __set_configuration_entry(self, section, key, value):
        '''Set a configuration entry in the config file'''

        try:
            # Create a ConfigParser object
            config = configparser.ConfigParser()

            # Check which config file to use
            if self.is_shared and section in ['NIH', 'S3', 'SLURM', 'CLOUD']:

                # Create shared config directory in case it does not exist
                os.makedirs(self.shared_dir, exist_ok=True, mode=0o775)

                # Get the shared config file
                file = self.shared_config_file
            else:

                # Create config directory in case it does not exist
                os.makedirs(self.config_dir, exist_ok=True, mode=0o775)

                # Get the config file
                file = self.config_file

            # if exists, read the config file
            if os.path.exists(file):
                config.read(file)

            # Create the section if it does not exist
            if not config.has_section(section):
                config.add_section(section)

            # Set the value
            config[section][key] = str(value)

            # Write the config object to the config file
            with open(file, 'w') as f:
                config.write(f)

            # Set the value in the config object
            setattr(self, key, value)

        except Exception:
            print_error()

    def set_ec2_last_instance(self, instance):
        '''Set the last ec2 instance in configuration file'''

        try:
            if not instance:
                raise ValueError('No instance provided')

            # Write the config object to the config file
            self.__set_configuration_entry(
                'CLOULD', 'ec2_last_instance', instance)

        except Exception:
            print_error()

    def set_nih(self):
        '''Set the NIH configuration'''

        try:
            print(f'\n*** NIH S3 CONFIGURATION ***\n')

            is_nih = inquirer.confirm(
                message="Do you want to search and link NIH life sciences grants with your archives?", default=False)

            self.__set_configuration_entry('NIH', 'is_nih', is_nih)

            print(f'*** NIH S3 CONFIGURATION DONE***\n')

            # Set the nih init flag
            self.nih_init = True

            return True

        except Exception:
            print_error()
            return False

    def set_s3(self, aws: "AWSBoto"):
        '''Set the S3 configuration'''

        try:
            print(f'\n*** S3 CONFIGURATION ***\n')

            # Check if aws configuration is complete
            if not self.aws_init:
                print(f'AWS configuration is missing')
                print('You can configure aws settings using the command:')
                print('    froster config --aws')
                return False

            print(
                f'Checking AWS credentials for profile "{self.aws_profile}"...')
            if aws.check_credentials(aws_profile=self.aws_profile):
                print('    ...AWS credentials are valid\n')
            else:
                print('    ...AWS credentials are NOT valid\n')
                print('\nYou can configure aws credentials using the command:')
                print('    froster config --aws')
                print(f'\n*** S3 CONFIGURATION DONE ***\n')
                return False

            # Get list froster buckets for the given profile
            s3_buckets = aws.get_buckets()

            # Add an option to create a new bucket
            s3_buckets.append('+ Create new bucket')

            default_bucket = self.bucket_name if hasattr(
                self, 'bucket_name') else None

            # Ask user to choose an existing aws s3 bucket or create a new one
            s3_bucket = inquirer.list_input("Choose your aws s3 bucket",
                                            default=default_bucket,
                                            choices=s3_buckets)

            # Check if user wants to create a new aws s3 bucket
            if s3_bucket == '+ Create new bucket':

                # Get new bucket name
                new_bucket_name = inquirer.text(
                    message='Enter new bucket name (it must start with "froster-")',
                    validate=self.__inquirer_check_bucket_name)

                if new_bucket_name in s3_buckets:
                    print(f'Bucket {new_bucket_name} already exists')
                    return False

                # Create new bucket
                if not aws.create_bucket(bucket_name=new_bucket_name,
                                         region=self.aws_region):
                    print(f'Could not create bucket {new_bucket_name}')
                    return False

                # Store new aws s3 bucket in the config object
                self.__set_configuration_entry(
                    'S3', 'bucket_name', new_bucket_name)
            else:
                # Store aws s3 bucket in the config object
                self.__set_configuration_entry('S3', 'bucket_name', s3_bucket)

            # Get the archive directory in the selected bucket
            archive_dir = inquirer.text(
                message='Enter the directory name inside S3 bucket (default= "froster")',
                default='froster',
                validate=self.__inquirer_check_required)

            # Print newline after this prompt
            print()

            # Store aws s3 archive dir in the config object
            self.__set_configuration_entry('S3', 'archive_dir', archive_dir)

            # Get the storage class for the selected bucket
            if hasattr(self, 'storage_class') and self.storage_class is not None:
                default_storage_class = self.storage_class
            else:
                default_storage_class = 'DEEP_ARCHIVE'

            # Get the storage class for the selected bucket
            storage_class = inquirer.list_input("Choose the AWS S3 storage class",
                                                default=default_storage_class,
                                                choices={'DEEP_ARCHIVE', 'GLACIER', 'INTELLIGENT_TIERING'})

            # Store aws s3 storage class in the config object
            self.__set_configuration_entry(
                'S3', 'storage_class', storage_class)

            # Set the s3 init flag
            self.s3_init = True

            print(f'\n*** S3 CONFIGURATION DONE ***\n')

            return True

        except Exception:
            print_error()
            return False

    def set_shared(self):
        '''Set the shared configuration'''

        try:
            print(f'\n*** SHARED CONFIGURATION ***\n')

            is_shared = inquirer.confirm(
                message="Do you want to collaborate with other users on archive and restore?", default=False)

            # If it is a shared configuration we need to ask the user for the path to the shared config directory
            # and check if we need to move cfg.archive_json_file_name and configuration to the shared directory
            if is_shared:

                # Ask user to enter the path to a shared config directory
                # TODO: make this inquiring in shortchut mode once this PR is merged: https://github.com/magmax/python-inquirer/pull/543
                shared_config_dir_question = [
                    inquirer.Path(
                        'shared_dir', message='Enter the path to a shared config directory', validate=self.__inquirer_check_path_exists)
                ]

                # Get the answer from the user
                shared_config_dir_answer = inquirer.prompt(
                    shared_config_dir_question)
                shared_config_dir = shared_config_dir_answer['shared_dir']
                shared_config_dir = os.path.expanduser(shared_config_dir)

                # Create the directory in case it does not exist
                os.makedirs(shared_config_dir, exist_ok=True, mode=0o775)

                # Ask the user if they want to move the froster-archives.json file to the shared directory
                if os.path.isfile(os.path.join(shared_config_dir, self.archive_json_file_name)):
                    # If the froster-archives.json file is found in the shared config directory we are done here
                    print(
                        f"\nNOTE: the {self.archive_json_file_name} file was found in the shared config directory\n")
                else:

                    # If the froster-archives.json file is found in the local directory we ask the user if they want to move it to the shared directory
                    if os.path.isfile(os.path.join(self.data_dir, self.archive_json_file_name)):
                        print(
                            f"\nNOTE: the {self.archive_json_file_name} file was found in the local directory\n")

                        # Ask user if they want to move the local list of files and directories that were archived to the shared directory
                        local_froster_archives_to_shared = inquirer.confirm(
                            message="Do you want to move the local list of files and directories that were archived to the shared directory?", default=True)

                        # Move the local froster archives to shared directory
                        if local_froster_archives_to_shared:
                            shutil.copy(os.path.join(
                                self.data_dir, self.archive_json_file_name), shared_config_dir)
                            print(
                                f"\nNOTE: Local list of archived files and directories was moved to {shared_config_dir}\n")

            # Set the shared flag in the config file
            self.__set_configuration_entry('SHARED', 'is_shared', is_shared)

            # Set the shared directory in the config file and move the config file shared sections to the shared config file
            if is_shared:
                self.__set_configuration_entry(
                    'SHARED', 'shared_dir', shared_config_dir)
                self.__set_configuration_entry('SHARED', 'shared_config_file', os.path.join(
                    shared_config_dir, self.shared_config_file_name))
                self.__set_shared_move_config()

                self.is_shared = True
            else:
                self.is_shared = False

            print(f'*** SHARED CONFIGURATION DONE ***\n')

            return True

        except Exception:
            print_error()
            return False

    def __set_shared_move_config(self):
        '''Move the local configuration sections to the shared configuration file'''

        try:
            # If shared configuration file exists, nothing to move
            if hasattr(self, 'shared_config_file') and os.path.isfile(self.shared_config_file):
                print(
                    f"NOTE: Using shared configuration file found in {self.shared_config_file}\n")
                return

            # Clean up both configuration files
            local_config = configparser.ConfigParser()
            local_config.read(self.config_file)

            if not 'NIH' in local_config and not 'S3' in local_config and not 'SLURM' in local_config:
                # Nothing to copy from local configuration to shared configuration
                return

            move_config_to_shared = inquirer.confirm(
                message="Do you want to move your current configuration to the shared directory?", default=True)

            if move_config_to_shared:
                shutil.copy(self.config_file, self.shared_config_file)
                print(
                    "NOTE: Shared configuration file was moved to the shared directory\n")

                shared_config = configparser.ConfigParser()
                shared_config.read(self.shared_config_file)

                # Remove sections from local_config
                if 'NIH' in local_config:
                    local_config.remove_section('NIH')
                if 'S3' in local_config:
                    local_config.remove_section('S3')
                if 'SLURM' in local_config:
                    local_config.remove_section('SLURM')

                # Remove sections from shared_config
                if 'USER' in shared_config:
                    shared_config.remove_section('USER')
                if 'AWS' in shared_config:
                    shared_config.remove_section('AWS')
                if 'SHARED' in shared_config:
                    shared_config.remove_section('SHARED')

                # Write the source INI file
                with open(self.config_file, 'w') as f:
                    local_config.write(f)

                # Write the source INI file
                with open(self.shared_config_file, 'w') as f:
                    shared_config.write(f)

        except Exception:
            print_error()

    def set_user(self):
        '''Set the user configuration'''

        try:
            print(f'\n*** USER CONFIGURATION ***\n')

            # Ask the user for their full name
            fullname = inquirer.text(
                message="Enter your full name", validate=self.__inquirer_check_required)

            # Print for a new line when prompting
            print()

            # Set the user's full name in the config file
            self.__set_configuration_entry('USER', 'name', fullname)

            # Ask the user for their email
            email = inquirer.text(message="Enter your email",
                                  validate=self.__inquirer_check_email_format)

            # Print for a new line when prompting
            print()

            # Set the user's email in the config file
            self.__set_configuration_entry('USER', 'email', email)

            # Set the user init flag
            self.user_init = True

            print(f'*** USER CONFIGURATION DONE ***\n')

            return True

        except Exception:
            print_error()
            return False

    def set_slurm(self, args):
        '''Set the Slurm configuration'''

        try:
            # Run the sacctmgr command
            result = subprocess.run(
                ['sacctmgr', 'show', 'config'], capture_output=False)

            if result.returncode != 0:
                print(
                    "sacctmgr command failed. Please ensure it's installed and in your PATH and you are in a head node.")
                return False

            if shutil.which('scontrol'):

                print(f'\n*** SLURM CONFIGURATION ***\n')

                slurm_walltime_days = inquirer.text(
                    message="Set the Slurm --time (days) for froster jobs (default = 7)",
                    default=7,
                    validate=self.__inquirer_check_is_number)

                slurm_walltime_hours = inquirer.text(
                    message="Set the Slurm --time (hours) for froster jobs (default = 0)",
                    default=0,
                    validate=self.__inquirer_check_is_number)

                # TODO: This class __init__ should not be here, it should be in the main
                se = Slurm(args, self)

                # Get the allowed partitions and QOS
                parts = se.get_allowed_partitions_and_qos()

                if parts is not None:
                    # Ask the user to select the Slurm partition and QOS
                    slurm_partition = inquirer.list_input(
                        message=f'Select the Slurm partition for jobs that last up to {slurm_walltime_days} days and {slurm_walltime_hours} hours',
                        choices=list(parts.keys()))

                    # Ask the user to select the Slurm QOS
                    slurm_qos = inquirer.list_input(
                        message=f'Select the Slurm QOS for jobs that last up to {slurm_walltime_days} days and {slurm_walltime_hours} hours',
                        choices=list(parts[slurm_partition]))

                # Set the Slurm configuration in the config file
                self.__set_configuration_entry(
                    'SLURM', 'slurm_walltime_days', slurm_walltime_days)
                self.__set_configuration_entry(
                    'SLURM', 'slurm_walltime_hours', slurm_walltime_hours)
                self.__set_configuration_entry(
                    'SLURM', 'slurm_partition', slurm_partition)
                self.__set_configuration_entry('SLURM', 'slurm_qos', slurm_qos)

                if shutil.which('sbatch'):
                    slurm_lscratch = inquirer.text(
                        message="How do you request local scratch from Slurm? (Optional: press enter to skip)")
                    lscratch_mkdir = inquirer.text(
                        message="Is there a user script that provisions local scratch? (Optional: press enter to skip)")
                    lscratch_rmdir = inquirer.text(
                        message="Is there a user script that tears down local scratch at the end? (Optional: press enter to skip)")
                    lscratch_root = inquirer.text(
                        message="What is the local scratch root? (Optional: press enter to skip)")

                    self.__set_configuration_entry(
                        'SLURM', 'slurm_lscratch', slurm_lscratch)
                    self.__set_configuration_entry(
                        'SLURM', 'lscratch_mkdir', lscratch_mkdir)
                    self.__set_configuration_entry(
                        'SLURM', 'lscratch_rmdir', lscratch_rmdir)
                    self.__set_configuration_entry(
                        'SLURM', 'lscratch_root', lscratch_root)

                print(f'\n*** SLURM CONFIGURATION DONE ***\n')

            else:
                print(f'\n*** SLURM NOT FOUND: Nothing to configure ***\n')

            return True

        except FileNotFoundError:
            print("sacctmgr command not found. Please ensure it's installed and in your PATH and you are in a head node.")
            return False

        except Exception:
            print_error()
            return False

    def check_update(self):
        '''Set the update check'''

        try:
            timestamp = time.time()

            if hasattr(self, 'update_check_timestamp') and self.update_check_timestamp is not None:
                # Check if last day was less than 86400 * 7 = (1 day) * 7  = 1 week
                print(timestamp)
                print(self.update_check_timestamp)
                print(timestamp - self.update_check_timestamp)
                if timestamp - self.update_check_timestamp < (86400*7):
                    # Less than a week since last check
                    return False

            # Set the update check flag in the config file
            self.__set_configuration_entry(
                'UPDATE', 'update_check_timestamp', timestamp)
            return True

        except Exception:
            print_error()
            return False


class AWSBoto:
    '''AWS handler class. This class is used to interact with AWS services.'''
    # TODO: arch must be defined as an class Archive instance

    def __init__(self, args: argparse.Namespace, cfg: ConfigManager, arch: "Archiver"):
        '''Initialize the AWSBoto class'''

        try:
            # Initialize variables
            self.args = args
            self.cfg = cfg
            self.arch = arch

            # Set the AWS directory
            if hasattr(self.cfg, 'aws_dir'):
                self.set_aws_directory(self.cfg.aws_dir)

        except Exception:
            print_error()

    def set_aws_directory(self, aws_dir):
        '''Set the AWS directory'''

        try:
            # Specify the paths to the config and credentials files
            os.environ['AWS_CONFIG_FILE'] = os.path.join(aws_dir, 'config')
            os.environ['AWS_SHARED_CREDENTIALS_FILE'] = os.path.join(
                aws_dir, 'credentials')
        except Exception:
            print_error()

    def check_session(self):
        '''Check if the current AWS session is valid'''

        try:
            if not self.cfg.aws_init:
                return False

            if self.check_credentials(aws_profile=self.cfg.aws_profile):
                self.set_session(profile_name=self.cfg.aws_profile,
                                 region=self.cfg.aws_region)
                return True
            else:
                return False

        except Exception:
            print_error()
            return False

    def check_bucket_access(self, bucket_name, readwrite=False):
        '''Check if the user has access to the given bucket'''

        if not bucket_name:
            raise ValueError('No bucket name provided')

        try:
            # Check if the session is valid
            if not self._check_session():
                print(
                    f"\nError: AWS credentials are not valid for profile {self.cfg.aws_profile}")
                print("run 'froster config --aws' to fix this.\n")
                sys.exit(1)

            # Get the bucket Access Control List (ACL)
            bucket_info = self.s3_client.get_bucket_acl(Bucket=bucket_name)

            # Access the 'Permission' key
            permission = bucket_info['Grants'][0]['Permission']

            if readwrite:
                return (permission == 'FULL_CONTROL')
            else:
                return (permission == 'READ')

        except Exception:
            return False

    def check_credentials(self,
                          aws_profile=None,
                          aws_access_key_id=None,
                          aws_secret_access_key=None,
                          aws_region_name=None):
        ''' AWS credential checker

        Check if the provided AWS credentials or provide AWS profile are valid.
        If nothing is provided, the current session is checked.'''

        try:
            if aws_access_key_id and aws_secret_access_key:
                # Build a new STS client with the provided credentials
                sts = boto3.Session(aws_access_key_id=aws_access_key_id,
                                    aws_secret_access_key=aws_secret_access_key,
                                    region_name=aws_region_name).client('sts')

            elif aws_profile:
                # Build a new STS client with the provided profile
                sts = boto3.Session(profile_name=aws_profile,
                                    region_name=aws_region_name).client('sts')

            elif hasattr(self, 's3_client'):
                # Get the current sts_client
                sts = self.sts_client

            else:
                return False

            # Check that we can get the caller identity
            sts.get_caller_identity()

            # Close the session
            sts.close()

            # Credentials are valid
            return True

        except Exception:
            print_error()
            return False

    def create_bucket(self, bucket_name, region):
        '''Create a new S3 bucket with the provided name.'''

        if not bucket_name:
            raise ValueError("Bucket name not provided")

        try:

            # Check if the session is valid
            if not self._check_session():
                print(
                    f"\nError: AWS credentials are not valid for profile {self.cfg.aws_profile}")
                print("run 'froster config --aws' to fix this.\n")
                return False

            print(f'\nCreating bucket {bucket_name}...')

            self.s3_client.create_bucket(Bucket=bucket_name,
                                         CreateBucketConfiguration={'LocationConstraint': region})
            print(f'    ...bucket created\n')

            print(f'\nApplying AES256 encryption to bucket {bucket_name}...')
            encryption_configuration = {
                'Rules': [
                    {
                        'ApplyServerSideEncryptionByDefault': {
                            'SSEAlgorithm': 'AES256'
                        }
                    }
                ]
            }
            self.s3_client.put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration=encryption_configuration
            )
            print(f'    ...encryption applied.\n')

            return True

        except Exception:
            print_error()
            return False

    def get_buckets(self):
        ''' Get a list of all the froster buckets in the current session'''

        # Check if the session is valid
        if not self._check_session():
            print(
                f"\nError: AWS credentials are not valid for profile {self.cfg.aws_profile}")
            print("run 'froster config --aws' to fix this.\n")
            sys.exit(1)

        try:
            # Get all the buckets
            existing_buckets = self.s3_client.list_buckets()

            # Extract the bucket names
            bucket_list = [bucket['Name']
                           for bucket in existing_buckets['Buckets']]

            # Filter the bucket names and retrieve only froster-* buckets
            froster_bucket_list = [
                x for x in bucket_list if x.startswith('froster-')]

            # Return the list of froster buckets
            return froster_bucket_list

        except Exception:
            print_error()
            sys.exit(1)

    def get_profiles(self):
        ''' Get a list of available AWS profiles'''

        try:
            return boto3.Session().available_profiles

        except Exception:
            print_error()
            return None

    def get_regions(self):
        '''Get the regions for the current session or get default regions.'''

        try:
            # Check if the session is valid
            self._check_session()

            regions = self.ec2_client.describe_regions()
            region_names = [region['RegionName']
                            for region in regions['Regions']]
            return region_names

        except Exception:
            # If current session does not have a region, return default regions
            try:
                s = boto3.Session()
                dynamodb_regions = s.get_available_regions('dynamodb')
                return dynamodb_regions
            except Exception:
                print_error()
                sys.exit(1)

    def list_objects_in_bucket(self, bucket_name):
        '''List all the objects in the given bucket'''

        if not bucket_name:
            raise ValueError('No bucket name provided')

        # Check if the session is valid
        if not self._check_session():
            print(
                f"\nError: AWS credentials are not valid for profile {self.cfg.aws_profile}")
            print("run 'froster config --aws' to fix this.\n")
            sys.exit(1)

        try:
            response = self.s3_client.list_objects_v2(Bucket=bucket_name)

            return response.get('Contents', [])
        except Exception:
            print_error()
            return []

    def set_session(self, profile_name, region):
        ''' Set the AWS profile for the current session'''

        try:
            # Initialize a Boto3 session using the configured profile
            session = boto3.Session(
                profile_name=profile_name, region_name=region)

            # Initialize the AWS clients
            self.ce_client = session.client('ce')
            self.ec2_client = session.client('ec2')
            self.iam_client = session.client('iam')
            self.s3_client = session.client('s3')
            self.ses_client = session.client('ses')
            self.sts_client = session.client('sts')

            # TODO: This is for _ec2_create_instance function. Review if we really needed
            self.session = session

        except Exception as e:
            pass

    def close_session(self):
        if hasattr(self, 'ce_client'):
            self.ce_client.close()
            del self.ce_client
        if hasattr(self, 'ec2_client'):
            self.ec2_client.close()
            del self.ec2_client
        if hasattr(self, 'iam_client'):
            self.iam_client.close()
            del self.iam_client
        if hasattr(self, 's3_client'):
            self.s3_client.close()
            del self.s3_client
        if hasattr(self, 'ses_client'):
            self.ses_client.close()
            del self.ses_client
        if hasattr(self, 'sts_client'):
            self.sts_client.close()
            del self.sts_client

    def get_time_zone(self):
        '''Get the current time zone string from the system'''

        try:
            # Resolve the /etc/localtime symlink
            timezone_path = os.path.realpath("/etc/localtime")

            # Extract the time zone string by stripping off the prefix of the zoneinfo path
            current_tz_str = timezone_path.split("zoneinfo/")[-1]

            # Return the time zone string
            return current_tz_str

        except Exception as e:
            print(f'Error: {e}. Using default value "America/Los_Angeles"')
            return ('America/Los_Angeles')

    def glacier_restore(self, bucket, prefix, keep_days=30, ret_opt="Bulk"):
        '''Restore the objects in the given bucket with the given prefix'''

        # Check if the session is valid
        if not self._check_session():
            print(
                f"\nError: AWS credentials are not valid for profile {self.cfg.aws_profile}")
            print("run 'froster config --aws' to fix this.\n")
            sys.exit(1)

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                print(f"Access denied for bucket '{bucket}'", file=sys.stderr)
                print('Check your permissions and/or credentials.', file=sys.stderr)
            else:
                print_error()
            return [], [], [], []

        # Initialize lists to store the keys
        triggered_keys = []
        restoring_keys = []
        restored_keys = []
        not_glacier_keys = []

        for page in pages:
            if not 'Contents' in page:
                continue

            for object in page['Contents']:
                object_key = object['Key']

                # Check if there are additional slashes after the prefix,
                # indicating that the object is in a subfolder.
                remaining_path = object_key[len(prefix):]
                if '/' in remaining_path:
                    continue

                header = self.s3_client.head_object(
                    Bucket=bucket, Key=object_key)

                if 'StorageClass' in header:
                    if not header['StorageClass'] in {'GLACIER', 'DEEP_ARCHIVE'}:
                        not_glacier_keys.append(object_key)
                        continue
                else:
                    continue

                if 'Restore' in header:
                    if 'ongoing-request="true"' in header['Restore']:
                        restoring_keys.append(object_key)
                        continue

                if 'Restore' in header:
                    if 'ongoing-request="false"' in header['Restore']:
                        restored_keys.append(object_key)
                        continue

                try:
                    self.s3_client.restore_object(
                        Bucket=bucket,
                        Key=object_key,
                        RestoreRequest={
                            'Days': keep_days,
                            'GlacierJobParameters': {
                                'Tier': ret_opt
                            }
                        }
                    )
                    triggered_keys.append(object_key)

                except Exception:
                    print_error()
                    print(f'Restore request for {object_key} failed.')
                    return [], [], [], []

        return triggered_keys, restoring_keys, restored_keys, not_glacier_keys

    def _get_s3_data_size(self, folders):
        """
        Get the size of data in GiB aggregated from multiple
        S3 buckets from froster archives identified by a
        list of folders

        :return: Size of the data in GiB.
        """
        # Initialize total size
        total_size_bytes = 0

        # bucket_name, prefix, recursive=False
        for fld in folders:
            buc, pre, recur, _ = self.arch.archive_get_bucket_info(fld)
            if not buc:
                print(f'Error: No archive config found for folder {fld}')
                continue
            # returns bucket(str), prefix(str), recursive(bool), glacier(bool)
            # Use paginator to handle buckets with large number of objects
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=buc, Prefix=pre):
                if "Contents" in page:  # Ensure there are objects under the specified prefix
                    for obj in page['Contents']:
                        key = obj['Key']
                        if recur or (key.count('/') == pre.count('/') and key.startswith(pre)):
                            total_size_bytes += obj['Size']

        total_size_gib = total_size_bytes / (1024 ** 3)  # Convert bytes to GiB
        return total_size_gib

    def wait_for_ssh_ready(self, hostname, port=22, timeout=60):
        start_time = time.time()
        while time.time() - start_time < timeout:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)  # Set a timeout on the socket operations
            result = s.connect_ex((hostname, port))
            if result == 0:
                s.close()
                return True
            else:
                time.sleep(5)  # Wait for 5 seconds before retrying
                s.close()
        print("Timeout reached without SSH server being ready.")
        return False

    def ec2_deploy(self, folders, s3size=NotImplementedError):

        if s3size != 0:
            s3size = self._get_s3_data_size(folders)
        print(f"Total data in all folders: {s3size:.2f} GiB")
        prof = self._ec2_create_iam_policy_roles_ec2profile()
        iid, ip = self._ec2_create_instance(s3size, prof)
        print(' Waiting for ssh host to become ready ...')
        if not self.wait_for_ssh_ready(ip):
            return False

        bootstrap_restore = self._ec2_user_space_script(iid)

        # part 2, prep restoring .....
        for folder in self.args.folders:
            refolder = os.path.join(os.path.sep, 'restored', folder[1:])
            bootstrap_restore += f'\nmkdir -p "{refolder}"'
            bootstrap_restore += f'\nln -s "{refolder}" ~/restored-$(basename "{folder}")'
            bootstrap_restore += f'\nsudo mkdir -p $(dirname "{folder}")'
            bootstrap_restore += f'\nsudo chown ec2-user $(dirname "{folder}")'
            bootstrap_restore += f'\nln -s "{refolder}" "{folder}"'

        # this block may need to be moved to a function
        argl = ['--aws', '-a']
        cmdlist = [item for item in sys.argv if item not in argl]
        argl = ['--instance-type', '-i']  # if found remove option and next arg
        cmdlist = [x for i, x in enumerate(cmdlist) if x
                   not in argl and (i == 0 or cmdlist[i-1] not in argl)]
        if not '--profile' in cmdlist and self.args.aws_profile:
            cmdlist.insert(1, '--profile')
            cmdlist.insert(2, self.args.aws_profile)
        cmdline = 'froster ' + \
            " ".join(map(shlex.quote, cmdlist[1:]))  # original cmdline
        if not self.args.folders[0] in cmdline:
            folders = '" "'.join(self.args.folders)
            cmdline = f'{cmdline} "{folders}"'
        # end block

        print(f" will execute '{cmdline}' on {ip} ... ")
        bootstrap_restore += '\n' + cmdline
        # once retrieved from Glacier we need to restore this 5 and 12 hours from now
        bootstrap_restore += '\n' + f"echo '{cmdline}' | at now + 5 hours"
        bootstrap_restore += '\n' + f"echo '{cmdline}' | at now + 12 hours"
        ret = self.ssh_upload('ec2-user', ip,
                              bootstrap_restore, "bootstrap.sh", is_string=True)
        if ret.stdout or ret.stderr:
            print(ret.stdout, ret.stderr)
        ret = self.ssh_execute('ec2-user', ip,
                               'nohup bash bootstrap.sh < /dev/null > bootstrap.out 2>&1 &')
        if ret.stdout or ret.stderr:
            print(ret.stdout, ret.stderr)
        print(' Executed bootstrap and restore script ... you may have to wait a while ...')
        print(' but you can already login using "froster ssh"')

        os.system(f'echo "ls -l {self.args.folders[0]}" >> ~/.bash_history')
        ret = self.ssh_upload('ec2-user', ip,
                              "~/.bash_history", ".bash_history")
        if ret.stdout or ret.stderr:
            print(ret.stdout, ret.stderr)

        ret = self.ssh_upload(
            'ec2-user', ip, self.cfg.archive_json, "~/.config/froster/")
        if ret.stdout or ret.stderr:
            print(ret.stdout, ret.stderr)

        self.send_email_ses(self.cfg.email, self.cfg.email, 'Froster restore on EC2',
                            f'this command line was executed on host {ip}:\n{cmdline}')

    def _ec2_create_or_get_iam_policy(self, pol_name, pol_doc):

        policy_arn = None
        try:
            response = self.iam_client.create_policy(
                PolicyName=pol_name,
                PolicyDocument=json.dumps(pol_doc)
            )
            policy_arn = response['Policy']['Arn']
            print(f"Policy created with ARN: {policy_arn}")
        except self.iam_client.exceptions.EntityAlreadyExistsException as e:
            policies = self.iam_client.list_policies(Scope='Local')
            # Scope='Local' for customer-managed policies,
            # 'AWS' for AWS-managed policies
            for policy in policies['Policies']:
                if policy['PolicyName'] == pol_name:
                    policy_arn = policy['Arn']
                    break
            print(f'Policy {pol_name} already exists')
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)
        return policy_arn

    def _ec2_create_froster_iam_policy(self):

        # Define policy name and policy document
        policy_name = 'FrosterEC2DescribePolicy'
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "ec2:Describe*",
                    "Resource": "*"
                }
            ]
        }

        # Get current IAM user's details
        user = self.iam_client.get_user()
        user_name = user['User']['UserName']

        # Check if policy already exists for the user
        existing_policies = self.iam_client.list_user_policies(
            UserName=user_name)
        if policy_name in existing_policies['PolicyNames']:
            print(f"{policy_name} already exists for user {user_name}.")
            return

        # Create policy for user
        self.iam_client.put_user_policy(
            UserName=user_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )

        print(
            f"Policy {policy_name} attached successfully to user {user_name}.")

    def _ec2_create_iam_policy_roles_ec2profile(self):
        # create all the IAM requirement to allow an ec2 instance to
        # 1. self destruct, 2. monitor cost with CE and 3. send emails via SES

      # Step 0: Create IAM self destruct and EC2 read policy
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ec2:Describe*",     # Basic EC2 read permissions
                    ],
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": "ec2:TerminateInstances",
                    "Resource": "*",
                    "Condition": {
                        "StringEquals": {
                            "ec2:ResourceTag/Name": "FrosterSelfDestruct"
                        }
                    }
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "ce:GetCostAndUsage"
                    ],
                    "Resource": "*"
                }
            ]
        }
        policy_name = 'FrosterSelfDestructPolicy'

        destruct_policy_arn = self._ec2_create_or_get_iam_policy(
            policy_name, policy_document)

        # 1. Create an IAM role
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                },
            ]
        }

        role_name = "FrosterEC2Role"
        try:
            self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Froster role allows Billing, SES and Terminate'
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print(f'Role {role_name} already exists.')
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)

        # 2. Attach permissions policies to the IAM role
        cost_explorer_policy = "arn:aws:iam::aws:policy/AWSBillingReadOnlyAccess"
        ses_policy = "arn:aws:iam::aws:policy/AmazonSESFullAccess"

        try:

            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=cost_explorer_policy
            )

            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=ses_policy
            )

            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=destruct_policy_arn
            )
        except self.iam_client.exceptions.PolicyNotAttachableException as e:
            print(
                f"Policy {e.policy_arn} is not attachable. Please check your permissions.")
            return False
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)
            return False
        # 3. Create an instance profile and associate it with the role
        instance_profile_name = "FrosterEC2Profile"
        try:
            self.iam_client.create_instance_profile(
                InstanceProfileName=instance_profile_name
            )
            self.iam_client.add_role_to_instance_profile(
                InstanceProfileName=instance_profile_name,
                RoleName=role_name
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print(f'Profile {instance_profile_name} already exists.')
            return instance_profile_name
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
            return None
        except Exception as e:
            print('Other Error:', e)
            return None

        # Give AWS a moment to propagate the changes
        print('wait for 15 sec ...')
        time.sleep(15)  # Wait for 15 seconds

        return instance_profile_name

    def _ec2_create_and_attach_security_group(self, instance_id):

        ec2_resource = self.session.resource('ec2')
        group_name = 'SSH-HTTP-ICMP'

        # Check if security group already exists
        security_groups = self.ec2_client.describe_security_groups(
            Filters=[{'Name': 'group-name', 'Values': [group_name]}])
        if security_groups['SecurityGroups']:
            security_group_id = security_groups['SecurityGroups'][0]['GroupId']
        else:
            # Create security group
            response = self.ec2_client.create_security_group(
                GroupName=group_name,
                Description='Allows SSH and ICMP inbound traffic'
            )
            security_group_id = response['GroupId']

            # Allow ports 22, 80, 443, 8000-9000, ICMP
            self.ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 8000,
                        'ToPort': 9000,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },                    {
                        'IpProtocol': 'icmp',
                        'FromPort': -1,  # -1 allows all ICMP types
                        'ToPort': -1,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )

        # Attach the security group to the instance
        instance = ec2_resource.Instance(instance_id)
        current_security_groups = [sg['GroupId']
                                   for sg in instance.security_groups]

        # Check if the security group is already attached to the instance
        if security_group_id not in current_security_groups:
            current_security_groups.append(security_group_id)
            instance.modify_attribute(Groups=current_security_groups)

        return security_group_id

    def _ec2_get_latest_amazon_linux2_ami(self):

        response = self.ec2_client.describe_images(
            Filters=[
                {'Name': 'name', 'Values': ['al2023-ami-*']},
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'architecture', 'Values': ['x86_64']},
                {'Name': 'virtualization-type', 'Values': ['hvm']}
            ],
            Owners=['amazon']

            # amzn2-ami-hvm-2.0.*-x86_64-gp2
            # al2023-ami-kernel-default-x86_64

        )

        # Sort images by creation date to get the latest
        images = sorted(response['Images'],
                        key=lambda k: k['CreationDate'], reverse=True)
        if images:
            return images[0]['ImageId']
        else:
            return None

    def _create_progress_bar(self, max_value):
        def show_progress_bar(iteration):
            percent = ("{0:.1f}").format(100 * (iteration / float(max_value)))
            length = 50  # adjust as needed for the bar length
            filled_length = int(length * iteration // max_value)
            bar = "█" * filled_length + '-' * (length - filled_length)
            if sys.stdin.isatty():
                print(f'\r|{bar}| {percent}%', end='\r')
            if iteration == max_value:
                print()

        return show_progress_bar

    def _ec2_cloud_init_script(self):
        # Define the User Data script
        long_timezone = self.get_time_zone()
        userdata = textwrap.dedent(f'''
        #! /bin/bash
        dnf install -y gcc mdadm
        bigdisks=$(lsblk --fs --json | jq -r '.blockdevices[] | select(.children == null and .fstype == null) | "/dev/" + .name')
        numdisk=$(echo $bigdisks | wc -w)
        mkdir /restored
        if [[ $numdisk -gt 1 ]]; then
          mdadm --create /dev/md0 --level=0 --raid-devices=$numdisk $bigdisks
          mkfs -t xfs /dev/md0
          mount /dev/md0 /restored
        elif [[ $numdisk -eq 1 ]]; then
          mkfs -t xfs $bigdisks
          mount $bigdisks /restored
        fi
        chown ec2-user /restored
        dnf check-update
        dnf update -y
        dnf install -y at gcc vim wget python3-pip python3-psutil
        hostnamectl set-hostname froster
        timedatectl set-timezone '{long_timezone}'
        loginctl enable-linger ec2-user
        systemctl start atd
        dnf upgrade
        dnf install -y mc git docker lua lua-posix lua-devel tcl-devel nodejs-npm
        dnf group install -y 'Development Tools'
        cd /tmp
        wget https://sourceforge.net/projects/lmod/files/Lmod-8.7.tar.bz2
        tar -xjf Lmod-8.7.tar.bz2
        cd Lmod-8.7 && ./configure && make install
        ''').strip()
        return userdata

    def _ec2_user_space_script(self, instance_id='', bscript='~/bootstrap.sh'):
        # Define script that will be installed by ec2-user

        # TODO: Replicate the configuration of the user space script

        # short_timezone = datetime.datetime.now().astimezone().tzinfo
        long_timezone = self.get_time_zone()
        return textwrap.dedent(f'''
        #! /bin/bash
        mkdir -p ~/.froster/config
        sleep 3 # give us some time to upload json to ~/.froster/config
        echo 'PS1="\\u@froster:\\w$ "' >> ~/.bashrc
        echo '#export EC2_INSTANCE_ID={instance_id}' >> ~/.bashrc
        echo '#export AWS_DEFAULT_REGION={self.cfg.aws_region}' >> ~/.bashrc
        echo '#export TZ={long_timezone}' >> ~/.bashrc
        echo '#alias singularity="apptainer"' >> ~/.bashrc
        cd /tmp
        curl https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh | bash
        froster config --monitor
        aws configure set aws_access_key_id {os.environ['AWS_ACCESS_KEY_ID']}
        aws configure set aws_secret_access_key {os.environ['AWS_SECRET_ACCESS_KEY']}
        aws configure set region {self.cfg.aws_region}
        aws configure --profile {self.cfg.aws_profile} set aws_access_key_id {os.environ['AWS_ACCESS_KEY_ID']}
        aws configure --profile {self.cfg.aws_profile} set aws_secret_access_key {os.environ['AWS_SECRET_ACCESS_KEY']}
        aws configure --profile {self.cfg.aws_profile} set region {self.cfg.aws_region}
        python3 -m pip install boto3
        sed -i 's/aws_access_key_id [^ ]*/aws_access_key_id /' {bscript}
        sed -i 's/aws_secret_access_key [^ ]*/aws_secret_access_key /' {bscript}
        curl -s https://raw.githubusercontent.com/apptainer/apptainer/main/tools/install-unprivileged.sh | bash -s - ~/.local
        curl -OkL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
        bash Miniconda3-latest-Linux-x86_64.sh -b
        ~/miniconda3/bin/conda init bash
        source ~/.bashrc
        conda activate
        echo '#! /bin/bash' > ~/.local/bin/get-public-ip
        echo 'ETOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")' >> ~/.local/bin/get-public-ip
        cp -f ~/.local/bin/get-public-ip ~/.local/bin/get-local-ip
        echo 'curl -sH "X-aws-ec2-metadata-token: $ETOKEN" http://169.254.169.254/latest/meta-data/public-ipv4' >> ~/.local/bin/get-public-ip
        echo 'curl -sH "X-aws-ec2-metadata-token: $ETOKEN" http://169.254.169.254/latest/meta-data/local-ipv4' >> ~/.local/bin/get-local-ip
        chmod +x ~/.local/bin/get-public-ip
        chmod +x ~/.local/bin/get-local-ip
        ~/miniconda3/bin/conda install -y jupyterlab
        ~/miniconda3/bin/conda install -y -c r r-irkernel r # R kernel and R for Jupyter
        conda run bash -c "~/miniconda3/bin/jupyter-lab --ip=$(get-local-ip) --no-browser --autoreload --notebook-dir=~ > ~/.jupyter.log 2>&1" &
        sleep 60
        sed "s/$(get-local-ip)/$(get-public-ip)/g" ~/.jupyter.log > ~/.jupyter-public.log
        echo 'test -d /usr/local/lmod/lmod/init && source /usr/local/lmod/lmod/init/bash' >> ~/.bashrc
        echo "" >> ~/.bash_profile
        echo 'echo "Access JupyterLab:"' >> ~/.bash_profile
        url=$(tail -n 7 ~/.jupyter-public.log | grep $(get-public-ip) |  tr -d ' ')
        echo "echo \\" $url\\"" >> ~/.bash_profile
        echo 'echo "type \\"conda deactivate\\" to leave current conda environment"' >> ~/.bash_profile
        ''').strip()

    def _ec2_create_instance(self, required_space, iamprofile=None):
        # to avoid egress we are creating an EC2 instance
        # with ephemeral (local) disk for a temporary restore
        #
        # i3en.24xlarge, 96 vcpu, 60TiB for $10.85
        # i3en.12xlarge, 48 vcpu, 30TiB for $5.42
        # i3en.6xlarge, 24 vcpu, 15TiB for $2.71
        # i3en.3xlarge, 12 vcpu, 7.5Tib for $1.36
        # i3en.xlarge, 4 vcpu, 2.5Tib for $0.45
        # i3en.large, 2 vcpu, 1.25Tib for $0.22
        # c5ad.large, 2 vcpu, 75GB, for $0.09

        instance_types = {'i3en.24xlarge': 60000,
                          'i3en.12xlarge': 30000,
                          'i3en.6xlarge': 15000,
                          'i3en.3xlarge': 7500,
                          'i3en.xlarge': 2500,
                          'i3en.large': 1250,
                          'c5ad.large': 75,
                          't3a.micro': 5,
                          }

        ec2_resource = self.session.resource('ec2')

        if required_space > 1:
            required_space = required_space + 5  # avoid low disk space in micro instances
        chosen_instance_type = None
        for itype, space in instance_types.items():
            if space > 1.5 * required_space:
                chosen_instance_type = itype

        if self.args.instancetype:
            chosen_instance_type = self.args.instancetype
        print('Chosen Instance:', chosen_instance_type)

        if not chosen_instance_type:
            print("No suitable instance type found for the given disk space requirement.")
            return False

        # Create a new EC2 key pair
        key_dir = self.cfg.shared_dir if self.cfg.is_shared else self.cfg.config_dir
        key_path = os.path.join(key_dir, f'{self.cfg.ssh_key_name}.pem')
        if not os.path.exists(key_path):
            try:
                self.ec2_client.describe_key_pairs(
                    KeyNames=[self.cfg.ssh_key_name])
                # If the key pair exists, delete it
                self.ec2_client.delete_key_pair(KeyName=self.cfg.ssh_key_name)
            except self.ec2_client.exceptions.ClientError:
                # Key pair doesn't exist in AWS, no need to delete
                pass
            key_pair = ec2_resource.create_key_pair(
                KeyName=self.cfg.ssh_key_name)
            with open(key_path, 'w') as key_file:
                key_file.write(key_pair.key_material)
            os.chmod(key_path, 0o640)  # Set file permission to 600

        mykey_path = os.path.join(
            self.cfg.shared_dir, f'{self.cfg.ssh_key_name}-{self.cfg.whoami}.pem')
        if not os.path.exists(mykey_path):
            shutil.copyfile(key_path, mykey_path)
            os.chmod(mykey_path, 0o600)  # Set file permission to 600

        imageid = self._ec2_get_latest_amazon_linux2_ami()
        print(f'Using Image ID: {imageid}')

        # print(f'*** userdata-script:\n{self._ec2_user_data_script()}')

        iam_instance_profile = {}
        if iamprofile:
            iam_instance_profile = {
                'Name': iamprofile  # Use the instance profile name
            }
        print(f'IAM Instance profile: {iamprofile}.')

        # iam_instance_profile = {}

        try:
            # Create EC2 instance
            instance = ec2_resource.create_instances(
                ImageId=imageid,
                MinCount=1,
                MaxCount=1,
                InstanceType=chosen_instance_type,
                KeyName=self.cfg.ssh_key_name,
                UserData=self._ec2_cloud_init_script(),
                IamInstanceProfile=iam_instance_profile,
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [{'Key': 'Name', 'Value': 'FrosterSelfDestruct'}]
                    }
                ]
            )[0]
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                print(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
            sys.exit(1)
        except Exception as e:
            print('Other Error: {e}')
            sys.exit(1)

        # Use a waiter to ensure the instance is running before trying to access its properties
        instance_id = instance.id

        # tag the instance for cost explorer
        tag = {
            'Key': 'INSTANCE_ID',
            'Value': instance_id
        }
        try:
            ec2_resource.create_tags(Resources=[instance_id], Tags=[tag])
        except Exception as e:
            printdbg('Error creating Tags: {e}')

        print(f'Launching instance {instance_id} ... please wait ...')

        max_wait_time = 300  # seconds
        delay_time = 10  # check every 10 seconds, adjust as needed
        max_attempts = max_wait_time // delay_time

        waiter = self.ec2_client.get_waiter('instance_running')
        progress = self._create_progress_bar(max_attempts)

        for attempt in range(max_attempts):
            try:
                waiter.wait(InstanceIds=[instance_id], WaiterConfig={
                            'Delay': delay_time, 'MaxAttempts': 1})
                progress(attempt)
                break
            except botocore.exceptions.WaiterError:
                progress(attempt)
                continue
        print('')
        instance.reload()

        grpid = self._ec2_create_and_attach_security_group(
            instance_id)
        if grpid:
            print(f'Security Group "{grpid}" attached.')
        else:
            print('No Security Group ID created.')
        instance.wait_until_running()
        print(f'Instance IP: {instance.public_ip_address}')

        # Save the last instance IP address
        self.cfg.set_ec2_last_instance(instance.public_ip_address)

        return instance_id, instance.public_ip_address

    def ec2_terminate_instance(self, ip):
        # terminate instance
        # with ephemeral (local) disk for a temporary restore

        # ips = self.ec2_list_ips(self, 'Name', 'FrosterSelfDestruct')
        # Use describe_instances with a filter for the public IP address to find the instance ID
        filters = [{
            'Name': 'network-interface.addresses.association.public-ip',
            'Values': [ip]
        }]

        if not ip.startswith('i-'):  # this an ip and not an instance ID
            try:
                response = self.ec2_client.describe_instances(Filters=filters)
            except botocore.exceptions.ClientError as e:
                print(f'Error: {e}')
                return False
            # Check if any instances match the criteria
            instances = [instance for reservation in response['Reservations']
                         for instance in reservation['Instances']]
            if not instances:
                print(f"No EC2 instance found with public IP: {ip}")
                return
            # Extract instance ID from the instance
            instance_id = instances[0]['InstanceId']
        else:
            instance_id = ip
        # Terminate the instance
        self.ec2_client.terminate_instances(InstanceIds=[instance_id])

        print(f"EC2 Instance {instance_id} ({ip}) is being terminated !")

    def ec2_list_instances(self, tag_name, tag_value):
        """
        List all IP addresses of running EC2 instances with a specific tag name and value.
        :param tag_name: The name of the tag
        :param tag_value: The value of the tag
        :return: List of IP addresses
        """

        # Define the filter
        filters = [
            {
                'Name': 'tag:' + tag_name,
                'Values': [tag_value]
            },
            {
                'Name': 'instance-state-name',
                'Values': ['running']
            }
        ]

        # Make the describe instances call
        try:
            response = self.ec2_client.describe_instances(Filters=filters)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
            return []
        # An error occurred (AuthFailure) when calling the DescribeInstances operation: AWS was not able to validate the provided access credentials
        ilist = []
        # Extract IP addresses
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                row = [instance['PublicIpAddress'],
                       instance['InstanceId'],
                       instance['InstanceType']]
                ilist.append(row)
        return ilist

    def _ssh_get_key_path(self):
        key_path = os.path.join(self.cfg.shared_dir,
                                f'{self.cfg.ssh_key_name}.pem')
        mykey_path = os.path.join(
            self.cfg.shared_dir, f'{self.cfg.ssh_key_name}-{self.cfg.whoami}.pem')
        if not os.path.exists(key_path):
            print(
                f'{key_path} does not exist. Please create it by launching "froster restore --aws"')
            sys.exit
        if not os.path.exists(mykey_path):
            shutil.copyfile(key_path, mykey_path)
            os.chmod(mykey_path, 0o600)  # Set file permission to 600
        return mykey_path

    def ssh_execute(self, user, host, command=None):
        """Execute an SSH command on the remote server."""
        SSH_OPTIONS = "-o StrictHostKeyChecking=no"
        key_path = self._ssh_get_key_path()
        cmd = f"ssh {SSH_OPTIONS} -i '{key_path}' {user}@{host}"
        if command:
            cmd += f" '{command}'"
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True)
                return result
            except Exception:
                print(f'Error executing "{cmd}."')
        else:
            subprocess.run(cmd, shell=True, capture_output=False, text=True)
        printdbg(f'ssh command line: {cmd}')
        return None

    def ssh_upload(self, user, host, local_path, remote_path, is_string=False):
        """Upload a file to the remote server using SCP."""
        SSH_OPTIONS = "-o StrictHostKeyChecking=no"
        key_path = self._ssh_get_key_path()
        if is_string:
            # the local_path is actually a string that needs to go into temp file
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
                temp.write(local_path)
                local_path = temp.name
        cmd = f"scp {SSH_OPTIONS} -i '{key_path}' {local_path} {user}@{host}:{remote_path}"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True)
            if is_string:
                os.remove(local_path)
            return result
        except Exception:
            print(f'Error executing "{cmd}."')
        return None

    def ssh_download(self, user, host, remote_path, local_path):
        """Upload a file to the remote server using SCP."""
        SSH_OPTIONS = "-o StrictHostKeyChecking=no"
        key_path = self._ssh_get_key_path()
        cmd = f"scp {SSH_OPTIONS} -i '{key_path}' {user}@{host}:{remote_path} {local_path}"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True)
            return result
        except Exception:
            print(f'Error executing "{cmd}."')
        return None

    def send_email_ses(self, sender, to, subject, body):
        '''Using AWS ses service to send emails'''

        # Check if required parameters are provided
        if not sender:
            raise ValueError('Sender email address is required.')
        if not to:
            raise ValueError('Recipient email address is required.')
        if not subject:
            raise ValueError('Email subject is required.')
        if not body:
            raise ValueError('Email body is required.')

        ses_verify_requests_sent = self.cfg.ses_verify_requests_sent

        verified_email_addr = []
        try:
            response = self.ses_client.list_verified_email_addresses()
            verified_email_addr = response.get('VerifiedEmailAddresses', [])
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print(f'Other Error: {e}')

        checks = [sender, to]
        checks = list(set(checks))  # remove duplicates
        email_list = []

        try:
            for check in checks:
                if check not in verified_email_addr and check not in ses_verify_requests_sent:
                    response = self.ses_client.verify_email_identity(
                        EmailAddress=check)
                    email_list.append(check)
                    print(
                        f'{check} was used for the first time, verification email sent.')
                    print(
                        'Please have {check} check inbox and confirm email from AWS.\n')

        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print(f'Other Error: {e}')

        self.cfg.ses_verify_requests_sent(email_list)

        try:
            response = self.ses_client.send_email(
                Source=sender,
                Destination={
                    'ToAddresses': [to]
                },
                Message={
                    'Subject': {
                        'Data': subject
                    },
                    'Body': {
                        'Text': {
                            'Data': body
                        }
                    }
                }
            )
            print(f'Sent email "{subject}" to {to}!')
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'MessageRejected':
                print(f'Message was rejected, Error: {e}')
            elif error_code == 'AccessDenied':
                printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
                if not self.args.debug:
                    print(
                        ' Cannot use SES email features to send you status messages: AccessDenied')
            else:
                print(f'Client Error: {e}')
            return False
        except Exception as e:
            print(f'Other Error: {e}')
            return False
        return True

        # The below AIM policy is needed if you do not want to confirm
        # each and every email you want to send to.

        # iam = boto3.client('iam')
        # policy_document = {
        #     "Version": "2012-10-17",
        #     "Statement": [
        #         {
        #             "Effect": "Allow",
        #             "Action": [
        #                 "ses:SendEmail",
        #                 "ses:SendRawEmail"
        #             ],
        #             "Resource": "*"
        #         }
        #     ]
        # }

        # policy_name = 'SES_SendEmail_Policy'

        # policy_arn = self._ec2_create_or_get_iam_policy(
        #     policy_name, policy_document, profile)

        # username = 'your_iam_username'  # Change this to the username you wish to attach the policy to

        # response = iam.attach_user_policy(
        #     UserName=username,
        #     PolicyArn=policy_arn
        # )

        # print(f"Policy {policy_arn} attached to user {username}")

    def send_ec2_costs(self, instance_id):
        pass

    def _ec2_create_iam_costexplorer_ses(self, instance_id):

        # Define the policy
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "ses:SendEmail",
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "ce:*",              # Permissions for Cost Explorer
                        "ce:GetCostAndUsage",  # all
                        "ec2:Describe*",     # Basic EC2 read permissions
                    ],
                    "Resource": "*"
                }
            ]
        }

        # Step 1: Create the policy in IAM
        policy_name = "CostExplorerSESPolicy"

        policy_arn = self._ec2_create_or_get_iam_policy(
            policy_name, policy_document)

        # Step 2: Retrieve the IAM instance profile attached to the EC2 instance
        response = self.ec2_client.describe_instances(
            InstanceIds=[instance_id])
        instance_data = response['Reservations'][0]['Instances'][0]
        if 'IamInstanceProfile' not in instance_data:
            print(
                f"No IAM Instance Profile attached to the instance: {instance_id}")
            return False

        instance_profile_arn = response['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']

        # Extract the instance profile name from its ARN
        instance_profile_name = instance_profile_arn.split('/')[-1]

        # Step 3: Fetch the role name from the instance profile
        response = self.iam_client.get_instance_profile(
            InstanceProfileName=instance_profile_name)
        role_name = response['InstanceProfile']['Roles'][0]['RoleName']

        # Step 4: Attach the desired policy to the role
        try:
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            print(f"Policy {policy_arn} attached to role {role_name}")
        except self.iam_client.exceptions.NoSuchEntityException:
            print(f"Role {role_name} does not exist!")
        except self.iam_client.exceptions.InvalidInputException as e:
            print(f"Invalid input: {e}")
        except Exception as e:
            print(f"Other Error: {e}")

    def _ec2_create_iam_self_destruct_role(self):

        # Step 1: Create IAM policy
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "ec2:TerminateInstances",
                    "Resource": "*",
                    "Condition": {
                        "StringEquals": {
                            "ec2:ResourceTag/Name": "FrosterSelfDestruct"
                        }
                    }
                }
            ]
        }
        policy_name = 'SelfDestructPolicy'

        policy_arn = self._ec2_create_or_get_iam_policy(
            policy_name, policy_document)

        # Step 2: Create an IAM role and attach the policy
        trust_relationship = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        role_name = 'SelfDestructRole'
        try:
            self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_relationship),
                Description='Allows EC2 instances to call AWS services on your behalf.'
            )
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            print('IAM SelfDestructRole already exists.')

        self.iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn=policy_arn
        )

        return True

    def _get_ec2_metadata(self, metadata_entry):

        # request 'local-hostname', 'public-hostname', 'local-ipv4', 'public-ipv4'

        # Define the base URL for the EC2 metadata service
        base_url = "http://169.254.169.254/latest/meta-data/"

        # Request a token with a TTL of 60 seconds
        token_url = "http://169.254.169.254/latest/api/token"
        token_headers = {"X-aws-ec2-metadata-token-ttl-seconds": "60"}
        try:
            token_response = requests.put(
                token_url, headers=token_headers, timeout=2)
        except Exception as e:
            print(f'Other Error: {e}')
            return ""
        token = token_response.text

        # Use the token to retrieve the specified metadata entry
        headers = {"X-aws-ec2-metadata-token": token}
        try:
            response = requests.get(
                base_url + metadata_entry, headers=headers, timeout=2)
        except Exception as e:
            print(f'Other Error: {e}')
            return ""

        if response.status_code != 200:
            print(
                f"Error: Failed to retrieve metadata for entry: {metadata_entry}. HTTP Status Code: {response.status_code}")
            return ""

        return response.text

    # TODO: OHSU-97: Implement cost monitoring and email sending
    def monitor_ec2(self):

        # TODO: function pendint to review
        print(f'TODO: function {inspect.stack()[0][3]} pending to review')
        exit(1)

        # if system is idle self-destroy

        instance_id = self._get_ec2_metadata('instance-id')
        public_ip = self._get_ec2_metadata('public-ipv4')
        instance_type = self._get_ec2_metadata('instance-type')
        ami_id = self._get_ec2_metadata('ami-id')
        reservation_id = self._get_ec2_metadata('reservation-id')

        nowstr = datetime.datetime.now().strftime('%H:%M:%S')
        print(
            f'froster-monitor ({nowstr}): {public_ip} ({instance_id}, {instance_type}, {ami_id}, {reservation_id}) ... ')

        if self._monitor_is_idle():
            # This machine was idle for a long time, destroy it
            print(
                f'froster-monitor ({nowstr}): Destroying current idling machine {public_ip} ({instance_id}) ...')
            if public_ip:
                body_text = "Instance was detected as idle and terminated"
                self.send_email_ses(self.cfg.email, self.cfg.email,
                                    f'Terminating idle instance {public_ip} ({instance_id})', body_text)
                self.ec2_terminate_instance(public_ip)
                return
            else:
                print('Could not retrieve metadata (IP)')
                return

        current_time = datetime.datetime.now().time()
        start_time = datetime.datetime.strptime("23:00:00", "%H:%M:%S").time()
        end_time = datetime.datetime.strptime("23:59:59", "%H:%M:%S").time()
        if start_time >= current_time or current_time > end_time:
            # only run cost emails once a day
            return

        monthly_cost, monthly_unit, daily_costs_by_instance, user_monthly_cost, user_monthly_unit, \
            user_daily_cost, user_daily_unit, user_name = self._monitor_get_ec2_costs()

        body = []
        body.append(
            f"{monthly_cost:.2f} {monthly_unit} total account cost for the current month.")
        body.append(
            f"{user_monthly_cost:.2f} {user_monthly_unit} cost of user {user_name} for the current month.")
        body.append(
            f"{user_daily_cost:.2f} {user_daily_unit} cost of user {user_name} in the last 24 hours.")
        body.append("Cost for each EC2 instance type in the last 24 hours:")
        for instance_t, (cost, unit) in daily_costs_by_instance.items():
            if instance_t != 'NoInstanceType':
                body.append(f"  {instance_t:12}: ${cost:.2f} {unit}")
        body_text = "\n".join(body)
        self.send_email_ses(self.cfg.email, self.cfg.email,
                            f'Froster AWS cost report ({instance_id})', body_text)

    def _monitor_users_logged_in(self):
        """Check if any users are logged in."""
        try:
            output = subprocess.check_output(
                ['who']).decode('utf-8', errors='ignore')
            if output:
                print('froster-monitor: Not idle, logged in:', output)
                return True  # Users are logged in
            return False
        except Exception as e:
            print(f'Other Error: {e}')
            return True

    def _monitor_is_idle(self, interval=60, min_idle_cnt=72):

        # each run checks idle time for 60 seconds (interval)
        # if the system has been idle for 72 consecutive runs
        # the fucntion will return idle state after 3 days
        # if the cron job is running hourly

        # Constants
        CPU_THRESHOLD = 20  # percent
        NET_READ_THRESHOLD = 1000  # bytes per second
        NET_WRITE_THRESHOLD = 1000  # bytes per second
        DISK_WRITE_THRESHOLD = 100000  # bytes per second
        PROCESS_CPU_THRESHOLD = 10  # percent (for individual processes)
        PROCESS_MEM_THRESHOLD = 10  # percent (for individual processes)
        DISK_WRITE_EXCLUSIONS = ["systemd", "systemd-journald",
                                 "chronyd", "sshd", "auditd", "agetty"]

        # Not idle if any users are logged in
        if self._monitor_users_logged_in():
            print(f'froster-monitor: Not idle: user(s) logged in')
            # return self._monitor_save_idle_state(False, min_idle_cnt)

        # CPU, Time I/O and Network Activity
        io_start = psutil.disk_io_counters()
        net_start = psutil.net_io_counters()
        cpu_percent = psutil.cpu_percent(interval=interval)
        io_end = psutil.disk_io_counters()
        net_end = psutil.net_io_counters()

        print(f'froster-monitor: Current CPU% {cpu_percent}')

        # Check CPU Utilization
        if cpu_percent > CPU_THRESHOLD:
            print(f'froster-monitor: Not idle: CPU% {cpu_percent}')
            # return self._monitor_save_idle_state(False, min_idle_cnt)

        # Check I/O Activity
        write_diff = io_end.write_bytes - io_start.write_bytes
        write_per_second = write_diff / interval

        if write_per_second > DISK_WRITE_THRESHOLD:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] in DISK_WRITE_EXCLUSIONS:
                    continue
                try:
                    if proc.io_counters().write_bytes > 0:
                        print(
                            f'froster-monitor:io bytes written: {proc.io_counters().write_bytes}')
                        return self._monitor_save_idle_state(False, min_idle_cnt)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # Check Network Activity
        bytes_sent_diff = net_end.bytes_sent - net_start.bytes_sent
        bytes_recv_diff = net_end.bytes_recv - net_start.bytes_recv

        bytes_sent_per_second = bytes_sent_diff / interval
        bytes_recv_per_second = bytes_recv_diff / interval

        if bytes_sent_per_second > NET_WRITE_THRESHOLD or \
                bytes_recv_per_second > NET_READ_THRESHOLD:
            print(f'froster-monitor:net bytes recv: {bytes_recv_per_second}')
            return self._monitor_save_idle_state(False, min_idle_cnt)

        # Examine Running Processes for CPU and Memory Usage
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            if proc.info['name'] not in DISK_WRITE_EXCLUSIONS:
                if proc.info['cpu_percent'] > PROCESS_CPU_THRESHOLD:
                    print(
                        f'froster-monitor: Not idle: CPU% {proc.info["cpu_percent"]}')
                    # return False
                # disabled this idle checker
                # if proc.info['memory_percent'] > PROCESS_MEM_THRESHOLD:
                #    print(f'froster-monitor: Not idle: MEM% {proc.info["memory_percent"]}')
                #    return False

        # Write idle state and read consecutive idle hours
        print(f'froster-monitor: Idle state detected')
        return self._monitor_save_idle_state(True, min_idle_cnt)

    def _monitor_save_idle_state(self, is_system_idle, min_idle_cnt):
        IDLE_STATE_FILE = os.path.join(os.getenv('TMPDIR', '/tmp'),
                                       'froster_idle_state.txt')
        with open(IDLE_STATE_FILE, 'a') as file:
            file.write('1\n' if is_system_idle else '0\n')
        with open(IDLE_STATE_FILE, 'r') as file:
            states = file.readlines()
        count = 0
        for state in reversed(states):
            if state.strip() == '1':
                count += 1
            else:
                break
        return count >= min_idle_cnt

    def _monitor_get_ec2_costs(self):

        # Identify current user/account
        identity = self.sts_client.get_caller_identity()
        user_arn = identity['Arn']

        # Check if it's the root user
        is_root = ":root" in user_arn

        # Dates for the current month and the last 24 hours
        today = datetime.datetime.today()
        first_day_of_month = datetime.datetime(
            today.year, today.month, 1).date()
        yesterday = (today - datetime.timedelta(days=1)).date()

        # Fetch EC2 cost of the current month
        monthly_response = self.ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': str(first_day_of_month),
                'End': str(today.date())
            },
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': ['Amazon Elastic Compute Cloud - Compute']
                }
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
        )
        monthly_cost = float(
            monthly_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
        monthly_unit = monthly_response['ResultsByTime'][0]['Total']['UnblendedCost']['Unit']

        # If it's the root user, the whole account's costs are assumed to be caused by root.
        if is_root:
            user_name = 'root'
            user_monthly_cost = monthly_cost
            user_monthly_unit = monthly_unit
        else:
            # Assuming a tag `CreatedBy` (change as per your tagging system)
            user_name = user_arn.split('/')[-1]
            user_monthly_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': str(first_day_of_month),
                    'End': str(today.date())
                },
                Filter={
                    "And": [
                        {
                            'Dimensions': {
                                'Key': 'SERVICE',
                                'Values': ['Amazon Elastic Compute Cloud - Compute']
                            }
                        },
                        {
                            'Tags': {
                                'Key': 'CreatedBy',
                                'Values': [user_name]
                            }
                        }
                    ]
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
            )
            user_monthly_cost = float(
                user_monthly_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            user_monthly_unit = user_monthly_response['ResultsByTime'][0]['Total']['UnblendedCost']['Unit']

        # Fetch cost of each EC2 instance type in the last 24 hours
        daily_response = self.ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': str(yesterday),
                'End': str(today.date())
            },
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': ['Amazon Elastic Compute Cloud - Compute']
                }
            },
            Granularity='DAILY',
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'INSTANCE_TYPE'}],
            Metrics=['UnblendedCost'],
        )
        daily_costs_by_instance = {group['Keys'][0]: (float(group['Metrics']['UnblendedCost']['Amount']),
                                                      group['Metrics']['UnblendedCost']['Unit']) for group in daily_response['ResultsByTime'][0]['Groups']}

        # Fetch cost caused by the current user in the last 24 hours
        if is_root:
            user_daily_cost = sum([cost[0]
                                  for cost in daily_costs_by_instance.values()])
            # Using monthly unit since it should be the same for daily
            user_daily_unit = monthly_unit
        else:
            user_daily_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': str(yesterday),
                    'End': str(today.date())
                },
                Filter={
                    "And": [
                        {
                            'Dimensions': {
                                'Key': 'SERVICE',
                                'Values': ['Amazon Elastic Compute Cloud - Compute']
                            }
                        },
                        {
                            'Tags': {
                                'Key': 'CreatedBy',
                                'Values': [user_name]
                            }
                        }
                    ]
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
            )
            user_daily_cost = float(
                user_daily_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            user_daily_unit = user_daily_response['ResultsByTime'][0]['Total']['UnblendedCost']['Unit']

        return monthly_cost, monthly_unit, daily_costs_by_instance, user_monthly_cost, \
            user_monthly_unit, user_daily_cost, user_daily_unit, user_name


class Archiver:

    def __init__(self, args: argparse.Namespace, cfg: ConfigManager):
        self.args = args

        self.cfg = cfg

        self.archive_json = cfg.archive_json

        x = cfg.max_small_file_size_kib
        self.thresholdKB = int(x) if x else 1024

        x = cfg.min_index_folder_size_gib
        self.thresholdGB = int(x) if x else 10

        x = cfg.min_index_folder_size_avg_mib
        self.thresholdMB = int(x) if x else 10

        x = cfg.max_hotspots_display_entries
        global MAXHOTSPOTS
        MAXHOTSPOTS = int(x) if x else 5000

        self.smallfiles_tar_filename = 'Froster.smallfiles.tar'
        self.allfiles_csv_filename = 'Froster.allfiles.csv'
        self.md5sum_filename = '.froster.md5sum'
        self.md5sum_restored_filename = '.froster-restored.md5sum'
        self.where_did_the_files_go_filename = 'Where-did-the-files-go.txt'

        self.dirmetafiles = [self.allfiles_csv_filename,
                             self.md5sum_filename,
                             self.md5sum_restored_filename,
                             self.where_did_the_files_go_filename]

        self.grants = []

    def _index_locally(self, folder):
        '''Index the given folder for archiving'''
        try:
            # move down to class
            daysaged = [5475, 3650, 1825, 1095, 730, 365, 90, 30]
            TiB = 1099511627776
            # GiB=1073741824
            # MiB=1048576

            # If pwalkcopy location provided, run pwalk and copy the output to the specified location every time
            if self.args.pwalkcopy:
                print(
                    f'\nIndexing folder "{folder}" and copying output to {self.args.pwalkcopy}...', flush=True)
            else:
                print(f'\nIndexing folder "{folder}"...', flush=True)

                # Get the path to the hotspots CSV file
                folder_hotspot = self.get_hotspots_path(folder)

                # If the folder is already indexed don't run pwalk again
                if os.path.isfile(folder_hotspot):
                    if self.args.force:
                        # Ignore the existing file and re-index the folder
                        pass
                    else:
                        print(
                            f'    ...folder already indexed at {folder_hotspot}. Use "-f" or "--force" flag to force indexing.\n')
                        return

            # Run pwalk on given folder
            with tempfile.NamedTemporaryFile() as pwalk_output:
                with tempfile.NamedTemporaryFile() as pwalk_output_folders:
                    with tempfile.NamedTemporaryFile() as pwalk_output_folders_converted:

                        # Build the pwalk command
                        pwalk_bin = os.path.join(sys.prefix, 'bin', 'pwalk')
                        pwalkcmd = f'{pwalk_bin} --NoSnap --one-file-system --header'
                        mycmd = f'{pwalkcmd} "{folder}" > {pwalk_output.name}'

                        # Run the pwalk command
                        ret = subprocess.run(mycmd, shell=True,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        # Check if the pwalk command was successful
                        if ret.returncode != 0:
                            print(
                                f"\nError: command {mycmd} failed with returncode {ret.returncode}\n", file=sys.stderr)
                            sys.exit(1)

                        # If pwalkcopy location provided, then copy the pwalk output file to the specified location
                        if self.args.pwalkcopy:

                            copy_filename = folder.replace('/', '+') + '.csv'
                            copy_file_path = os.path.join(
                                self.args.pwalkcopy, copy_filename)

                            # Build the copy command
                            mycmd = f'iconv -f ISO-8859-1 -t UTF-8 {pwalk_output.name} -o {copy_file_path}'

                            # Run the copy command
                            result = subprocess.run(mycmd, shell=True)

                            # Check if the copy command was successful
                            if result.returncode != 0:
                                print(
                                    f"\nError: command {mycmd} failed with returncode {result.returncode}\n", file=sys.stderr)
                                sys.exit(1)

                        # Build the files removing command
                        mycmd = f'grep -v ",-1,0$" "{pwalk_output.name}" > {pwalk_output_folders.name}'

                        # Run the files removing command
                        result = subprocess.run(mycmd, shell=True)

                        # Check if the files removing command was successful
                        if result.returncode != 0:
                            print(
                                f"\nError: command {mycmd} failed with returncode {result.returncode}\n", file=sys.stderr)
                            sys.exit(1)

                        # WORKAROUND: Converting file from ISO-8859-1 to utf-8 to avoid DuckDB import error
                        # pwalk does already output UTF-8, weird, probably duckdb error

                        # Build the file conversion command
                        mycmd = f'iconv -f ISO-8859-1 -t UTF-8 {pwalk_output_folders.name} -o {pwalk_output_folders_converted.name}'

                        # Run the file conversion command
                        result = subprocess.run(mycmd, shell=True)

                        # Check if the file conversion command was successful
                        if result.returncode != 0:
                            print(
                                f"\nError: command {mycmd} failed with returncode {result.returncode}\n", file=sys.stderr)
                            sys.exit(1)

                        # Build the SQL query on the CSV file
                        sql_query = f"""SELECT UID as User,
                                        st_atime as AccD, st_mtime as ModD,
                                        pw_dirsum/1073741824 as GiB,
                                        pw_dirsum/1048576/pw_fcount as MiBAvg,
                                        filename as Folder, GID as Group,
                                        pw_dirsum/1099511627776 as TiB,
                                        pw_fcount as FileCount, pw_dirsum as DirSize
                                    FROM read_csv_auto('{pwalk_output_folders_converted.name}',
                                            ignore_errors=1)
                                    WHERE pw_fcount > -1 AND pw_dirsum > 0
                                    ORDER BY pw_dirsum Desc
                                """  # pw_dirsum > 1073741824

                        # Connect to an in-memory DuckDB instance
                        duckdb_connection = duckdb.connect(':memory:')

                        # Set the number of threads to use
                        duckdb_connection.execute(
                            f'PRAGMA threads={self.args.cores};')

                        # Execute the SQL query
                        rows = duckdb_connection.execute(sql_query).fetchall()

                        # Get the column names
                        header = duckdb_connection.execute(
                            sql_query).description

                        # Close the DuckDB connection
                        duckdb_connection.close()

            # Set up variables for the hotspots
            totalbytes = 0
            numhotspots = 0
            agedbytes = [0] * len(daysaged)

            # Get the path to the hotspots CSV file
            mycsv = self.get_hotspots_path(folder)

            # Write the hotspots to the CSV file
            with open(mycsv, 'w') as f:
                writer = csv.writer(f, dialect='excel')
                writer.writerow([col[0] for col in header])
                # 0:Usr,1:AccD,2:ModD,3:GiB,4:MiBAvg,5:Folder,6:Grp,7:TiB,8:FileCount,9:DirSize
                for r in rows:
                    row = list(r)
                    if row[3] >= self.thresholdGB and row[4] >= self.thresholdMB:
                        atime = self._get_newest_file_atime(row[5], row[1])
                        mtime = self._get_newest_file_mtime(row[5], row[2])
                        row[0] = self.uid2user(row[0])
                        row[1] = self.daysago(atime)
                        row[2] = self.daysago(mtime)
                        row[3] = int(row[3])
                        row[4] = int(row[4])
                        row[6] = self.gid2group(row[6])
                        row[7] = int(row[7])
                        writer.writerow(row)
                        numhotspots += 1
                        totalbytes += row[9]
                        for i in range(0, len(daysaged)):
                            if row[1] > daysaged[i]:
                                if i == 0:
                                    # Is this really 15 years ?
                                    printdbg(
                                        f'  {row[5]} has not been accessed for {row[1]} days. (atime = {atime})')
                                agedbytes[i] += row[9]

            print(f'    ...indexing done.')

            print(textwrap.dedent(f'''
                Hotspots file: {mycsv}
                    with {numhotspots} hotspots >= {self.thresholdGB} GiB
                    with a total disk use of {round(totalbytes/TiB,3)} TiB
                '''))

            print(f'Total folders processed: {len(rows)}')

            lastagedbytes = 0
            for i in range(0, len(daysaged)):
                if agedbytes[i] > 0 and agedbytes[i] != lastagedbytes:
                    # dedented multi-line removing \n
                    print(textwrap.dedent(f'''
                    {round(agedbytes[i]/TiB,3)} TiB have not been accessed
                    for {daysaged[i]} days (or {round(daysaged[i]/365,1)} years)
                    ''').replace('\n', ''))
                lastagedbytes = agedbytes[i]

            # Output decoration print
            print()

        except Exception:
            print_error()

    def _slurm_cmd(self, folders, cmd_type, scheduled):
        '''Execute the current command using SLURM'''

        try:
            # Create a SlurmEssentials object
            se = Slurm(self.args, self.cfg)

            # Get the label for the job
            label = self._get_hotspots_filename(
                folders[0]).replace('.csv', '').replace(' ', '_')

            # Get the shortlabel for the Slurm job
            shortlabel = os.path.basename(folders[0])

            # Add the original cmdline to the Slurm script
            cmd = " ".join(map(shlex.quote, sys.argv))

            # Submit the job
            se.submit_job(cmd=cmd,
                          cmd_type=cmd_type,
                          label=label,
                          shortlabel=shortlabel,
                          scheduled=scheduled)

        except Exception:
            print_error()

    def index(self, folders):
        '''Index the given folders for archiving'''
        try:
            # Clean the provided paths
            folders = clean_path_list(folders)

            if self._is_recursive_collision(folders):
                print(
                    f'\nError: You cannot index folders if there is a dependency between them. Specify only the parent folder.\n')
                sys.exit(1)

            # Check if we can read & write all files and folders
            if not self._is_correct_files_folders_permissions(folders, is_recursive=True):
                print(
                    '\nError: Cannot read or write to all files and folders.\n', file=sys.stderr)
                print(
                    f'You can check the permissions of the files and folders using the command:', file=sys.stderr)
                print(
                    f'    froster archive --permissions "/your/folder/to/archive"\n', file=sys.stderr)
                sys.exit(1)

            if use_slurm(self.args.noslurm):
                self._slurm_cmd(folders=folders, cmd_type='index')
            else:
                for folder in folders:
                    self._index_locally(folder)
        except Exception:
            print_error()

    def archive_select_hotspots(self):

        # Get the hotspots directory
        hotspots_dir = self.cfg.shared_hotspots_dir if self.cfg.is_shared else self.cfg.hotspots_dir

        # Check if the Hotspots directory exists
        if not hotspots_dir or not os.path.exists(hotspots_dir):
            print(
                '\nNo folders to archive in arguments and no Hotspots CSV files found.')

            print('\nFor archive a specific folder run:')
            print('    froster archive "/your/folder/to/archive"')

            print('\n For index a folder a find hotspots run:')
            print('    froster index "/your/folder/to/index"\n')

            return

        # Get all the hotspot CSV files in the hotspots directory
        hotspots_files = [f for f in os.listdir(
            hotspots_dir) if fnmatch.fnmatch(f, '*.csv')]

        # Check if there are CSV files, if don't there are no folders to archive
        if not hotspots_files:
            print('\nNo hotposts found. \n')

            print(f'You can search for hotspot by indexing folders using command:')
            print('    froster index "/your/folder/to/index"\n')

            print('For archive a specific folder run:')
            print('    froster archive "/your/folder/to/archive"\n')

            return

        # Sort the CSV files by their modification time in descending order (newest first)
        hotspots_files.sort(key=lambda x: os.path.getmtime(
            os.path.join(hotspots_dir, x)), reverse=True)

        # Ask the user to select a Hotspot file
        ret = TextualStringListSelector(
            title="Select a Hotspot file", items=hotspots_files).run()

        # No file selected
        if not ret:
            return

        # Get the selected CSV file
        hotspot_selected = os.path.join(hotspots_dir, ret[0])

        # Get the folders to archive from the selected Hotspot file
        folders_to_archive = self.get_hotspot_folders(hotspot_selected)

        if not folders_to_archive:
            print(
                f'\nNo hotspots to archive found in {hotspot_selected}.')
            return

        # Archiving options
        archiving_options = ['Archive all hotspots',
                             'Archive one hotspot', 'Cancel']

        # Ask the user how to proceed with the archiving process
        archive_procedure = inquirer.list_input(
            message=f"How should we proceed with the archiving process?",
            choices=archiving_options,
            default='Cancel')

        if archive_procedure == 'Archive all hotspots':
            # Do nothing, we already have the folders list to archive
            pass

        elif archive_procedure == 'Archive one hotspot':
            ret = TextualStringListSelector(
                title="Select hotspot to archive ", items=folders_to_archive).run()
            if not ret:
                # No file selected
                return
            else:
                folders_to_archive = [ret[0]]

        elif archive_procedure == 'Cancel':
            return

        else:
            # We should never end up here
            raise ValueError("Invalid option selected.")

        # Archive the selected folders
        self.archive(folders_to_archive)

    def _is_recursive_collision(self, folders):
        '''Check if there is a collision between folders and recursive flag'''
        is_collision = False

        try:
            for i in range(len(folders)):
                for j in range(i + 1, len(folders)):
                    # Check if folders[j] is a subdirectory of folders[i]
                    if os.path.commonpath([folders[i], folders[j]]) == folders[i]:
                        is_collision = True
                        print(
                            f'Folder {folders[j]} is a subdirectory of folder {folders[i]}.\n', file=sys.stderr)

                    # Check if folders[i] is a subdirectory of folders[j]
                    elif os.path.commonpath([folders[i], folders[j]]) == folders[j]:
                        is_collision = True
                        print(
                            f'Folder {folders[i]} is a subdirectory of folder {folders[j]}.\n')
        except Exception as e:
            print_error()
            is_collision = True

        return is_collision

    def _archive_locally(self, folder_to_archive, is_recursive, is_subfolder, is_tar, is_force):
        '''Archive the given folder'''

        # Set workflow execution flags
        is_folder_tarred = False
        is_folder_archived = False
        is_froster_allfiles_generated = False
        is_checksum_generated = False
        is_checksum_correct = False

        try:
            s3_dest = os.path.join(
                f':s3:{self.cfg.bucket_name}',
                self.cfg.archive_dir,
                folder_to_archive.lstrip(os.path.sep))

            # TODO: vmachado: review this code
            froster_md5sum_exists = os.path.isfile(
                os.path.join(folder_to_archive, ".froster.md5sum"))

            if froster_md5sum_exists:
                if is_force:
                    self.reset_folder(folder_to_archive)
                else:
                    print(
                        f'\nThe hashfile ".froster.md5sum" already exists in {folder_to_archive} from a previous archiving process.')
                    print(
                        f'\nIf you want to force the archiving process again on this folder, please us the -f or --force flag\n')
                    sys.exit(1)

            # Check if the folder is empty
            with os.scandir(folder_to_archive) as entries:
                if not any(True for _ in entries):
                    print(
                        f'\nFolder {folder_to_archive} is empty, skipping.\n')
                    return

            print(f'\nARCHIVING {folder_to_archive}')

            if is_tar:
                print(f'\n    Generating Froster.allfiles.csv and tar small files...')
            else:
                print(f'\n    Generating Froster.allfiles.csv...')

            # Generate Froster.allfiles.csv and if is_tar tar small files
            if self._gen_allfiles_and_tar(folder_to_archive, self.thresholdKB, is_tar):
                is_froster_allfiles_generated = True
                print(f'        ...done')
            else:
                # Something failed, exit
                print(f'        ...FAILED\n')
                return

            # Generate md5 checksums for all files in the folder
            print(f'\n    Generating checksums...')
            if self._gen_md5sums(folder_to_archive, self.md5sum_filename):
                is_checksum_generated = True
                print('        ...done')
            else:
                return

            # Get the path to the hashfile
            hashfile = os.path.join(folder_to_archive, self.md5sum_filename)

            # Create an Rclone object
            rclone = Rclone(self.args, self.cfg)

            # Archive the folder to S3
            print(f'\n    Uploading files...')
            ret = rclone.copy(folder_to_archive, s3_dest, '--max-depth', '1', '--links',
                              '--exclude', self.md5sum_filename,
                              '--exclude', self.md5sum_restored_filename,
                              '--exclude', self.allfiles_csv_filename,
                              '--exclude', self.where_did_the_files_go_filename
                              )

            # Check if the folder was archived successfully
            if ret:
                print('        ...done')
                is_folder_archived = True
            else:
                print('        ...FAILED\n')
                return

            # Get the path to the allfiles CSV file
            allfiles_source = os.path.join(
                folder_to_archive, self.allfiles_csv_filename)

            print(f'\n    Uploading Froster.allfiles.csv file...')

            # Change the storage class to INTELLIGENT_TIERING
            rclone.envrn['RCLONE_S3_STORAGE_CLASS'] = 'INTELLIGENT_TIERING'

            # Archive the allfiles CSV file to S3 INTELLIGENT_TIERING
            ret = rclone.copy(allfiles_source, s3_dest, '--max-depth', '1', '--links',
                              '--exclude', self.md5sum_filename,
                              '--exclude', self.md5sum_restored_filename,
                              '--exclude', self.allfiles_csv_filename,
                              '--exclude', self.where_did_the_files_go_filename
                              )

            # Change the storage class back to the user preference
            rclone.envrn['RCLONE_S3_STORAGE_CLASS'] = self.cfg.storage_class

            if ret:
                print('        ...done')
                is_folder_archived = True
            else:
                print('        ...FAILED\n')
                return

            print(f'\n    Verifying checksums...')
            ret = rclone.checksum(hashfile, s3_dest, '--max-depth', '1')

            # Check if the checksums are correct
            if ret:
                print('        ...done')
                is_checksum_correct = True
            else:
                print('        ...FAILED\n')
                return

            # Add the metadata to the archive JSON file ONLY if this is not a subfolder
            if not is_subfolder:
                # Get current timestamp
                timestamp = datetime.datetime.now().isoformat()

                # Get the archive mode
                if is_recursive:
                    archive_mode = "Recursive"
                else:
                    archive_mode = "Single"

                # Generate the metadata dictionary
                new_entry = {'local_folder': folder_to_archive,
                             'archive_folder': s3_dest,
                             's3_storage_class': self.cfg.storage_class,
                             'profile': self.cfg.aws_profile,
                             'archive_mode': archive_mode,
                             'timestamp': timestamp,
                             'timestamp_archive': timestamp,
                             'user': getpass.getuser()
                             }

                # Add NIH information to the metadata dictionary
                if self.args.nihref:
                    new_entry['nih_project'] = self.args.nihref

                # Write the metadata to the archive JSON file
                self._archive_json_add_entry(key=folder_to_archive.rstrip(os.path.sep),
                                             value=new_entry)

            # Print the final message
            print(f'\nARCHIVING SUCCESSFULLY COMPLETED\n')
            print(f'    LOCAL SOURCE:       "{folder_to_archive}"')
            print(f'    AWS S3 DESTINATION: "{s3_dest}"\n')
            print(
                f'    All files were correctly uploaded to AWS S3 bucket and double-checked with md5sum checksum.\n')

        except Exception:
            print_error()

    def archive(self, folders):
        '''Archive the given folders'''
        try:
            # Clean the provided paths
            folders = clean_path_list(folders)

            # Set flags
            is_recursive = self.args.recursive

            # Check if NIH information is required by configuration, by command line argument or if there is a NIH reference
            is_nih = self.cfg.is_nih or self.args.nih and not self.args.nihref

            is_tar = not self.args.notar
            is_force = self.args.force

            # Check if there is a conflict between folders and recursive flag,
            # i.e. recursive flag is set and a folder is a subdirectory of another one
            if is_recursive:
                if self._is_recursive_collision(folders):
                    print(
                        f'\nError: You cannot archive folders recursively if there is a dependency between them.\n')
                    sys.exit(1)

            # Check if we can read & write all files and folders
            if not self._is_correct_files_folders_permissions(folders, is_recursive):
                print(
                    '\nError: Cannot read or write to all files and folders.\n', file=sys.stderr)
                print(
                    f'You can check the permissions of the files and folders using the command:', file=sys.stderr)
                print(
                    f'    froster archive --permissions "/your/folder/to/archive"\n', file=sys.stderr)
                sys.exit(1)

            nih = ''

            if is_nih:
                app = TableNIHGrants()
                nih = app.run()

                if nih:
                    # Add the nihref to arguments for slurm script execution
                    sys.argv.append('--nih-ref')
                    sys.argv.append(nih[0])
                    self.args.nihref = nih[0]

                else:
                    # Nothing selected. Exit
                    return

            if use_slurm(self.args.noslurm):

                if '--hotspots' in sys.argv:

                    # Remove the hotspots flag from the arguments as this will be a non-interactive slurm execution
                    sys.argv.remove('--hotspots')

                    # Append the selected folders to the arguments. Again: non-interactive slurm execution
                    for folder in folders:
                        sys.argv.append(folder)

                # Execute slurm command
                self._slurm_cmd(folders=folders, cmd_type='archive')

            else:
                for folder in folders:
                    if is_recursive:
                        for root, dirs, files in self._walker(folder):
                            if folder == root:
                                is_subfolder = False
                            else:
                                is_subfolder = True
                            self._archive_locally(
                                root, is_recursive, is_subfolder, is_tar, is_force)

                    else:
                        is_subfolder = False
                        self._archive_locally(
                            folder, is_recursive, is_subfolder, is_tar, is_force)
        except Exception:
            print_error()

    def get_mounts(self):
        try:
            rclone = Rclone(self.args, self.cfg)
            return rclone.get_mounts()
        except Exception:
            print_error()
            sys.exit(1)

    def _is_mounted(self, folder):
        '''Check if the given folder is already mounted'''

        mounts = self.get_mounts()

        if folder in mounts:
            return True
        else:
            return False

    def print_current_mounts(self):
        '''Print the current mounted folders'''

        mounts = self.get_mounts()

        if mounts:
            print('\nCURRENT MOUNTED FOLDERS:\n')
            for mount in mounts:
                print(f'    {mount}')

            # Decorator print
            print()
        else:
            print('\nNO FOLDERS MOUNTED\n')

    def _mount_locally(self, folders, mountpoint):

        for folder in folders:

            archive_folder_info = self.froster_archives_get_entry(folder)

            if archive_folder_info is None:
                print(f'\nWARNING: folder "{folder}" not in archive.\n')
                print(f'Nothing will be restored.\n')
                continue

            if not os.path.exists(folder) and not mountpoint:
                print(
                    f'\nWARNING: folder "{folder}" does not exist and no mountpoint provided.\n')
                print(f'Nothing will be restored.\n')
                continue

            s3_folder = archive_folder_info['archive_folder']
            local_folder = archive_folder_info['local_folder']

            if folder == local_folder:
                if mountpoint:
                    print(f'\nMOUNTING "{local_folder}" at "{mountpoint}"...')
                else:
                    print(f'\nMOUNTING "{local_folder}"...')
            else:
                if mountpoint:
                    print(
                        f'\nMOUNTING parent folder "{local_folder}" at "{mountpoint}"...')
                else:
                    print(f'\nMOUNTING parent folder "{local_folder}"...')

            if not mountpoint:
                mountpoint = local_folder

            # Check if the folder is already mounted
            if self._is_mounted(mountpoint):
                print(f'    ..."{mountpoint}" already mounted\n')
                sys.exit(1)

            # Mount the folder
            rclone = Rclone(self.args, self.cfg)
            ret = rclone.mount(s3_folder, mountpoint)

            # Check if the folder was mounted successfully
            if ret:
                print('    ...MOUNTED\n')
            else:
                print('    ...FAILED\n')
                return

    def mount(self, folders, mountpoint):
        '''Mount the given folder'''

        # Clean the provided paths
        folders = clean_path_list(folders)
        mountpoint = clean_path(mountpoint)

        self._mount_locally(folders, mountpoint)

    def _unmount_locally(self, folders):

        # rclone instance
        rclone = Rclone(self.args, self.cfg)

        for folder in folders:
            print(f'\nUNMOUNTING {folder}...')

            if self._is_mounted(folder):
                ret = rclone.unmount(folder)

                # Check if the folder was unmounted successfully
                if ret:
                    print('    ...UNMOUNTED SUCCESS\n')
                else:
                    print('    ...UNMOUNTING FAILED\n')
            else:
                print(f'    ...IS NOT MOUNTED\n')

    def unmount(self, folders):

        # Clean the provided paths
        folders = clean_path_list(folders)

        self._unmount_locally(folders)

    def get_hotspot_folders(self, hotspot_file):

        agefld = 'AccD'

        if self.args.agemtime:
            agefld = 'ModD'

        # Initialize a connection to an in-memory database
        duckdb_connection = duckdb.connect(
            database=':memory:', read_only=False)

        # Set the number of threads to use
        duckdb_connection.execute(f'PRAGMA threads={self.args.cores};')

        # Register CSV file as a virtual table
        duckdb_connection.execute(
            f"CREATE TABLE hs AS SELECT * FROM read_csv_auto('{hotspot_file}')")

        query = "SELECT COUNT(*) FROM hs"
        result = duckdb_connection.execute(query).fetchall()

        if result[0][0] == 0:
            return []

        # Run SQL queries on this virtual table
        # Filter by given age and size. The default value for all is 0
        if self.args.older > 0:
            rows = duckdb_connection.execute(
                f"SELECT * FROM hs WHERE {agefld} >= {self.args.older} and GiB >= {self.args.larger} ").fetchall()

        elif self.args.newer > 0:
            rows = duckdb_connection.execute(
                f"SELECT * FROM hs WHERE {agefld} <= {self.args.newer} and GiB >= {self.args.larger} ").fetchall()

        else:
            rows = duckdb_connection.execute(
                f"SELECT * FROM hs WHERE GiB >= {self.args.larger} ").fetchall()

        # Close the DuckDB connection
        duckdb_connection.close()

        folders_to_archive = [(item[5], item[3])
                              for item in rows]  # Include size in the tuple

        print(f'Hotspots file: {hotspot_file}')
        print(f'\nFolders to archive:\n')
        for folder, size in folders_to_archive:
            print(f'  {folder} - Size: {size} GiB')

        totalspace = sum(item[3] for item in rows)
        print(
            f'\nTotal space to archive: {format(round(totalspace, 3),",")} GiB\n')

        # Return only the folders
        return [folder for folder, size in folders_to_archive]

    def _check_path_permissions(self, path):
        '''Check if the user has read and write permissions to the given path'''

        # If path is empty, return True
        if not path:
            return True

        # Get path permissions
        can_read = os.access(path, os.R_OK)
        can_write = os.access(path, os.W_OK)

        # Print error messages if the user does not have read or write permissions
        if not can_read:
            print(f"Cannot read: {path}", file=sys.stderr)
        if not can_write:
            print(f"Cannot write: {path}", file=sys.stderr)

        # Return True if the user has read and write permissions, otherwise return False
        return can_read and can_write

    def _is_correct_files_folders_permissions(self, folders, is_recursive=False):
        '''Check if the user has read and write permissions to the given folders'''

        correct_permissions = True

        try:

            for folder in folders:

                if not os.path.isdir(folder):
                    print(f"Error: {folder} is not a directory.",
                          file=sys.stderr)
                    sys.exit(1)

                if is_recursive:

                    # Recursive flag set, using os.walk to get all files and folders

                    for root, dirs, files in os.walk(folder, topdown=True):

                        # Check if the user has read and write permissions to the root folder
                        if not self._check_path_permissions(root):
                            correct_permissions = False

                        # Check if the user has read and write permissions to all subfolders
                        for d in dirs:
                            d_path = os.path.join(root, d)
                            if not self._check_path_permissions(d_path):
                                correct_permissions = False

                        # Check if the user has read and write permissions to all files
                        for f in files:
                            f_path = os.path.join(root, f)
                            if not self._check_path_permissions(f_path):
                                correct_permissions = False
                else:

                    # Recursive flag not set, using os.listdir to get and check all files
                    for f in os.listdir(folder):
                        file_path = os.path.join(folder, f)
                        if os.path.isfile(file_path):
                            if not self._check_path_permissions(file_path):
                                correct_permissions = False

            return correct_permissions

        except Exception:
            return False

    def _create_progress_bar(self, max_value):
        '''Create a progress bar'''

        def show_progress_bar(iteration):
            percent = ("{0:.1f}").format(100 * (iteration / float(max_value)))
            length = 50  # adjust as needed for the bar length
            filled_length = int(length * iteration // max_value)
            bar = "█" * filled_length + '-' * (length - filled_length)
            if sys.stdin.isatty():
                print(f'\r|{bar}| {percent}%', end='\r')
            if iteration == max_value:
                print()

        return show_progress_bar

    def print_paths_rw_info(self, paths):

        if not paths:
            print('\nError: No file paths provided.\n', file=sys.stderr)
            return

        for path in paths:

            # Check if file exists
            if not os.path.exists(path):
                continue

            try:
                # Getting the status of the file
                file_stat = os.lstat(path)

                # Getting the current user and group IDs
                current_uid = os.getuid()
                current_gid = os.getgid()

                # Checking if the user is the owner
                is_owner = file_stat.st_uid == current_uid

                # Checking if the user is in the file's group
                is_group_member = file_stat.st_gid == current_gid or \
                    any(grp.getgrgid(g).gr_gid ==
                        file_stat.st_gid for g in os.getgroups())

            except Exception as e:
                print_error()
                return

            # Extracting permission bits
            permissions = file_stat.st_mode

            # Checking for owner read permission
            has_owner_read_permission = bool(permissions & stat.S_IRUSR)

            # Checking for group read permission
            has_group_read_permission = bool(permissions & stat.S_IRGRP)

            # Checking for '444' (read permission for everyone)
            is_444 = permissions & 0o444 == 0o444

            # Determining if the user can read the file
            can_read = (is_owner and has_owner_read_permission) or \
                (is_group_member and has_group_read_permission) or \
                is_444

            # Checking for owner write permission
            has_owner_write_permission = bool(permissions & stat.S_IWUSR)

            # Checking for group write permission
            has_group_write_permission = bool(permissions & stat.S_IWGRP)

            # Checking for '666' or '777' permissions
            is_666_or_777 = permissions & 0o666 == 0o666 or permissions & 0o777 == 0o777

            # Determining if the user can delete the file
            can_write = (is_owner and has_owner_write_permission) or \
                        (is_group_member and has_group_write_permission) or \
                is_666_or_777

            # Printing the file's permissions
            print(f'\nFile: {path}')
            print(f'\nis_owner: {is_owner}')
            print(f'has_owner_read_permission: {has_owner_read_permission}')
            print(f'has_owner_write_permission: {has_owner_write_permission}')
            print(f'\nis_group_member: {is_group_member}')
            print(f'has_group_read_permission: {has_group_read_permission}')
            print(f'has_group_write_permission: {has_group_write_permission}')
            print(f'\nis_444: {is_444}')
            print(f'is_666_or_777: {is_666_or_777}')
            print(f'\ncan_read: {can_read}')
            print(f'can_write: {can_write}\n')

    def _gen_md5sums(self, directory, hash_file):
        '''Generate md5sums for all files in the directory and write them to a hash file'''

        try:
            for root, dirs, files in self._walker(directory):

                # We only want to generate the hash file in the root directory. Avoid recursion
                if root != directory:
                    break

                # Build the path to the hash file
                hashpath = os.path.join(root, hash_file)

                # Set the number of workers
                max_workers = max(4, int(self.args.cores))

                with open(hashpath, "w") as out_f:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:

                        tasks = {}

                        for file in files:

                            # Get the file path
                            file_path = os.path.join(root, file)

                            # Skip froster files
                            if os.path.isfile(file_path) and \
                                    file != hash_file and \
                                    file != self.where_did_the_files_go_filename and \
                                    file != self.md5sum_filename and \
                                    file != self.md5sum_restored_filename:

                                task = executor.submit(self.md5sum, file_path)

                                tasks[task] = file_path

                        for future in concurrent.futures.as_completed(tasks):
                            file = os.path.basename(tasks[future])
                            md5 = future.result()
                            out_f.write(f"{md5}  {file}\n")

                # Check we generated the hash file
                if os.path.getsize(hashpath) == 0:
                    os.remove(hashpath)
                    return False
                else:
                    return True

        except Exception:
            print_error()
            return False

    def _gen_allfiles_and_tar(self, directory, smallsize=1024, is_tar=True):
        '''Tar small files in a directory'''

        try:
            tar_path = os.path.join(directory, self.smallfiles_tar_filename)
            csv_path = os.path.join(directory, self.allfiles_csv_filename)

            if os.path.exists(tar_path):
                return True

            for root, dirs, files in self._walker(directory):

                # We only want to tar the files in the root directory. Avoid recursion.
                if root != directory:
                    break

                # Flag to check if any files were tarred
                didtar = False

                # Create tar file and csv file
                with tarfile.open(tar_path, "w") as tar_file, open(csv_path, 'w', newline='') as csv_file:

                    # Create csv writer
                    writer = csv.writer(csv_file)

                    # Write the header
                    writer.writerow(["File", "Size(bytes)", "Date-Modified",
                                    "Date-Accessed", "Owner", "Group", "Permissions", "Tarred"])

                    for file in files:
                        # Get the file path
                        file_path = os.path.join(root, file)

                        # Skip the csv file
                        if file_path == csv_path:
                            continue

                        # Check if file is larger than X MB
                        size, mtime, atime = self._get_file_stats(file_path)

                        # Get last modified date
                        mdate = datetime.datetime.fromtimestamp(
                            mtime).strftime('%Y-%m-%d %H:%M:%S')

                        # Get last accessed date
                        adate = datetime.datetime.fromtimestamp(
                            atime).strftime('%Y-%m-%d %H:%M:%S')

                        # Get ownership
                        owner = self.uid2user(os.lstat(file_path).st_uid)
                        group = self.gid2group(os.lstat(file_path).st_gid)

                        # Get permissions
                        permissions = oct(os.lstat(file_path).st_mode)

                        # Set tarred to No
                        tarred = "No"

                        # Tar the file if it's smaller than the specified size
                        if is_tar and size < smallsize*1024:
                            # add to tar file
                            tar_file.add(file_path, arcname=file)

                            # Set didtar to True, so we know we tarred a file
                            didtar = True

                            # remove original file
                            os.remove(file_path)

                            # Set tarred to Yes
                            tarred = "Yes"

                        # Write file info to the csv file
                        writer.writerow(
                            [file, size, mdate, adate, owner, group, permissions, tarred])

                # Check if we tarred any files
                if not didtar:
                    # Remove the tar file if it's empty
                    os.remove(tar_path)

            return True

        except Exception:
            print_error()
            return False

    def reset_folder(self, directory, recursive=False):
        '''Remove all froster artifacts from a folder and untar small files'''

        for root, dirs, files in self._walker(directory):
            if not recursive and root != directory:
                break
            try:
                print(f'\nResetting folder {root}...')

                if self._is_folder_archived(root.rstrip(os.path.sep)):
                    print(
                        f'    ...folder {root} is archived, nothing to reset\n')
                    continue

                # Get the path to the tar file
                tar_path = os.path.join(root, self.smallfiles_tar_filename)

                if os.path.exists(tar_path):
                    print('    Untarring Froster.smallfiles.tar... ', end='')
                    with tarfile.open(tar_path, "r") as tar:
                        tar.extractall(path=root)
                    os.remove(tar_path)
                    print('done.')

                for file in self.dirmetafiles:
                    delfile = os.path.join(root, file)
                    print(f'    Removing {file}... ', end='')
                    if os.path.exists(delfile):
                        os.remove(delfile)
                        print('done')
                    else:
                        print('nothing to remove')

                print(f'...folder {root} reset successfully\n')

            except Exception:
                print_error()

    def _is_small_file_in_dir(self, dir, small=1024):
        # Get all files in the specified directory
        files = [os.path.join(dir, f) for f in os.listdir(
            dir) if os.path.isfile(os.path.join(dir, f))]
        # print("** files:",files)
        # Check if there's any file less than small
        is_there_small_file = False
        for f in files:
            try:
                s, *_ = self._get_file_stats(f)
                if s < small*1024:
                    is_there_small_file = True
                    break
            except FileNotFoundError:
                # Handle the error (e.g., print a message or continue to the next file)
                print(f"File not found: {f}")
                continue
        return is_there_small_file

    def _get_file_stats(self, filepath):
        try:
            # Use lstat to get stats of symlink itself, not the file it points to
            stats = os.lstat(filepath)
            return stats.st_size, stats.st_mtime, stats.st_atime
        except FileNotFoundError:
            print(f"{filepath} not found.")
            return None, None, None

    def _delete_locally(self, folder_to_delete):
        '''Delete the given folder'''

        print(f'\nDELETING {folder_to_delete}...')

        # Check if the folder is already archived
        where_did_files_go = os.path.join(
            folder_to_delete, self.where_did_the_files_go_filename)
        if os.path.isfile(where_did_files_go):
            print(f'    ...already deleted\n')
            return

        archived_folder_info = self.froster_archives_get_entry(
            folder_to_delete)

        if archived_folder_info is None:
            print(f'\nFolder {folder_to_delete} is not archived')
            print(f'No entry found in froster-archives.json\n')
            return

        try:

            # Get the path to the hash file
            hashfile = os.path.join(folder_to_delete, self.md5sum_filename)

            # Check if the hashfile exists
            if not os.path.exists(hashfile):

                # Regular hashfile does not exist, check if the restored hashfile exists
                hashfile = os.path.join(
                    folder_to_delete, self.md5sum_restored_filename)

                if not os.path.exists(hashfile):
                    print(
                        f'There is no hashfile therefore cannot delete files in {folder_to_delete}')
                    return

            # Get the subfolder path
            subfolder_path = folder_to_delete.replace(
                archived_folder_info['local_folder'], '')

            # Get the path to the S3 destination
            # Risky, but os.paht.join does not work with :s3: paths
            s3_dest = archived_folder_info['archive_folder'] + subfolder_path

            print(f'\n    Verifying checksums...')
            rclone = Rclone(self.args, self.cfg)
            ret = rclone.checksum(hashfile, s3_dest, '--max-depth', '1')
            # Check if the checksums are correct
            if ret:
                print('        ...done')
            else:
                return

            deleted_files = []

            # Delete the files
            for root, dirs, files in self._walker(folder_to_delete):
                if root != folder_to_delete:
                    break

                print(f'\n    Deleting files...')
                for file in files:
                    if file == self.md5sum_filename or file == self.md5sum_restored_filename or file == self.allfiles_csv_filename or file == self.where_did_the_files_go_filename:
                        continue
                    else:
                        file_path = os.path.join(root, file)
                        os.remove(file_path)
                        deleted_files.append(file)
                print(f'        ...done')

            # Write a readme file with the metadata
            email = self.cfg.email
            readme = os.path.join(
                folder_to_delete, self.where_did_the_files_go_filename)

            with open(readme, 'w') as rme:
                rme.write(
                    f'The files in this folder have been moved to an AWS S3 archive!\n')
                rme.write(f'\nArchive location: {s3_dest}\n')
                rme.write(
                    f"Archive aws profile: {archived_folder_info['profile']}\n")
                rme.write(f"Archiver user: {archived_folder_info['user']}\n")
                rme.write(f'Archiver email: {self.cfg.email}\n')
                rme.write(
                    f'Archive tool: https://github.com/dirkpetersen/froster\n')
                rme.write(
                    f'Restore command: froster restore "{folder_to_delete}"\n')
                rme.write(
                    f'Deletion date: {datetime.datetime.now()}\n')
                rme.write(f'\n\nFirst 10 files deleted this time:\n')
                rme.write(', '.join(deleted_files[:10]))
                rme.write(
                    f'\n\nPlease see more metadata in Froster.allfiles.csv file')
                rme.write(
                    f'\n\nYou can use "visidata" or "vd" tool to help you visualize Froster.allfiles.csv file\n')

            print(f'\nDELETING SUCCESSFULLY COMPLETED\n')

            # Print the final message
            print(f'    LOCAL DELETED FOLDER:   {folder_to_delete}')
            print(f'    AWS S3 DESTINATION:     {s3_dest}\n')
            print(f'    Total files deleted:    {len(deleted_files)}\n')
            print(f'    Manifest:               {readme}\n')

        except Exception:
            print_error()
            return

    def delete(self, folders):
        '''Delete the given folders'''

        try:
            # Clean the provided paths
            folders = clean_path_list(folders)

            # Set flags
            is_recursive = self.args.recursive

            if is_recursive:
                if self._is_recursive_collision(folders):
                    print(
                        f'\nError: You cannot delete folders recursively if there is a dependency between them.\n')
                    return

            # Check if we can read & write all files and folders
            if not self._is_correct_files_folders_permissions(folders, is_recursive):
                print(
                    '\nError: Cannot read or write to all files and folders.\n', file=sys.stderr)
                print(
                    f'You can check the permissions of the files and folders using the command:', file=sys.stderr)
                print(
                    f'    froster archive --permissions "/your/folder/to/archive"\n', file=sys.stderr)
                return

            if use_slurm(self.args.noslurm):
                self._slurm_cmd(folders=folders, cmd_type='delete')
            else:
                for folder in folders:
                    if is_recursive:
                        for root, dirs, files in self._walker(folder):
                            self._delete_locally(root)
                    else:
                        self._delete_locally(folder)
        except Exception:
            print_error()

    def _download(self, folder):
        '''Download the restored files'''

        try:
            where_did_file_go_full_path = os.path.join(
                folder, self.where_did_the_files_go_filename)

            # Get the bucket and prefix
            bucket, prefix, *_ = self.archive_get_bucket_info(folder)

            if not bucket:
                print(f'\nFolder {folder} is not registered as archived')
                return

            # All retrievals are done, now we can download the files
            source = ':s3:' + bucket + '/' + prefix
            target = folder

            # Download the restored files
            print(f'Downloading files...')
            rclone = Rclone(self.args, self.cfg)
            if rclone.copy(source, target, '--max-depth', '1'):
                print('    ...done\n')
            else:
                print('    ...FAILED\n')

            # checksum verification
            self._restore_verify(source, target)

        except Exception:
            print_error()

    def _restore_locally(self, folder, aws: AWSBoto):
        '''Restore the given folder'''

        try:
            print(f'\nRestoring folder "{folder}..."\n')

            # Get folder info
            bucket, prefix, is_recursive, is_glacier, profile, user = self.archive_get_bucket_info(
                folder)

            if is_glacier:
                trig, rest, done, notg = aws.glacier_restore(
                    bucket, prefix, self.args.days, self.args.retrieveopt)

                print(f'    Triggered Glacier retrievals: {len(trig)}')
                print(f'    Currently retrieving from Glacier: {len(rest)}')
                print(f'    Retrieved from Glacier: {len(done)}')
                print(f'    Not in Glacier: {len(notg)}\n')

                if len(trig) > 0 or len(rest) > 0:
                    # glacier is still ongoing
                    print(
                        f'\n    Glacier retrievals pending. Depending on the storage class and restore mode run this command again in:')
                    print(f'        Expedited mode: ~ 5 minuts\n')
                    print(f'        Standard mode: ~ 12 hours\n')
                    print(f'        Bulk mode: ~ 48 hours\n')
                    print(
                        f'        \nNOTE: You can check more accurate times in the AWS S3 console\n')
                    return False
            else:
                print(f'...no glacier restore needed\n')

            print(f'...folder restored\n')

            return True

        except Exception:
            print_error()

    def _contains_non_froster_files(self, folder):
        '''Check if the folder contains non-froster files'''

        try:
            # Check if the folder has any non-froster file

            for root, dirs, files in self._walker(folder):
                if root != folder:
                    break
                for file in files:
                    if file not in self.dirmetafiles:
                        return False
            return True

        except Exception:
            print_error()
            return False

    def restore(self, folders, aws: AWSBoto):
        '''Restore the given folder'''

        try:
            # Clean the provided paths
            folders = clean_path_list(folders)

            # Set flags
            is_recursive = self.args.recursive

            # Check if there is a conflict between folders and recursive flag,
            # i.e. recursive flag is set and a folder is a subdirectory of another one
            if is_recursive:
                if self._is_recursive_collision(folders):
                    print(
                        f'\nError: You cannot restore folders recursively if there is a dependency between them.\n')
                    return

            # Check if we can read & write all files and folders
            if not self._is_correct_files_folders_permissions(folders, is_recursive):
                print(
                    '\nError: Cannot read or write to all files and folders.\n', file=sys.stderr)
                print(
                    f'You can check the permissions of the files and folders using the command:', file=sys.stderr)
                print(
                    f'    froster archive --permissions "/your/folder/to/archive"\n', file=sys.stderr)
                return


            # Archive locally all folders. If recursive flag set, archive all subfolders too.
            for folder in folders:
                for root, dirs, files in self._walker(folder):

                    # Break in case of non-recursive restore
                    if not is_recursive and root != folder:
                        break

                    archived_folder_info = self.froster_archives_get_entry(
                        root)

                    if archived_folder_info is None:
                        print(f'\nFolder {root} is not archived')
                        print(f'No entry found in froster-archives.json\n')
                        continue

                    if not self._contains_non_froster_files(root):
                        print(
                            f'\nWARNING: Folder {root} contains non-froster metadata files')
                        print(
                            'Has this folder been deleted using "froster delete" command?.')
                        print('Please empty the folder before restoring.\n')
                        continue

                    if self._restore_locally(root, aws):
                        # Already restored

                        # If nodownload flag is set we are done
                        if self.args.nodownload:
                            print(
                                f'\nFolder restored but not downloaded (--no-download flag set)\n')
                            return
                        else:
                                self._download(root)
                    else:
                        # Restore ongoing
                        # In this case the slurm will only be used for downloading. AWS has taken care of the restore
                           if is_slurm_installed() and not self.args.noslurm:
                                # schedule execution in 12 hours
                                self._slurm_cmd(
                                    folders=folders, cmd_type='restore', scheduled=12)



        except Exception:
            print_error()

    def _restore_verify(self, source, target):
        '''Verify the restored files'''

        try:
            for root, dirs, files in self._walker(target):
                if root != target:
                    break

                restpath = root
                if root != target:
                    source = source + os.path.basename(root) + '/'

                # Generate md5 checksums for all files in the folder
                print(f'Generating checksums...')
                if self._gen_md5sums(restpath, self.md5sum_restored_filename):
                    print('    ...done')
                else:
                    print('    ...FAILED\n')
                    return

                # Get the path to the hashfile
                hashfile = os.path.join(
                    restpath,  self.md5sum_restored_filename)

                # Create the Rclone object
                rclone = Rclone(self.args, self.cfg)

                print(f'\nVerifying checksums...')
                if rclone.checksum(hashfile, source, '--max-depth', '1'):
                    print('    ...done')
                else:
                    print('    ...FAILED\n')
                    return

                # Check if Froster.smallfiles.tar exists
                tar_path = os.path.join(target, self.smallfiles_tar_filename)
                if os.path.exists(tar_path):
                    print(f'\nUntarring Froster.smallfiles.tar... ')
                    with tarfile.open(tar_path, "r") as tar:
                        tar.extractall(path=target)
                    os.remove(tar_path)
                    print('    ...done\n')

                where_did_file_go_full_path = os.path.join(
                    target, self.where_did_the_files_go_filename)
                if os.path.exists(where_did_file_go_full_path):
                    os.remove(where_did_file_go_full_path)

                print(f'Restoration of {root} completed successfully\n')

        except Exception:
            print_error()

    def md5sum(self, file_path):
        '''Calculate md5sum of a file'''

        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def uid2user(self, uid):
        '''Convert uid to username'''

        try:
            return pwd.getpwuid(uid)[0]
        except Exception:
            print_error()
            return uid

    def gid2group(self, gid):
        '''Convert gid to group name'''

        try:
            return grp.getgrgid(gid)[0]
        except Exception:
            print_error()
            return gid

    def daysago(self, unixtime):
        '''Calculate the number of days ago from a given unixtime'''
        try:
            if not unixtime:
                printdbg(
                    'daysago: an integer is required (got type NoneType)')
                return 0
            diff = datetime.datetime.now()-datetime.datetime.fromtimestamp(unixtime)
            return diff.days

        except Exception:
            print_error()
            return 0

    def convert_size(self, size_bytes):
        '''Convert bytes to human readable format'''
        try:
            if size_bytes == 0:
                return "0B"
            size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes/p, 3)
            return f"{s} {size_name[i]}"

        except Exception:
            print_error()

    def _archive_json_add_entry(self, key, value):
        '''Add a new entry to the archive JSON file'''
        try:

            # Initialize the data dictionary in case archive_json does not exist
            data = {}

            # Read the archive JSON file
            if os.path.isfile(self.archive_json):
                with open(self.archive_json, 'r') as file:
                    try:
                        data = json.load(file)
                    except Exception:
                        print('Error in Archiver._archive_json_add_entry():')
                        print(
                            f'Cannot read {self.archive_json}, file corrupt?')
                        return

            # Add the new entry to the data dictionary
            data[key] = value

            # Create the directory for the archive JSON file if it does not exist
            os.makedirs(os.path.dirname(self.archive_json), exist_ok=True)

            # Write the updated data dictionary to the archive JSON file
            with open(self.archive_json, 'w') as file:
                json.dump(data, file, indent=4)
        except Exception:
            print_error()

    def _is_folder_archived(self, folder):
        '''Check if an entry exists in the archive JSON file'''

        return (self.froster_archives_get_entry(folder) != None)

    def archive_get_bucket_info(self, folder):
        '''Get the bucket and prefix of an archived folder'''

        try:
            is_glacier = False
            is_recursive = False

            # Get the folder archiving info from froster-archives.json file
            archive_folder_info = self.froster_archives_get_entry(folder)

            # Check the folder is archived
            if not archive_folder_info:
                print(f'\nFolder {folder} is not registered as archived')
                return None, None, None, None, None, None

            # Get the archive folder
            local_folder = archive_folder_info['local_folder']
            archive_folder = archive_folder_info['archive_folder']
            s3_storage_class = archive_folder_info['s3_storage_class']
            profile = archive_folder_info['profile']
            archive_mode = archive_folder_info['archive_mode']
            user = archive_folder_info['user']

            # Get the bucket and prefix
            bucket, prefix = archive_folder.split('/', 1)

            # Clean bucket
            bucket = bucket.replace(':s3:', '')

            # Clean prefix so it works even if folder is a subfolder of an stored parent
            prefix = prefix.replace(local_folder, '')
            prefix = prefix + folder + '/'

            # Get the archived mode
            if archive_mode == "Recursive":
                is_recursive = True

            # Get the S3 storage class
            if s3_storage_class in ['DEEP_ARCHIVE', 'GLACIER']:
                is_glacier = True

            return bucket, prefix, is_recursive, is_glacier, profile, user

        except Exception:
            print_error()
            return None, None, None, None, None, None

    def froster_archives_get_entry(self, folder):
        '''Get an entry from the archive JSON file'''

        try:
            # If the archive JSON file does not exist, the entry does not exist
            if not os.path.isfile(self.archive_json):
                return None

            # Read the archive JSON file
            with open(self.archive_json, 'r') as file:
                try:
                    data = json.load(file)
                except Exception:
                    print('Error in Archiver._archive_json_entry_exists():')
                    print(f'Cannot read {self.archive_json}, file corrupt?')
                    return None

            # Check if the entry exists in the data dictionary
            if folder in data:
                return data[folder]
            else:
                # Check if a parent folder exists in the data dictionary with recursive archiving
                path = Path(folder)

                for parent in path.parents:
                    parent = str(parent)
                    if parent in data and data[parent]['archive_mode'] == 'Recursive':
                        return data[parent]

                return None

        except Exception:
            print_error()

    def archive_json_get_csv(self, columns):
        '''Get the archive JSON data as a CSV string'''
        try:
            if not os.path.exists(self.archive_json):
                return

            with open(self.archive_json, 'r') as file:
                try:
                    data = json.load(file)

                except Exception:
                    print('Error in Archiver._archive_json_get_csv():')
                    print(f'Cannot read {self.archive_json}, file corrupt?')
                    return

            # Sort data by timestamp in reverse order
            sorted_data = sorted(
                data.items(), key=lambda x: x[1]['timestamp'], reverse=True)

            # Prepare CSV data
            csv_data = [columns]

            for path_name, row_data in sorted_data:
                csv_row = [row_data[col] for col in columns if col in row_data]
                csv_data.append(csv_row)

            # Convert CSV data to a CSV string
            output = io.StringIO()

            writer = csv.writer(output, dialect='excel')
            writer.writerows(csv_data)
            csv_string = output.getvalue()

            output.close()

            return csv_string

        except Exception:
            print_error()

    def _get_newest_file_atime(self, folder_path, folder_atime=None):
        '''Get the atime of the newest file in the folder'''

        try:
            if not folder_path or not os.path.exists(folder_path):
                print(f" Invalid folder path: {folder_path}")
                return folder_atime

            last_accessed_time = None

            subobjects = os.listdir(folder_path)

            for file_name in subobjects:
                if file_name in self.dirmetafiles:
                    continue
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):
                    accessed_time = os.path.getatime(file_path)
                    if last_accessed_time is None or accessed_time > last_accessed_time:
                        last_accessed_time = accessed_time
            if last_accessed_time == None:
                last_accessed_time = folder_atime
            return last_accessed_time

        except Exception as e:
            print_error()
            return folder_atime

    def _get_newest_file_mtime(self, folder_path, folder_mtime=None):
        '''Get the mtime of the newest file in the folder'''

        try:
            if not folder_path or not os.path.exists(folder_path):
                print(f" Invalid folder path: {folder_path}")
                return folder_mtime

            last_modified_time = None

            subobjects = os.listdir(folder_path)

            for file_name in subobjects:
                if file_name in self.dirmetafiles:
                    continue
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):
                    modified_time = os.path.getmtime(file_path)
                    if last_modified_time is None or modified_time > last_modified_time:
                        last_modified_time = modified_time

            if last_modified_time == None:
                last_modified_time = folder_mtime

            return last_modified_time

        except Exception as e:
            print_error()
            return folder_mtime

    def get_hotspots_path(self, folder):
        ''' Get a full path name of a new hotspots file'''
        try:
            # Take the correct hotspots directory
            hotspotdir = self.cfg.shared_hotspots_dir if self.cfg.is_shared else self.cfg.hotspots_dir

            # create hotspots directory if it does not exist
            os.makedirs(hotspotdir, exist_ok=True, mode=0o775)

            # Get the full path name of the new hotspots file
            return os.path.join(hotspotdir, self._get_hotspots_filename(folder))
        except Exception:
            print_error()
            return None

    def _get_hotspots_filename(self, folder):
        '''Get the hotspots file name'''
        try:
            mountlist = self._get_mount_info()

            for mnt in mountlist:
                if folder.startswith(mnt['mount_point']):
                    # Get the last directory in the path
                    traildir = self._get_last_directory(mnt['mount_point'])

                    # Build the hotspots file name
                    hsfile = folder.replace(mnt['mount_point'], '')
                    hsfile = f'@{traildir}{hsfile}'

                    # Shorten the length of the file if it is too long
                    if len(hsfile) > 255:
                        hsfile = f'{hsfile[:25]}.....{hsfile[-225:]}'

            hsfile = folder.replace('/', '+') + '.csv'

            return hsfile

        except Exception:
            print_error()

    def _walker(self, top, skipdirs=['.snapshot',]):
        """ returns subset of os.walk  """
        try:
            for root, dirs, files in os.walk(top, topdown=True, onerror=self._walkerr):
                for skipdir in skipdirs:
                    if skipdir in dirs:
                        dirs.remove(skipdir)  # don't visit this directory
                yield root, dirs, files
        except Exception:
            print_error()

    def _walkerr(self, oserr):
        """ error handler for os.walk """
        try:
            sys.stderr.write(str(oserr))
            sys.stderr.write('\n')
        except Exception:
            print_error()

    def _get_last_directory(self, path):
        '''Get the last directory in the path'''

        try:
            # Remove any trailing slashes
            path = path.rstrip(os.path.sep)

            # Split the path by the separator
            path_parts = path.split(os.path.sep)

            # Return the last directory
            return path_parts[-1]

        except Exception:
            print_error()
            return None

    def _get_mount_info(self):
        '''Get the mount information'''
        try:
            file_path = '/proc/self/mountinfo'

            fs_types = {'nfs', 'nfs4', 'cifs', 'smb', 'afs', 'ncp',
                        'ncpfs', 'glusterfs', 'ceph', 'beegfs',
                        'lustre', 'orangefs', 'wekafs', 'gpfs'}

            mountinfo_list = []

            with open(file_path, 'r') as f:
                for line in f:
                    fields = line.strip().split(' ')
                    _, _, _, _, mount_point, _ = fields[:6]
                    for field in fields[6:]:
                        if field == '-':
                            break
                    fs_type, mount_source, _ = fields[-3:]
                    mount_source_folder = mount_source.split(
                        ':')[-1] if ':' in mount_source else ''
                    if fs_type in fs_types:
                        mountinfo_list.append({
                            'mount_source_folder': mount_source_folder,
                            'mount_point': mount_point,
                            'fs_type': fs_type,
                            'mount_source': mount_source,
                        })
            return mountinfo_list

        except Exception:
            print_error()
            return None


class ScreenConfirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    ScreenConfirm {
        align: center middle;
    }

    ScreenConfirm > Vertical {
        background: $secondary;
        width: auto;
        height: auto;
        border: thick $primary;
        padding: 2 4;
    }

    ScreenConfirm > Vertical > * {
        width: auto;
        height: auto;
    }

    ScreenConfirm > Vertical > Label {
        padding-bottom: 2;
    }

    ScreenConfirm > Vertical > Horizontal {
        align: right middle;
    }

    ScreenConfirm Button {
        margin-left: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():

            yield Label("Do you want to start this archiving job now?\nChoose 'Quit' if you would like to archive recursively")
            with Horizontal():
                yield Button("Start Job", id="continue")
                yield Button("Back to List", id="return")
                yield Button("Quit to CLI", id="quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # self.dismiss(result=event.button.id == "continue")
        self.dismiss(result=event.button.id)


class TableHotspots(App[list]):

    BINDINGS = [("q", "request_quit", "Quit")]

    def __init__(self, file):
        super().__init__()
        self.myrow = []
        self.file = file

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        yield table
        # yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        fh = open(self.file, 'r')
        rows = csv.reader(fh)
        table.add_columns(*next(rows))
        table.add_rows(itertools.islice(rows, MAXHOTSPOTS))

    def accept_answer(self, answer: str) -> None:
        # adds yesno answer as last element in list
        if answer == 'continue':
            self.exit(self.myrow+[True])
        elif answer == 'quit':
            self.exit(self.myrow+[False])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.myrow = self.query_one(DataTable).get_row(event.row_key)
        # self.exit(self.myrow)
        self.push_screen(ScreenConfirm(), callback=self.accept_answer)

    def action_request_quit(self) -> None:
        self.app.exit()


class TextualStringListSelector(App[list]):

    BINDINGS = [("q", "request_quit", "Quit")]

    def __init__(self, title: str, items: list[str]):
        super().__init__()
        self.title = title
        self.items = items

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        yield table
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(self.title)
        for item in self.items:
            table.add_row(item)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

    def action_request_quit(self) -> None:
        self.app.exit()


class TableArchive(App[list]):

    BINDINGS = [("q", "request_quit", "Quit")]

    def __init__(self, files: list[str]):
        super().__init__()
        self.files = files

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        # table.fixed_rows = 1
        yield table
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        rows = csv.reader(io.StringIO(self.files))
        table.add_columns(*next(rows))
        table.add_rows(itertools.islice(rows, MAXHOTSPOTS))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

    def action_request_quit(self) -> None:
        self.app.exit()


class TableNIHGrants(App[list]):

    DEFAULT_CSS = """
    Input.-valid {
        border: tall $success 60%;
    }
    Input.-valid:focus {
        border: tall $success;
    }
    Input {
        margin: 1 1;
    }
    Label {
        margin: 1 2;
    }
    DataTable {
        margin: 1 2;
    }
    """

    BINDINGS = [("q", "request_quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Label("Enter search to link your data with metadata of an NIH grant/project and press Enter")
        yield Input(
            placeholder="Enter a part of a Grant Number, PI, Institution or Full Text (Title, Abstract, Terms) ...",
        )
        yield LoadingIndicator()
        table = DataTable()
        # table.focus()
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        yield table
        # yield Footer()

    def on_mount(self) -> None:
        self.query_one(LoadingIndicator).display = False
        self.query_one(DataTable).display = False

    @on(Input.Submitted)
    def action_submit(self):
        self.query_one(LoadingIndicator).display = True
        self.query_one(DataTable).display = False
        inp = self.query_one(Input)
        if inp.value:
            self.load_data(inp.value)
        else:
            self.app.exit([])
        inp.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

    def action_request_quit(self) -> None:
        self.app.exit([])

    @work
    async def load_data(self, searchstr):
        table = self.query_one(DataTable)
        table.clear(columns=True)

        await asyncio.sleep(0.1)

        rep = NIHReporter()
        data = rep.search_full(searchstr)
        if not data:
            return
        rows = iter(data)

        table.add_columns(*next(rows))
        table.add_rows(rows)

        table.display = True
        self.query_one(LoadingIndicator).display = False

        return


class Rclone:
    def __init__(self, args: argparse.Namespace, cfg: ConfigManager):
        '''Initialize Rclone object'''

        try:
            # Store the arguments and configuration
            self.args = args
            self.cfg = cfg

            # Set the Rclone executable path
            self.rc = os.path.join(sys.prefix, 'bin', 'rclone')

            # Set the Rclone environment variables
            # Note: Keys are set in the AWS Boto __init__ function
            self.envrn = {}
            self.envrn['RCLONE_S3_ENV_AUTH'] = 'true'
            self.envrn['RCLONE_S3_PROVIDER'] = 'AWS'
            self.envrn['RCLONE_S3_REGION'] = self.cfg.aws_region
            self.envrn['RCLONE_S3_LOCATION_CONSTRAINT'] = self.cfg.aws_region
            self.envrn['RCLONE_S3_STORAGE_CLASS'] = self.cfg.storage_class

            # Set the credentials for AWS
            if self.cfg.aws_init:

                # Create a ConfigParser object
                config = configparser.ConfigParser()

                # Read AWS Credentials file
                if os.path.exists(self.cfg.aws_credentials_file):
                    config.read(self.cfg.aws_credentials_file)

                    # Check if the AWS profile exists
                    if config.has_section(self.cfg.aws_profile):
                        # Set the environment variables for creds
                        self.envrn['AWS_ACCESS_KEY_ID'] = config.get(
                            self.cfg.aws_profile, 'aws_access_key_id')
                        self.envrn['AWS_SECRET_ACCESS_KEY'] = config.get(
                            self.cfg.aws_profile, 'aws_secret_access_key')
        except Exception:
            print_error()
            sys.exit(1)

    def _run_rclone_command(self, command, background=False):
        '''Run Rclone command'''
        try:
            # Add options to Rclone command
            command = self._add_opt(command, '--use-json-log')

            # Run the command
            if background:

                # This is the solution i found to prevent the popen subprocess to throw errors due
                # our particular usage of rclone.
                output = False

                if output:
                    # Print output in stdout
                    ret = subprocess.Popen(
                        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=self.envrn)

                else:
                    # DO not print output
                    with open(os.devnull, 'w') as devnull:
                        ret = subprocess.Popen(
                            command, stdout=devnull, stderr=devnull, text=True, env=self.envrn)

                # If we have a pid we assume the command was successful
                if ret.pid:
                    return True
                else:
                    return False

            else:
                ret = subprocess.run(
                    command, capture_output=True, text=True, env=self.envrn)

                # Check if the command was successful
                if ret.returncode == 0:
                    # Execution successfull
                    return True
                else:
                    # Execution failed
                    exit_codes = {
                        0: "Success",
                        1: "Syntax or usage error",
                        2: "Error not otherwise categorised",
                        3: "Directory not found",
                        4: "File not found",
                        5: "Temporary error (one that more retries might fix) (Retry errors)",
                        6: "Less serious errors (like 461 errors from dropbox) (NoRetry errors)",
                        7: "Fatal error (one that more retries won't fix, like account suspended) (Fatal errors)",
                        8: "Transfer exceeded - limit set by --max-transfer reached",
                        9: "Operation successful, but no files transferred",
                    }

                    print(
                        f'\n        Error: Rclone {command[1]} command failed', file=sys.stderr)
                    print(
                        f'        Command: {" ".join(command)}', file=sys.stderr)
                    print(
                        f'        Return code: {ret.returncode}', file=sys.stderr)
                    print(
                        f'        Return code meaning: {exit_codes[ret.returncode]}\n', file=sys.stderr)

                    out, err = ret.stdout.strip(), ret.stderr.strip()
                    stats, ops = self._parse_log(err)
                    ret = stats[-1]  # return the stats
                    print(
                        f"        Error message: {ret['stats']['lastError']}\n", file=sys.stderr)

                    return False

        except Exception:
            print_error()
            return False

    def copy(self, src, dst, *args):
        '''Copy files from source to destination using Rclone'''
        try:
            # Build the copy command
            command = [self.rc, 'copy'] + list(args)
            command.append(src)
            command.append(dst)
            command.append('-vvv')

            # Run the copy command and return if it was successful
            return self._run_rclone_command(command)
        except Exception:
            print_error()
            return False

    def checksum(self, md5file, dst, *args):
        '''Check the checksum of a file using Rclone'''
        try:
            command = [self.rc, 'checksum'] + list(args)
            command.append('md5')
            command.append(md5file)
            command.append(dst)

            return self._run_rclone_command(command)

        except Exception:
            print_error()
            return False

    def mount(self, src, dst, *args):
        '''Mount files from url to on-premises using Rclone'''

        if not shutil.which('fusermount3'):
            print('Could not find "fusermount3". Please install the "fuse3" OS package')
            sys.exit(1)

        try:
            # Build the copy command
            command = [self.rc, 'mount'] + list(args)
            command.append('--allow-non-empty')
            command.append('--default-permissions')
            command.append('--read-only')
            command.append('--no-checksum')
            command.append(src)
            command.append(dst)

            # Run the copy command and return if it was successful
            return self._run_rclone_command(command, background=True)

        except Exception:
            print_error()
            return False

    def unmount(self, mountpoint, wait=False):
        '''Unmount files from on-premises using Rclone'''

        if not shutil.which('fusermount3'):
            print(
                'Could not find "fusermount3". Please install the "fuse3" OS package')
            sys.exit(1)

        try:
            # Build command
            cmd = ['fusermount3', '-u', mountpoint]
            ret = subprocess.run(cmd, capture_output=False,
                                 text=True, env=self.envrn)

            if ret.returncode == 0:
                return True
            else:
                return False

        except Exception:
            print_error()
            return False

    def version(self):
        '''Get the Rclone version'''
        try:
            command = [self.rc, 'version']
            return self._run_rclone_command(command)
        except Exception:
            print_error()
            return False

    def get_mounts(self):
        '''Get the mounted Rclone mounts'''
        try:
            mounts = []
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    mount_point, fs_type = parts[1], parts[2]
                    if fs_type.startswith('fuse.rclone'):
                        mounts.append(mount_point)
            return mounts
        except Exception:
            print_error()
            return []

    def _get_pids(self, process, full=False):
        '''Get the process ids of the given process name'''

        try:
            process = process.rstrip(os.path.sep)

            if full:
                command = ['pgrep', '-f', process]
            else:
                command = ['pgrep', process]

            output = subprocess.check_output(command)
            pids = [int(pid) for pid in output.decode(
                errors='ignore').split('\n') if pid]

            return pids

        except Exception:
            print_error()
            return []

    def _add_opt(self, cmd, option, value=None):
        '''Add an option to the command if it is not already present'''
        try:
            if option not in cmd:
                cmd.append(option)
                if value:
                    cmd.append(value)

            return cmd

        except Exception:
            print_error()
            return cmd

    def _parse_log(self, strstderr):
        '''Parse the Rclone log'''
        try:
            lines = strstderr.split('\n')
            data = [json.loads(line.rstrip())
                    for line in lines if line[0] == "{"]
            stats = []
            operations = []
            for obj in data:
                if 'accounting/stats' in obj['source']:
                    stats.append(obj)
                elif 'operations/operations' in obj['source']:
                    operations.append(obj)
            return stats, operations

        except Exception:
            print_error()
            return [], []


class Slurm:
    '''Class to handle Slurm essentials'''

    def __init__(self, args, cfg: ConfigManager):
        '''Initialize Slurm object'''

        try:
            # Create the slurm directory if it does not exist
            os.makedirs(cfg.slurm_dir, exist_ok=True, mode=0o775)

            self.script_lines = ["#!/bin/bash"]
            self.cfg = cfg
            self.args = args
            self.squeue_output_format = '"%i","%j","%t","%M","%L","%D","%C","%m","%b","%R"'
            self.jobs = []
            self.job_info = {}

            self.partition = cfg.slurm_partition if hasattr(
                cfg, 'slurm_partition') else None

            if self.partition is not None:

                # Make sure we are not exceeding the number of cores available
                total_cpus = self.get_total_cpus(self.partition)
                if self.args.cores > total_cpus:
                    self.args.cores = total_cpus

                # Transform memory from GB to MB
                self.args.memory *= 1024

                # Make sure we are not exceeding the memory available
                max_memory_per_node_in_mb = self.get_max_memory_per_node_in_mb()
                if self.args.memory > max_memory_per_node_in_mb:
                    self.args.memory = max_memory_per_node_in_mb

            self.qos = cfg.slurm_qos if hasattr(cfg, 'slurm_qos') else None

            walltime_days = cfg.slurm_walltime_days if hasattr(
                cfg, 'slurm_walltime_days') else None

            walltime_hours = cfg.slurm_walltime_hours if hasattr(
                cfg, 'slurm_walltime_hours') else None

            if walltime_days is not None and walltime_hours is not None:
                self.walltime = f'{walltime_days}-{walltime_hours}'
            else:
                self.walltime = '7-0'

            self.slurm_lscratch = cfg.slurm_lscratch if hasattr(
                cfg, 'slurm_lscratch') else None

            self.lscratch_mkdir = cfg.lscratch_mkdir if hasattr(
                cfg, 'lscratch_mkdir') else None

            self.lscratch_root = cfg.lscratch_root if hasattr(
                cfg, 'lscratch_root') else None

            if self.slurm_lscratch:
                self.add_line(f'#SBATCH {self.slurm_lscratch}')

            self.add_line(f'{self.lscratch_mkdir}')

            if self.lscratch_root:
                self.add_line(
                    'export TMPDIR=%s/${SLURM_JOB_ID}' % self.lscratch_root)
        except Exception:
            print_error()

    def add_line(self, line):
        '''Add a line to the Slurm script'''
        try:
            if line:
                self.script_lines.append(line)
        except Exception:
            print_error()

    def get_future_start_time(self, add_hours):
        '''Get the future start time for a Slurm job'''
        try:
            now = datetime.datetime.now()
            future_time = now + datetime.timedelta(hours=add_hours)
            return future_time.strftime("%Y-%m-%dT%H:%M")
        except Exception:
            print_error()
            return None

    def get_total_cpus(self, partition):
        '''Get the total number of CPUs in a partition'''
        try:
            cmd = ['sinfo', '-N', '-p', partition, '--format="%n %c"']
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                raise Exception(f'Error executing command: {result.stderr}')
            lines = result.stdout.split('\n')
            total_cpus = 0
            for line in lines[1:]:  # Skip the header line
                if line:  # Skip empty lines
                    node, cpus = line.split()
                    cpus = cpus.replace('"', '').replace("'", '')
                    total_cpus += int(cpus)
            return total_cpus

        except Exception:
            print_error()
            return 1

    def get_max_memory_per_node_in_mb(self):
        '''Get the maximum memory per node in MB.'''

        try:
            # Run the sinfo command and capture its output
            sinfo_output = subprocess.check_output(
                "sinfo -N -o '%m'", shell=True).decode('utf-8')

            # The output is a string with one line per node, so split it into lines
            lines = sinfo_output.split('\n')

            # The first line is a header, so ignore it. The rest of the lines are the memory values.
            # Convert these values to integers and find the minimum value.
            max_memory_per_node = min(int(line) for line in lines[1:] if line)

            return max_memory_per_node

        except Exception:
            print_error()

    def _reorder_sbatch_lines(self, script_buffer):
        '''Reorder the Slurm script lines to have all #SBATCH lines at the top.'''

        try:
            # we need to make sure that all #BATCH are at the top
            script_buffer.seek(0)
            lines = script_buffer.readlines()
            # Remove the shebang line from the list of lines
            shebang_line = lines.pop(0)
            sbatch_lines = [
                line for line in lines if line.startswith("#SBATCH")]
            non_sbatch_lines = [
                line for line in lines if not line.startswith("#SBATCH")]
            reordered_script = io.StringIO()
            reordered_script.write(shebang_line)
            for line in sbatch_lines:
                reordered_script.write(line)
            for line in non_sbatch_lines:
                reordered_script.write(line)
            # add a local scratch teardown, if configured
            reordered_script.write(self.cfg.lscratch_rmdir)
            reordered_script.seek(0)
            return reordered_script

        except Exception:
            print_error()

    def submit_job(self, cmd, cmd_type, label, shortlabel, scheduled=None):
        '''Submit a Slurm job'''

        try:
            # Build output slurm dir
            output_dir = os.path.join(
                self.cfg.slurm_dir, f'froster-{cmd_type}@{label}')

            # Compile the Slurm script
            self.add_line(
                f'#SBATCH --job-name=froster:{cmd_type}:{shortlabel}')
            self.add_line(f'#SBATCH --cpus-per-task={self.args.cores}')
            self.add_line(f'#SBATCH --mem={self.args.memory}')
            if scheduled:
                self.add_line(f'#SBATCH --begin={scheduled}')
            self.add_line(f'#SBATCH --requeue')
            self.add_line(f'#SBATCH --output={output_dir}-%J.out')
            self.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')
            self.add_line(f'#SBATCH --mail-user={self.cfg.email}')
            self.add_line(f'#SBATCH --time={self.walltime}')
            self.add_line(f'#SBATCH --partition={self.partition}')
            self.add_line(f'#SBATCH --qos={self.qos}')

            # Add the command line to the Slurm script
            self.add_line(cmd)

            # Execute the Slurm script
            jobid = self.sbatch()

            # Print the Slurm job information
            print(f'\nSLURM JOB\n')
            print(f'  ID: {jobid}')
            print(f'  Type: {cmd_type}')
            print(f'  Check status: "squeue -j {jobid}"')
            print(f'  Check output: "cat {output_dir}-{jobid}.out"')
            print(f'  Cancel the job: "scancel {jobid}"\n')

        except Exception:
            print_error()

    def sbatch(self):
        '''Submit the Slurm script'''

        try:
            script = io.StringIO()
            for line in self.script_lines:
                script.write(line + "\n")
            script.seek(0)
            oscript = self._reorder_sbatch_lines(script)
            script = oscript.read()

            # Print the script to be submitted
            printdbg(script)

            result = subprocess.run(["sbatch"], text=True, shell=True, input=script,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                if 'Invalid generic resource' in result.stderr:
                    print(
                        'Invalid generic resource request. Please change configuration of slurm_lscratch')
                else:
                    raise RuntimeError(
                        f"Error running sbatch: {result.stderr.strip()}")
                sys.exit(1)

            job_id = int(result.stdout.split()[-1])

            if self.args.debug:
                oscript.seek(0)
                with open(f'submitted-{job_id}.sh', "w", encoding="utf-8") as file:
                    file.write(oscript.read())
                    print(f' Debug script created: submitted-{job_id}.sh')
            return job_id

        except Exception:
            print_error()
            return None

    def squeue(self):
        '''Get the Slurm jobs'''
        try:
            result = subprocess.run(["squeue", "--me", "-o", self.squeue_output_format],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Error running squeue: {result.stderr.strip()}")
            self.jobs = self._parse_squeue_output(result.stdout.strip())

        except Exception:
            print_error()

    def _parse_squeue_output(self, output):
        try:
            csv_file = io.StringIO(output)
            reader = csv.DictReader(csv_file, delimiter=',',
                                    quotechar='"', skipinitialspace=True)
            jobs = [row for row in reader]
            return jobs
        except Exception:
            print_error()
            return []

    def _parse_tabular_data(self, data_str, separator="|"):
        """Parse data (e.g. acctmgr) presented in a tabular format into a list of dictionaries."""

        try:
            lines = data_str.strip().splitlines()
            headers = lines[0].split(separator)
            data = []
            for line in lines[1:]:
                values = line.split(separator)
                data.append(dict(zip(headers, values)))
            return data

        except Exception:
            print_error()
            return []

    def _parse_partition_data(self, data_str):
        """Parse data presented in a tabular format into a list of dictionaries."""

        try:
            lines = data_str.strip().split('\n')
            # Parse each line into a dictionary
            partitions = []
            for line in lines:
                parts = line.split()
                partition_dict = {}
                for part in parts:
                    key, value = part.split("=", 1)
                    partition_dict[key] = value
                partitions.append(partition_dict)
            return partitions

        except Exception:
            print_error()

    def _get_user_groups(self):
        """Get the groups the current Unix user is a member of."""
        try:
            groups = [grp.getgrgid(gid).gr_name for gid in os.getgroups()]
            return groups
        except Exception:
            print_error()
            return []

    def _get_output(self, command):
        """Execute a shell command and return its output."""
        try:
            result = subprocess.run(command, shell=True, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Error running {command}: {result.stderr.strip()}")
            return result.stdout.strip()
        except Exception:
            print_error()
            return None

    def _get_default_account(self):
        """Get the default account for the current user."""
        return self._get_output(f'sacctmgr --noheader --parsable2 show user {self.cfg.whoami} format=DefaultAccount')

    def _get_associations(self):
        """Get the associations between accounts and QOSs."""
        try:
            mystr = self._get_output(
                f"sacctmgr show associations where user={self.cfg.whoami} format=Account,QOS --parsable2")
            asso = {item['Account']: item['QOS'].split(
                ",") for item in self._parse_tabular_data(mystr) if 'Account' in item}
            return asso

        except Exception:
            print_error()
            return {}

    def get_allowed_partitions_and_qos(self):
        """Get a dictionary with keys = partitions and values = QOSs the user is allowed to use."""

        try:
            bacc = os.environ.get('SBATCH_ACCOUNT', '')
            account = bacc if bacc else None
            sacc = os.environ.get('SLURM_ACCOUNT', '')
            account = sacc if sacc else account
            allowed_partitions = {}
            partition_str = self._get_output(
                "scontrol show partition --oneliner")
            partitions = self._parse_partition_data(partition_str)
            user_groups = self._get_user_groups()
            if account is None:
                account = self._get_default_account()
            for partition in partitions:
                pname = partition['PartitionName']
                add_partition = False
                if partition.get('State', '') != 'UP':
                    continue
                if any(group in user_groups for group in partition.get('DenyGroups', '').split(',')):
                    continue
                if account in partition.get('DenyAccounts', '').split(','):
                    continue
                allowedaccounts = partition.get('AllowAccounts', '').split(',')
                if allowedaccounts != ['']:
                    if account in allowedaccounts or 'ALL' in allowedaccounts:
                        add_partition = True
                elif any(group in user_groups for group in partition.get('AllowGroups', '').split(',')):
                    add_partition = True
                elif partition.get('AllowGroups', '') == 'ALL':
                    add_partition = True
                if add_partition:
                    p_deniedqos = partition.get('DenyQos', '').split(',')
                    p_allowedqos = partition.get('AllowQos', '').split(',')
                    associations = self._get_associations()
                    account_qos = associations.get(account, [])
                    if p_deniedqos != ['']:
                        allowed_qos = [
                            q for q in account_qos if q not in p_deniedqos]
                        # print(f"p_deniedqos: allowed_qos in {pname}:", allowed_qos)
                    elif p_allowedqos == ['ALL']:
                        allowed_qos = account_qos
                        # print(f"p_allowedqos = ALL in {pname}:", allowed_qos)
                    elif p_allowedqos != ['']:
                        allowed_qos = [
                            q for q in account_qos if q in p_allowedqos]
                        # print(f"p_allowedqos: allowed_qos in {pname}:", allowed_qos)
                    else:
                        allowed_qos = []
                        # print(f"p_allowedqos = [] in {pname}:", allowed_qos)
                    allowed_partitions[pname] = allowed_qos
            return allowed_partitions

        except Exception:
            print_error()
            print("Are you in a Control Node?")
            sys.exit(1)


class NIHReporter:
    # if we use --nih as an argument we query NIH Reporter
    # for metadata

    def __init__(self, verbose=False, active=False, years=None):
        '''Initialize NIHReporter object'''
        self.verbose = verbose
        self.active = active
        self.years = years
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.exclude_fields = ['Terms', 'AbstractText',
                               'PhrText']  # pref_terms still included
        self.grants = []

    def search_full(self, searchstr):
        '''Search NIH Reporter for metadata using a search string'''
        searchstr = self._clean_string(searchstr)
        if not searchstr:
            return []

        # Search by PI
        if not self._is_number(searchstr):

            print('PI search ...')
            criteria = {"pi_names": [{"any_name": searchstr}]}
            self._post_request(criteria)
            print('* # Grants:', len(self.grants))

        if not self.grants:
            # Search by Project
            print('Project search ...')
            criteria = {'project_nums': [searchstr]}
            self._post_request(criteria)
            print('* # Grants:', len(self.grants))

        if not self.grants and not self._is_number(searchstr):
            # Search by Organizations
            print('Org search ...')
            criteria = {'org_names': [searchstr]}
            self._post_request(criteria)
            print('* # Grants:', len(self.grants))

        # Search by text in  "projecttitle", "terms", and "abstracttext"
        print('Text search ...')
        criteria = {'advanced_text_search':
                    {'operator': 'and', 'search_field': 'all',
                     'search_text': searchstr}
                    }
        self._post_request(criteria)
        print('* # Grants:', len(self.grants))

        return self._result_sets(True)

    def search_one(self, criteria, header=False):
        '''Search NIH Reporter for metadata using a criteria'''
        try:
            searchstr = self._clean_string(searchstr)
            self._post_request(criteria)
            return self._result_sets(header)

        except Exception:
            print_error()

    def _is_number(self, string):
        '''Check if a string is a number'''
        try:
            float(string)
            return True
        except ValueError:
            return False

    def _clean_string(self, mystring):
        '''Clean a string'''

        mychars = ",:?'$^%&*!`~+={}\\[]"+'"'
        for i in mychars:
            mystring = mystring.replace(i, ' ')
            # print('mystring:', mystring)
        return mystring

    def _post_request(self, criteria):
        '''Make a POST request to NIH Reporter'''

        # make request with retries
        offset = 0
        timeout = 30
        limit = 250
        max = 250
        max_retries = 5
        retry_delay = 1
        retry_count = 0
        total = max
        # for retry_count in range(max_retries):
        try:
            while offset < max:
                params = {'offset': offset, 'limit': limit, 'criteria': criteria,
                          'exclude_fields': self.exclude_fields}
                # make request
                print('Params:', params)
                response = requests.post(
                    self.url, json=params, timeout=timeout)
                # check status code - else return data
                if response.status_code >= 400 and response.status_code < 500:
                    print(f"Bad request: {response.text}")
                    if retry_count < max_retries - 1:
                        print(f"Retrying after {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_count += 1
                    else:
                        # raise Exception(f"Failed to complete POST request after {max_retries} attempts")
                        print(
                            f"Failed to complete POST request after {max_retries} attempts")
                        return False
                else:
                    json = response.json()
                    total = json['meta']['total']
                    if total == 0:
                        if self.verbose:
                            print("No records for criteria '{}'".format(criteria))
                        return
                    if total < max:
                        max = total
                    if self.verbose:
                        print("Found {0} records for criteria '{1}'".format(
                            total, criteria))
                    self.grants += [g for g in json['results']]
                    if self.verbose:
                        print("{0} records off {1} total returned ...".format(
                            offset, total), file=sys.stderr)
                    offset += limit
                    if offset == 15000:
                        offset == 14999
                    elif offset > 15000:
                        return
        except requests.exceptions.RequestException as e:
            print(f"POST request failed: {e}")
            if retry_count < max_retries - 1:
                print(f"Retrying after {retry_delay} seconds...")
                retry_count += 1
                time.sleep(retry_delay)
            else:
                return
        except Exception:
            print_error()
            return

    def _result_sets(self, header=False):
        '''Get the result sets'''

        try:
            sets = []
            if header:
                sets.append(('project_num', 'start', 'end', 'contact_pi_name', 'project_title',
                            'org_name', 'project_detail_url', 'pi_profile_id'))
            grants = {}
            for g in self.grants:
                # print(json.dumps(g, indent=2))
                # return
                core_project_num = str(g.get('core_project_num', '')).strip()
                line = (
                    core_project_num,
                    str(g.get('project_start_date', '')).strip()[:10],
                    str(g.get('project_end_date', '')).strip()[:10],
                    str(g.get('contact_pi_name', '')).strip(),
                    str(g.get('project_title', '')).strip()  # [:50]
                )
                org = ""
                if g['organization']['org_name']:
                    org = g['organization']['org_name']
                line += (
                    str(org.encode('utf-8'), 'utf-8'),
                    g.get('project_detail_url', '')
                )
                for p in g['principal_investigators']:
                    if p.get('is_contact_pi', False):
                        line += (str(p.get('profile_id', '')),)
                if not core_project_num in grants:
                    grants[core_project_num] = line
            for g in grants.values():
                sets.append(g)
            return sets

        except Exception:
            print_error()
            return []


class Commands:

    def __init__(self):
        '''Initialize Commands object'''

        # parse arguments using python's internal module argparse.py
        self.parser = self.parse_arguments()
        self.args = self.parser.parse_args()

        # TODO: OHSU-96: To be changed for a logger
        if self.args.debug:
            os.environ['DEBUG'] = '1'

    def print_help(self):
        '''Print help message'''
        self.parser.print_help()

    def print_version(self):
        '''Print froster version'''
        print(
            f'froster v{pkg_resources.get_distribution("froster").version}')
        
    def print_info(self):
        '''Print froster info'''

        print(
            f'froster v{pkg_resources.get_distribution("froster").version}\n')
        print(f'Tools version:')
        print(f'    python v{platform.python_version()}')
        print('    pwalk ', 'v'+subprocess.run([os.path.join(sys.prefix, 'bin', 'pwalk'), '--version'],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stderr.split('\n')[0].split()[2])
        print('   ', subprocess.run([os.path.join(sys.prefix, 'bin', 'rclone'), '--version'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.split('\n')[0])

        print(textwrap.dedent(f'''
            Authors:
                Written by Dirk Petersen and Hpc Now Consulting SL

            Repository:
                https://github.com/dirkpetersen/froster


            Copyright (C) 2024 Oregon Health & Science University (OSHU)

            Licensed under the Apache License, Version 2.0 (the "License");
            you may not use this file except in compliance with the License.
            You may obtain a copy of the License at

                http://www.apache.org/licenses/LICENSE-2.0

            Unless required by applicable law or agreed to in writing, software
            distributed under the License is distributed on an "AS IS" BASIS,
            WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
            See the License for the specific language governing permissions and
            limitations under the License.
            '''))

    def subcmd_config(self, cfg: ConfigManager, aws: AWSBoto):
        '''Configure Froster settings.'''

        try:
            if self.args.user:
                return cfg.set_user()

            if self.args.aws:
                return cfg.set_aws(aws)

            if self.args.shared:
                return cfg.set_shared()

            if self.args.nih:
                return cfg.set_nih()

            if self.args.s3:
                return cfg.set_s3(aws)

            if self.args.slurm:
                return cfg.set_slurm(self.args)

            if self.args.print:
                return cfg.print_config()

            if self.args.monitor:
                froster_binary = os.path.join(cfg.bin_dir, 'froster')
                return cfg.add_systemd_cron_job(
                    f'{froster_binary} restore --monitor', '30')

            print(f'\n*****************************')
            print(f'*** FROSTER CONFIGURATION ***')
            print(f'*****************************\n')

            # Check if the configuration file exists and ask for overwrite
            if os.path.exists(cfg.config_file):
                print(
                    f'WARNING: You are about to overwrite {cfg.config_file}\n')
                is_overwrite = inquirer.confirm(
                    message=f"Do you want to continue?", default=False)

                if is_overwrite:
                    os.remove(cfg.config_file)
                else:
                    return True

            if not cfg.set_user():
                return False

            if not cfg.set_aws(aws):
                return False

            if not cfg.set_shared():
                return False

            # If shared configuration and shared_config.ini file exists, then use it
            if cfg.is_shared:
                if hasattr(cfg, 'shared_config_file') and os.path.exists(cfg.shared_config_file):

                    print(f'\n**********************************')
                    print(f'*** FROSTER CONFIGURATION DONE ***')
                    print(f'**********************************\n')

                    print(textwrap.dedent(f'''
                        Local configuration: {cfg.config_file}
                        Shared configuration: {cfg.shared_config_file}

                        You can overwrite specific configuration sections. Check options using the command:
                            froster config --help
                        '''))
                    return True

            if not cfg.set_nih():
                return False

            if not cfg.set_s3(aws):
                return False

            if not cfg.set_slurm(self.args):
                return False

            print(f'\n**********************************')
            print(f'*** FROSTER CONFIGURATION DONE ***')
            print(f'**********************************\n')

            print(f'\nYou can print the current configuration using the command:')
            print(f'    froster config --print\n')

            return True
        except Exception:
            print_error()
            return False

    def subcmd_index(self, cfg: ConfigManager, arch: Archiver):
        '''Index folders for Froster.'''

        try:
            # Check if user provided at least one argument
            if not self.args.folders:
                print(
                    '\nError: Folder not provided. Check the index command usage with "froster index --help"\n')
                sys.exit(1)

            # Check if the provided pwalk copy folder exists
            if self.args.pwalkcopy and not os.path.isdir(self.args.pwalkcopy):
                print(
                    f'\nError: Folder "{self.args.pwalkcopy}" does not exist.\n')
                sys.exit(1)

            # Check if all the provided folders exist
            for folder in self.args.folders:
                if not os.path.isdir(folder):
                    print(f'\nError: The folder {folder} does not exist.\n')
                    sys.exit(1)

            # Index the given folders
            arch.index(self.args.folders)
        except Exception:
            print_error()

    def subcmd_archive(self, arch: Archiver, aws: AWSBoto):
        '''Check command for archiving folders for Froster.'''

        try:

            if self.args.older > 0 and self.args.newer > 0:
                print(
                    '\nError: Cannot use both --older and --newer flags together.\n', file=sys.stderr)
                sys.exit(1)

            # Check if the user provided the permissions argument
            if self.args.permissions:
                if not self.args.folders:
                    print(
                        '\nError: Folder not provided. Check the archive command usage with "froster archive --help"\n', file=sys.stderr)
                    sys.exit(1)

                # Print the permissions of the provided folders
                arch.print_paths_rw_info(self.args.folder)
                return

            # Check if the user provided the reset argument
            if self.args.reset:
                for folder in self.args.folders:
                    arch.reset_folder(folder, self.args.recursive)
                return

            if not aws.check_session():
                print_error('Invalid credentials. Set new AWS credentials by running "froster config --aws"')
                sys.exit(1)

            # Check if the user provided the hotspots argument
            if self.args.hotspots:
                if self.args.folders:
                    print('\nError: Incorrect "froster archive" usage. Choose between:')
                    print('    Using --hotspots flag to select hotspots')
                    print('    Provide folder(s) to archive\n')
                    sys.exit(1)

                else:
                    arch.archive_select_hotspots()
            else:
                if not self.args.folders:
                    print(
                        '\nError: Folder not provided. Check the archive command usage with "froster archive --help"\n')
                    sys.exit(1)

                else:
                    # Archive the given folders
                    arch.archive(self.args.folders)
        except Exception:
            print_error()

    def subcmd_restore(self, arch: Archiver, aws: AWSBoto):
        '''Check command for restoring folders for Froster.'''

        try:
            if not aws.check_session():
                print_error(
                    'Invalid credentials. Set new AWS credentials by running "froster config --aws"')
                sys.exit(1)

            if self.args.monitor:
                # aws inactivity and cost monitoring
                aws.monitor_ec2()
                return

            if not self.args.folders:

                # Get the list of folders from the archive
                files = arch.archive_json_get_csv(
                    ['local_folder', 's3_storage_class', 'profile', 'archive_mode'])

                if not files:
                    print("No archives available.")
                    sys.exit(0)

                app = TableArchive(files)
                retline = app.run()

                if not retline:
                    return

                if len(retline) < 2:
                    print(f'\nNo archived folders found\n')
                    return

                self.args.folders = [retline[0]]

                # Append the folder for restoring to the arguments
                sys.argv.append(self.args.folders[0])

            arch.restore(self.args.folders, aws)

        except Exception:
            print_error()

    def subcmd_delete(self, arch: Archiver, aws: AWSBoto):
        '''Check command for deleting folders for Froster.'''

        try:
            if not aws.check_session():
                print_error('Invalid credentials. Set new AWS credentials by running "froster config --aws"')
                sys.exit(1)

            if not self.args.folders:

                # Get the list of folders from the archive
                files = arch.archive_json_get_csv(
                    ['local_folder', 's3_storage_class', 'profile'])

                if not files:
                    print("No archives available.")
                    return

                app = TableArchive(files)
                retline = app.run()

                if not retline:
                    return

                if len(retline) < 2:
                    print(f'\nNo archived folders found\n')
                    return

                self.args.folders = [retline[0]]

                # Append the folder to delete to the arguments
                sys.argv.append(self.args.folders[0])

            arch.delete(self.args.folders)

        except Exception:
            print_error()

    def subcmd_mount(self, arch: Archiver, aws: AWSBoto):

        try:
            if not aws.check_session():
                print_error(
                    'Invalid credentials. Set new AWS credentials by running "froster config --aws"')
                sys.exit(1)

            if self.args.list:
                arch.print_current_mounts()
                return

            if self.args.mountpoint:
                if not os.path.isdir(self.args.mountpoint):
                    print(
                        f'\nError: Folder "{self.args.mountpoint}" does not exist.\n')
                    sys.exit(1)

                if len(self.args.folders) > 1:
                    print(
                        '\nError: Cannot mount multiple folders to a single mountpoint.')
                    print('Check the mount command usage with "froster mount --help"\n')
                    sys.exit(1)

            if not self.args.folders:
                # Get the list of folders from the archive
                files = arch.archive_json_get_csv(
                    ['local_folder', 's3_storage_class', 'profile', 'archive_mode'])

                if not files:
                    print("\nNo archives available.\n")
                    return

                app = TableArchive(files)
                retline = app.run()

                if not retline:
                    return False
                if len(retline) < 2:
                    print(f'\nNo archived folders found\n')
                    sys.exit(0)

                self.args.folders = [retline[0]]

            # TODO: Mount in AWS EC2 instance
            # if self.args.aws:
            #     cfg.create_ec2_instance()
            #     return True

            arch.mount(folders=self.args.folders,
                       mountpoint=self.args.mountpoint)

        except Exception:
            print_error()

    def subcmd_umount(self, arch: Archiver):
        '''Unmount a folder from the system.'''

        try:
            if self.args.list:
                arch.print_current_mounts()
                sys.exit(0)

            # Get current mounts
            mounts = arch.get_mounts()
            if len(mounts) == 0:
                print("\nNOTE: No rclone mounts on this computer.\n")
                sys.exit(0)

            if not self.args.folders:
                # No folders provided, manually select folder to unmount
                files = "\n".join(mounts)
                files = "Mountpoint\n" + files

                app = TableArchive(files)
                retline = app.run()

                self.args.folders = [retline[0]]

            arch.unmount(self.args.folders)

        except Exception:
            print_error()

    def subcmd_ssh(self, cfg: ConfigManager, aws: AWSBoto):
        '''SSH into an AWS EC2 instance'''

        ilist = aws.ec2_list_instances('Name', 'FrosterSelfDestruct')
        ips = [sublist[0] for sublist in ilist if sublist]
        if self.args.list:
            if ips:
                print("Running AWS EC2 Instances:")
                for row in ilist:
                    print(' - '.join(row))
            else:
                print('No running instances detected')
            return True
        if self.args.terminate:
            aws.ec2_terminate_instance(self.args.terminate)
            return True
        if self.args.sshargs:
            if ':' in self.args.sshargs[0]:
                myhost, remote_path = self.args.sshargs[0].split(':')
            else:
                myhost = self.args.sshargs[0]
                remote_path = ''
        else:
            myhost = cfg.ec2_last_instance
        if ips and not myhost in ips:
            print(f'{myhost} is no longer running, replacing with {ips[-1]}')
            myhost = ips[-1]
        if self.args.subcmd == 'ssh':
            print(f'Connecting to {myhost} ...')
            aws.ssh_execute('ec2-user', myhost)
            return True
        elif self.args.subcmd == 'scp':
            if len(self.args.sshargs) != 2:
                print('The "scp" sub command supports currently 2 arguments')
                return False
            hostloc = next((i for i, item in enumerate(
                self.args.sshargs) if ":" in item), None)
            if hostloc == 0:
                # the hostname is in the first argument: download
                host, remote_path = self.args.sshargs[0].split(':')
                ret = aws.ssh_download(
                    'ec2-user', host, remote_path, self.args.sshargs[1])
            elif hostloc == 1:
                # the hostname is in the second argument: uploaad
                host, remote_path = self.args.sshargs[1].split(':')
                ret = aws.ssh_upload(
                    'ec2-user', host, self.args.sshargs[0], remote_path)
            else:
                print('The "scp" sub command supports currently 2 arguments')
                return False
            print(ret.stdout, ret.stderr)

    def subcmd_credentials(self, cfg: ConfigManager, aws: AWSBoto):
        '''Check AWS credentials'''

        print("\nChecking AWS credentials...")

        if aws.check_credentials(aws_profile=cfg.aws_profile):
            print('    ...AWS credentials are valid\n')
            return True
        else:
            print('    ...AWS credentials are NOT valid\n')
            return False

    def subcmd_update(self, mute_no_update):
        '''Check if an update is available'''
        try:

            cmd = "curl -s https://api.github.com/repos/hpcnow/froster/releases"

            result = subprocess.run(cmd, shell=True, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                print(
                    f"Error checking if froster update available. Command run: {cmd}: {result.stderr.strip()}")
                return False

            def compare_versions(version1, version2):
                v1 = [int(v) for v in version1.split(".")]
                v2 = [int(v) for v in version2.split(".")]

                for i in range(max(len(v1), len(v2))):
                    v1_part = v1[i] if i < len(v1) else 0
                    v2_part = v2[i] if i < len(v2) else 0
                    if v1_part != v2_part:
                        return v1_part - v2_part
                return 0

            releases = json.loads(result.stdout)
            if not releases:
                print('Note: Could not check for updates')
                return

            latest = releases[0]['tag_name'].replace('v', '')
            current = pkg_resources.get_distribution("froster").version

            if compare_versions(latest, current) > 0:
                print(f'\nA froster update is available: froster v{latest}')
                print(f'\nYou can update froster using the command:')
                print(
                    f'    curl -s https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh?$(date +%s) | bash\n')
            else:
                if not mute_no_update:
                    print(f'\nFroster is up to date: froster v{current}\n')

        except Exception:
            print_error()

    def parse_arguments(self):
        '''Gather and parse command-line arguments'''

        parser = argparse.ArgumentParser(prog='froster ',
                                         description='A (mostly) automated tool for archiving large scale data ' +
                                         'after finding folders in the file system that are worth archiving.')

        # ***

        parser.add_argument('-c', '--cores', dest='cores', type=int, default=4,
                            help='Number of cores to be allocated for the machine. (default=4)')
        
        parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                            help="verbose output for all commands")
        
        parser.add_argument('-i', '--info', dest='info', action='store_true',
                    help='print froster and packages info')

        parser.add_argument('-m', '--mem', dest='memory', type=int, default=64,
                            help='Amount of memory to be allocated for the machine in GB. (default=64)')
        
        parser.add_argument('-n', '--no-slurm', dest='noslurm', action='store_true',
                            help="do not submit a Slurm job, execute in the foreground. ")
        
        parser.add_argument('-p', '--profile', dest='aws_profile', action='store_true', default='',
                            help='which AWS profile in ~/.aws/ should be used. default="aws"')

        parser.add_argument('-v', '--version', dest='version', action='store_true',
                            help='print froster version')

        subparsers = parser.add_subparsers(
            dest="subcmd", help='sub-command help')

        # ***

        parser_credentials = subparsers.add_parser('credentials', aliases=['crd'],
                                                   help=textwrap.dedent(f'''
                Credential manager
            '''), formatter_class=argparse.RawTextHelpFormatter)
        parser_credentials.add_argument('-c', '--check', dest='crd-check', action='store_true',
                                        help="Check if there are valid credentials on default routes.")

        # ***

        parser_config = subparsers.add_parser('config', aliases=['cnf'],
                                              help=textwrap.dedent(f'''
                Bootstrap the configurtion, install dependencies and setup your environment.
                You will need to answer a few questions about your cloud and hpc setup.
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_config.add_argument('-a', '--aws', dest='aws', action='store_true',
                                   help="Setup AWS profile")

        parser_config.add_argument('-m', '--monitor', dest='monitor', action='store_true',
                                   help='Setup froster as a monitoring cronjob ' +
                                   'on an ec2 instance and notify the user email address')

        parser_config.add_argument('-n', '--nih', dest='nih', action='store_true',
                                   help="Setup NIH reporter configuration")

        parser_config.add_argument('-p', '--print', dest='print', action='store_true',
                                   help="Print the current configuration")

        parser_config.add_argument('-3', '--s3', dest='s3', action='store_true',
                                   help="Setup s3 bucket configuration")

        parser_config.add_argument('-s', '--shared', dest='shared', action='store_true',
                                   help="Setup shared configuration")

        parser_config.add_argument('-l', '--slurm', dest='slurm', action='store_true',
                                   help="Setup slurm configuration")

        parser_config.add_argument('-u', '--user', dest='user', action='store_true',
                                   help="Setup user specific configuration")

        # ***

        parser_index = subparsers.add_parser('index', aliases=['idx'],
                                             help=textwrap.dedent(f'''
                Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file
                that lists the largest folders. As this process is compute intensive the
                index job will be automatically submitted to Slurm if the Slurm tools are
                found.
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_index.add_argument('folders', action='store', default=[],  nargs='*',
                                  help='Folders you would like to index (separated by space), ' +
                                  'using the pwalk file system crawler ')

        parser_index.add_argument('-f', '--force', dest='force', action='store_true',
                                  help="Force indexing")

        parser_index.add_argument('-y', '--pwalk-copy', dest='pwalkcopy', action='store', default='',
                                  help='Directory where the pwalk CSV file should be copied to.')

        # ***

        parser_archive = subparsers.add_parser('archive', aliases=['arc'],
                                               help=textwrap.dedent(f'''
                Select from a list of large folders, that has been created by 'froster index', and
                archive a folder to S3/Glacier. Once you select a folder the archive job will be
                automatically submitted to Slurm. You can also automate this process

            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_archive.add_argument('folders', action='store', default=[], nargs='*',
                                    help='folders you would like to archive (separated by space), ' +
                                    'the last folder in this list is the target   ')

        parser_archive.add_argument('-f', '--force', dest='force', action='store_true',
                                    help="Force archiving of a folder that contains the .froster.md5sum file")

        parser_archive.add_argument('-H', '--hotspots', dest='hotspots', action='store_true',
                                    help="Select hotspots to archive from CSV file generated by 'froster index'")

        parser_archive.add_argument('-p', '--permissions', dest='permissions', action='store_true',
                                    help="Print read and write permissions for the provided folder(s)")

        parser_archive.add_argument('-l', '--larger', dest='larger', type=int, action='store', default=0,
                                    help=textwrap.dedent(f'''
                Archive folders larger than <GiB>. This option
                works in conjunction with --older <days>. If both
                options are set froster will print a command that
                allows you to archive all matching folders at once.
            '''))
        parser_archive.add_argument('-o', '--older', dest='older', type=int, action='store', default=0,
                                    help=textwrap.dedent(f'''
                Archive folders that have not been accessed more than
                <days>. (optionally set --mtime to select folders that
                have not been modified more than <days>). This option
                works in conjunction with --larger <GiB>. If both
                options are set froster will print a command that
                allows you to archive all matching folders at once.
            '''))

        parser_archive.add_argument('--newer', '-w', dest='newer', type=int, action='store', default=0,
                                    help=textwrap.dedent(f'''
                Archive folders that have been accessed within the last 
                <days>. (optionally set --mtime to select folders that
                have not been modified more than <days>). This option
                works in conjunction with --larger <GiB>. If both 
                options are set froster will print a command that 
                allows you to archive all matching folders at once.
            '''))

        parser_archive.add_argument('-n', '--nih', dest='nih', action='store_true',
                                    help="Search and Link Metadata from NIH Reporter")

        parser_archive.add_argument('-i', '--nih-ref', dest='nihref', action='store', default='',
                                    help="Use NIH Reporter reference for the current archive")

        parser_archive.add_argument('-m', '--mtime', dest='agemtime', action='store_true',
                                    help="Use modified file time (mtime) instead of accessed time (atime)")

        parser_archive.add_argument('-r', '--recursive', dest='recursive', action='store_true',
                                    help="Archive the current folder and all sub-folders")

        parser_archive.add_argument('-s', '--reset', dest='reset', action='store_true',
                                    help=textwrap.dedent(f'''
                                                        This will not download any data, but recusively reset a folder
                                                        from previous (e.g. failed) archiving attempt.
                                                        It will delete .froster.md5sum and extract Froster.smallfiles.tar
                                                        '''))

        parser_archive.add_argument('-t', '--no-tar', dest='notar', action='store_true',
                                    help="Do not move small files to tar file before archiving")

        parser_archive.add_argument('-d', '--dry-run', dest='dryrun', action='store_true',
                                    help="Execute a test archive without actually copying the data")

        # ***

        parser_delete = subparsers.add_parser('delete', aliases=['del'],
                                              help=textwrap.dedent(f'''
                Remove data from a local filesystem folder that has been confirmed to
                be archived (through checksum verification). Use this instead of deleting manually
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_delete.add_argument('folders', action='store', default=[],  nargs='*',
                                   help='folders (separated by space) from which you would like to delete files, ' +
                                   'you can only delete files that have been archived')

        parser_delete.add_argument('-r', '--recursive', dest='recursive', action='store_true',
                                   help="Delete the current archived folder and all archived sub-folders")

        # ***

        parser_mount = subparsers.add_parser('mount', aliases=['umount'],
                                             help=textwrap.dedent(f'''
                Mount or unmount the remote S3 or Glacier storage in your local file system
                at the location of the original folder.
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_mount.add_argument('folders', action='store', default=[],  nargs='*',
                                  help='archived folders (separated by space) which you would like to mount.' +
                                  '')
        parser_mount.add_argument('-a', '--aws', dest='aws', action='store_true',
                                  help="Mount folder on new EC2 instance instead of local machine")

        parser_mount.add_argument('-l', '--list', dest='list', action='store_true',
                                  help="List all mounted folders")

        parser_mount.add_argument('-m', '--mount-point', dest='mountpoint', action='store', default='',
                                  help='pick a custom mount point, this only works if you select a single folder.')

        # ***

        parser_restore = subparsers.add_parser('restore', aliases=['rst'],
                                               help=textwrap.dedent(f'''
                Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need
                to download all data to local storage after the restore is complete.
                Just use the mount sub command.
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
                                    help='folders you would like to to restore (separated by space)')

        parser_restore.add_argument('-a', '--aws', dest='aws', action='store_true',
                                    help="Restore folder on new AWS EC2 instance instead of local machine")

        parser_restore.add_argument('-d', '--days', dest='days', action='store', default=30,
                                    help='Number of days to keep data in S3 One Zone-IA storage at $10/TiB/month (default: 30)')

        parser_restore.add_argument('-i', '--instance-type', dest='instancetype', action='store', default="",
                                    help='The EC2 instance type is auto-selected, but you can pick any other type here')

        parser_restore.add_argument('-l', '--no-download', dest='nodownload', action='store_true',
                                    help="skip download to local storage after retrieval from Glacier")

        parser_restore.add_argument('-m', '--monitor', dest='monitor', action='store_true',
                                    help="Monitor EC2 server for cost and idle time.")

        parser_restore.add_argument('-o', '--retrieve-opt', dest='retrieveopt', action='store', default='Bulk',
                                    help=textwrap.dedent(f'''
            More information at:
                https://docs.aws.amazon.com/AmazonS3/latest/userguide/restoring-objects-retrieval-options.html
                https://aws.amazon.com/es/s3/pricing/

            S3 GLACIER DEEP ARCHIVE or S3 INTELLIGET-TIERING DEEP ARCHIVE ACCESS
                Bulk:
                    - Within 48 hours retrieval            <-- default
                    - costs of $2.50 per TiB
                Standard:
                    - Within 12 hours retrieval
                    - costs of $10 per TiB
                Expedited:
                    - 9-12 hours retrieval
                    - costs of $30 per TiB
                                                         
            S3 GLACIER FLEXIBLE RETRIEVAL or S3 INTELLIGET-TIERING ARCHIVE ACCESS
                Bulk:
                    - 5-12 hours retrieval
                    - costs of $2.50 per TiB
                Standard:
                    - 3-5 hours retrieval
                    - costs of $10 per TiB
                Expedited:
                    - 1-5 minutes retrieval
                    - costs of $30 per TiB

                                                         
                In addition to the retrieval cost, AWS will charge you about
                $10/TiB/month for the duration you keep the data in S3.
                (Costs in Summer 2023)
                '''))

        parser_restore.add_argument('-r', '--recursive', dest='recursive', action='store_true',
                                    help="Restore the current archived folder and all archived sub-folders")

        # ***

        parser_ssh = subparsers.add_parser('ssh', aliases=['scp'],
                                           help=textwrap.dedent(f'''
                Login to an AWS EC2 instance to which data was restored with the --aws option
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_ssh.add_argument('--list', '-l', dest='list', action='store_true', default=False,
                                help="List running Froster AWS EC2 instances")

        parser_ssh.add_argument('--terminate', '-t', dest='terminate', action='store', default='',
                                metavar='<hostname>', help='Terminate AWS EC2 instance with this public IP Address.')

        parser_ssh.add_argument('sshargs', action='store', default=[], nargs='*',
                                help='multiple arguments to ssh/scp such as hostname or user@hostname oder folder' +
                                '')

        # ***

        parser_update = subparsers.add_parser('update', aliases=['upd'],
                                              help=textwrap.dedent(f'''
                Update froster to the latest version
            '''), formatter_class=argparse.RawTextHelpFormatter)

        parser_update.add_argument('--rclone', '-r', dest='rclone', action='store_true',
                                   help="Update rclone to latests version")

        return parser


def printdbg(*args, **kwargs):
    if os.environ.get('DEBUG') == '1':
        current_frame = inspect.currentframe()
        calling_function = current_frame.f_back.f_code.co_name
        print(f' DBG {calling_function}():', args, kwargs)


def clean_path(path):
    try:
        if path:
            return os.path.realpath(os.path.expanduser(path).rstrip(os.path.sep))
        else:
            return path

    except Exception:
        print_error()
        sys.exit(1)


def clean_path_list(paths):
    '''Clean paths by expanding user and symlinks, and removing trailing slashes.'''

    if not paths:
        return []

    cleaned_paths = []

    for path in paths:
        try:
            # Expand user and symlinks, and remove trailing slashes only if path is not empty
            if path:
                # Split the path into its components
                cleaned_paths.append(clean_path(path))

        except Exception:
            print_error()
            sys.exit(1)

    return cleaned_paths


def is_slurm_installed():
    if shutil.which('sbatch'):
        return True
    else:
        return False


def is_inside_slurm_job():
    if os.getenv('SLURM_JOB_ID'):
        return True
    else:
        return False


def use_slurm(noslurm_flag):
    return is_slurm_installed() and not noslurm_flag and not is_inside_slurm_job()

def get_caller_line():
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    line_number = caller_frame.f_lineno
    return line_number

def get_caller_function():
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_name = caller_frame.f_code.co_name
    return caller_name

def print_error(msg: str = None):
    exc_type, exc_value, exc_tb = sys.exc_info()

    if exc_tb is None:
        # Printing error message but no error raised from the code
        function_name = get_caller_function()
        line = get_caller_line()
        file_name = os.path.split(__file__)[1]
        error_code = 1
    else:
        # Get the traceback details
        traceback_details = traceback.extract_tb(exc_tb)

        # Get the last call stack. The third element in the tuple is the function name
        function_name = traceback_details[-1][2]
        
        # Get the filename
        file_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

        # Get the line number
        line = exc_tb.tb_lineno

        # Get the error code
        error_code = exc_value

    # Check if the exception is a KeyboardInterrupt
    if exc_type is KeyboardInterrupt:
        print(f'\nKeyboard Interrupt\n')

    elif exc_type is SystemExit:
        pass

    else:
        print('\nError')
        print('  File:', file_name, file=sys.stderr)
        print('  Function:', function_name, file=sys.stderr)
        print('  Line:', line, file=sys.stderr)
        print('  Error code:', error_code, file=sys.stderr)
        if (msg):
            print('  Error message:', msg, file=sys.stderr)

        print('\nIf you thing this is a bug, please report this to froster developers at: https://github.com/dirkpetersen/froster/issues \n', file=sys.stderr)


def main():

    if not sys.platform.startswith('linux'):
        print('Froster currently only runs on Linux x64\n')
        sys.exit(1)

    try:

        # Declaring variables
        TABLECSV = ''  # CSV string for DataTable
        SELECTEDFILE = ''  # CSV filename to open in hotspots
        MAXHOTSPOTS = 0

        # Init Commands class
        cmd = Commands()

        # Get the args
        args = cmd.args

        # Init Config Manager class
        cfg = ConfigManager()

        # Init Archiver class
        arch = Archiver(args, cfg)

        # Init AWS Boto class
        aws = AWSBoto(args, cfg, arch)

        # Print current version of froster
        if args.version:
            cmd.print_version()
            return
        
        if args.info:
            cmd.print_info()
            return

        if cfg.is_shared and cfg.shared_dir:
            cfg.assure_permissions_and_group(cfg.shared_dir)

        # Do not allow other commands rather than config if the configuration is not set
        if not cfg.configuration_done and args.subcmd not in ['config', 'cnf']:
            print('\nWARNING: Froster is not full configured yet:')
            print(f'  user: {"done" if cfg.user_init else "pending"}')
            print(f'  aws: {"done" if cfg.aws_init else "pending"}')
            print(f'  s3: {"done" if cfg.s3_init else "pending"}')
            print(f'  nih: {"done" if cfg.nih_init else "pending"}')
            print(f'\nRun "froster config --help" for more information.\n')
            return

        # call a function for each sub command in our CLI
        if args.subcmd in ['config', 'cnf']:
            cmd.subcmd_config(cfg, aws)
        elif args.subcmd in ['index', 'ind']:
            cmd.subcmd_index(cfg, arch)
        elif args.subcmd in ['archive', 'arc']:
            cmd.subcmd_archive(arch, aws)
        elif args.subcmd in ['restore', 'rst']:
            cmd.subcmd_restore(arch, aws)
        elif args.subcmd in ['delete', 'del']:
            cmd.subcmd_delete(arch, aws)
        elif args.subcmd in ['mount', 'mnt']:
            cmd.subcmd_mount(arch, aws)
        elif args.subcmd in ['umount']:
            cmd.subcmd_umount(arch, aws)
        elif args.subcmd in ['ssh', 'scp']:
            cmd.subcmd_ssh(cfg, aws)
        elif args.subcmd in ['credentials', 'crd']:
            cmd.subcmd_credentials(cfg, aws)
        elif args.subcmd in ['update', 'upd']:
            cmd.subcmd_update(mute_no_update=False)
        else:
            cmd.print_help()

        # Check if there are updates on froster every X days
        if cfg.check_update() and args.subcmd not in ['update', 'upd']:
            cmd.subcmd_update(mute_no_update=True)

        # Close the AWS session
        aws.close_session()

    except Exception:
        print_error()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print_error()
        sys.exit(1)