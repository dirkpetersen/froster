#! /usr/bin/env python3

"""
Froster automates much of the challenging tasks when 
archiving many Terabytes of data on large (HPC) systems.
"""

# internal modules
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
import zipfile
import textwrap
import tarfile
import time
import platform
import concurrent.futures
import hashlib
import fnmatch
import io
import math
import signal
import shlex
import glob
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

# stuff from pypi
import requests
import duckdb
import boto3
import botocore
import psutil
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Input, LoadingIndicator
from textual.widgets import DataTable, Footer, Button

__app__ = 'Froster, a user friendly S3/Glacier archiving tool'
__version__ = '0.9.0.70'


def main():

    if args.debug:
        pass

    if len(sys.argv) == 1:
        print(textwrap.dedent(f'''\n
            For example, use one of these commands:
              froster config 
              froster index /your/lab/root
              froster archive
            or you can use one of these: 
              'froster delete', 'froster mount' or 'froster restore'
            '''))

    # Instantiate classes required by all functions
    cfg = ConfigManager(args)
    arch = Archiver(args, cfg)
    aws = AWSBoto(args, cfg, arch)

    if args.version:
        args_version()
        return True

    if args.subcmd in ['archive', 'delete', 'restore']:
        # remove folders that are not writable from args.folders
        errfld = []
        for fld in args.folders:
            ret = arch.test_write(fld)
            if ret == 13 or ret == 2:
                errfld.append(fld)
        if errfld:
            errflds = '" \n"'.join(errfld)
            print(
                f'\nERROR: These folder(s) \n"{errflds}"\n must exist and you need write access to them.')
            return False

    # call a function for each sub command in our CLI
    if args.subcmd in ['config', 'cnf']:
        subcmd_config(args, cfg, aws)
    elif args.subcmd in ['index', 'ind']:
        subcmd_index(args, cfg, arch)
    elif args.subcmd in ['archive', 'arc']:
        subcmd_archive(args, cfg, arch, aws)
    elif args.subcmd in ['restore', 'rst']:
        subcmd_restore(args, cfg, arch, aws)
    elif args.subcmd in ['delete', 'del']:
        subcmd_delete(args, cfg, arch, aws)
    elif args.subcmd in ['mount', 'mnt']:
        subcmd_mount(args, cfg, arch, aws)
    elif args.subcmd in ['umount']:  # or args.unmount:
        subcmd_umount(args, cfg)
    elif args.subcmd in ['ssh', 'scp']:  # or args.unmount:
        subcmd_ssh(args, cfg, aws)


def args_version():

    print(f'froster version {__version__}\n')
    print(f'Packages version:')
    print(f'    python v{platform.python_version()}')

    print(f'''
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
''')

    # TODO: make a froster --info function with these old lines
    # print(f'Froster version: {__version__}')
    # print(f'  The Script: {os.path.abspath(__file__)}')
    # print(f'  Config dir: {cfg.config_root.replace("/.config/froster","")}')
    # print(f'  Profs .aws: {", ".join(cfg.get_aws_profiles())}')
    # print(f'Python version:\n{sys.version}')
    # try:
    #     print('* Pwalk ----- ')
    #     print('  Binary:', shutil.which('pwalk'))
    #     print('  Version:', subprocess.run([os.path.join(cfg.binfolderx, 'pwalk'), '--version'],
    #             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stderr.split('\n')[0])
    #     print('* Rclone ---- ')
    #     print('  Binary:', shutil.which('rclone'))
    #     print('  Version:', subprocess.run([os.path.join(cfg.binfolderx, 'rclone'), '--version'],
    #             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.split('\n')[0])
    # except FileNotFoundError as e:
    #     print(f'Error: {e}')
    #     return False
    # return True


def subcmd_config(args, cfg, aws):
    # configure user and / or team settings
    # arguments are Class instances passed from main

    cfg.fix_tree_permissions(cfg.config_root)

    if args.cfgfolder:
        binfolder = os.path.join(
            args.cfgfolder, '.config', 'froster', 'general', 'binfolder')
        if os.path.exists(binfolder):
            theroot = os.path.join(args.cfgfolder, '.config', 'froster')
            config_root_file = os.path.join(
                cfg.config_root_local, 'config_root')
            with open(config_root_file, 'w') as myfile:
                myfile.write(theroot)
            cfg.config_root = theroot
            print(
                f'  Config folder set to {cfg.config_root}, please restart froster without config folder argument.')
            return True

    first_time = True
    binfolder = cfg.binfolder
    if not cfg.binfolder:
        cfg.binfolder = '~/.local/bin'
        cfg.binfolderx = os.path.expanduser(cfg.binfolder)
        if not os.path.exists(cfg.binfolderx):
            os.makedirs(cfg.binfolderx, mode=0o775)
    else:
        if cfg.binfolder.startswith(cfg.home_dir):
            cfg.binfolder = cfg.binfolder.replace(cfg.home_dir, '~')
        cfg.binfolderx = os.path.expanduser(cfg.binfolder)
        first_time = False
    if binfolder != cfg.binfolder:
        cfg.write('general', 'binfolder', cfg.binfolder)

    # Basic setup, focus the indexer on larger folders and file sizes
    if not cfg.read('general', 'max_small_file_size_kib'):
        cfg.write('general', 'max_small_file_size_kib', '1024')
    if not cfg.read('general', 'min_index_folder_size_gib'):
        cfg.write('general', 'min_index_folder_size_gib', "1")
    if not cfg.read('general', 'min_index_folder_size_avg_mib'):
        cfg.write('general', 'min_index_folder_size_avg_mib', "10")
    if not cfg.read('general', 'max_hotspots_display_entries'):
        cfg.write('general', 'max_hotspots_display_entries', "5000")

    # general setup
    defdom = cfg.get_domain_name()
    whoami = cfg.whoami

    if args.monitor:
        # monitoring only setup, do not continue
        fro = os.path.join(cfg.binfolderx, 'froster')
        cfg.write('general', 'email', args.monitor)
        cfg.add_systemd_cron_job(f'{fro} restore --monitor', '30')
        return True

    if args.index:
        # only basic configuration required for indexing jobs
        return True

    print(f'\n*** Asking a few questions  ({cfg.config_root}) ***')
    print('*** For most you can just hit <Enter> to accept the default. ***\n')

    # determine if we need to move the (shared) config to a new folder
    movecfg = False
    if first_time and args.cfgfolder == '' and cfg.config_root == cfg.config_root_local:
        if cfg.ask_yes_no(f'  Do you want to collaborate with other users on archive and restore?', 'no'):
            movecfg = True
            args.cfgfolder = cfg.prompt(
                'Enter the path to a shared config folder:')
    elif args.cfgfolder:
        movecfg = True
    if movecfg:
        if cfg.move_config(args.cfgfolder):
            print('\n  IMPORTANT: All archiving collaborators need to have consistent AWS profile names in their ~/.aws/credentials\n')
        else:
            print(f'  ERROR: Could not move config folder to {args.cfgfolder}')
            return False

    # domain-name not needed right now
    # domain = cfg.prompt('Enter your domain name:',
    #                    f'{defdom}|general|domain','string')
    emailaddr = cfg.prompt('Enter your email address:',
                           f'{whoami}@{defdom}|general|email', 'string')
    emailstr = emailaddr.replace('@', '-')
    emailstr = emailstr.replace('.', '-')

    do_prompt = cfg.read('general', 'prompt_nih_reporter', 'yes')
    if cfg.ask_yes_no(f'\n*** Do you want to search and link NIH life sciences grants with your archives?', do_prompt):
        cfg.write('general', 'prompt_nih_reporter', 'yes')
    else:
        cfg.write('general', 'prompt_nih_reporter', 'no')

    print("")

    # cloud setup
    bucket = cfg.prompt('Please confirm/edit S3 bucket name to be created in all used profiles.',
                        f'froster-{emailstr}|general|bucket', 'string')
    archiveroot = cfg.prompt('Please confirm/edit the archive root path inside your S3 bucket',
                             'archive|general|archiveroot', 'string')

    cls = cfg.read('general', 's3_storage_class')
    s3_storage_class = cfg.prompt(f'Please confirm/edit the AWS S3 Storage class ({cls})',
                                  'DEEP_ARCHIVE,GLACIER,INTELLIGENT_TIERING|general|s3_storage_class', 'string')
    cfg.write('general', 's3_storage_class', s3_storage_class)

    cfg.create_aws_configs()
    # if there is a shared ~/.aws/config copy it over
    if cfg.config_root_local != cfg.config_root:
        cfg.replicate_ini('ALL', cfg.awsconfigfileshr, cfg.awsconfigfile)

    aws_region = cfg.get_aws_region('aws')
    if not aws_region:
        aws_region = cfg.get_aws_region()

    if not aws_region:
        aws_region = cfg.prompt('Please select AWS S3 region (e.g. us-west-2 for Oregon)',
                                aws.get_aws_regions())
    aws_region = cfg.prompt(
        'Please confirm/edit the AWS S3 region', aws_region)

    # cfg.create_aws_configs(None, None, aws_region)
    print(f"\n  Verify that bucket '{bucket}' is configured ... ")

    # for accessing glacier use one of these
    allowed_aws_profiles = ['default', 'aws', 'AWS']
    profmsg = 1
    profs = cfg.get_aws_profiles()

    for prof in profs:
        if prof in allowed_aws_profiles:
            cfg.set_aws_config(prof, 'region', aws_region)
            if prof == 'AWS' or prof == 'aws':
                cfg.write('general', 'aws_profile', prof)
            elif prof == 'default':
                cfg.write('general', 'aws_profile', 'default')
            aws.create_s3_bucket(bucket, prof)

    for prof in profs:
        if prof in allowed_aws_profiles:
            continue
        if profmsg == 1:
            print(
                '\nFound additional profiles in ~/.aws and need to ask a few more questions.\n')
            profmsg = 0
        if not cfg.ask_yes_no(f'Do you want to configure profile "{prof}"?', 'yes'):
            continue
        profile = {'name': '', 'provider': '', 'storage_class': ''}
        pendpoint = ''
        pregion = ''
        pr = cfg.read('profiles', prof)
        if isinstance(pr, dict):
            profile = cfg.read('profiles', prof)
        profile['name'] = prof

        if not profile['provider']:
            profile['provider'] = ['AWS', 'GCS', 'Wasabi',
                                   'IDrive', 'Ceph', 'Minio', 'Other']
        profile['provider'] = \
            cfg.prompt(
                f'S3 Provider for profile "{prof}"', profile['provider'])

        pregion = cfg.get_aws_region(prof)
        if not pregion:
            pregion = cfg.prompt('Please select the S3 region',
                                 aws.get_aws_regions(prof, profile['provider']))
        pregion = \
            cfg.prompt(f'Confirm/edit S3 region for profile "{prof}"', pregion)
        if pregion:
            cfg.set_aws_config(prof, 'region', pregion)

        if profile['provider'] != 'AWS':
            if not pendpoint:
                pendpoint = cfg.get_aws_s3_endpoint_url(prof)
                if not pendpoint:
                    if 'Wasabi' == profile['provider']:
                        pendpoint = f'https://s3.{pregion}.wasabisys.com'
                    elif 'GCS' == profile['provider']:
                        pendpoint = 'https://storage.googleapis.com'

            pendpoint = \
                cfg.prompt(
                    f'S3 Endpoint for profile "{prof}" (e.g https://s3.domain.com)', pendpoint)
            if pendpoint:
                if not pendpoint.startswith('http'):
                    pendpoint = 'https://' + pendpoint
                cfg.set_aws_config(prof, 'endpoint_url', pendpoint, 's3')

        if not profile['storage_class']:
            if profile['provider'] == 'AWS':
                profile['storage_class'] = s3_storage_class
            else:
                profile['storage_class'] = 'STANDARD'

        if profile['provider']:
            cfg.write('profiles', prof, profile)
        else:
            print(f'\nConfig for AWS profile "{prof}" was not saved.')

        aws.create_s3_bucket(bucket, prof)

    if shutil.which('scontrol') and shutil.which('sacctmgr'):
        se = SlurmEssentials(args, cfg)
        parts = se.get_allowed_partitions_and_qos()
        print('')

        slurm_walltime = cfg.read('hpc', 'slurm_walltime', '7-0')
        slurm_walltime = cfg.prompt(
            f'Please confirm or set the Slurm --time (wall time as days-hours) for froster jobs', slurm_walltime)
        cfg.write('hpc', 'slurm_walltime', slurm_walltime)
        if '-' in slurm_walltime:
            days, hours = slurm_walltime.split('-')
        else:
            days = 0
            hours = slurm_walltime

        mydef = cfg.read('hpc', 'slurm_partition')
        if mydef:
            mydef = f' (now: {mydef})'
        slurm_partition = cfg.prompt(f'Please select the Slurm partition for jobs that last up to {days} days and {hours} hours.{mydef}',
                                     list(parts.keys()))
        cfg.write('hpc', 'slurm_partition', slurm_partition)
        # slurm_partition =  cfg.prompt('Please confirm the Slurm partition', slurm_partition)
        print('')

        mydef = cfg.read('hpc', 'slurm_qos')
        if mydef:
            mydef = f' (now: {mydef})'
        slurm_qos = cfg.prompt(f'Please select the Slurm QOS for jobs that last up to {days} days and {hours} days.{mydef}',
                               parts[slurm_partition])
        cfg.write('hpc', 'slurm_qos', slurm_qos)
        # slurm_qos =  cfg.prompt('Please confirm the Slurm QOS', slurm_qos)
        print('')

    if shutil.which('sbatch'):
        print('\n*** And finally a few questions how your HPC uses local scratch space ***')
        print('*** This config is optional and you can hit ctrl+c to cancel any time ***')
        print('*** If you skip this, froster will use HPC /tmp which may have limited disk space  ***\n')

        # setup local scratch spaces, the defauls are OHSU specific
        x = cfg.prompt('How do you request local scratch from Slurm?',
                       '--gres disk:1024|hpc|slurm_lscratch', 'string')  # get 1TB scratch space
        x = cfg.prompt('Is there a user script that provisions local scratch?',
                       'mkdir-scratch.sh|hpc|lscratch_mkdir', 'string')  # optional
        x = cfg.prompt('Is there a user script that tears down local scratch at the end?',
                       'rmdir-scratch.sh|hpc|lscratch_rmdir', 'string')  # optional
        x = cfg.prompt('What is the local scratch root ?',
                       '/mnt/scratch|hpc|lscratch_root', 'string')  # add slurm jobid at the end

    print(f'\nChecked permissions in {cfg.config_root}')
    cfg.fix_tree_permissions(cfg.config_root)

    print('\nDone!\n')


def subcmd_index(args, cfg, arch):

    cfg.printdbg(" Command line:", args.cores, args.noslurm,
                 args.pwalkcsv, args.folders, flush=True)

    if not args.folders:
        print('you must point to at least one folder in your command line')
        return False
    args.folders = cfg.replace_symlinks_with_realpaths(args.folders)
    if args.pwalkcsv and not os.path.exists(args.pwalkcsv):
        print(f'File "{args.pwalkcsv}" does not exist.')
        return False

    for fld in args.folders:
        if not os.path.isdir(fld):
            print(f'The folder {fld} does not exist.')
            if not args.pwalkcsv:
                return False

    if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
        for fld in args.folders:
            fld = fld.rstrip(os.path.sep)
            print(f'Indexing folder {fld}, please wait ...', flush=True)
            arch.index(fld)
    else:
        se = SlurmEssentials(args, cfg)
        label = arch._get_hotspots_file(args.folders[0]).replace('.csv', '')
        label = label.replace(' ', '_')
        shortlabel = os.path.basename(args.folders[0])
        myjobname = f'froster:index:{shortlabel}'
        email = cfg.read('general', 'email')
        se.add_line(f'#SBATCH --job-name={myjobname}')
        se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
        se.add_line(f'#SBATCH --mem=64G')
        se.add_line(f'#SBATCH --output=froster-index-{label}-%J.out')
        se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')
        se.add_line(f'#SBATCH --mail-user={email}')
        se.add_line(f'#SBATCH --time={se.walltime}')
        if se.partition:
            se.add_line(f'#SBATCH --partition={se.partition}')
        if se.qos:
            se.add_line(f'#SBATCH --qos={se.qos}')
        # se.add_line(f'ml python')
        cmdline = " ".join(map(shlex.quote, sys.argv))  # original cmdline
        cmdline = cmdline.replace('/froster.py ', '/froster ')
        if args.debug:
            print(f'Command line passed to Slurm:\n{cmdline}')
        se.add_line(cmdline)
        jobid = se.sbatch()
        print(f'Submitted froster indexing job: {jobid}')
        print(f'Check Job Output:')
        print(f' tail -f froster-index-{label}-{jobid}.out')


def subcmd_archive(args, cfg, arch, aws):

    global TABLECSV
    global SELECTEDFILE

    if args.debug:
        print("archive:", args.cores, args.awsprofile, args.noslurm,
              args.larger, args.older, args.agemtime, args.folders)
    fld = '" "'.join(args.folders)
    if args.debug:
        print(f'default cmdline: froster.py archive "{fld}"')

    archmeta = []
    if not args.folders:
        hsfolder = os.path.join(cfg.config_root, 'hotspots')
        if not os.path.exists(hsfolder):
            print("No folders to archive in arguments and no Hotspots CSV files found!")
            print('Run: froster archive "/your/folder/to/archive"')
            return False
        csv_files = [f for f in os.listdir(
            hsfolder) if fnmatch.fnmatch(f, '*.csv')]
        if len(csv_files) == 0:
            print("No folders to archive in arguments and no Hotspots CSV files found!")
            print('Run: froster archive "/your/folder/to/archive"')
            return False
        # Sort the CSV files by their modification time in descending order (newest first)
        csv_files.sort(key=lambda x: os.path.getmtime(
            os.path.join(hsfolder, x)), reverse=True)
        # if there are multiple files allow for selection
        if len(csv_files) > 1:
            TABLECSV = '"Select a Hotspot file"\n' + '\n'.join(csv_files)
            app = TableArchive()
            retline = app.run()
            if not retline:
                return False
            SELECTEDFILE = os.path.join(hsfolder, retline[0])
        else:
            SELECTEDFILE = os.path.join(hsfolder, csv_files[0])
        if args.larger > 0 and args.older > 0:
            # implement archiving batchmode
            arch.archive_batch()
            return
        elif args.larger > 0 or args.older > 0:
            print('You need to combine both "--older <days> and --larger <GiB> options')
            return

        SELECTEDFILE = arch.get_user_hotspot(SELECTEDFILE)
        app = TableHotspots()
        retline = app.run()
        # print('Retline:', retline)
        if not retline:
            return False
        if len(retline) < 6:
            print('Error: Hotspots table did not return all columns')
            return False

        if retline[-1]:
            if cfg.nih == 'yes' or args.nih:
                app = TableNIHGrants()
                archmeta = app.run()
        else:
            print(
                f'\nYou can start this archive process later by using this command:\n  froster archive "{retline[5]}"')
            print(
                f'\n... or if you like to include all subfolders run:\n  froster archive --recursive "{retline[5]}"\n')
            return False

        badfiles = arch.cannot_read_files(retline[5])
        if badfiles:
            print(
                f'  Cannot read {len(badfiles)} files in folder {retline[5]}, for example:\n  {", ".join(badfiles[:10])}')
            return False

        args.folders.append(retline[5])

    else:
        args.folders = cfg.replace_symlinks_with_realpaths(args.folders)

    if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
        print(f'Profile "{args.awsprofile}" not found.')
        return False
    if not aws.check_bucket_access(cfg.bucket, readwrite=True):
        return False

    # if recursive archiving, check if we can read all files
    if args.recursive:
        isbad = False
        for fld in args.folders:
            # check for bad files first
            print(
                f'Checking access to files in folder tree "{fld}" ... ', flush=True)
            for root, dirs, files in arch._walker(fld):
                print(f'  Folder "{root}" ... ', flush=True)
                badfiles = arch.cannot_read_files(root)
                if badfiles:
                    isbad = True
                    print(
                        f'  Error: Cannot read {len(badfiles)} files in folder, for example:\n  {", ".join(badfiles[:10])}', flush=True)
                for dir in dirs:
                    dirpath = os.path.join(root, dir)
                    ret = arch.test_write(dirpath)
                    if ret == 13 or ret == 2:
                        print(
                            f'  Cannot write to sub-folder {dir}', flush=True)
                        isbad = True
        if isbad:
            print(
                f'Error: Cannot archive folder(s) resursively, fix some permissions first.', flush=True)
            return False

    if not shutil.which('sbatch') or args.noslurm or args.reset or os.getenv('SLURM_JOB_ID'):
        for fld in args.folders:
            fld = fld.rstrip(os.path.sep)
            if args.reset:
                ret = arch.reset_folder(fld, args.recursive)
                continue
            if args.recursive:
                print(
                    f'Archiving folder "{fld}" and subfolders, please wait ...', flush=True)
                if not arch.archive_recursive(fld, archmeta):
                    if args.debug:
                        print(
                            f'  Archiver.archive_recursive({fld}) returned False', flush=True)
            else:
                print(
                    f'Archiving folder "{fld}" (no subfolders), please wait ...', flush=True)
                arch.archive(fld, archmeta)
    else:
        se = SlurmEssentials(args, cfg)
        label = args.folders[0].replace('/', '+')
        label = label.replace(' ', '_')
        shortlabel = os.path.basename(args.folders[0])
        myjobname = f'froster:archive:{shortlabel}'
        email = cfg.read('general', 'email')
        se.add_line(f'#SBATCH --job-name={myjobname}')
        se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
        se.add_line(f'#SBATCH --mem=64G')
        se.add_line(f'#SBATCH --requeue')
        se.add_line(f'#SBATCH --output=froster-archive-{label}-%J.out')
        se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')
        se.add_line(f'#SBATCH --mail-user={email}')
        se.add_line(f'#SBATCH --time={se.walltime}')
        if se.partition:
            se.add_line(f'#SBATCH --partition={se.partition}')
        if se.qos:
            se.add_line(f'#SBATCH --qos={se.qos}')
        cmdline = " ".join(map(shlex.quote, sys.argv))  # original cmdline
        if not "--profile" in cmdline and args.awsprofile:
            cmdline = cmdline.replace(
                '/froster.py ', f'/froster --profile {args.awsprofile} ')
        else:
            cmdline = cmdline.replace('/froster.py ', '/froster ')
        if not args.folders[0] in cmdline:
            folders = '" "'.join(args.folders)
            cmdline = f'{cmdline} "{folders}"'
        if args.debug:
            print(f'Command line passed to Slurm:\n{cmdline}')
        se.add_line(cmdline)
        jobid = se.sbatch()
        print(f'Submitted froster archiving job: {jobid}')
        print(f'Check Job Output:')
        print(f' tail -f froster-archive-{label}-{jobid}.out')


def subcmd_restore(args, cfg, arch, aws):

    global TABLECSV
    global SELECTEDFILE

    cfg.printdbg("restore:", args.cores, args.awsprofile, args.noslurm,
                 args.days, args.retrieveopt, args.nodownload, args.folders)
    fld = '" "'.join(args.folders)
    cfg.printdbg(f'default cmdline: froster restore "{fld}"')

    # *********
    if args.monitor:
        # aws inactivity and cost monitoring
        aws.monitor_ec2()
        return True

    if not args.folders:
        TABLECSV = arch.archive_json_get_csv(
            ['local_folder', 's3_storage_class', 'profile', 'archive_mode'])
        if TABLECSV == None:
            print("No archives available.")
            return False
        app = TableArchive()
        retline = app.run()
        if not retline:
            return False
        if len(retline) < 2:
            print('Error: froster-archives table did not return result')
            return False
        cfg.printdbg("subcmd_restore dialog returns:", retline)
        args.folders.append(retline[0])
        if retline[2]:
            cfg.awsprofile = retline[2]
            args.awsprofile = cfg.awsprofile
            cfg._set_env_vars(cfg.awsprofile)
            cfg.printdbg("AWS profile:", cfg.awsprofile)
    else:
        pass
        # we actually want to support symlinks
        # args.folders = cfg.replace_symlinks_with_realpaths(args.folders)

    if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
        print(f'Profile "{args.awsprofile}" not found.')
        return False
    if not aws.check_bucket_access_folders(args.folders):
        return False

    if args.aws:
        # run ec2_deploy(self, bucket='', prefix='', recursive=False, profile=None):
        ret = aws.ec2_deploy(args.folders)
        return True

    if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
        # either no slurm or already running inside a slurm job
        for fld in args.folders:
            fld = fld.rstrip(os.path.sep)
            print(f'Restoring folder {fld}, please wait ...', flush=True)
            # check if triggered a restore from glacier and other conditions
            if arch.restore(fld) > 0:
                if shutil.which('sbatch') and \
                        args.noslurm == False and \
                        args.nodownload == False:
                    # start a future Slurm job just for the download
                    se = SlurmEssentials(args, cfg)
                    # get a job start time 12 hours from now
                    fut_time = se.get_future_start_time(12)
                    label = fld.replace('/', '+')
                    label = label.replace(' ', '_')
                    shortlabel = os.path.basename(fld)
                    myjobname = f'froster:restore:{shortlabel}'
                    email = cfg.read('general', 'email')
                    se.add_line(f'#SBATCH --job-name={myjobname}')
                    se.add_line(f'#SBATCH --begin={fut_time}')
                    se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
                    se.add_line(f'#SBATCH --mem=64G')
                    se.add_line(f'#SBATCH --requeue')
                    se.add_line(
                        f'#SBATCH --output=froster-download-{label}-%J.out')
                    se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')
                    se.add_line(f'#SBATCH --mail-user={email}')
                    se.add_line(f'#SBATCH --time={se.walltime}')
                    if se.partition:
                        se.add_line(f'#SBATCH --partition={se.partition}')
                    if se.qos:
                        se.add_line(f'#SBATCH --qos={se.qos}')
                    # original cmdline
                    cmdline = " ".join(map(shlex.quote, sys.argv))
                    if not "--profile" in cmdline and args.awsprofile:
                        cmdline = cmdline.replace(
                            '/froster.py ', f'/froster --profile {args.awsprofile} ')
                    else:
                        cmdline = cmdline.replace('/froster.py ', '/froster ')
                    if not fld in cmdline:
                        cmdline = f'{cmdline} "{fld}"'
                    cfg.printdbg(f'Command line passed to Slurm:\n{cmdline}')
                    se.add_line(cmdline)
                    jobid = se.sbatch()
                    print(
                        f'Submitted froster download job to run in 12 hours: {jobid}')
                    print(f'Check Job Output:')
                    print(f' tail -f froster-download-{label}-{jobid}.out')
                else:
                    print(
                        f'\nGlacier retrievals pending, run this again in 5-12 hours\n')

    else:
        se = SlurmEssentials(args, cfg)
        label = args.folders[0].replace('/', '+')
        label = label.replace(' ', '_')
        shortlabel = os.path.basename(args.folders[0])
        myjobname = f'froster:restore:{shortlabel}'
        email = cfg.read('general', 'email')
        se.add_line(f'#SBATCH --job-name={myjobname}')
        se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
        se.add_line(f'#SBATCH --mem=64G')
        se.add_line(f'#SBATCH --requeue')
        se.add_line(f'#SBATCH --output=froster-restore-{label}-%J.out')
        se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')
        se.add_line(f'#SBATCH --mail-user={email}')
        se.add_line(f'#SBATCH --time={se.walltime}')
        if se.partition:
            se.add_line(f'#SBATCH --partition={se.partition}')
        if se.qos:
            se.add_line(f'#SBATCH --qos={se.qos}')
        cmdline = " ".join(map(shlex.quote, sys.argv))  # original cmdline
        if not "--profile" in cmdline and args.awsprofile:
            cmdline = cmdline.replace(
                '/froster.py ', f'/froster --profile {args.awsprofile} ')
        else:
            cmdline = cmdline.replace('/froster.py ', '/froster ')
        if not args.folders[0] in cmdline:
            folders = '" "'.join(args.folders)
            cmdline = f'{cmdline} "{folders}"'
        cfg.printdbg(f'Command line passed to Slurm:\n{cmdline}')
        se.add_line(cmdline)
        jobid = se.sbatch()
        print(f'Submitted froster restore job: {jobid}')
        print(f'Check Job Output:')
        print(f' tail -f froster-restore-{label}-{jobid}.out')


def subcmd_delete(args, cfg, arch, aws):

    global TABLECSV
    global SELECTEDFILE

    cfg.printdbg("delete:", args.awsprofile, args.folders)
    fld = '" "'.join(args.folders)
    cfg.printdbg(f'default cmdline: froster delete "{fld}"')

    if not args.folders:
        TABLECSV = arch.archive_json_get_csv(
            ['local_folder', 's3_storage_class', 'profile', 'archive_mode'])
        if TABLECSV == None:
            print("No archives available.")
            return False
        app = TableArchive()
        retline = app.run()
        if not retline:
            return False
        if len(retline) < 2:
            print('Error: froster-archives table did not return result')
            return False
        cfg.printdbg("dialog returns:", retline)
        args.folders.append(retline[0])
        if retline[2]:
            cfg.awsprofile = retline[2]
            args.awsprofile = cfg.awsprofile
            cfg._set_env_vars(cfg.awsprofile)
    else:
        pass
        # we actually want to support symlinks
        # args.folders = cfg.replace_symlinks_with_realpaths(args.folders)

    if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
        print(f'Profile "{args.awsprofile}" not found.')
        return False
    if not aws.check_bucket_access_folders(args.folders):
        return False

    for fld in args.folders:
        fld = fld.rstrip(os.path.sep)
        # get archive storage location
        print(
            f'Deleting archived files in "{fld}", please wait ...', flush=True)
        if not arch.delete(fld):
            cfg.printdbg(
                f'  Archiver.delete({fld}) returned False', flush=True)


def subcmd_mount(args, cfg, arch, aws):

    global TABLECSV
    global SELECTEDFILE

    cfg.printdbg("mount:", args.awsprofile, args.mountpoint, args.folders)
    fld = '" "'.join(args.folders)
    cfg.printdbg(f'default cmdline: froster mount "{fld}"')

    interactive = False
    if not args.folders:
        interactive = True
        TABLECSV = arch.archive_json_get_csv(
            ['local_folder', 's3_storage_class', 'profile', 'archive_mode'])
        if TABLECSV == None:
            print("No archives available.")
            return False
        app = TableArchive()
        retline = app.run()
        if not retline:
            return False
        if len(retline) < 2:
            print('Error: froster-archives table did not return result')
            return False
        cfg.printdbg("dialog returns:", retline)
        args.folders.append(retline[0])
        if retline[2]:
            cfg.awsprofile = retline[2]
            args.awsprofile = cfg.awsprofile
            cfg._set_env_vars(cfg.awsprofile)
    else:
        pass
        # we actually want to support symlinks
        # args.folders = cfg.replace_symlinks_with_realpaths(args.folders)

    if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
        print(f'Profile "{args.awsprofile}" not found.')
        return False
    if not aws.check_bucket_access_folders(args.folders):
        return False

    if args.aws:
        cfg.create_ec2_instance()
        return True

    hostname = platform.node()
    rclone = Rclone(args, cfg)
    for fld in args.folders:
        fld = fld.rstrip(os.path.sep)
        if fld == os.path.realpath(os.getcwd()):
            print(f' Cannot mount current working directory {fld}')
            continue
        # get archive storage location
        rowdict = arch.archive_json_get_row(fld)
        if rowdict == None:
            print(f'Folder "{fld}" not in archive.')
            continue
        archive_folder = rowdict['archive_folder']

        if args.mountpoint and os.path.isdir(args.mountpoint):
            fld = args.mountpoint

        print(f'Mounting archive folder at {fld} ... ', flush=True, end="")
        pid = rclone.mount(archive_folder, fld)
        print('Done!', flush=True)
        if interactive:
            print(textwrap.dedent(f'''
                Note that this mount point will only work on the current machine, 
                if you would like to have this work in a batch job you need to enter 
                these commands in the beginning and the end of a batch script:
                froster mount {fld}
                froster umount {fld}
                '''))
        if args.mountpoint:
            # we can only mount a single folder if mountpoint is set
            break


def subcmd_umount(args, cfg):

    global TABLECSV
    global SELECTEDFILE

    rclone = Rclone(args, cfg)
    mounts = rclone.get_mounts()
    if len(mounts) == 0:
        print("No Rclone mounts on this computer.")
        return False
    folders = cfg.replace_symlinks_with_realpaths(args.folders)
    if len(folders) == 0:
        TABLECSV = "\n".join(mounts)
        TABLECSV = "Mountpoint\n"+TABLECSV
        app = TableArchive()
        retline = app.run()
        folders.append(retline[0])
    for fld in folders:
        print(f'Unmounting folder {fld} ... ', flush=True, end="")
        rclone.unmount(fld)
        print('Done!', flush=True)


def subcmd_ssh(args, cfg, aws):

    ilist = aws.ec2_list_instances('Name', 'FrosterSelfDestruct')
    ips = [sublist[0] for sublist in ilist if sublist]
    if args.list:
        if ips:
            print("Running AWS EC2 Instances:")
            for row in ilist:
                print(' - '.join(row))
        else:
            print('No running instances detected')
        return True
    if args.terminate:
        aws.ec2_terminate_instance(args.terminate)
        return True
    if args.sshargs:
        if ':' in args.sshargs[0]:
            myhost, remote_path = args.sshargs[0].split(':')
        else:
            myhost = args.sshargs[0]
            remote_path = ''
    else:
        myhost = cfg.read('cloud', 'ec2_last_instance')
    if ips and not myhost in ips:
        print(f'{myhost} is no longer running, replacing with {ips[-1]}')
        myhost = ips[-1]
        # cfg.write('cloud', 'ec2_last_instance', myhost)
    if args.subcmd == 'ssh':
        print(f'Connecting to {myhost} ...')
        aws.ssh_execute('ec2-user', myhost)
        return True
    elif args.subcmd == 'scp':
        if len(args.sshargs) != 2:
            print('The "scp" sub command supports currently 2 arguments')
            return False
        hostloc = next((i for i, item in enumerate(
            args.sshargs) if ":" in item), None)
        if hostloc == 0:
            # the hostname is in the first argument: download
            host, remote_path = args.sshargs[0].split(':')
            ret = aws.ssh_download(
                'ec2-user', host, remote_path, args.sshargs[1])
        elif hostloc == 1:
            # the hostname is in the second argument: uploaad
            host, remote_path = args.sshargs[1].split(':')
            ret = aws.ssh_upload(
                'ec2-user', host, args.sshargs[0], remote_path)
        else:
            print('The "scp" sub command supports currently 2 arguments')
            return False
        print(ret.stdout, ret.stderr)


class Archiver:
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.archive_json = os.path.join(
            cfg.config_root, 'froster-archives.json')
        x = self.cfg.read('general', 'max_small_file_size_kib')
        self.thresholdKB = int(x) if x else 1024
        x = self.cfg.read('general', 'min_index_folder_size_gib')
        self.thresholdGB = int(x) if x else 10
        x = self.cfg.read('general', 'min_index_folder_size_avg_mib')
        self.thresholdMB = int(x) if x else 10
        x = self.cfg.read('general', 'max_hotspots_display_entries')
        global MAXHOTSPOTS
        MAXHOTSPOTS = int(x) if x else 5000
        self.dirmetafiles = ['Froster.allfiles.csv', 'Froster.smallfiles.tar',
                             '.froster.md5sum', '.froster-restored.md5sum', 'Where-did-the-files-go.txt']

        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.grants = []

    def index(self, pwalkfolder):

        # move down to class
        daysaged = [5475, 3650, 1825, 1095, 730, 365, 90, 30]
        TiB = 1099511627776
        # GiB=1073741824
        # MiB=1048576

        # Connect to an in-memory DuckDB instance
        con = duckdb.connect(':memory:')
        con.execute(f'PRAGMA threads={self.args.cores};')

        locked_dirs = ''
        with tempfile.NamedTemporaryFile() as tmpfile:
            with tempfile.NamedTemporaryFile() as tmpfile2:
                if not self.args.pwalkcsv:
                    pwalkcmd = 'pwalk --NoSnap --one-file-system --header'
                    # 2> {tmpfile2.name}.err'
                    mycmd = f'{self.cfg.binfolderx}/{pwalkcmd} "{pwalkfolder}" > {tmpfile2.name}'
                    self.cfg.printdbg(f' Running {mycmd} ...', flush=True)
                    ret = subprocess.run(mycmd, shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if ret.returncode != 0:
                        print(
                            f'pwalk run failed: {mycmd} Error:\n{ret.stderr}')
                        return False
                    lines = ret.stderr.decode(
                        'utf-8', errors='ignore').splitlines()
                    locked_dirs = '\n'.join(
                        [l for l in lines if "Locked Dir:" in l])
                    pwalkcsv = tmpfile2.name
                else:
                    pwalkcsv = self.args.pwalkcsv
                with tempfile.NamedTemporaryFile() as tmpfile3:
                    # copy/backup pwalk csv file to network location
                    if args.pwalkcopy:
                        print(
                            f' Copying and cleaning {pwalkcsv} to {args.pwalkcopy}, please wait ... ', flush=True, end="")
                        mycmd = f'iconv -f ISO-8859-1 -t UTF-8 {pwalkcsv} > {args.pwalkcopy}'
                        self.cfg.printdbg(f' Running {mycmd} ...', flush=True)
                        result = subprocess.run(mycmd, shell=True)
                        print('Done!', flush=True)
                        if result.returncode != 0:
                            print(f"File conversion failed: {mycmd}")
                            return False
                    # removing all files from pwalk output, keep only folders
                    mycmd = f'grep -v ",-1,0$" "{pwalkcsv}" > {tmpfile3.name}'
                    self.cfg.printdbg(f' Running {mycmd} ...', flush=True)
                    result = subprocess.run(mycmd, shell=True)
                    if result.returncode != 0:
                        print(f"Folder extraction failed: {mycmd}")
                        return False
                    # Temp hack: e.g. Revista_Española_de_Quimioterapia in Spellman
                    # Converting file from ISO-8859-1 to utf-8 to avoid DuckDB import error
                    # pwalk does already output UTF-8, weird, probably duckdb error
                    mycmd = f'iconv -f ISO-8859-1 -t UTF-8 {tmpfile3.name} > {tmpfile.name}'
                    self.cfg.printdbg(f' Running {mycmd} ...', flush=True)
                    result = subprocess.run(mycmd, shell=True)
                    if result.returncode != 0:
                        print(f"File conversion failed: {mycmd}")
                        return False

            sql_query = f"""SELECT UID as User,
                            st_atime as AccD, st_mtime as ModD,
                            pw_dirsum/1073741824 as GiB, 
                            pw_dirsum/1048576/pw_fcount as MiBAvg,                            
                            filename as Folder, GID as Group,
                            pw_dirsum/1099511627776 as TiB,
                            pw_fcount as FileCount, pw_dirsum as DirSize
                        FROM read_csv_auto('{tmpfile.name}', 
                                ignore_errors=1)
                        WHERE pw_fcount > -1 AND pw_dirsum > 0
                        ORDER BY pw_dirsum Desc
                    """  # pw_dirsum > 1073741824
            self.cfg.printdbg(
                f' Running SQL query on CSV file {tmpfile.name} ...', flush=True)
            rows = con.execute(sql_query).fetchall()
            # also query 'parent-inode' as pi,

            # Get the column names
            header = con.execute(sql_query).description

        totalbytes = 0
        agedbytes = []
        for i in daysaged:
            agedbytes.append(0)
        numhotspots = 0

        mycsv = self._get_hotspots_path(pwalkfolder)
        self.cfg.printdbg(
            f' Running filter and write results to CSV file {mycsv} ...', flush=True)

        with tempfile.NamedTemporaryFile() as tmpcsv:
            with open(tmpcsv.name, 'w') as f:
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
                                    self.cfg.printdbg(
                                        f'  {row[5]} has not been accessed for {row[1]} days. (atime = {atime})', flush=True)
                                agedbytes[i] += row[9]
            if numhotspots > 0:
                shutil.copyfile(tmpcsv.name, mycsv)
                # filter hotspots file for folders to which the current user has write access
                self.get_user_hotspot(mycsv)

        if numhotspots > 0:
            # dedented multi-line retaining \n
            print(textwrap.dedent(f'''       
                Wrote {os.path.basename(mycsv)}
                with {numhotspots} hotspots >= {self.thresholdGB} GiB 
                with a total disk use of {round(totalbytes/TiB,3)} TiB
                '''), flush=True)
            lastagedbytes = 0
            print(
                f'Histogram for {len(rows)} total folders processed:', flush=True)
            for i in range(0, len(daysaged)):
                if agedbytes[i] > 0 and agedbytes[i] != lastagedbytes:
                    # dedented multi-line removing \n
                    print(textwrap.dedent(f'''  
                    {round(agedbytes[i]/TiB,3)} TiB have not been accessed 
                    for {daysaged[i]} days (or {round(daysaged[i]/365,1)} years)
                    ''').replace('\n', ''), flush=True)
                lastagedbytes = agedbytes[i]
            print('')
        else:
            print(
                f'No folders larger than {self.thresholdGB} GiB found under {pwalkfolder}', flush=True)

        if locked_dirs:
            print('\n'+locked_dirs, flush=True)
            print(textwrap.dedent(f'''
            \n   WARNING: You cannot access the locked folder(s) 
            above, because you don't have permissions to see
            their content. You will not be able to archive these
            folders until you have the permissions granted.
            '''), flush=True)
        self.cfg.printdbg(f' Done indexing {pwalkfolder}!', flush=True)

    def archive(self, folder, meta, isrecursive=False, issubfolder=False):

        source = os.path.abspath(folder)
        target = os.path.join(f':s3:{self.cfg.archivepath}',
                              source.lstrip(os.path.sep))

        if os.path.isfile(os.path.join(source, ".froster.md5sum")):
            print(
                f'  The hashfile ".froster.md5sum" already exists in {source} from a previous archiving process.')
            print('  You need to manually rename the file before you can proceed.')
            print('')
            return False

        if not [f for f in os.listdir(source) if os.path.isfile(os.path.join(source, f))]:
            print("    Folder is empty, skipping")
            return True

        badfiles = self.cannot_read_files(source)
        if badfiles:
            print(
                f'  Cannot read {len(badfiles)} files in folder, for example:\n  {", ".join(badfiles[:10])}')
            return False

        if not self.args.notar:
            ret = self._tar_small_files(source, self.thresholdKB)
            if ret == 13:  # cannot write to folder
                return False
            elif not ret:
                print('  Could not create Froster.smallfiles.tar')
                print('  Perhaps there are no files or the folder does not exist?')
                return False

        ret = self._gen_md5sums(source, '.froster.md5sum')
        if ret == 13:  # cannot write to folder
            return False
        elif not ret:
            print('  Could not create hashfile .froster.md5sum.')
            print('  Perhaps there are no files or the folder does not exist?')
            return False
        hashfile = os.path.join(source, '.froster.md5sum')

        rclone = Rclone(self.args, self.cfg)

        print('  Copying files to archive ... ', end="")
        ret = rclone.copy(source, target, '--max-depth', '1', '--links',
                          '--exclude', '.froster.md5sum',
                          '--exclude', '.froster-restored.md5sum',
                          '--exclude', 'Froster.allfiles.csv',
                          '--exclude', 'Where-did-the-files-go.txt'
                          )
        self.cfg.printdbg('*** RCLONE copy ret ***:\n', ret, '\n')
        # print ('Message:', ret['msg'].replace('\n',';'))
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Copying was not successful.')
            return False
        print('Done.')

        ttransfers = ret['stats']['totalTransfers']
        tbytes = ret['stats']['totalBytes']
        if self.args.debug:
            print('\n')
            print('Speed:', ret['stats']['speed'])
            print('Transfers:', ret['stats']['transfers'])
            print('Tot Transfers:', ret['stats']['totalTransfers'])
            print('Tot Bytes:', ret['stats']['totalBytes'])
            print('Tot Checks:', ret['stats']['totalChecks'])

        #   {'bytes': 0, 'checks': 0, 'deletedDirs': 0, 'deletes': 0, 'elapsedTime': 2.783003019,
        #    'errors': 1, 'eta': None, 'fatalError': False, 'lastError': 'directory not found',
        #    'renames': 0, 'retryError': True, 'speed': 0, 'totalBytes': 0, 'totalChecks': 0,
        #    'totalTransfers': 0, 'transferTime': 0, 'transfers': 0}

        # upload of Froster.allfiles.csv to INTELLIGENT_TIERING
        #
        allf_s = os.path.join(source, 'Froster.allfiles.csv')
        allf_d = os.path.join(self.cfg.archiveroot,
                              source.lstrip(os.path.sep),
                              'Froster.allfiles.csv')
        if os.path.exists(allf_s):
            self._upload_file_to_s3(allf_s, self.cfg.bucket, allf_d)

        ret = rclone.checksum(hashfile, target, '--max-depth', '1')
        self.cfg.printdbg('*** RCLONE checksum ret ***:\n', ret, '\n')
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Checksum test was not successful.')
            return False

        # If success, write metadata to froster-archives.json database
        s3_storage_class = os.getenv(
            'RCLONE_S3_STORAGE_CLASS', 'INTELLEGENT_TIERING')
        timestamp = datetime.datetime.now().isoformat()
        archive_mode = "Single"
        if isrecursive:
            archive_mode = "Recursive"
        # meta = #['R41HL129728', '2016-09-30', '2017-07-31', 'MOLLER, DAVID ROBERT',
        # 'Developing a Diagnostic Blood Test for Sarcoidosis', 'SARCOIDOSIS DIAGNOSTIC TESTING, LLC',
        #  'https://reporter.nih.gov/project-details/9331239', '12519577']
        dictrow = {'local_folder': source, 'archive_folder': target,
                   's3_storage_class': s3_storage_class,
                   'profile': self.cfg.awsprofile, 'archive_mode': archive_mode,
                   'timestamp': timestamp, 'timestamp_archive': timestamp,
                   'user': getpass.getuser()
                   }
        if meta:
            dictrow['nih_project'] = meta[0]
            dictrow['nih_project_url'] = meta[6]
            dictrow['nih_project_pi'] = meta[3]

        if not issubfolder:
            self._archive_json_put_row(source, dictrow)

        total = self.convert_size(tbytes)
        print(
            f'  Source and archive are identical. {ttransfers} files with {total} transferred.\n')

    def archive_recursive(self, folder, meta):
        for root, dirs, files in self._walker(folder):
            archpath = root
            print(f'  Processing folder "{archpath}" ... ')
            try:
                if folder == root:
                    # main directory, store metadata in json file
                    self.archive(archpath, meta, True, False)
                else:
                    # a subdirectory, don't write metadata to json
                    self.archive(archpath, meta, True, True)
            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(f'  Permission denied to "{archpath}"')
                    continue
                else:
                    print(f"  An unexpected PermissionError occurred:\n{e}")
                    continue
            except Exception as e:
                print(f"  An unexpected error occurred:\n{e}")
                continue
        return True

    def archive_batch(self):

        print(f'\nProcessing hotspots file {SELECTEDFILE}!')

        agefld = 'AccD'
        if args.agemtime:
            agefld = 'ModD'

        # Initialize a connection to an in-memory database
        conn = duckdb.connect(database=':memory:', read_only=False)
        conn.execute(f'PRAGMA threads={self.args.cores};')

        # Register CSV file as a virtual table
        conn.execute(
            f"CREATE TABLE hs AS SELECT * FROM read_csv_auto('{SELECTEDFILE}')")

        # Now, you can run SQL queries on this virtual table
        rows = conn.execute(
            f"SELECT * FROM hs WHERE {agefld} > {args.older} and GiB > {args.larger} ").fetchall()

        totalspace = 0
        cmdline = ""
        for row in rows:
            totalspace += row[3]
            cmdline += f'"{row[5]}" \\\n'

        print(f'\nRun this command to archive all selected folders in batch mode:\n')
        print(f'froster archive \\\n{cmdline[:-3]}\n')  # add --dry-run later
        print(
            f'Total space to archive: {format(round(totalspace, 3),",")} GiB\n')

        # Don't forget to close the connection when done
        conn.close()

        return True

    def get_user_hotspot(self, hotspot_csv):
        # Reduce a hotspots file to the folders that the user has write access to
        try:
            hsdir, hsfile = os.path.split(hotspot_csv)
            hsdiruser = os.path.join(hsdir, self.cfg.whoami)
            os.makedirs(hsdiruser, exist_ok=True)
            user_csv = os.path.join(hsdiruser, hsfile)
            if os.path.exists(user_csv):
                if os.path.getmtime(user_csv) > os.path.getmtime(hotspot_csv):
                    # print(f"File {user_csv} already exists and is newer than {hotspot_csv}.")
                    return user_csv
            print('Filtering hotspots for folders with write permissions ...')
            writable_folders = []
            with open(hotspot_csv, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                mylen = sum(1 for row in reader)
                file.seek(0)
                reader = csv.DictReader(file)
                progress = self._create_progress_bar(mylen+1)
                for row in reader:
                    ret = self.test_write(row['Folder'])
                    if ret != 13 and ret != 2:
                        writable_folders.append(row)
                    progress(reader.line_num)
            with open(user_csv, mode='w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(writable_folders)
            return user_csv
        except Exception as e:
            print(f"Error in get_user_hotspot:\n{e}")
            return False

    def test_write(self, directory):
        testpath = os.path.join(directory, f'.froster.test.{self.cfg.whoami}')
        try:
            with open(testpath, "w") as f:
                f.write('just a test')
            os.remove(testpath)
            return True
        except PermissionError as e:
            # Check if error number is 13 (Permission denied)
            if e.errno == 13:
                # print("Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                return 13
            else:
                print(
                    f"An unexpected PermissionError occurred in {directory}:\n{e}")
                return False
        except Exception as e:
            if e.errno == 2:
                # No such file or directory:
                return 2
            else:
                print(f"An unexpected error occurred in {directory}:\n{e}")
                return False

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

    def can_delete_file(self, file_path):
        # Check if file exists
        if not os.path.exists(file_path):
            if self.args.debug:
                print(f'File {file_path} does not exist.')
            return False
        # Getting the status of the file
        file_stat = os.lstat(file_path)
        # Getting the current user and group IDs
        current_uid = os.getuid()
        current_gid = os.getgid()
        # Checking if the user is the owner
        is_owner = file_stat.st_uid == current_uid
        # Checking if the user is in the file's group
        is_group_member = file_stat.st_gid == current_gid or \
            any(grp.getgrgid(g).gr_gid == file_stat.st_gid for g in os.getgroups())
        # Extracting permission bits
        permissions = file_stat.st_mode
        # Checking for owner write permission
        has_owner_write_permission = bool(permissions & stat.S_IWUSR)
        # Checking for group write permission
        has_group_write_permission = bool(permissions & stat.S_IWGRP)
        # Checking for '666' or '777' permissions
        is_666_or_777 = permissions & 0o666 == 0o666 or permissions & 0o777 == 0o777
        # Determining if the user can delete the file
        can_delete = (is_owner and has_owner_write_permission) or \
                     (is_group_member and has_group_write_permission) or \
            is_666_or_777
        if self.args.debug:
            print('\ncan_delete_file ?:', file_path, flush=True)
            print('  is_owner:', is_owner, flush=True)
            print('  has_owner_write_permission:',
                  has_owner_write_permission, flush=True)
            print('  is_group_member:', is_group_member, flush=True)
            print('  has_group_write_permission:',
                  has_group_write_permission, flush=True)
            print('  is_666_or_777:', is_666_or_777, flush=True)
            print('  can_delete:', can_delete, flush=True)
        return can_delete

    def can_read_file(self, file_path):
        # Check if file exists
        if not os.path.exists(file_path):
            return False
        # Getting the status of the file
        file_stat = os.lstat(file_path)
        # Getting the current user and group IDs
        current_uid = os.getuid()
        current_gid = os.getgid()
        # Checking if the user is the owner
        is_owner = file_stat.st_uid == current_uid
        # Checking if the user is in the file's group
        is_group_member = file_stat.st_gid == current_gid or \
            any(grp.getgrgid(g).gr_gid == file_stat.st_gid for g in os.getgroups())
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
        if self.args.debug:
            print('\ncan_read_file ?:', file_path, flush=True)
            print('  is_owner:', is_owner, flush=True)
            print('  has_owner_read_permission:',
                  has_owner_read_permission, flush=True)
            print('  is_group_member:', is_group_member, flush=True)
            print('  has_group_read_permission:',
                  has_group_read_permission, flush=True)
            print('  is_444:', is_444, flush=True)
            print('  can_read:', can_read, flush=True)
        return can_read

    def cannot_read_files(self, directory):
        # List to hold files that cannot be read
        unreadable_files = []
        # Iterate over all files in the given directory
        try:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                # Check if it's a file and not readable
                if os.path.isfile(file_path) and not self.can_read_file(file_path):
                    unreadable_files.append(filename)
        except PermissionError as e:
            print(f"  An unexpected PermissionError occurred:\n{e}")
        return unreadable_files

    def _gen_md5sums(self, directory, hash_file, num_workers=4, no_subdirs=True):
        for root, dirs, files in self._walker(directory):
            if no_subdirs and root != directory:
                break
            hashpath = os.path.join(root, hash_file)
            try:
                print(f'  Generating hash file {hash_file} ... ', end='')
                with open(hashpath, "w") as out_f:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                        tasks = {}
                        for filen in files:
                            file_path = os.path.join(root, filen)
                            if not self.can_read_file(file_path):
                                print(
                                    f'  Cannot add {file_path} to {hash_file} due to permissions, skipping ...')
                                continue
                            if os.path.isfile(file_path) and \
                                    filen != os.path.basename(hash_file) and \
                                    filen != "Where-did-the-files-go.txt" and \
                                    filen != ".froster.md5sum" and \
                                    filen != ".froster-restored.md5sum":
                                task = executor.submit(self.md5sum, file_path)
                                tasks[task] = file_path
                        for future in concurrent.futures.as_completed(tasks):
                            filen = os.path.basename(tasks[future])
                            md5 = future.result()
                            out_f.write(f"{md5}  {filen}\n")
                if os.path.getsize(hashpath) == 0:
                    os.remove(hashpath)
                    return False
                print('Done.')
            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(
                        "Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                    return 13
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                return False
        return True

    def _tar_small_files(self, directory, smallsize=1024, recursive=False):
        for root, dirs, files in self._walker(directory):
            if not recursive and root != directory:
                break
            tar_path = os.path.join(root, 'Froster.smallfiles.tar')
            csv_path = os.path.join(root, 'Froster.allfiles.csv')
            if os.path.exists(tar_path):
                print(f'Froster.smallfiles.tar alreadly exists in {root}')
                continue
            # create a csv file even if there are no small files
            # if not self._is_small_file_in_dir(root,smallsize):
            #    continue
            try:
                print(f'  Creating Froster.smallfiles.tar ... ', end='')
                didtar = False
                with tarfile.open(tar_path, "w") as tar, open(csv_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    # write the header
                    writer.writerow(["File", "Size(bytes)", "Date-Modified",
                                    "Date-Accessed", "Owner", "Group", "Permissions", "Tarred"])
                    for filen in files:
                        file_path = os.path.join(root, filen)
                        if file_path == csv_path:
                            continue
                        # check if file is larger than X MB
                        size, mtime, atime = self._get_file_stats(file_path)
                        # get last modified and accessed dates
                        mdate = datetime.datetime.fromtimestamp(
                            mtime).strftime('%Y-%m-%d %H:%M:%S')
                        adate = datetime.datetime.fromtimestamp(
                            atime).strftime('%Y-%m-%d %H:%M:%S')
                        # ownership and permissions
                        owner = self.uid2user(os.lstat(file_path).st_uid)
                        group = self.gid2group(os.lstat(file_path).st_gid)
                        permissions = oct(os.lstat(file_path).st_mode)
                        tarred = "No"
                        # write file info to the csv file
                        if size < smallsize*1024:
                            # add to tar file
                            if self.can_delete_file(file_path):
                                tar.add(file_path, arcname=filen)
                                didtar = True
                                # remove original file
                                os.remove(file_path)
                                tarred = "Yes"
                        writer.writerow(
                            [filen, size, mdate, adate, owner, group, permissions, tarred])
                if didtar:
                    print('Done.')
                else:
                    os.remove(tar_path)
                    print('No small files to tar.')
            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(
                        "Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                    return 13
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                return False
                # raise e
        return True

    def _untar_files(self, directory, recursive=False):
        for root, dirs, files in self._walker(directory):
            if not recursive and root != directory:
                break
            tar_path = os.path.join(root, 'Froster.smallfiles.tar')
            if not os.path.exists(tar_path):
                # print('{tar_path} does not exist, skipping folder {root}')
                continue
            try:
                print(f'  Untarring Froster.smallfiles.tar ... ', end='')
                with tarfile.open(tar_path, "r") as tar:
                    tar.extractall(path=root)
                os.remove(tar_path)
                print('Done.')
            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(
                        "Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                    return 13
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                return False
        return True

    def reset_folder(self, directory, recursive=False):
        # Remove all froster artifacts from a folder and untar small files
        for root, dirs, files in self._walker(directory):
            if not recursive and root != directory:
                break
            try:
                print(f'  Resetting folder {root} ... ', end='')
                min_metafiles = ['Froster.allfiles.csv',
                                 '.froster.md5sum', 'Where-did-the-files-go.txt']
                if set(min_metafiles).issubset(set(files)):
                    if len(files) <= 5:
                        print(
                            f'  There are only {len(files)} files in {root}, please reset it manually ...')
                        continue
                tar_path = os.path.join(root, 'Froster.smallfiles.tar')
                if os.path.exists(tar_path):
                    print(f'  Untarring Froster.smallfiles.tar ... ', end='')
                    with tarfile.open(tar_path, "r") as tar:
                        tar.extractall(path=root)
                    os.remove(tar_path)
                csv_path = os.path.join(root, 'Froster.allfiles.csv')
                if os.path.exists(csv_path):
                    if os.path.getsize(csv_path) < 100:
                        os.remove(csv_path)
                delfiles = [
                    '.froster.md5sum', '.froster-restored.md5sum', 'Where-did-the-files-go.txt']
                for d in delfiles:
                    delfile = os.path.join(root, d)
                    if os.path.exists(delfile):
                        os.remove(delfile)
                print('Done.')

            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print("Permission denied in _reset_folder.")
                    return 13
                else:
                    print(
                        f"An unexpected PermissionError occurred in _reset_folder:\n{e}")
                    return False
            except Exception as e:
                print(f"An unexpected error occurred in _reset_folder:\n{e}")
                return False
        return True

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

    def delete(self, folder, recursive=False):
        # Delete files that are archived and referenced in .froster.md5sum
        rclone = Rclone(self.args, self.cfg)
        lfolder = os.path.abspath(folder)
        rowdict = self.archive_json_get_row(lfolder)
        if rowdict == None:
            print(f'Folder "{folder}" not in archive.')
            return False
        if 'archive_mode' in rowdict:
            if rowdict['archive_mode'] == "Recursive":
                recursive = True

        tail = ''
        if folder != rowdict['local_folder']:
            # try to delete from subdir, we need to check if archived recursively
            if not recursive:
                print(textwrap.dedent(f'''\n
                    You are trying to remove a sub folder but the parent archive 
                    was not saved recursively. You can try remove this folder:
                    {rowdict['local_folder']}
                    '''))
                return False
            tail = folder.replace(rowdict['local_folder'], '')

        afolder = rowdict['archive_folder']+tail+'/'

        for root, dirs, files in self._walker(lfolder):
            if not recursive and root != lfolder:
                break
            print(f'  Checking folder "{root}" ... ')
            if root != lfolder:
                afolder = afolder + os.path.basename(root) + '/'
            try:
                hashfile = os.path.join(root, '.froster.md5sum')
                if not os.path.exists(hashfile):
                    if os.path.exists(os.path.join(root, '.froster-restored.md5sum')):
                        hashfile = os.path.join(
                            root, '.froster-restored.md5sum')
                        print(f'  Changed Hashfile to "{hashfile}"')
                    else:
                        print(textwrap.dedent(f'''\n
                            Hashfile {hashfile} does not exist.
                            Cannot delete files in {root}.
                        '''))
                        continue
                ret = rclone.checksum(hashfile, afolder, '--max-depth', '1')
                self.cfg.printdbg('*** RCLONE checksum ret ***:\n', ret, '\n')
                if ret['stats']['errors'] > 0:
                    print('Last Error:', ret['stats']['lastError'])
                    print('Checksum test was not successful.')
                    return False

                # delete files if confirmed that hashsums are identical
                delete_files = []
                with open(hashfile, 'r') as inp:
                    for line in inp:
                        fn = line.strip().split('  ', 1)[1]
                        if fn != 'Froster.allfiles.csv':
                            delete_files.append(fn)
                deleted_files = []
                for dfile in delete_files:
                    dpath = os.path.join(root, dfile)
                    if os.path.isfile(dpath) or os.path.islink(dpath):
                        os.remove(dpath)
                        deleted_files.append(dfile)
                        self.cfg.printdbg(
                            f"File '{dpath}' deleted successfully.")

                # if there is a restore that needs to be deleted a second time
                # make sure that all files extracted from the archive are deleted again
                tarred_files = self._get_tar_content(root)
                archived_files = []
                if len(tarred_files) > 0:
                    archived_files = list(set(delete_files + tarred_files))
                deleted_tar = self._delete_tar_content(root, tarred_files)
                if len(deleted_tar) > 0:
                    # merge 2 lists and remove dups by converting them to set and back to list
                    deleted_files = list(set(deleted_files + deleted_tar))
                if 'Froster.smallfiles.tar' in archived_files:
                    archived_files.remove('Froster.smallfiles.tar')

                if len(deleted_files) > 0:
                    email = self.cfg.read('general', 'email')
                    readme = os.path.join(root, 'Where-did-the-files-go.txt')
                    with open(readme, 'w') as rme:
                        rme.write(
                            f'The files in this folder have been moved to an archive!\n')
                        rme.write(f'\nArchive location: {afolder}\n')
                        rme.write(
                            f'Archive profile (~/.aws): {self.cfg.awsprofile}\n')
                        rme.write(f'Archiver: {email}\n')
                        rme.write(
                            f'Archive tool: https://github.com/dirkpetersen/froster\n')
                        rme.write(
                            f'Restore command: froster restore "{root}"\n')
                        rme.write(
                            f'Deletion date: {datetime.datetime.now()}\n')
                        rme.write(f'\nFirst 10 files archived:\n')
                        rme.write(', '.join(archived_files[:10]))
                        rme.write(f'\n\nFirst 10 files deleted this time:\n')
                        rme.write(', '.join(deleted_files[:10]))
                        rme.write(
                            f'\n\nPlease see more metadata in Froster.allfiles.csv')
                        rme.write(f'\n')
                    print(
                        f'  Deleted {len(deleted_files)} files and wrote manifest to "{readme}"\n')
                else:
                    print(f'  No files were deleted in "{root}".\n')

            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(f'Permission denied to "{root}"')
                    continue
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")
                    continue
            except OSError as e:
                print(f"Error deleting the file: {e}")
                continue
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                continue
        return True

    def _delete_tar_content(self, directory, files):
        deleted = []
        for f in files:
            fp = os.path.join(directory, f)

            if os.path.isfile(fp) or os.path.islink(fp):
                os.remove(fp)
                deleted.append(f)
        self.cfg.printdbg(
            f'Files deleted in _delete_tar_content: {", ".join(deleted)}')

        return deleted

    def _get_tar_content(self, directory):
        files = []
        tar_path = os.path.join(directory, 'Froster.smallfiles.tar')
        if os.path.exists(tar_path):
            with tarfile.open(tar_path, 'r') as tar:
                for member in tar.getmembers():
                    files.append(member.name)
        csv_path = os.path.join(directory, 'Froster.allfiles.csv')
        if os.path.exists(csv_path):
            file_list = []
            with open(csv_path, 'r') as csvfile:
                # Use csv reader
                reader = csv.DictReader(csvfile)
                # Iterate over each row in the csv
                for row in reader:
                    # If "Tarred" is "Yes", append the "File" to the list
                    if row['Tarred'] == 'Yes':
                        if not row['File'] in files:
                            files.append(row['File'])
        self.cfg.printdbg(
            f'Files founds in _get_tar_content: {", ".join(files)}')
        return files

    def restore(self, folder, recursive=False):

        # copied from archive
        rowdict = self.archive_json_get_row(folder)
        if rowdict == None:
            return False
        tail = ''
        if 'archive_mode' in rowdict:
            if rowdict['archive_mode'] == "Recursive":
                recursive = True
        if folder != rowdict['local_folder']:
            self.cfg.printdbg(
                f"rowdict[local_folder]: {rowdict['local_folder']}")
            # try to restore from subdir, we need to check if archived recursively
            if not recursive:
                print(textwrap.dedent(f'''\n
                    You are trying to restore a sub folder but the parent archive 
                    was not saved recursively. You can try restoring this folder:
                    {rowdict['local_folder']}
                    '''))
                return False
            tail = folder.replace(rowdict['local_folder'], '')

        source = rowdict['archive_folder']+tail+'/'
        target = folder

        buc, pre, recur, isglacier = self.archive_get_bucket_info(target)
        if isglacier:
            # sps = source.split('/', 1)
            # bk = sps[0].replace(':s3:','')
            # pr = f'{sps[1]}/' # trailing slash ensured
            trig, rest, done, notg = self._glacier_restore(buc, pre,
                                                           self.args.days, self.args.retrieveopt, recur)
            print('Triggered Glacier retrievals:', len(trig))
            print('Currently retrieving from Glacier:', len(rest))
            print('Retrieved from Glacier:', len(done))
            print('Not in Glacier:', len(notg))
            if len(trig) > 0 or len(rest) > 0:
                # glacier is still ongoing, return # of pending ops
                return len(trig)+len(rest)

        if self.args.nodownload:
            return -1

        rclone = Rclone(self.args, self.cfg)

        if recursive:
            print(f'Recursively copying files from archive to "{target}" ...')
            ret = rclone.copy(source, target)
        else:
            print(f'Copying files from archive to "{target}" ...')
            ret = rclone.copy(source, target, '--max-depth', '1')

        self.cfg.printdbg('*** RCLONE copy ret ***:\n', ret, '\n')
        # print ('Message:', ret['msg'].replace('\n',';'))
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Copying was not successful.')
            return False
            # lastError could contain: Object in GLACIER, restore first

        ttransfers = ret['stats']['totalTransfers']
        tbytes = ret['stats']['totalBytes']
        total = self.convert_size(tbytes)
        if self.args.debug:
            print('\n')
            print('Speed:', ret['stats']['speed'])
            print('Transfers:', ret['stats']['transfers'])
            print('Tot Transfers:', ret['stats']['totalTransfers'])
            print('Tot Bytes:', ret['stats']['totalBytes'])
            print('Tot Checks:', ret['stats']['totalChecks'])

        #   {'bytes': 0, 'checks': 0, 'deletedDirs': 0, 'deletes': 0, 'elapsedTime': 2.783003019,
        #    'errors': 1, 'eta': None, 'fatalError': False, 'lastError': 'directory not found',
        #    'renames': 0, 'retryError': True, 'speed': 0, 'totalBytes': 0, 'totalChecks': 0,
        #    'totalTransfers': 0, 'transferTime': 0, 'transfers': 0}
        # checksum

        if self._restore_verify(source, target, recursive):
            print(
                f'Target and archive are identical. {ttransfers} files with {total} transferred.')
        else:
            print(f'Problem: target and archive are NOT identical.')
            return False

        return -1

    def _restore_verify(self, source, target, recursive=False):
        # post download tasks like checksum verification and untarring
        rclone = Rclone(self.args, self.cfg)
        for root, dirs, files in self._walker(target):
            if not recursive and root != target:
                break
            restpath = root
            print(f'\n  Checking folder "{restpath}" ... ')
            if root != target:
                source = source + os.path.basename(root) + '/'
            try:

                # This needs to happen recursively
                tarred_files = self._get_tar_content(root)
                if len(tarred_files) > 0:
                    self._delete_tar_content(restpath, tarred_files)

                ret = self._gen_md5sums(restpath, '.froster-restored.md5sum')
                if ret == 13:  # cannot write to folder
                    return False
                hashfile = os.path.join(restpath, '.froster-restored.md5sum')
                ret = rclone.checksum(hashfile, source, '--max-depth', '1')
                self.cfg.printdbg('*** RCLONE checksum ret ***:\n', ret, '\n')
                if ret['stats']['errors'] > 0:
                    print('Last Error:', ret['stats']['lastError'])
                    print('Checksum test was not successful.')
                    return False

                ret = self._untar_files(restpath)

                if ret == 13:  # cannot write to folder
                    return False
                elif not ret:
                    print('  Could not create hashfile .froster-restored.md5sum.')
                    print('  Perhaps there are no files or the folder does not exist?')
                    return False

            except PermissionError as e:
                # Check if error number is 13 (Permission denied)
                if e.errno == 13:
                    print(f'Permission denied to "{restpath}"')
                    continue
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")
                    continue
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                continue
        return True

    def _glacier_restore(self, bucket, prefix, keep_days=30, ret_opt="Bulk", recursive=False):
        # this is dropping back to default creds, need to fix
        # print("AWS_ACCESS_KEY_ID:", os.environ['AWS_ACCESS_KEY_ID'])
        # print("AWS_PROFILE:", os.environ['AWS_PROFILE'])
        glacier_classes = {'GLACIER', 'DEEP_ARCHIVE'}
        try:
            # not needed here as profile comes from env
            # session = boto3.Session(profile_name=profile)
            # s3 = session.client('s3')
            s3 = boto3.client('s3')
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                print(f"Access denied for bucket '{bucket}'")
                print('Check your permissions and/or credentials.')
            else:
                print(f"An error occurred: {e}")
            return [], [], []
        triggered_keys = []
        restoring_keys = []
        restored_keys = []
        not_glacier_keys = []
        for page in pages:
            if not 'Contents' in page:
                continue
            for obj in page['Contents']:
                object_key = obj['Key']
                # Check if there are additional slashes after the prefix,
                # indicating that the object is in a subfolder.
                remaining_path = object_key[len(prefix):]
                if '/' in remaining_path and not recursive:
                    continue
                header = s3.head_object(Bucket=bucket, Key=object_key)
                if 'StorageClass' in header:
                    if not header['StorageClass'] in glacier_classes:
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
                    s3.restore_object(
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
                    self.cfg.printdbg(
                        f'Restore request initiated for {object_key} using {ret_opt} retrieval.')
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
                        print(
                            f'Restore is already in progress for {object_key}. Skipping...')
                        restoring_keys.append(object_key)
                    else:
                        print(f'Error occurred for {object_key}: {e}')
                except:
                    print(f'Restore request for {object_key} failed.')
        return triggered_keys, restoring_keys, restored_keys, not_glacier_keys

    def md5sumex(self, file_path):
        try:
            cmd = f'md5sum {file_path}'
            ret = subprocess.run(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, Shell=True)
            if ret.returncode != 0:
                print(f'md5sum return code > 0: {cmd} Error:\n{ret.stderr}')
            return ret.stdout.strip()  # , ret.stderr.strip()

        except Exception as e:
            print(f'md5sum Error: {str(e)}')
            return None, str(e)

    def md5sum(self, file_path):
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def uid2user(self, uid):
        # try to convert uid to user name
        try:
            return pwd.getpwuid(uid)[0]
        except:
            self.cfg.printdbg(f'uid2user: Error converting uid {uid}')
            return uid

    def gid2group(self, gid):
        # try to convert gid to group name
        try:
            return grp.getgrgid(gid)[0]
        except:
            self.cfg.printdbg(f'gid2group: Error converting gid {gid}')
            return gid

    def daysago(self, unixtime):
        # how many days ago is this epoch time ?
        if not unixtime:
            self.cfg.printdbg(
                'daysago: an integer is required (got type NoneType)')
            return 0
        diff = datetime.datetime.now()-datetime.datetime.fromtimestamp(unixtime)
        return diff.days

    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes/p, 3)
        return f"{s} {size_name[i]}"

    def _archive_json_put_row(self, path_name, row_dict):
        data = {}
        if os.path.exists(self.archive_json):
            with open(self.archive_json, 'r') as file:
                try:
                    data = json.load(file)
                # except json.JSONDecodeError:
                except:
                    print('Error in Archiver._archive_json_put_row():')
                    print(f'Cannot read {self.archive_json}, file corrupt?')
                    return None
        path_name = path_name.rstrip(os.path.sep)  # remove trailing slash
        # this is a key that can be changed
        row_dict['local_folder'] = path_name
        data[path_name] = row_dict
        with open(self.archive_json, 'w') as file:
            json.dump(data, file, indent=4)

    def archive_get_bucket_info(self, folder):
        # returns bucket(str), prefix(str), recursive(bool), glacier(bool)
        recursive = False
        glacier = False
        rowdict = self.archive_json_get_row(folder)
        self.cfg.printdbg(f'path: {folder} rowdict: {rowdict}')
        if rowdict == None:
            return None, None, recursive, glacier
        if 'archive_mode' in rowdict:
            if rowdict['archive_mode'] == "Recursive":
                recursive = True
        s3_storage_class = rowdict['s3_storage_class']
        if s3_storage_class in ['DEEP_ARCHIVE', 'GLACIER']:
            glacier = True
        sps = rowdict['archive_folder'].split('/', 1)
        bucket = sps[0].replace(':s3:', '')
        prefix = f'{sps[1]}/'  # trailing slash ensured
        return bucket, prefix, recursive, glacier

    def archive_json_get_row(self, path_name):
        # get an archive record
        if not os.path.exists(self.archive_json):
            self.cfg.printdbg(
                f'archive_json_get_row: {self.archive_json} does not exist')
            return None
        with open(self.archive_json, 'r') as file:
            try:
                data = json.load(file)
            # except json.JSONDecodeError:
            except:
                print('Error in Archiver._archive_json_get_row():')
                print(f'Cannot read {self.archive_json}, file corrupt?')
                return None
        path_name = path_name.rstrip(os.path.sep)  # remove trailing slash
        if path_name in data:
            data[path_name]['subdir'] = path_name
            return data[path_name]
        else:
            # perhaps we find the searched path in a parent folder
            trypath = path_name
            while len(trypath) > 1:
                trypath = os.path.dirname(trypath)
                if trypath in data:
                    data[trypath]['subdir'] = path_name
                    return data[trypath]
            self.cfg.printdbg(
                f'archive_json_get_row: {path_name} not found in {self.archive_json}')
            return None

    def archive_json_get_csv(self, columns):
        if not os.path.exists(self.archive_json):
            return None
        with open(self.archive_json, 'r') as file:
            try:
                data = json.load(file)
            # except json.JSONDecodeError:
            except:
                print('Error in Archiver._archive_json_get_csv():')
                print(f'Cannot read {self.archive_json}, file corrupt?')
                return None
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

    def _get_newest_file_atime(self, folder_path, folder_atime=None):
        # Because the folder atime is reset when crawling we need
        # to lookup the atime of the last accessed file in this folder
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            if self.args.debug and not self.args.pwalkcsv:
                print(f" Invalid folder path: {folder_path}")
            return folder_atime
        last_accessed_time = None
        try:
            subobjects = os.listdir(folder_path)
        except Exception as e:
            print(f'Error accessing folder {folder_path}:\n{e}')
            return folder_atime
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

    def _get_newest_file_mtime(self, folder_path, folder_mtime=None):
        # Because the folder atime is reset when crawling we need
        # to lookup the atime of the last modified file in this folder
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            if self.args.debug and not self.args.pwalkcsv:
                print(f" Invalid folder path: {folder_path}")
            return folder_mtime
        last_modified_time = None
        try:
            subobjects = os.listdir(folder_path)
        except Exception as e:
            print(f'Error accessing folder {folder_path}:\n{e}')
            return folder_mtime
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

    def _get_hotspots_path(self, folder):
        # get a full path name of a new hotspots file
        # based on a folder name that has been crawled
        hsfld = os.path.join(self.cfg.config_root, 'hotspots')
        os.makedirs(hsfld, exist_ok=True)
        return os.path.join(hsfld, self._get_hotspots_file(folder))

    def _get_hotspots_file(self, folder):
        # get a full path name of a new hotspots file
        # based on a folder name that has been crawled
        mountlist = self._get_mount_info()
        traildir = ''
        hsfile = folder.replace('/', '+') + '.csv'
        for mnt in mountlist:
            if folder.startswith(mnt['mount_point']):
                traildir = self._get_last_directory(
                    mnt['mount_point'])
                hsfile = folder.replace(mnt['mount_point'], '')
                hsfile = hsfile.replace('/', '+') + '.csv'
                hsfile = f'@{traildir}{hsfile}'
                if len(hsfile) > 255:
                    hsfile = f'{hsfile[:25]}.....{hsfile[-225:]}'
        return hsfile

    def _walker(self, top, skipdirs=['.snapshot',]):
        """ returns subset of os.walk  """
        for root, dirs, files in os.walk(top, topdown=True, onerror=self._walkerr):
            for skipdir in skipdirs:
                if skipdir in dirs:
                    dirs.remove(skipdir)  # don't visit this directory
            yield root, dirs, files

    def _walkerr(self, oserr):
        sys.stderr.write(str(oserr))
        sys.stderr.write('\n')
        return 0

    def _get_last_directory(self, path):
        # Remove any trailing slashes
        path = path.rstrip(os.path.sep)
        # Split the path by the separator
        path_parts = path.split(os.path.sep)
        # Return the last directory
        return path_parts[-1]

    def _get_mount_info(self, fs_types=None):
        file_path = '/proc/self/mountinfo'
        if fs_types is None:
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

    def download_restored_file(self, bucket_name, object_key, local_path):
        s3 = boto3.resource('s3')
        s3.Bucket(bucket_name).download_file(object_key, local_path)
        print(f'Downloaded {object_key} to {local_path}.')

    def _upload_file_to_s3(self, filename, bucket, object_name=None, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        s3 = session.client('s3')
        # If S3 object_name was not specified, use the filename
        if object_name is None:
            object_name = os.path.basename(filename)
        try:
            # Upload the file with Intelligent-Tiering storage class
            s3.upload_file(filename, bucket, object_name, ExtraArgs={
                           'StorageClass': 'INTELLIGENT_TIERING'})
            self.cfg.printdbg(
                f"File {object_name} uploaded to Intelligent-Tiering storage class!")
            # print(f"File {filename} uploaded successfully to Intelligent-Tiering storage class!")
        except Exception as e:
            print(f"An error occurred: {e}")
            return False
        return True


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

            # badfiles = arch.cannot_read_files(retline[5])
            # if badfiles:
            #     print(f'  Cannot read these files in folder {retline[5]}: {", ".join(badfiles)}')
            #     return False

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

    def __init__(self):
        super().__init__()
        self.myrow = []

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
        fh = open(SELECTEDFILE, 'r')
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


class TableArchive(App[list]):

    BINDINGS = [("q", "request_quit", "Quit")]

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
        rows = csv.reader(io.StringIO(TABLECSV))
        table.add_columns(*next(rows))
        table.add_rows(itertools.islice(rows, MAXHOTSPOTS))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))
        # self.push_screen(ScreenConfirm())

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
        yield Label("Enter search to link your data with metadata of an NIH grant/project")
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
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.rc = os.path.join(self.cfg.binfolderx, 'rclone')

    # ensure that file exists or nagging /home/dp/.config/rclone/rclone.conf

    # backup: rclone --verbose --files-from tmpfile --use-json-log copy --max-depth 1 ./tests/ :s3:posix-dp/tests4/ --exclude .froster.md5sum
    # restore: rclone --verbose --use-json-log copy --max-depth 1 :s3:posix-dp/tests4/ ./tests2
    # rclone copy --verbose --use-json-log --max-depth 1  :s3:posix-dp/tests5/ ./tests5
    # rclone --use-json-log checksum md5 ./tests/.froster.md5sum :s3:posix-dp/tests2/
    # storage tier for each file
    # rclone lsf --csv :s3:posix-dp/tests4/ --format=pT
    # list without subdir
    # rclone lsjson --metadata --no-mimetype --no-modtime --hash :s3:posix-dp/tests4
    # rclone checksum md5 ./tests/.froster.md5sum --verbose --use-json-log :s3:posix-dp/archive/home/dp/gh/froster/tests

    def _run_rc(self, command):

        command = self._add_opt(command, '--verbose')
        command = self._add_opt(command, '--use-json-log')

        self.cfg.printdbg('Rclone command:', " ".join(command))
        try:
            ret = subprocess.run(command, capture_output=True,
                                 text=True, env=self.cfg.envrn)
            if ret.returncode != 0:
                # pass
                sys.stderr.write(
                    f'*** Error, Rclone return code > 0:\n{ret.stderr} Command:\n{" ".join(command)}\n\n')
                # list of exit codes
                # 0 - success
                # 1 - Syntax or usage error
                # 2 - Error not otherwise categorised
                # 3 - Directory not found
                # 4 - File not found
                # 5 - Temporary error (one that more retries might fix) (Retry errors)
                # 6 - Less serious errors (like 461 errors from dropbox) (NoRetry errors)
                # 7 - Fatal error (one that more retries won't fix, like account suspended) (Fatal errors)
                # 8 - Transfer exceeded - limit set by --max-transfer reached
                # 9 - Operation successful, but no files transferred

            # lines = ret.stderr.decode('utf-8').splitlines() #needed if you do not use ,text=True
            # locked_dirs = '\n'.join([l for l in lines if "Locked Dir:" in l])
            # print("   STDOUT:",ret.stdout)
            # print("   STDERR:",ret.stderr)
            # rclone mount --daemon
            return ret.stdout.strip(), ret.stderr.strip()

        except Exception as e:
            print(f'\nRclone Error in _run_rc: {str(e)}, command run:')
            print(f" ".join(command))
            return None, str(e)

    def _run_bk(self, command):
        # command = self._add_opt(command, '--verbose')
        # command = self._add_opt(command, '--use-json-log')
        cmdline = " ".join(command)
        self.cfg.printdbg('Rclone command:', cmdline)
        try:
            ret = subprocess.Popen(command, preexec_fn=os.setsid, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, env=self.cfg.envrn)
            # _, stderr = ret.communicate(timeout=3)  # This does not work with rclone
            if ret.stderr:
                sys.stderr.write(
                    f'*** Error in command "{cmdline}":\n {ret.stderr} ')
            return ret.pid
        except Exception as e:
            print(f'Rclone Error: {str(e)}')
            return None

    def copy(self, src, dst, *args):
        command = [self.rc, 'copy'] + list(args)
        command.append(src)  # command.append(f'{src}/')
        command.append(dst)
        out, err = self._run_rc(command)
        if out:
            print(f'rclone copy output: {out}')
        # print('ret', err)
        stats, ops = self._parse_log(err)
        if stats:
            return stats[-1]  # return the stats
        else:
            st = {}
            st['stats'] = {}
            st['stats']['errors'] = 1
            st['stats']['lastError'] = err
            return st

    def checksum(self, md5file, dst, *args):
        # checksum md5 ./tests/.froster.md5sum
        command = [self.rc, 'checksum'] + list(args)
        command.append('md5')
        command.append(md5file)
        command.append(dst)
        # print("Command:", command)
        out, err = self._run_rc(command)
        if out:
            print(f'rclone checksum output: {out}')
        # print('ret', err)
        stats, ops = self._parse_log(err)
        if stats:
            return stats[-1]  # return the stats
        else:
            return []

    def mount(self, url, mountpoint, *args):
        if not shutil.which('fusermount3'):
            print('Could not find "fusermount3". Please install the "fuse3" OS package')
            return False
        if not url.endswith('/'):
            url+'/'
        mountpoint = mountpoint.rstrip(os.path.sep)
        command = [self.rc, 'mount'] + list(args)
        try:
            current_permissions = os.lstat(mountpoint).st_mode
            new_permissions = (current_permissions & ~0o07) | 0o05
            os.chmod(mountpoint, new_permissions)
        except:
            pass
        command.append('--allow-non-empty')
        command.append('--default-permissions')
        command.append('--read-only')
        command.append('--no-checksum')
        command.append('--quiet')
        command.append(url)
        command.append(mountpoint)
        pid = self._run_bk(command)
        return pid

    def unmount(self, mountpoint, wait=False):
        mountpoint = mountpoint.rstrip(os.path.sep)
        if self._is_mounted(mountpoint):
            if shutil.which('fusermount3'):
                cmd = ['fusermount3', '-u', mountpoint]
                ret = subprocess.run(
                    cmd, capture_output=False, text=True, env=self.cfg.envrn)
            else:
                rclone_pids = self._get_pids('rclone')
                fld_pids = self._get_pids(mountpoint, True)
                common_pids = [
                    value for value in rclone_pids if value in fld_pids]
                for pid in common_pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        if wait:
                            _, _ = os.waitpid(int(pid), 0)
                        return True
                    except PermissionError:
                        print(
                            f'Permission denied when trying to send signal SIGTERM to rclone process with PID {pid}.')
                    except Exception as e:
                        print(
                            f'An unexpected error occurred when trying to send signal SIGTERM to rclone process with PID {pid}: {e}')
        else:
            print(
                f'\nError: Folder {mountpoint} is currently not used as a mountpoint by rclone.')

    def version(self):
        command = [self.rc, 'version']
        return self._run_rc(command)

    def get_mounts(self):
        mounts = []
        with open('/proc/mounts', 'r') as f:
            for line in f:
                parts = line.split()
                mount_point, fs_type = parts[1], parts[2]
                if fs_type.startswith('fuse.rclone'):
                    mounts.append(mount_point)
        return mounts

    def _get_pids(self, process, full=False):
        process = process.rstrip(os.path.sep)
        if full:
            command = ['pgrep', '-f', process]
        else:
            command = ['pgrep', process]
        try:
            output = subprocess.check_output(command)
            pids = [int(pid) for pid in output.decode(
                errors='ignore').split('\n') if pid]
            return pids
        except subprocess.CalledProcessError:
            # No rclone processes found
            return []

    def _is_mounted(self, folder_path):
        # Resolve any symbolic links
        folder_path = os.path.realpath(folder_path)
        with open('/proc/mounts', 'r') as f:
            for line in f:
                parts = line.split()
                mount_point, fs_type = parts[1], parts[2]
                if mount_point == folder_path and fs_type.startswith('fuse.rclone'):
                    return True

    def _add_opt(self, cmd, option, value=None):
        if option in cmd:
            return cmd
        cmd.append(option)
        if value:
            cmd.append(value)
        return cmd

    def _parse_log(self, strstderr):
        lines = strstderr.split('\n')
        data = [json.loads(line.rstrip()) for line in lines if line[0] == "{"]
        stats = []
        operations = []
        for obj in data:
            if 'accounting/stats' in obj['source']:
                stats.append(obj)
            elif 'operations/operations' in obj['source']:
                operations.append(obj)
        return stats, operations

        # stats":{"bytes":0,"checks":0,"deletedDirs":0,"deletes":0,"elapsedTime":4.121489785,"errors":12,"eta":null,"fatalError":false,
        # "lastError":"failed to open source object: Object in GLACIER, restore first: bucket=\"posix-dp\", key=\"tests4/table_example.py\"",
        # "renames":0,"retryError":true,"speed":0,"totalBytes":0,"totalChecks":0,"totalTransfers":0,"transferTime":0,"transfers":0},
        # "time":"2023-04-16T10:18:46.121921-07:00"}


class SlurmEssentials:
    # exit code 64 causes Slurm to --requeue, e.g. sys.exit(64)
    def __init__(self, args, cfg):
        self.script_lines = ["#!/bin/bash"]
        self.cfg = cfg
        self.args = args
        self.squeue_output_format = '"%i","%j","%t","%M","%L","%D","%C","%m","%b","%R"'
        self.jobs = []
        self.job_info = {}
        self.partition = cfg.read('hpc', 'slurm_partition')
        self.qos = cfg.read('hpc', 'slurm_qos')
        self.walltime = cfg.read('hpc', 'slurm_walltime', '7-0')
        self._add_lines_from_cfg()

    def add_line(self, line):
        if line:
            self.script_lines.append(line)

    def get_future_start_time(self, add_hours):
        now = datetime.datetime.now()
        future_time = now + datetime.timedelta(hours=add_hours)
        return future_time.strftime("%Y-%m-%dT%H:%M")

    def _add_lines_from_cfg(self):
        slurm_lscratch = self.cfg.read('hpc', 'slurm_lscratch')
        lscratch_mkdir = self.cfg.read('hpc', 'lscratch_mkdir')
        lscratch_root = self.cfg.read('hpc', 'lscratch_root')
        if slurm_lscratch:
            self.add_line(f'#SBATCH {slurm_lscratch}')
        self.add_line(f'{lscratch_mkdir}')
        if lscratch_root:
            self.add_line('export TMPDIR=%s/${SLURM_JOB_ID}' % lscratch_root)

    def _reorder_sbatch_lines(self, script_buffer):
        # we need to make sure that all #BATCH are at the top
        script_buffer.seek(0)
        lines = script_buffer.readlines()
        # Remove the shebang line from the list of lines
        shebang_line = lines.pop(0)
        sbatch_lines = [line for line in lines if line.startswith("#SBATCH")]
        non_sbatch_lines = [
            line for line in lines if not line.startswith("#SBATCH")]
        reordered_script = io.StringIO()
        reordered_script.write(shebang_line)
        for line in sbatch_lines:
            reordered_script.write(line)
        for line in non_sbatch_lines:
            reordered_script.write(line)
        # add a local scratch teardown, if configured
        reordered_script.write(self.cfg.read('hpc', 'lscratch_rmdir'))
        reordered_script.seek(0)
        return reordered_script

    def sbatch(self):
        script = io.StringIO()
        for line in self.script_lines:
            script.write(line + "\n")
        script.seek(0)
        oscript = self._reorder_sbatch_lines(script)
        result = subprocess.run(["sbatch"], text=True, shell=True, input=oscript.read(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            if 'Invalid generic resource' in result.stderr:
                print('Invalid generic resource request. Please remove or change file:')
                print(os.path.join(self.config_root, 'hpc', 'slurm_lscratch'))
            else:
                raise RuntimeError(
                    f"Error running sbatch: {result.stderr.strip()}")
            sys.exit(1)
        job_id = int(result.stdout.split()[-1])
        if args.debug:
            oscript.seek(0)
            with open(f'submitted-{job_id}.sh', "w", encoding="utf-8") as file:
                file.write(oscript.read())
                print(f' Debug script created: submitted-{job_id}.sh')
        return job_id

    def squeue(self):
        result = subprocess.run(["squeue", "--me", "-o", self.squeue_output_format],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Error running squeue: {result.stderr.strip()}")
        self.jobs = self._parse_squeue_output(result.stdout.strip())

    def _parse_squeue_output(self, output):
        csv_file = io.StringIO(output)
        reader = csv.DictReader(csv_file, delimiter=',',
                                quotechar='"', skipinitialspace=True)
        jobs = [row for row in reader]
        return jobs

    def print_jobs(self):
        for job in self.jobs:
            print(job)

    def job_comment_read(self, job_id):
        jobdict = self._scontrol_show_job(job_id)
        return jobdict['Comment']

    def job_comment_write(self, job_id, comment):
        # a comment can be maximum 250 characters, will be chopped automatically
        args = ['update', f'JobId={str(job_id)}',
                f'Comment={comment}', str(job_id)]
        result = subprocess.run(['scontrol'] + args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Error running scontrol: {result.stderr.strip()}")

    def _scontrol_show_job(self, job_id):
        args = ["--oneliner", "show", "job", str(job_id)]
        result = subprocess.run(['scontrol'] + args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Error running scontrol: {result.stderr.strip()}")
        self.job_info = self._parse_scontrol_output(result.stdout)

    def _parse_scontrol_output(self, output):
        fields = output.strip().split()
        job_info = {}
        for field in fields:
            key, value = field.split('=', 1)
            job_info[key] = value
        return job_info

    def _parse_tabular_data(self, data_str, separator="|"):
        """Parse data (e.g. acctmgr) presented in a tabular format into a list of dictionaries."""
        lines = data_str.strip().splitlines()
        headers = lines[0].split(separator)
        data = []
        for line in lines[1:]:
            values = line.split(separator)
            data.append(dict(zip(headers, values)))
        return data

    def _parse_partition_data(self, data_str):
        """Parse data presented in a tabular format into a list of dictionaries."""
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

    def _get_user_groups(self):
        """Get the groups the current Unix user is a member of."""
        groups = [grp.getgrgid(gid).gr_name for gid in os.getgroups()]
        return groups

    def _get_output(self, command):
        """Execute a shell command and return its output."""
        result = subprocess.run(command, shell=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(
                f"Error running {command}: {result.stderr.strip()}")
        return result.stdout.strip()

    def _get_default_account(self):
        return self._get_output(f'sacctmgr --noheader --parsable2 show user {self.cfg.whoami} format=DefaultAccount')

    def _get_associations(self):
        mystr = self._get_output(
            f"sacctmgr show associations where user={self.cfg.whoami} format=Account,QOS --parsable2")
        asso = {item['Account']: item['QOS'].split(
            ",") for item in self._parse_tabular_data(mystr) if 'Account' in item}
        return asso

    def get_allowed_partitions_and_qos(self, account=None):
        """Get a dictionary with keys = partitions and values = QOSs the user is allowed to use."""
        bacc = os.environ.get('SBATCH_ACCOUNT', '')
        account = bacc if bacc else account
        sacc = os.environ.get('SLURM_ACCOUNT', '')
        account = sacc if sacc else account
        allowed_partitions = {}
        partition_str = self._get_output("scontrol show partition --oneliner")
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
                    allowed_qos = [q for q in account_qos if q in p_allowedqos]
                    # print(f"p_allowedqos: allowed_qos in {pname}:", allowed_qos)
                else:
                    allowed_qos = []
                    # print(f"p_allowedqos = [] in {pname}:", allowed_qos)
                allowed_partitions[pname] = allowed_qos
        return allowed_partitions

    def display_job_info(self):
        print(self.job_info)


class NIHReporter:
    # if we use --nih as an argument we query NIH Reporter
    # for metadata

    def __init__(self, verbose=False, active=False, years=None):
        # self.args = args
        self.verbose = verbose
        self.active = active
        self.years = years
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.exclude_fields = ['Terms', 'AbstractText',
                               'PhrText']  # pref_terms still included
        self.grants = []

    def search_full(self, searchstr):
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
        searchstr = self._clean_string(searchstr)
        self._post_request(criteria)
        return self._result_sets(header)

    def _is_number(self, string):
        try:
            float(string)
            return True
        except ValueError:
            return False

    def _clean_string(self, mystring):
        mychars = ",:?'$^%&*!`~+={}\\[]"+'"'
        for i in mychars:
            mystring = mystring.replace(i, ' ')
            # print('mystring:', mystring)
        return mystring

    def _post_request(self, criteria):
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
        # raise Exception(f"Failed to complete POST request after {max_retries} attempts")

    def _result_sets(self, header=False):
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
            # print(g)
        # print("{0} total # of grants...".format(len(grants)),file=sys.stderr)
        return sets


class AWSBoto:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as
    # multi-line files and dictionaries which are written to json

    def __init__(self, args, cfg, arch):
        self.args = args
        self.cfg = cfg
        self.arch = arch
        self.awsprofile = self.cfg.awsprofile

    def get_aws_regions(self, profile=None, provider='AWS'):
        # returns a list of AWS regions
        if provider == 'AWS':
            try:
                session = boto3.Session(
                    profile_name=profile) if profile else boto3.Session()
                regions = session.get_available_regions('ec2')
                # make the list a little shorter
                regions = [i for i in regions if not i.startswith('ap-')]
                return sorted(regions, reverse=True)
            except:
                return ['us-west-2', 'us-west-1', 'us-east-1', '']
        elif provider == 'GCS':
            return ['us-west1', 'us-east1', '']
        elif provider == 'Wasabi':
            return ['us-west-1', 'us-east-1', '']
        elif provider == 'IDrive':
            return ['us-or', 'us-va', 'us-la', '']
        elif provider == 'Ceph':
            return ['default-placement', 'us-east-1', '']

    def check_bucket_access_folders(self, folders, readwrite=False):
        # check all the buckets that have been used for archiving
        sufficient = True
        myaccess = 'read'
        if readwrite:
            myaccess = 'write'
        buckets = []
        for folder in folders:
            bucket, *_ = self.arch.archive_get_bucket_info(folder)
            if bucket:
                buckets.append(bucket)
            else:
                print(f'Error: No archive config found for folder {folder}')
                sufficient = False
        buckets = list(set(buckets))  # remove dups
        for bucket in buckets:
            if not self.check_bucket_access(bucket, readwrite):
                print(f' You have no {myaccess} access to bucket "{bucket}" !')
                sufficient = False
        return sufficient

    def check_bucket_access(self, bucket_name, readwrite=False, profile=None):

        if not bucket_name:
            print('check_bucket_access: bucket_name empty. You may have not yet configured a S3 bucket name. Please run "froster config" first')
            sys.exit(1)
        if not self._check_s3_credentials(profile):
            print('_check_s3_credentials failed. Please edit file ~/.aws/credentials')
            return False
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ep_url = self.cfg._get_aws_s3_session_endpoint_url(profile)
        s3 = session.client('s3', endpoint_url=ep_url)

        try:
            # Check if bucket exists
            s3.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                print(
                    f"Error: Access denied to bucket {bucket_name} for profile {self.awsprofile}. Check your permissions.")
            elif error_code == '404':
                print(
                    f"Error: Bucket {bucket_name} does not exist in profile {self.awsprofile}.")
                print("run 'froster config' to create this bucket.")
            else:
                print(
                    f"Error accessing bucket {bucket_name} in profile {self.awsprofile}: {e}")
            return False
        except Exception as e:
            print(
                f"An unexpected error in function check_bucket_access for profile {self.awsprofile}: {e}")
            return False

        if not readwrite:
            return True

        # Test write access by uploading a small test file
        try:
            test_object_key = "test_write_access.txt"
            s3.put_object(Bucket=bucket_name, Key=test_object_key,
                          Body="Test write access")
            # print(f"Successfully wrote test to {bucket_name}")

            # Clean up by deleting the test object
            s3.delete_object(Bucket=bucket_name, Key=test_object_key)
            # print(f"Successfully deleted test object from {bucket_name}")
            return True
        except botocore.exceptions.ClientError as e:
            print(
                f"Error: cannot write to bucket {bucket_name} in profile {self.awsprofile}: {e}")
            return False

    def create_s3_bucket(self, bucket_name, profile=None):
        if not self._check_s3_credentials(profile, verbose=True):
            print(
                f"Cannot create bucket '{bucket_name}' with these credentials")
            print('check_s3_credentials failed. Please edit file ~/.aws/credentials')
            return False
        region = self.cfg.get_aws_region(profile)
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ep_url = self.cfg._get_aws_s3_session_endpoint_url(profile)
        s3_client = session.client('s3', endpoint_url=ep_url)
        existing_buckets = s3_client.list_buckets()
        for bucket in existing_buckets['Buckets']:
            if bucket['Name'] == bucket_name:
                self.cfg.printdbg(f'S3 bucket {bucket_name} exists')
                return True
        try:
            if region and region != 'default-placement':
                response = s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )
            else:
                response = s3_client.create_bucket(
                    Bucket=bucket_name,
                )
            print(f"Created S3 Bucket '{bucket_name}'")
        except botocore.exceptions.BotoCoreError as e:
            print(f"BotoCoreError: {e}")
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidBucketName':
                print(f"Error: Invalid bucket name '{bucket_name}'\n{e}")
            elif error_code == 'BucketAlreadyExists':
                pass
                # print(f"Error: Bucket '{bucket_name}' already exists.")
            elif error_code == 'BucketAlreadyOwnedByYou':
                pass
                # print(f"Error: You already own a bucket named '{bucket_name}'.")
            elif error_code == 'InvalidAccessKeyId':
                # pass
                print(
                    "Error: InvalidAccessKeyId. The AWS Access Key Id you provided does not exist in our records")
            elif error_code == 'SignatureDoesNotMatch':
                pass
                # print("Error: Invalid AWS Secret Access Key.")
            elif error_code == 'AccessDenied':
                print(
                    "Error: Access denied. Check your account permissions for creating S3 buckets")
            elif error_code == 'IllegalLocationConstraintException':
                print(f"Error: The specified region '{region}' is not valid.")
            else:
                print(f"ClientError: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False
        encryption_configuration = {
            'Rules': [
                {
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': 'AES256'
                    }
                }
            ]
        }
        try:
            response = s3_client.put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration=encryption_configuration
            )
            print(f"Applied AES256 encryption to S3 bucket '{bucket_name}'")
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidBucketName':
                print(f"Error: Invalid bucket name '{bucket_name}'\n{e}")
            elif error_code == 'AccessDenied':
                print(
                    "Error: Access denied. Check your account permissions for creating S3 buckets")
            elif error_code == 'IllegalLocationConstraintException':
                print(f"Error: The specified region '{region}' is not valid.")
            elif error_code == 'InvalidLocationConstraint':
                if not ep_url:
                    # do not show this error with non AWS endpoints
                    print(
                        f"Error: The specified location-constraint '{region}' is not valid")
            else:
                print(f"ClientError: {e}")
        except Exception as e:
            print(f"An unexpected error occurred in create_s3_bucket: {e}")
            return False
        return True

    def _check_s3_credentials(self, profile=None, verbose=False):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        try:
            if verbose or self.args.debug:
                self.cfg.printdbg(
                    f'  Checking credentials for profile "{profile}" ... ', end='')
            ep_url = self.cfg._get_aws_s3_session_endpoint_url(profile)
            s3_client = session.client('s3', endpoint_url=ep_url)
            s3_client.list_buckets()
            if verbose or self.args.debug:
                print('Done.')
        # return True
        # try:
        #    pass
        except botocore.exceptions.NoCredentialsError:
            print(
                "No AWS credentials found. Please check your access key and secret key.")
        except botocore.exceptions.EndpointConnectionError:
            print(
                "Unable to connect to the AWS S3 endpoint. Please check your internet connection.")
        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            # error_code = e.response['Error']['Code']
            if error_code == 'RequestTimeTooSkewed':
                print(
                    f"The time difference between S3 storage and your computer is too high:\n{e}")
            elif error_code == 'InvalidAccessKeyId':
                print(
                    f"Error: Invalid AWS Access Key ID in profile {profile}:\n{e}")
                print(
                    f"Fix your credentials in ~/.aws/credentials for profile {profile}")
            elif error_code == 'SignatureDoesNotMatch':
                if "Signature expired" in str(e):
                    print(
                        f"Error: Signature expired. The system time of your computer is likely wrong:\n{e}")
                    return False
                else:
                    print(
                        f"Error: Invalid AWS Secret Access Key in profile {profile}:\n{e}")
            elif error_code == 'InvalidClientTokenId':
                print(f"Error: Invalid AWS Access Key ID or Secret Access Key !")
                print(
                    f"Fix your credentials in ~/.aws/credentials for profile {profile}")
            else:
                print(
                    f"Error validating credentials for profile {profile}: {e}")
                print(
                    f"Fix your credentials in ~/.aws/credentials for profile {profile}")
            return False
        except Exception as e:
            print(
                f"An unexpected Error in _check_s3_credentials with profile {profile}: {e}")
            sys.exit(1)
        return True

    def _get_s3_data_size(self, folders, profile=None):
        """
        Get the size of data in GiB aggregated from multiple 
        S3 buckets from froster archives identified by a 
        list of folders 

        :return: Size of the data in GiB.
        """
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        s3 = session.client('s3')

        # Initialize total size
        total_size_bytes = 0

        # bucket_name, prefix, recursive=False
        for fld in folders:
            buc, pre, recur, _ = self.arch.archive_get_bucket_info(fld)
            # returns bucket(str), prefix(str), recursive(bool), glacier(bool)
            # Use paginator to handle buckets with large number of objects
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=buc, Prefix=pre):
                if "Contents" in page:  # Ensure there are objects under the specified prefix
                    for obj in page['Contents']:
                        key = obj['Key']
                        if recur or (key.count('/') == pre.count('/') and key.startswith(pre)):
                            total_size_bytes += obj['Size']

        total_size_gib = total_size_bytes / (1024 ** 3)  # Convert bytes to GiB
        return total_size_gib

    def ec2_deploy(self, folders, s3size=None, awsprofile=None):

        if not awsprofile:
            awsprofile = self.cfg.awsprofile
        if s3size != 0:
            s3size = self._get_s3_data_size(folders, awsprofile)
        print(f"Total data in all folders: {s3size:.2f} GiB")
        prof = self._ec2_create_iam_policy_roles_ec2profile()
        iid, ip = self._ec2_create_instance(s3size, prof, awsprofile)
        print(' Waiting for ssh host to become ready ...')
        if not self.cfg.wait_for_ssh_ready(ip):
            return False

        bootstrap_restore = self._ec2_user_space_script(iid)

        # part 2, prep restoring .....
        for folder in args.folders:
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
        if not '--profile' in cmdlist and self.args.awsprofile:
            cmdlist.insert(1, '--profile')
            cmdlist.insert(2, self.args.awsprofile)
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

        archive_json = os.path.join(
            self.cfg.config_root, 'froster-archives.json')
        ret = self.ssh_upload(
            'ec2-user', ip, archive_json, "~/.config/froster/")
        if ret.stdout or ret.stderr:
            print(ret.stdout, ret.stderr)

        self.send_email_ses('', '', 'Froster restore on EC2',
                            f'this command line was executed on host {ip}:\n{cmdline}')

    def _ec2_create_or_get_iam_policy(self, pol_name, pol_doc, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        iam = session.client('iam')

        policy_arn = None
        try:
            response = iam.create_policy(
                PolicyName=pol_name,
                PolicyDocument=json.dumps(pol_doc)
            )
            policy_arn = response['Policy']['Arn']
            print(f"Policy created with ARN: {policy_arn}")
        except iam.exceptions.EntityAlreadyExistsException as e:
            policies = iam.list_policies(Scope='Local')
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
                self.cfg.printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)
        return policy_arn

    def _ec2_create_froster_iam_policy(self, profile=None):
        # Initialize session with specified profile or default
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()

        # Create IAM client
        iam = session.client('iam')

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
        user = iam.get_user()
        user_name = user['User']['UserName']

        # Check if policy already exists for the user
        existing_policies = iam.list_user_policies(UserName=user_name)
        if policy_name in existing_policies['PolicyNames']:
            print(f"{policy_name} already exists for user {user_name}.")
            return

        # Create policy for user
        iam.put_user_policy(
            UserName=user_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )

        print(
            f"Policy {policy_name} attached successfully to user {user_name}.")

    def _ec2_create_iam_policy_roles_ec2profile(self, profile=None):
        # create all the IAM requirement to allow an ec2 instance to
        # 1. self destruct, 2. monitor cost with CE and 3. send emails via SES
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        iam = session.client('iam')

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
            policy_name, policy_document, profile)

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
            iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Froster role allows Billing, SES and Terminate'
            )
        except iam.exceptions.EntityAlreadyExistsException:
            print(f'Role {role_name} already exists.')
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)

        # 2. Attach permissions policies to the IAM role
        cost_explorer_policy = "arn:aws:iam::aws:policy/AWSBillingReadOnlyAccess"
        ses_policy = "arn:aws:iam::aws:policy/AmazonSESFullAccess"

        try:

            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=cost_explorer_policy
            )

            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=ses_policy
            )

            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=destruct_policy_arn
            )
        except iam.exceptions.PolicyNotAttachableException as e:
            print(
                f"Policy {e.policy_arn} is not attachable. Please check your permissions.")
            return False
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
                    f'Access denied! Please check your IAM permissions. \n   Error: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print('Other Error:', e)
            return False
        # 3. Create an instance profile and associate it with the role
        instance_profile_name = "FrosterEC2Profile"
        try:
            iam.create_instance_profile(
                InstanceProfileName=instance_profile_name
            )
            iam.add_role_to_instance_profile(
                InstanceProfileName=instance_profile_name,
                RoleName=role_name
            )
        except iam.exceptions.EntityAlreadyExistsException:
            print(f'Profile {instance_profile_name} already exists.')
            return instance_profile_name
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
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

    def _ec2_create_and_attach_security_group(self, instance_id, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ec2 = session.resource('ec2')
        client = session.client('ec2')

        group_name = 'SSH-HTTP-ICMP'

        # Check if security group already exists
        security_groups = client.describe_security_groups(
            Filters=[{'Name': 'group-name', 'Values': [group_name]}])
        if security_groups['SecurityGroups']:
            security_group_id = security_groups['SecurityGroups'][0]['GroupId']
        else:
            # Create security group
            response = client.create_security_group(
                GroupName=group_name,
                Description='Allows SSH and ICMP inbound traffic'
            )
            security_group_id = response['GroupId']

            # Allow ports 22, 80, 443, 8000-9000, ICMP
            client.authorize_security_group_ingress(
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
        instance = ec2.Instance(instance_id)
        current_security_groups = [sg['GroupId']
                                   for sg in instance.security_groups]

        # Check if the security group is already attached to the instance
        if security_group_id not in current_security_groups:
            current_security_groups.append(security_group_id)
            instance.modify_attribute(Groups=current_security_groups)

        return security_group_id

    def _ec2_get_latest_amazon_linux2_ami(self, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ec2_client = session.client('ec2')

        response = ec2_client.describe_images(
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
        long_timezone = self.cfg.get_time_zone()
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
        emailaddr = self.cfg.read('general', 'email')
        # short_timezone = datetime.datetime.now().astimezone().tzinfo
        long_timezone = self.cfg.get_time_zone()
        return textwrap.dedent(f'''
        #! /bin/bash
        mkdir -p ~/.config/froster
        sleep 3 # give us some time to upload json to ~/.config/froster
        echo 'PS1="\\u@froster:\\w$ "' >> ~/.bashrc
        echo '#export EC2_INSTANCE_ID={instance_id}' >> ~/.bashrc
        echo '#export AWS_DEFAULT_REGION={self.cfg.aws_region}' >> ~/.bashrc
        echo '#export TZ={long_timezone}' >> ~/.bashrc
        echo '#alias singularity="apptainer"' >> ~/.bashrc
        cd /tmp
        curl https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh | bash 
        froster config --monitor '{emailaddr}'
        aws configure set aws_access_key_id {os.environ['AWS_ACCESS_KEY_ID']}
        aws configure set aws_secret_access_key {os.environ['AWS_SECRET_ACCESS_KEY']}
        aws configure set region {self.cfg.aws_region}
        aws configure --profile {self.cfg.awsprofile} set aws_access_key_id {os.environ['AWS_ACCESS_KEY_ID']}
        aws configure --profile {self.cfg.awsprofile} set aws_secret_access_key {os.environ['AWS_SECRET_ACCESS_KEY']}
        aws configure --profile {self.cfg.awsprofile} set region {self.cfg.aws_region}
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

    def _ec2_create_instance(self, required_space, iamprofile=None, profile=None):
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

        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ec2 = session.resource('ec2')
        client = session.client('ec2')

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
        key_path = os.path.join(self.cfg.config_root,
                                'cloud', f'{self.cfg.ssh_key_name}.pem')
        if not os.path.exists(key_path):
            try:
                client.describe_key_pairs(KeyNames=[self.cfg.ssh_key_name])
                # If the key pair exists, delete it
                client.delete_key_pair(KeyName=self.cfg.ssh_key_name)
            except client.exceptions.ClientError:
                # Key pair doesn't exist in AWS, no need to delete
                pass
            key_pair = ec2.create_key_pair(KeyName=self.cfg.ssh_key_name)
            os.makedirs(os.path.join(
                self.cfg.config_root, 'cloud'), exist_ok=True)
            with open(key_path, 'w') as key_file:
                key_file.write(key_pair.key_material)
            os.chmod(key_path, 0o640)  # Set file permission to 600

        mykey_path = os.path.join(
            self.cfg.config_root, 'cloud', f'{self.cfg.ssh_key_name}-{self.cfg.whoami}.pem')
        if not os.path.exists(mykey_path):
            shutil.copyfile(key_path, mykey_path)
            os.chmod(mykey_path, 0o600)  # Set file permission to 600

        imageid = self._ec2_get_latest_amazon_linux2_ami(profile)
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
            instance = ec2.create_instances(
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
            ec2.create_tags(Resources=[instance_id], Tags=[tag])
        except Exception as e:
            self.cfg.printdbg('Error creating Tags: {e}')

        print(f'Launching instance {instance_id} ... please wait ...')

        max_wait_time = 300  # seconds
        delay_time = 10  # check every 10 seconds, adjust as needed
        max_attempts = max_wait_time // delay_time

        waiter = client.get_waiter('instance_running')
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
            instance_id, profile)
        if grpid:
            print(f'Security Group "{grpid}" attached.')
        else:
            print('No Security Group ID created.')
        instance.wait_until_running()
        print(f'Instance IP: {instance.public_ip_address}')

        self.cfg.write('cloud', 'ec2_last_instance',
                       instance.public_ip_address)

        return instance_id, instance.public_ip_address

    def ec2_terminate_instance(self, ip, profile=None):
        # terminate instance
        # with ephemeral (local) disk for a temporary restore

        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ec2 = session.client('ec2')
        # ips = self.ec2_list_ips(self, 'Name', 'FrosterSelfDestruct')
        # Use describe_instances with a filter for the public IP address to find the instance ID
        filters = [{
            'Name': 'network-interface.addresses.association.public-ip',
            'Values': [ip]
        }]

        if not ip.startswith('i-'):  # this an ip and not an instance ID
            try:
                response = ec2.describe_instances(Filters=filters)
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
        ec2.terminate_instances(InstanceIds=[instance_id])

        print(f"EC2 Instance {instance_id} ({ip}) is being terminated !")

    def ec2_list_instances(self, tag_name, tag_value, profile=None):
        """
        List all IP addresses of running EC2 instances with a specific tag name and value.
        :param tag_name: The name of the tag
        :param tag_value: The value of the tag
        :return: List of IP addresses
        """
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ec2 = session.client('ec2')

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
            response = ec2.describe_instances(Filters=filters)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
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
        key_path = os.path.join(self.cfg.config_root,
                                'cloud', f'{self.cfg.ssh_key_name}.pem')
        mykey_path = os.path.join(
            self.cfg.config_root, 'cloud', f'{self.cfg.ssh_key_name}-{self.cfg.whoami}.pem')
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
            except:
                print(f'Error executing "{cmd}."')
        else:
            subprocess.run(cmd, shell=True, capture_output=False, text=True)
        self.cfg.printdbg(f'ssh command line: {cmd}')
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
        except:
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
        except:
            print(f'Error executing "{cmd}."')
        return None

    def send_email_ses(self, sender, to, subject, body, profile=None):
        # Using AWS ses service to send emails
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        ses = session.client("ses")

        ses_verify_requests_sent = []
        if not sender:
            sender = self.cfg.read('general', 'email')
        if not to:
            to = self.cfg.read('general', 'email')
        if not to or not sender:
            print('from and to email addresses cannot be empty')
            return False
        ret = self.cfg.read('cloud', 'ses_verify_requests_sent')
        if isinstance(ret, list):
            ses_verify_requests_sent = ret
        else:
            ses_verify_requests_sent.append(ret)

        verified_email_addr = []
        try:
            response = ses.list_verified_email_addresses()
            verified_email_addr = response.get('VerifiedEmailAddresses', [])
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print(f'Other Error: {e}')

        checks = [sender, to]
        checks = list(set(checks))  # remove duplicates
        checked = []

        try:
            for check in checks:
                if check not in verified_email_addr and check not in ses_verify_requests_sent:
                    response = ses.verify_email_identity(EmailAddress=check)
                    checked.append(check)
                    print(
                        f'{check} was used for the first time, verification email sent.')
                    print(
                        'Please have {check} check inbox and confirm email from AWS.\n')

        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                self.cfg.printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
            else:
                print(f'Client Error: {e}')
        except Exception as e:
            print(f'Other Error: {e}')

        self.cfg.write('cloud', 'ses_verify_requests_sent', checked)
        try:
            response = ses.send_email(
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
                self.cfg.printdbg(
                    f'Access denied to SES advanced features! Please check your IAM permissions. \nError: {e}')
                if not args.debug:
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

    def send_ec2_costs(self, instance_id, profile=None):
        pass

    def _ec2_create_iam_costexplorer_ses(self, instance_id, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        iam = session.client('iam')
        ec2 = session.client('ec2')

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
            policy_name, policy_document, profile)

        # Step 2: Retrieve the IAM instance profile attached to the EC2 instance
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance_data = response['Reservations'][0]['Instances'][0]
        if 'IamInstanceProfile' not in instance_data:
            print(
                f"No IAM Instance Profile attached to the instance: {instance_id}")
            return False

        instance_profile_arn = response['Reservations'][0]['Instances'][0]['IamInstanceProfile']['Arn']

        # Extract the instance profile name from its ARN
        instance_profile_name = instance_profile_arn.split('/')[-1]

        # Step 3: Fetch the role name from the instance profile
        response = iam.get_instance_profile(
            InstanceProfileName=instance_profile_name)
        role_name = response['InstanceProfile']['Roles'][0]['RoleName']

        # Step 4: Attach the desired policy to the role
        try:
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            print(f"Policy {policy_arn} attached to role {role_name}")
        except iam.exceptions.NoSuchEntityException:
            print(f"Role {role_name} does not exist!")
        except iam.exceptions.InvalidInputException as e:
            print(f"Invalid input: {e}")
        except Exception as e:
            print(f"Other Error: {e}")

    def _ec2_create_iam_self_destruct_role(self, profile):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()
        iam = session.client('iam')

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
            policy_name, policy_document, profile)

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
            iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_relationship),
                Description='Allows EC2 instances to call AWS services on your behalf.'
            )
        except iam.exceptions.EntityAlreadyExistsException:
            print('IAM SelfDestructRole already exists.')

        iam.attach_role_policy(
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

    def monitor_ec2(self):

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
                self.send_email_ses(
                    "", "", f'Terminating idle instance {public_ip} ({instance_id})', body_text)
                self.ec2_terminate_instance(public_ip)
                return True
            else:
                print('Could not retrieve metadata (IP)')
                return False

        current_time = datetime.datetime.now().time()
        start_time = datetime.datetime.strptime("23:00:00", "%H:%M:%S").time()
        end_time = datetime.datetime.strptime("23:59:59", "%H:%M:%S").time()
        if start_time >= current_time or current_time > end_time:
            # only run cost emails once a day
            return True

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
        self.send_email_ses(
            "", "", f'Froster AWS cost report ({instance_id})', body_text)

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

    def _monitor_get_ec2_costs(self, profile=None):
        session = boto3.Session(
            profile_name=profile) if profile else boto3.Session()

        # Set up boto3 client for Cost Explorer
        ce = session.client('ce')
        sts = session.client('sts')

        # Identify current user/account
        identity = sts.get_caller_identity()
        user_arn = identity['Arn']
        # Check if it's the root user
        is_root = ":root" in user_arn

        # Dates for the current month and the last 24 hours
        today = datetime.datetime.today()
        first_day_of_month = datetime.datetime(
            today.year, today.month, 1).date()
        yesterday = (today - datetime.timedelta(days=1)).date()

        # Fetch EC2 cost of the current month
        monthly_response = ce.get_cost_and_usage(
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
            user_monthly_response = ce.get_cost_and_usage(
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
        daily_response = ce.get_cost_and_usage(
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
            user_daily_response = ce.get_cost_and_usage(
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


class ConfigManager:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as
    # multi-line files and dictionaries which are written to json

    def __init__(self, args):
        self.args = args
        self.home_dir = os.path.expanduser('~')
        self.config_root_local = os.path.join(
            self.home_dir, '.config', 'froster')
        os.makedirs(self.config_root_local, exist_ok=True)
        self.config_root = self._get_config_root()
        self.binfolder = self.read(
            'general', 'binfolder').replace(self.home_dir, '~')
        self.binfolderx = os.path.expanduser(self.binfolder)
        self.nih = self.read('general', 'prompt_nih_reporter')
        self.homepaths = self._get_home_paths()
        self.awscredsfile = os.path.join(self.home_dir, '.aws', 'credentials')
        self.awsconfigfile = os.path.join(self.home_dir, '.aws', 'config')
        self.awsconfigfileshr = os.path.join(self.config_root, 'aws_config')
        self.bucket = self.read('general', 'bucket')
        self.archiveroot = self.read('general', 'archiveroot')
        self.archivepath = os.path.join(
            self.bucket,
            self.archiveroot,)
        self.awsprofile = os.getenv('AWS_PROFILE', 'default')
        profs = self.get_aws_profiles()
        if "aws" in profs:
            self.awsprofile = os.getenv('AWS_PROFILE', 'aws')
        elif "AWS" in profs:
            self.awsprofile = os.getenv('AWS_PROFILE', 'AWS')
        if hasattr(self.args, "awsprofile") and args.awsprofile:
            self.awsprofile = self.args.awsprofile
        self.aws_region = self.get_aws_region(self.awsprofile)
        self.envrn = os.environ.copy()
        if not self._set_env_vars(self.awsprofile):
            self.awsprofile = ''
        self.ssh_key_name = 'froster-ec2'
        self.whoami = getpass.getuser()

    def _set_env_vars(self, profile):

        # Read the credentials file
        config = configparser.ConfigParser()
        config.read(self.awscredsfile)
        self.aws_region = self.get_aws_region(profile)

        if not config.has_section(profile):
            if self.args.debug:
                print(
                    f'~/.aws/credentials has no section for profile {profile}')
            return False
        if not config.has_option(profile, 'aws_access_key_id'):
            if self.args.debug:
                print(
                    f'~/.aws/credentials has no entry aws_access_key_id in section/profile {profile}')
            return False

        # Get the AWS access key and secret key from the specified profile
        aws_access_key_id = config.get(profile, 'aws_access_key_id')
        aws_secret_access_key = config.get(profile, 'aws_secret_access_key')

        # Set the environment variables for creds
        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        os.environ['AWS_PROFILE'] = profile
        self.envrn['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        self.envrn['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        self.envrn['AWS_PROFILE'] = profile
        self.envrn['RCLONE_S3_ACCESS_KEY_ID'] = aws_access_key_id
        self.envrn['RCLONE_S3_SECRET_ACCESS_KEY'] = aws_secret_access_key

        if profile in ['default', 'AWS', 'aws']:
            # Set the environment variables for AWS
            self.envrn['RCLONE_S3_PROVIDER'] = 'AWS'
            self.envrn['RCLONE_S3_REGION'] = self.aws_region
            self.envrn['RCLONE_S3_LOCATION_CONSTRAINT'] = self.aws_region
            self.envrn['RCLONE_S3_STORAGE_CLASS'] = self.read(
                'general', 's3_storage_class')
            os.environ['RCLONE_S3_STORAGE_CLASS'] = self.read(
                'general', 's3_storage_class')
        else:
            prf = self.read('profiles', profile)
            self.envrn['RCLONE_S3_ENV_AUTH'] = 'true'
            self.envrn['RCLONE_S3_PROFILE'] = profile
            # profile={'name': '', 'provider': '', 'storage_class': ''}
            if isinstance(prf, dict):
                self.envrn['RCLONE_S3_PROVIDER'] = prf['provider']
                self.envrn['RCLONE_S3_ENDPOINT'] = self._get_aws_s3_session_endpoint_url(
                    profile)
                self.envrn['RCLONE_S3_REGION'] = self.aws_region
                self.envrn['RCLONE_S3_LOCATION_CONSTRAINT'] = self.aws_region
                self.envrn['RCLONE_S3_STORAGE_CLASS'] = prf['storage_class']
                os.environ['RCLONE_S3_STORAGE_CLASS'] = prf['storage_class']

        return True

    def _get_home_paths(self):
        path_dirs = os.environ['PATH'].split(os.pathsep)
        # Filter the directories in the PATH that are inside the home directory
        dirs_inside_home = {
            directory for directory in path_dirs
            if directory.startswith(self.home_dir) and os.path.isdir(directory)
        }
        return sorted(dirs_inside_home, key=len)

    def _get_config_root(self):
        theroot = self.config_root_local
        rootfile = os.path.join(theroot, 'config_root')
        if os.path.exists(rootfile):
            with open(rootfile, 'r') as myfile:
                theroot = myfile.read().strip()
                if not os.path.isdir(theroot):
                    if not self.ask_yes_no(f'{rootfile} points to a shared config that does not exist. Do you want to configure {theroot} now?'):
                        print(
                            f"Please remove file {rootfile} to continue with a single user config.")
                        sys.exit(1)
                        # raise FileNotFoundError(f'Config root folder "{theroot}" not found. Please remove {rootfile}')
        return theroot

    def _get_section_path(self, section):
        return os.path.join(self.config_root, section)

    def _get_entry_path(self, section, entry):
        if section:
            section_path = self._get_section_path(section)
            return os.path.join(section_path, entry)
        else:
            return os.path.join(self.config_root, entry)

    def fix_tree_permissions(self, target_dir):
        try:
            if not os.path.isdir(target_dir):
                print(
                    f"Error: '{target_dir}' is not a directory", file=sys.stderr)
                return False
            # Get the group ID of the target directory
            gid = os.lstat(target_dir).st_gid
            for root, dirs, files in os.walk(target_dir):
                # Check and change the group of the directory
                self.fix_permissions_if_needed(root, gid)
                # Check and change the group of each file in the directory
                for file in files:
                    file_path = os.path.join(root, file)
                    self.fix_permissions_if_needed(file_path, gid)
            return True
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def fix_permissions_if_needed(self, path, gid=None):
        # setgid, g+rw, o+r and optionally enforce gid (group)
        # fix: different setup mey be needed to handle symlinks
        try:
            current_mode = os.lstat(path).st_mode
            # Add user rw, group rw and others read # 0o060 | 0o004
            new_mode = current_mode | 0o664
            if new_mode != current_mode:
                # new_mode = current_mode | 0o7077 # clear group and other permission
                if not path.endswith('.pem'):
                    os.chmod(path, new_mode)
                    print(
                        f"  Changed permissions of '{path}' from {oct(current_mode)} to {oct(new_mode)}")
                    current_mode = os.lstat(path).st_mode
            if os.path.isdir(path):
                new_mode = current_mode | 0o2000
                if new_mode != current_mode:  # Check if setgid bit is not set
                    os.chmod(path, new_mode)
                    current_mode = os.lstat(path).st_mode
                    print(f"  Set setgid bit on directory '{path}'")
                new_mode = current_mode | 0o0111
                if new_mode != current_mode:  # Check if execute bit is set on dirs
                    os.chmod(path, new_mode)
                    print(f"  Set execute bits on directory '{path}'")
            current_gid = os.lstat(path).st_gid
            if not gid:
                gid = current_gid
            if current_gid != gid:
                current_group_name = grp.getgrgid(current_gid).gr_name
                os.chown(path, -1, gid)  # -1 means don't change the user
                print(
                    f"  Changed group of '{path}' from '{current_group_name}' to '{grp.getgrgid(gid).gr_name}'")
            return True
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def replace_symlinks_with_realpaths(self, folders):
        cleaned_folders = []
        for folder in folders:
            try:
                # Split the path into its components
                folder = os.path.expanduser(folder)
                # print('expanduser folder:', folder)
                # print('real path:', os.path.realpath(folder))
                cleaned_folders.append(os.path.realpath(folder))
            except Exception as e:
                print(f"Error processing '{folder}': {e}")
        self.printdbg('cleaned_folders:', cleaned_folders)
        return cleaned_folders

    def printdbg(self, *args, **kwargs):
        # use inspect to get the name of the calling function
        if self.args.debug:
            current_frame = inspect.currentframe()
            calling_function = current_frame.f_back.f_code.co_name
            print(f' DBG {calling_function}():', args, kwargs)

    def prompt(self, question, defaults=None, type_check=None):
        # Prompts for user input and writes it to config.
        # defaults are up to 3 pipe separated strings:
        # if there is only one string this is the default
        #
        # if there are 2 strings they represent section
        # and key name of the config entry and if there are
        # 3 strings the last 2 represent section
        # and key name of the config file and the first is
        # the default if section and key name are empty
        #
        # if defaults is a python list it will assign a number
        # to each list element and prompt the user for one
        # of the options
        default = ''
        section = ''
        key = ''
        if not question.endswith(':'):
            question += ':'
        question = f"*** {question} ***"
        defaultlist = []
        if isinstance(defaults, list):
            defaultlist = defaults
        elif defaults:
            defaultlist = defaults.split('|')[0].split(',')
        if len(defaultlist) > 1:
            print(question)
            for i, option in enumerate(defaultlist, 1):
                print(f'  ({i}) {option}')
            while True:
                selected = input("  Enter the number of your selection: ")
                if selected.isdigit() and 1 <= int(selected) <= len(defaultlist):
                    return defaultlist[int(selected) - 1]
                else:
                    print("  Invalid selection. Please enter a number from the list.")
        elif defaults is not None:
            deflist = defaults.split('|')
            if len(deflist) == 3:
                section = deflist[1]
                key = deflist[2]
                default = self.read(section, key)
                if not default:
                    default = deflist[0]
            elif len(deflist) == 2:
                section = deflist[0]
                key = deflist[1]
                default = self.read(section, key)
            elif len(deflist) == 1:
                default = deflist[0]
            # if default:
            question += f"\n  [Default: {default}]"
        else:
            question += f"\n  [Default: '']"
        while True:
            # user_input = input(f"\033[93m{question}\033[0m ")
            user_input = input(f"{question} ")
            if not user_input:
                if default is not None:
                    if section:
                        self.write(section, key, default)
                    return default
                else:
                    print("Please enter a value.")
            else:
                if type_check == 'number':
                    try:
                        if '.' in user_input:
                            value = float(user_input)
                        else:
                            value = int(user_input)
                        if section:
                            self.write(section, key, value)
                        return value
                    except ValueError:
                        print("Invalid input. Please enter a number.")
                elif type_check == 'string':
                    if not user_input.isnumeric():
                        if section:
                            self.write(section, key, user_input)
                        return user_input
                    else:
                        print("Invalid input. Please enter a string not a number")
                else:
                    if section:
                        self.write(section, key, user_input)
                    return user_input

    def ask_yes_no(self, question, default="yes"):
        valid = {"yes": True, "y": True, "no": False, "n": False}

        if default is None:
            prompt = " [y/n] "
        elif default == "yes":
            prompt = " [Y/n] "
        elif default == "no":
            prompt = " [y/N] "
        else:
            raise ValueError("invalid default answer: '%s'" % default)

        while True:
            print(question + prompt, end="")
            choice = input().lower()
            if default and not choice:
                return valid[default]
            elif choice in valid:
                return valid[choice]
            else:
                print("Please respond with 'yes' or 'no' (or 'y' or 'n').")

    def add_cron_job(self, cmd, minute, hour='*', day_of_month='*', month='*', day_of_week='*'):
        # CURRENTLY INACTIVE
        if not minute:
            print('You must set the minute (1-60) explicily')
            return False
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            # Dump the current crontab to the temporary file
            try:
                os.system('crontab -l > {}'.format(temp.name))
            except Exception as e:
                print(f"Error: {e}")

            # Add the new cron job to the temporary file
            cron_time = "{} {} {} {} {}".format(
                str(minute), hour, day_of_month, month, day_of_week)
            with open(temp.name, 'a') as file:
                file.write('{} {}\n'.format(cron_time, cmd))

            # Install the new crontab
            try:
                os.system('crontab {}'.format(temp.name))
            except Exception as e:
                print(f"Error: {e}")

            # Clean up by removing the temporary file
            os.unlink(temp.name)

        print("Cron job added!")

    def add_systemd_cron_job(self, cmd, minute, hour='*'):

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
        os.makedirs(user_systemd_dir, exist_ok=True)

        SERVICE_PATH = os.path.join(
            user_systemd_dir, "froster-monitor.service")
        TIMER_PATH = os.path.join(user_systemd_dir, "froster-monitor.timer")

        # Create service and timer files
        with open(SERVICE_PATH, "w") as service_file:
            service_file.write(SERVICE_CONTENT)

        with open(TIMER_PATH, "w") as timer_file:
            timer_file.write(TIMER_CONTENT)

        # Reload systemd and enable/start timer
        try:
            os.chdir(user_systemd_dir)
            os.system("systemctl --user daemon-reload")
            os.system("systemctl --user enable froster-monitor.service")
            os.system("systemctl --user enable froster-monitor.timer")
            os.system("systemctl --user start froster-monitor.timer")
            print("Systemd froster-monitor.timer cron job started!")
        except Exception as e:
            print(f'Could not add systemd scheduler job, Error: {e}')

    def replicate_ini(self, section, src_file, dest_file):

        # copy an ini section from source to destination
        # sync values in dest that do not exist in src back to src
        # best used for sync of AWS profiles.
        # if section==ALL copy all but section called default

        if not os.path.exists(src_file):
            return

        # Create configparser objects
        src_parser = configparser.ConfigParser()
        dest_parser = configparser.ConfigParser()

        # Read source and destination files
        src_parser.read(src_file)
        dest_parser.read(dest_file)

        if section == 'ALL':
            sections = src_parser.sections()
            sections.remove('default') if 'default' in sections else None
        else:
            sections = [section]

        for section in sections:
            # Get the section from source and destination files
            src_section_data = dict(src_parser.items(section))
            dest_section_data = dict(dest_parser.items(
                section)) if dest_parser.has_section(section) else {}

            # If section does not exist in source or destination file, add it
            if not src_parser.has_section(section):
                src_parser.add_section(section)

            if not dest_parser.has_section(section):
                dest_parser.add_section(section)

            # Write the data into destination file
            for key, val in src_section_data.items():
                dest_parser.set(section, key, val)

            # Write the data into source file
            for key, val in dest_section_data.items():
                if key not in src_section_data:
                    src_parser.set(section, key, val)

        # Save the changes in the destination and source files
        with open(dest_file, 'w') as dest_configfile:
            dest_parser.write(dest_configfile)

        with open(src_file, 'w') as src_configfile:
            src_parser.write(src_configfile)

        if self.args.debug:
            print(f"Ini-section copied from {src_file} to {dest_file}")
            print(
                f"Missing entries in source from destination copied back to {src_file}")

    def get_aws_profiles(self):
        # get the full list of profiles from ~/.aws/ profile folder
        try:
            config = configparser.ConfigParser()
            # Read the AWS config file ---- optional, we only require a creds file
            if os.path.exists(self.awsconfigfile):
                config.read(self.awsconfigfile)
            # Read the AWS credentials file
            if os.path.exists(self.awscredsfile):
                config.read(self.awscredsfile)
            # Get the list of profiles
            profiles = []
            for section in config.sections():
                # .replace("default", "default")
                profile_name = section.replace("profile ", "")
                profiles.append(profile_name)
            # convert list to set and back to list to remove dups
            return list(set(profiles))
        except Exception as e:
            # print(f'Error: {e}')
            return []

    def create_aws_configs(self, access_key=None, secret_key=None, region=None):

        aws_dir = os.path.join(self.home_dir, ".aws")

        if not os.path.exists(aws_dir):
            os.makedirs(aws_dir)

        if not os.path.isfile(self.awsconfigfile):
            if region:
                print(
                    f'\nAWS config file {self.awsconfigfile} does not exist, creating ...')
                with open(self.awsconfigfile, "w") as config_file:
                    config_file.write("[default]\n")
                    config_file.write(f"region = {region}\n")
                    config_file.write("\n")
                    config_file.write("[profile aws]\n")
                    config_file.write(f"region = {region}\n")

        if not os.path.isfile(self.awscredsfile):
            print(
                f'\nAWS credentials file {self.awscredsfile} does not exist, creating ...')
            if not access_key:
                access_key = input("Enter your AWS access key ID: ")
            if not secret_key:
                secret_key = input("Enter your AWS secret access key: ")
            with open(self.awscredsfile, "w") as credentials_file:
                credentials_file.write("[default]\n")
                credentials_file.write(f"aws_access_key_id = {access_key}\n")
                credentials_file.write(
                    f"aws_secret_access_key = {secret_key}\n")
                credentials_file.write("\n")
                credentials_file.write("[aws]\n")
                credentials_file.write(f"aws_access_key_id = {access_key}\n")
                credentials_file.write(
                    f"aws_secret_access_key = {secret_key}\n")
            os.chmod(self.awscredsfile, 0o600)

    def set_aws_config(self, profile, key, value, service=''):
        if key == 'endpoint_url':
            if value.endswith('.amazonaws.com'):
                return False
            else:
                value = f'{value}\nsignature_version = s3v4'
        config = configparser.ConfigParser()
        config.read(os.path.expanduser("~/.aws/config"))
        section = profile
        if profile != 'default':
            section = f'profile {profile}'
        if not config.has_section(section):
            config.add_section(section)
        if service:
            config.set(section, service, f"\n{key} = {value}\n")
        else:
            config.set(section, key, value)
        with open(os.path.expanduser("~/.aws/config"), 'w') as configfile:
            config.write(configfile)
        if profile != 'default' and not self.args.cfgfolder:  # when moving cfg it still writes to old folder
            self.replicate_ini(
                f'profile {profile}', self.awsconfigfile, self.awsconfigfileshr)
        return True

    def get_aws_s3_endpoint_url(self, profile=None):
        # non boto3 method, use _get_aws_s3_session_endpoint_url instead
        if not profile:
            profile = self.awsprofile
        config = configparser.ConfigParser()
        config.read(os.path.expanduser('~/.aws/config'))
        prof = 'profile ' + profile
        if profile == 'default':
            prof = profile
        try:
            # We use the configparser's interpolation feature here to
            # flatten the 's3' subsection into the 'profile test' section.
            s3_config_string = config.get(prof, 's3')
            s3_config = configparser.ConfigParser()
            s3_config.read_string("[s3_section]\n" + s3_config_string)
            endpoint_url = s3_config.get('s3_section', 'endpoint_url')
            return endpoint_url
        except (configparser.NoSectionError, configparser.NoOptionError):
            if self.args.debug:
                print("  No endpoint_url found in aws profile:", profile)
            return None

    def _get_aws_s3_session_endpoint_url(self, profile=None):
        # retrieve endpoint url through boto API, not configparser
        import botocore.session  # only botocore Session object has attribute 'full_config'
        if not profile:
            profile = self.awsprofile
        session = botocore.session.Session(
            profile=profile) if profile else botocore.session.Session()
        config = session.full_config
        s3_config = config["profiles"][profile].get("s3", {})
        endpoint_url = s3_config.get("endpoint_url", None)
        if self.args.debug:
            print('*** endpoint url ***:', endpoint_url)
        return endpoint_url

    def get_aws_region(self, profile=None):
        try:
            session = boto3.Session(
                profile_name=profile) if profile else boto3.Session()
            if self.args.debug:
                print(
                    f'* get_aws_region for profile {profile}:', session.region_name)
            return session.region_name
        except:
            if self.args.debug:
                print(
                    f'  cannot retrieve AWS region for profile {profile}, no valid profile or credentials')
            return ""

    def get_domain_name(self):
        try:
            with open('/etc/resolv.conf', 'r') as file:
                content = file.readlines()
        except FileNotFoundError:
            return "mydomain.edu"
        tld = None
        for line in content:
            if line.startswith('search') or line.startswith('domain'):
                tokens = line.split()
                if len(tokens) > 1:
                    tld = tokens.pop()
                    break
        return tld if tld else "mydomain.edu"

    def get_time_zone(self):
        current_tz_str = 'America/Los_Angeles'
        try:
            # Resolve the /etc/localtime symlink
            timezone_path = os.path.realpath("/etc/localtime")
            # Extract the time zone string by stripping off the prefix of the zoneinfo path
            current_tz_str = timezone_path.split("zoneinfo/")[-1]
        except Exception as e:
            print(f'Error: {e}')
            current_tz_str = 'America/Los_Angeles'
        return current_tz_str

    def write(self, section, entry, value):
        try:
            entry_path = self._get_entry_path(section, entry)
            os.makedirs(os.path.dirname(entry_path), exist_ok=True)
            if value == '""':
                # Check if file exists before trying to remove
                if os.path.exists(entry_path):
                    os.remove(entry_path)
                return
            with open(entry_path, 'w') as entry_file:
                if isinstance(value, list):
                    for item in value:
                        entry_file.write(f"{item}\n")
                elif isinstance(value, dict):
                    json.dump(value, entry_file)
                else:
                    entry_file.write(value)
        except OSError as e:
            # Handle file operation errors (like permission issues, file not found, etc.)
            print(
                f"Please ask your Data Steward to add group permissions. File operation error: {e}")
            sys.exit(1)
        except TypeError as e:
            # Handle issues with the type of 'value'
            print(f"Type error: {e}")
        except Exception as e:
            # Handle any other unexpected errors
            print(f"An unexpected error occurred: {e}")

    def read(self, section, entry, default=""):
        entry_path = self._get_entry_path(section, entry)
        if not os.path.exists(entry_path):
            return default
            # raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')
        with open(entry_path, 'r') as entry_file:
            try:
                return json.load(entry_file)
            except json.JSONDecodeError:
                pass
            except:
                print('Error in ConfigManager.read(), returning default')
                return default
        with open(entry_path, 'r') as entry_file:
            try:
                content = entry_file.read().splitlines()
                if len(content) == 1:
                    return content[0].strip()
                else:
                    return content
            except:
                print('Error in ConfigManager.read(), returning default')
                return default

    def delete(self, section, entry):
        entry_path = self._get_entry_path(section, entry)
        if not os.path.exists(entry_path):
            raise FileNotFoundError(
                f'Config entry "{entry}" in section "{section}" not found.')
        os.remove(entry_path)

    def delete_section(self, section):
        section_path = self._get_section_path(section)
        if not os.path.exists(section_path):
            raise FileNotFoundError(f'Config section "{section}" not found.')
        for entry in os.listdir(section_path):
            os.remove(os.path.join(section_path, entry))
        os.rmdir(section_path)

    def move_config(self, cfgfolder):
        if not os.path.isdir(cfgfolder):
            print(f'{cfgfolder} is not a directory')
            return False
        else:
            # Get the group ID of the folder
            gid = os.lstat(cfgfolder).st_gid
            # Get the group name from the group ID
            pgroup = grp.getgrgid(gid)
            if pgroup.gr_name == self.whoami:
                print(
                    f'  Group ({pgroup.gr_name}) and user name ({self.whoami}) should not be the same for {cfgfolder}.')
                return False
            else:
                # set the correct permission for the folder including setgid to make sure that the group is inherited
                try:
                    os.chmod(cfgfolder, 0o2775)
                    # this will fail for non-owner users.
                except Exception as e:
                    print(f"  Could not set permissions on {cfgfolder} :\n{e}")
                    return False

        if not cfgfolder and self.config_root == self.config_root_local:
            cfgfolder = self.prompt("Please enter the root where folder .config/froster will be created.",
                                    os.path.expanduser('~'))
        if cfgfolder:
            new_config_root = os.path.join(
                os.path.expanduser(cfgfolder), '.config', 'froster')
        else:
            new_config_root = self.config_root
        old_config_root = self.config_root_local
        config_root_file = os.path.join(self.config_root_local, 'config_root')

        if os.path.exists(config_root_file):
            with open(config_root_file, 'r') as f:
                old_config_root = f.read().strip()

        # print(old_config_root,new_config_root)
        if old_config_root == new_config_root:
            return True

        if not os.path.isdir(new_config_root):
            if os.path.isdir(old_config_root):
                shutil.move(old_config_root, new_config_root)
                if os.path.isdir(old_config_root):
                    try:
                        os.rmdir(old_config_root)
                    except:
                        pass
                print(f'  Froster config moved to "{new_config_root}"\n')
            os.makedirs(new_config_root, exist_ok=True)
            if os.path.exists(self.awsconfigfile):
                self.replicate_ini('ALL', self.awsconfigfile,
                                   os.path.join(new_config_root, 'aws_config'))
                print(
                    f'  ~/.aws/config replicated to "{new_config_root}/aws_config"\n')

        self.config_root = new_config_root

        os.makedirs(old_config_root, exist_ok=True)
        with open(config_root_file, 'w') as f:
            f.write(self.config_root)
            print(f'  Switched configuration path to "{self.config_root}"')
        return True

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


def parse_arguments():
    """
    Gather command-line arguments.
    """

    parser = argparse.ArgumentParser(prog='froster ',
                                     description='A (mostly) automated tool for archiving large scale data ' +
                                     'after finding folders in the file system that are worth archiving.')

    parser.add_argument('-d', '--debug', dest='debug', action='store_true', default=False,
                        help="verbose output for all commands")

    parser.add_argument('-n', '--no-slurm', dest='noslurm', action='store_true', default=False,
                        help="do not submit a Slurm job, execute in the foreground. ")

    parser.add_argument('-c', '--cores', dest='cores', action='store_true', default='4',
                        help='Number of cores to be allocated for the machine. (default=4)')

    parser.add_argument('-p', '--profile', dest='awsprofile', action='store_true', default='',
                        help='which AWS profile in ~/.aws/ should be used. default="aws"')

    parser.add_argument('-v', '--version', dest='version', action='store_true',
                        help='print froster and packages version info')

    subparsers = parser.add_subparsers(dest="subcmd", help='sub-command help')

    # ***

    parser_config = subparsers.add_parser('config', aliases=['cnf'],
                                          help=textwrap.dedent(f'''
            Bootstrap the configurtion, install dependencies and setup your environment.
            You will need to answer a few questions about your cloud and hpc setup.
        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_config.add_argument('--index', '-i', dest='index', action='store_true', default=False,
                               help="configure froster for indexing only, don't ask addional questions.")
    parser_config.add_argument('--monitor', '-m', dest='monitor', action='store', default='',
                               metavar='<email@address.org>', help='setup froster as a monitoring cronjob ' +
                               'on an ec2 instance and notify an email address')
    parser_config.add_argument('cfgfolder', action='store', default="", nargs='?',
                               help='configuration root folder where .config/froster will be created ' +
                               '(default=~ home directory)  ')

    # ***

    parser_index = subparsers.add_parser('index', aliases=['idx'],
                                         help=textwrap.dedent(f'''
            Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file 
            that lists the largest folders. As this process is compute intensive the 
            index job will be automatically submitted to Slurm if the Slurm tools are
            found.
        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_index.add_argument('--pwalk-csv', '-p', dest='pwalkcsv', action='store', default='',
                              help='If someone else has already created CSV files using pwalk ' +
                              'you can enter a specific pwalk CSV file here and are not ' +
                              'required to run the time consuming pwalk.' +
                              '')
    parser_index.add_argument('--pwalk-copy', '-y', dest='pwalkcopy', action='store', default='',
                              help='Create this backup copy of a newly generated pwalk CSV file. ' +
                              'By default the pwalk csv file will only be gnerated in temp space ' +
                              'and then deleted.' +
                              '')
    parser_index.add_argument('folders', action='store', default=[],  nargs='*',
                              help='folders you would like to index (separated by space), ' +
                              'using the pwalk file system crawler ')

    # ***

    parser_archive = subparsers.add_parser('archive', aliases=['arc'],
                                           help=textwrap.dedent(f'''
            Select from a list of large folders, that has been created by 'froster index', and 
            archive a folder to S3/Glacier. Once you select a folder the archive job will be 
            automatically submitted to Slurm. You can also automate this process 

        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_archive.add_argument('--larger', '-l', dest='larger', type=int, action='store', default=0,
                                help=textwrap.dedent(f'''
            Archive folders larger than <GiB>. This option
            works in conjunction with --older <days>. If both 
            options are set froster will print a command that 
            allows you to archive all matching folders at once.
        '''))
    parser_archive.add_argument('--older', '-o', dest='older', type=int, action='store', default=0,
                                help=textwrap.dedent(f'''
            Archive folders that have not been accessed more than 
            <days>. (optionally set --mtime to select folders that
            have not been modified more than <days>). This option
            works in conjunction with --larger <GiB>. If both 
            options are set froster will print a command that 
            allows you to archive all matching folders at once.
        '''))

    parser_archive.add_argument('--mtime', '-m', dest='agemtime', action='store_true', default=False,
                                help="Use modified file time (mtime) instead of accessed time (atime)")

    parser_archive.add_argument('--recursive', '-r', dest='recursive', action='store_true', default=False,
                                help="Archive the current folder and all sub-folders")

    parser_archive.add_argument('--reset', '-s', dest='reset', action='store_true', default=False,
                                help="This will not download any data, but recusively reset a folder from previous (e.g. failed) " +
                                "archiving attempt. It will delete .froster.md5sum and extract Froster.smallfiles.tar")

    parser_archive.add_argument('--no-tar', '-t', dest='notar', action='store_true', default=False,
                                help="Do not move small files to tar file before archiving")

    parser_archive.add_argument('--nih', '-n', dest='nih', action='store_true', default=False,
                                help="Search and Link Metadata from NIH Reporter")

    parser_archive.add_argument('--dry-run', '-d', dest='dryrun', action='store_true', default=False,
                                help="Execute a test archive without actually copying the data")

    parser_archive.add_argument('folders', action='store', default=[], nargs='*',
                                help='folders you would like to archive (separated by space), ' +
                                'the last folder in this list is the target   ')

    # ***

    parser_delete = subparsers.add_parser('delete', aliases=['del'],
                                          help=textwrap.dedent(f'''
            Remove data from a local filesystem folder that has been confirmed to 
            be archived (through checksum verification). Use this instead of deleting manually
        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_delete.add_argument('folders', action='store', default=[],  nargs='*',
                               help='folders (separated by space) from which you would like to delete files, ' +
                               'you can only delete files that have been archived')

    # ***

    parser_mount = subparsers.add_parser('mount', aliases=['umount'],
                                         help=textwrap.dedent(f'''
            Mount or unmount the remote S3 or Glacier storage in your local file system 
            at the location of the original folder.
        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_mount.add_argument('--mount-point', '-m', dest='mountpoint', action='store', default='',
                              help='pick a custom mount point, this only works if you select a single folder.')
    parser_mount.add_argument('--aws', '-a', dest='aws', action='store_true', default=False,
                              help="Mount folder on new EC2 instance instead of local machine")
    parser_mount.add_argument('--unmount', '-u', dest='unmount', action='store_true', default=False,
                              help="unmount instead of mount, you can also use the umount sub command instead.")
    parser_mount.add_argument('folders', action='store', default=[],  nargs='*',
                              help='archived folders (separated by space) which you would like to mount.' +
                              '')

    # ***

    parser_restore = subparsers.add_parser('restore', aliases=['rst'],
                                           help=textwrap.dedent(f'''
            Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need
            to download all data to local storage after the restore is complete. 
            Just use the mount sub command. 
        '''), formatter_class=argparse.RawTextHelpFormatter)
    parser_restore.add_argument('--days', '-d', dest='days', action='store', default=30,
                                help='Number of days to keep data in S3 One Zone-IA storage at $10/TiB/month (default: 30)')
    parser_restore.add_argument('--retrieve-opt', '-r', dest='retrieveopt', action='store', default='Bulk',
                                help=textwrap.dedent(f'''
            Bulk (default): 
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

    parser_restore.add_argument('--aws', '-a', dest='aws', action='store_true', default=False,
                                help="Restore folder on new AWS EC2 instance instead of local machine")

    parser_restore.add_argument('--instance-type', '-i', dest='instancetype', action='store', default="",
                                help='The EC2 instance type is auto-selected, but you can pick any other type here')

    parser_restore.add_argument('--monitor', '-m', dest='monitor', action='store_true', default=False,
                                help="Monitor EC2 server for cost and idle time.")

    parser_restore.add_argument('--no-download', '-l', dest='nodownload', action='store_true', default=False,
                                help="skip download to local storage after retrieval from Glacier")

    parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
                                help='folders you would like to to restore (separated by space), ' +
                                '')

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

    if len(sys.argv) == 1:
        parser.print_help(sys.stdout)

    return parser.parse_args()


if __name__ == "__main__":

    if not sys.platform.startswith('linux'):
        print('This software currently only runs on Linux x64')
        sys.exit(1)

    try:
        # parse arguments using python's internal module argparse.py
        args = parse_arguments()

        # Declaring variables
        TABLECSV = ''  # CSV string for DataTable
        SELECTEDFILE = ''  # CSV filename to open in hotspots
        MAXHOTSPOTS = 0

        # TODO: Replace return values from main() from True/False to real exit codes
        if main():
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print('Keyboard interrupt')
        print()
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
