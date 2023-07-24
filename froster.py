#! /usr/bin/env python3

"""
Froster (almost) automates the challening task of 
archiving many Terabytes of data on HPC systems
"""
# internal modules
import sys, os, argparse, json, configparser, csv, platform
import urllib3, datetime, tarfile, zipfile, textwrap
import concurrent.futures, hashlib, fnmatch, io, math, signal
import shutil, tempfile, glob, shlex, subprocess, itertools
if sys.platform.startswith('linux'):
    import getpass, pwd, grp
# stuff from pypi
import requests, duckdb, boto3, botocore
from textual.app import App, ComposeResult
from textual.widgets import DataTable

__app__ = 'Froster, a simple archiving tool'
__version__ = '0.5'
TABLECSV = '' # CSV string for DataTable
SELECTEDFILE = '' # CSV filename to open in hotspots 
MAXHOTSPOTS = 0

def main():
    
    cfg = ConfigManager(args)
    arch = Archiver(args, cfg)
    global TABLECSV
    global SELECTEDFILE
    
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

    if args.version:
        print(f'Froster version: {__version__}')
        print(f'Python version:\n{sys.version}')
        return True

    if args.subcmd in ['archive','delete','restore']:
        errfld=[]
        for fld in args.folders:            
            ret = arch.test_write(fld)
            if ret==13 or ret == 2:
                errfld.append(fld)
        if errfld:
            errflds='" "'.join(errfld)
            print(f'Error: folder(s) "{errflds}" need to exist and you need write access to them.')
            return False

    if args.subcmd in ['config', 'cnf']:

        first_time=True
        binfolder = cfg.read('general', 'binfolder')
        if not binfolder:
            binfolder = f'{cfg.home_dir}/.local/bin'
            if not os.path.exists(binfolder):
                os.makedirs(binfolder, mode=0o775)
            cfg.write('general', 'binfolder', binfolder)
        else:
            first_time=False

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if not os.path.exists(os.path.join(binfolder,'pwalk')):
            print(" Installing pwalk ...", flush=True)        
            cfg.copy_compiled_binary_from_github('fizwit', 'filesystem-reporting-tools', 
                    'gcc -pthread pwalk.c exclude.c fileProcess.c -o pwalk', 
                    'pwalk', binfolder)

        if not os.path.exists(os.path.join(binfolder,'rclone')):
            print(" Installing rclone ... please wait ... ", end='', flush=True)
            rclone_url = 'https://downloads.rclone.org/rclone-current-linux-amd64.zip'
            cfg.copy_binary_from_zip_url(rclone_url, 'rclone', 
                                '/rclone-v*/',binfolder)
            print("Done!",flush=True)

        # Basic setup, focus the indexer on larger folders and file sizes 
        if not cfg.read('general', 'min_index_folder_size_gib'):
            cfg.write('general', 'min_index_folder_size_gib', "10")
        if not cfg.read('general', 'min_index_folder_size_avg_mib'):
            cfg.write('general', 'min_index_folder_size_avg_mib', "10")
        if not cfg.read('general', 'max_hotspots_display_entries'):
            cfg.write('general', 'max_hotspots_display_entries', "5000")

        print('\n*** Asking a few questions ***')
        print('*** For most you can just hit <Enter> to accept the default. ***\n')
        # general setup 
        defdom = cfg.get_domain_name()
        whoami = getpass.getuser()

        # determine if we need to move the (shared) config to a new folder 
        movecfg=False
        if first_time and args.cfgfolder == '' and cfg.config_root == cfg.config_root_local:
            if cfg.ask_yes_no(f'  Do you want to collaborate with other users on archive and restore?', 'no'):
                movecfg=True
        elif args.cfgfolder:
            movecfg=True
        if movecfg:
            if cfg.move_config(args.cfgfolder):
                print('\n  IMPORTANT: All archiving collaborators need to have consistent AWS profile names in their ~/.aws/credentials\n')

        # domain-name not needed right now
        #domain = cfg.prompt('Enter your domain name:',
        #                    f'{defdom}|general|domain','string')
        emailaddr = cfg.prompt('Enter your email address:',
                             f'{whoami}@{defdom}|general|email','string')
        emailstr = emailaddr.replace('@','-')
        emailstr = emailstr.replace('.','-')

        # cloud setup
        bucket = cfg.prompt('Please confirm/edit S3 bucket name to be created in all used profiles.',
                            f'froster-{emailstr}|general|bucket','string')
        archiveroot = cfg.prompt('Please confirm/edit the archive root path inside your S3 bucket',
                                 'archive|general|archiveroot','string')
        s3_storage_class =  cfg.prompt('Please confirm/edit the AWS S3 Storage class',
                                    'DEEP_ARCHIVE|general|s3_storage_class','string')
        #aws_profile =  cfg.prompt('Please enter the AWS profile in ~/.aws',
        #                          'default|general|aws_profile','string')
        #aws_region =  cfg.prompt('Please enter your AWS region for S3',
        #                         'us-west-2|general|aws_region','string')

        # if there is a shared ~/.aws/config copy it over
        cfg.replicate_ini('ALL',cfg.awsconfigfileshr,cfg.awsconfigfile)
        cfg.create_aws_configs()

        aws_region = cfg.get_aws_region('aws')
        if not aws_region:
            aws_region = cfg.get_aws_region()

        if not aws_region:
            aws_region =  cfg.prompt('Please select AWS S3 region (e.g. us-west-2 for Oregon)',
                                 cfg.get_aws_regions())
        aws_region =  cfg.prompt('Please confirm/edit the AWS S3 region', aws_region)
                
        #cfg.create_aws_configs(None, None, aws_region)
        print(f"\n  Verify that bucket '{bucket}' is configured ... ")
        
        allowed_aws_profiles = ['default', 'aws', 'AWS'] # for accessing glacier use one of these
        profmsg = 1
        profs = cfg.get_aws_profiles()

        for prof in profs:
            if prof in allowed_aws_profiles:
                cfg.set_aws_config(prof, 'region', aws_region)
                if prof == 'AWS' or prof == 'aws':
                    cfg.write('general', 'aws_profile', prof)                    
                elif prof == 'default': 
                    cfg.write('general', 'aws_profile', 'default')
                cfg.create_s3_bucket(bucket, prof)

        for prof in profs:
            if prof in allowed_aws_profiles:
                continue
            if profmsg == 1:
                print('\nFound additional profiles in ~/.aws and need to ask a few more questions.\n')
                profmsg = 0
            if not cfg.ask_yes_no(f'Do you want to configure profile "{prof}"?','yes'):
                continue 
            profile={'name': '', 'provider': '', 'storage_class': ''}
            pendpoint = ''
            pregion = ''
            pr=cfg.read('profiles', prof)
            if isinstance(pr, dict):
                profile = cfg.read('profiles', prof)            
            profile['name'] = prof

            if not profile['provider']: 
                profile['provider'] = ['AWS', 'GCS', 'Wasabi', 'IDrive', 'Ceph', 'Minio', 'Other']
            profile['provider'] = \
                cfg.prompt(f'S3 Provider for profile "{prof}"',profile['provider'])
            
            pregion = cfg.get_aws_region(prof) 
            if not pregion:
                pregion =  cfg.prompt('Please select the S3 region',
                                 cfg.get_aws_regions(prof,profile['provider']))
            pregion = \
                cfg.prompt(f'Confirm/edit S3 region for profile "{prof}"',pregion)
            if pregion:
                cfg.set_aws_config(prof, 'region', pregion)

            if profile['provider'] != 'AWS':
                if not pendpoint:
                    pendpoint=cfg.get_aws_s3_endpoint_url(prof)
                    if not pendpoint:
                        if 'Wasabi' == profile['provider']:
                            pendpoint = f'https://s3.{pregion}.wasabisys.com' 
                        elif 'GCS' == profile['provider']:
                            pendpoint = 'https://storage.googleapis.com' 

                pendpoint = \
                    cfg.prompt(f'S3 Endpoint for profile "{prof}" (e.g https://s3.domain.com)',pendpoint)
                if pendpoint:
                    if not pendpoint.startswith('http'):
                        pendpoint = 'https://' + pendpoint
                    cfg.set_aws_config(prof, 'endpoint_url', pendpoint, 's3')

            if not profile['storage_class']:
                if profile['provider'] == 'AWS':
                    profile['storage_class'] = s3_storage_class
                else:
                    profile['storage_class'] = 'STANDARD'

            if pregion and profile['provider']:
                cfg.write('profiles', prof, profile) 
            else:
                print(f'\nConfig for AWS profile "{prof}" was not saved.')
            
            cfg.create_s3_bucket(bucket, prof)

        print('\n*** And finally a few questions how your HPC uses local scratch space ***')
        print('*** This config is optional and you can hit ctrl+c to cancel any time ***')
        print('*** If you skip this, froster will use HPC /tmp which may have limited disk space  ***\n')

        # setup local scratch spaces, the defauls are OHSU specific 
        x = cfg.prompt('How do you request local scratch from Slurm?',
                            '--gres disk:1024|hpc|slurm_lscratch','string') # get 1TB scratch space
        x = cfg.prompt('Is there a user script that provisions local scratch?',
                            'mkdir-scratch.sh|hpc|lscratch_mkdir','string') # optional
        x = cfg.prompt('Is there a user script that tears down local scratch at the end?',
                            'rmdir-scratch.sh|hpc|lscratch_rmdir','string') # optional
        x = cfg.prompt('What is the local scratch root ?',
                            '/mnt/scratch|hpc|lscratch_root','string') # add slurm jobid at the end
        
        print('\nDone!\n')

    elif args.subcmd in ['index', 'ind']:
        if args.debug:
            print (" Command line:",args.cores, args.noslurm, 
                    args.pwalkcsv, args.folders,flush=True)

        if not args.folders:
            print('you must point to at least one folder in your command line')
            return False
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
                print (f'Indexing folder {fld}, please wait ...', flush=True)
                arch.index(fld)
        else:
            se = SlurmEssentials(args, cfg)
            label=arch._get_hotspots_file(args.folders[0]).replace('.csv','')            
            shortlabel=os.path.basename(args.folders[0])
            myjobname=f'froster:index:{shortlabel}'            
            email=cfg.read('general', 'email')
            se.add_line(f'#SBATCH --job-name={myjobname}')
            se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
            se.add_line(f'#SBATCH --mem=64G')            
            se.add_line(f'#SBATCH --output=froster-index-{label}-%J.out')
            se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')           
            se.add_line(f'#SBATCH --mail-user={email}')
            se.add_line(f'#SBATCH --time=1-0')
            #se.add_line(f'ml python')
            cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline
            cmdline = cmdline.replace('/froster.py ', '/froster ')
            if args.debug:
                print(f'Command line passed to Slurm:\n{cmdline}')
            se.add_line(cmdline)
            jobid = se.sbatch()
            print(f'Submitted froster indexing job: {jobid}')
            print(f'Check Job Output:')
            print(f' tail -f froster-index-{label}-{jobid}.out')

    elif args.subcmd in ['archive', 'arc']:
        if args.debug:
            print ("archive:",args.cores, args.awsprofile, args.noslurm,
                   args.larger, args.age, args.agemtime, args.folders)
        fld = '" "'.join(args.folders)
        if args.debug:
            print (f'default cmdline: froster.py archive "{fld}"')
        
        if not args.folders:            
            hsfolder = os.path.join(cfg.config_root, 'hotspots')
            if not os.path.exists(hsfolder):                
                print("No folders to archive in arguments and no Hotspots CSV files found!")
                print('Run: froster archive "/your/folder/to/archive"')
                return False
            csv_files = [f for f in os.listdir(hsfolder) if fnmatch.fnmatch(f, '*.csv')]
            if len(csv_files) == 0:
                print("No folders to archive in arguments and no Hotspots CSV files found!")
                print('Run: froster archive "/your/folder/to/archive"')
                return False
            # Sort the CSV files by their modification time in descending order (newest first)
            csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(hsfolder, x)), reverse=True)
            # if there are multiple files allow for selection
            if len(csv_files) > 1:
                TABLECSV='"Select a Hotspot file"\n' + '\n'.join(csv_files)
                app = TableArchive()
                retline=app.run()
                if not retline:
                    return False
                SELECTEDFILE = os.path.join(hsfolder, retline[0])
            else:
                SELECTEDFILE = os.path.join(hsfolder, csv_files[0])            
            app = TableHotspots()
            retline=app.run()
            if not retline:
                return False
            if len(retline) < 6:
                print('Error: Hotspots table did not return result')
                return False
            
            if cfg.ask_yes_no(f'Folder: "{retline[5]}"\nDo you want to start archiving now?'):
                args.folders.append(retline[5])
            else:
                print (f'You can start this process later by using this command:\n  froster archive "{retline[5]}"')
                return False

        if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
            print(f'Profile "{args.awsprofile}" not found.')
            return False
        if not cfg.check_bucket_access(cfg.bucket):
            return False

        if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
            for fld in args.folders:
                fld = fld.rstrip(os.path.sep)
                print (f'Archiving folder {fld}, please wait ...', flush=True)
                arch.archive(fld)
        else:
            se = SlurmEssentials(args, cfg)
            label=args.folders[0].replace('/','+')
            shortlabel=os.path.basename(args.folders[0])
            myjobname=f'froster:archive:{shortlabel}'
            email=cfg.read('general', 'email')
            se.add_line(f'#SBATCH --job-name={myjobname}')
            se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
            se.add_line(f'#SBATCH --mem=64G')
            se.add_line(f'#SBATCH --requeue')
            se.add_line(f'#SBATCH --output=froster-archive-{label}-%J.out')
            se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')           
            se.add_line(f'#SBATCH --mail-user={email}')
            se.add_line(f'#SBATCH --time=1-0')            
            cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline
            if not "--profile" in cmdline and args.awsprofile:            
                cmdline = cmdline.replace('/froster.py ', f'/froster --profile {args.awsprofile} ')
            else:
                cmdline = cmdline.replace('/froster.py ', '/froster ')
            if not args.folders[0] in cmdline:
                folders = '" "'.join(args.folders)
                cmdline=f'{cmdline} "{folders}"'
            if args.debug:
                print(f'Command line passed to Slurm:\n{cmdline}')
            se.add_line(cmdline)
            jobid = se.sbatch()
            print(f'Submitted froster archiving job: {jobid}')
            print(f'Check Job Output:')
            print(f' tail -f froster-archive-{label}-{jobid}.out')

    elif args.subcmd in ['restore', 'rst']:
        
        if args.debug:
            print ("restore:",args.cores, args.awsprofile, args.noslurm, 
                   args.days, args.retrieveopt, args.nodownload, args.folders)
        fld = '" "'.join(args.folders)
        if args.debug:
            print (f'default cmdline: froster.py restore "{fld}"')
        
        if not args.folders:
            TABLECSV=arch.archive_json_get_csv(['local_folder','s3_storage_class', 'profile'])
            if TABLECSV == None:
                print("No archives available.")
                return False
            app = TableArchive()
            retline=app.run()
            if not retline:
                return False
            if len(retline) < 2:
                print('Error: froster-archives table did not return result')
                return False
            if args.debug:
                print("dialog returns:",retline)
            args.folders.append(retline[0])
            if retline[2]: 
                cfg.awsprofile = retline[2]
                args.awsprofile = cfg.awsprofile
                cfg._set_env_vars(cfg.awsprofile)
                if args.debug:
                    print("AWS profile:", cfg.awsprofile)

        if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
            print(f'Profile "{args.awsprofile}" not found.')
            return False
        if not cfg.check_bucket_access(cfg.bucket):
            return False

        if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
            for fld in args.folders:
                fld = fld.rstrip(os.path.sep)
                print (f'Restoring folder {fld}, please wait ...', flush=True)
                # check if triggered a restore from glacier and other conditions 
                if arch.restore(fld) > 0:                    
                    if shutil.which('sbatch') and \
                            args.noslurm == False and \
                            args.nodownload == False:
                        # start a future Slurm job just for the download
                        se = SlurmEssentials(args, cfg)
                        #get a job start time 12 hours from now
                        fut_time = se.get_future_start_time(12)
                        label=fld.replace('/','+')
                        shortlabel=os.path.basename(fld)
                        myjobname=f'froster:restore:{shortlabel}'                        
                        email=cfg.read('general', 'email')
                        se.add_line(f'#SBATCH --job-name={myjobname}')
                        se.add_line(f'#SBATCH --begin={fut_time}')
                        se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
                        se.add_line(f'#SBATCH --mem=64G')
                        se.add_line(f'#SBATCH --requeue')
                        se.add_line(f'#SBATCH --output=froster-download-{label}-%J.out')
                        se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')           
                        se.add_line(f'#SBATCH --mail-user={email}')
                        se.add_line(f'#SBATCH --time=1-0')
                        cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline
                        if not "--profile" in cmdline and args.awsprofile:            
                            cmdline = cmdline.replace('/froster.py ', f'/froster --profile {args.awsprofile} ')
                        else:
                            cmdline = cmdline.replace('/froster.py ', '/froster ')
                        if not fld in cmdline:
                            cmdline=f'{cmdline} "{fld}"'
                        if args.debug:
                            print(f'Command line passed to Slurm:\n{cmdline}')
                        se.add_line(cmdline)
                        jobid = se.sbatch()
                        print(f'Submitted froster download job to run in 12 hours: {jobid}')
                        print(f'Check Job Output:')
                        print(f' tail -f froster-download-{label}-{jobid}.out')
                    else:
                        print(f'\nGlacier retrievals pending, run this again in up to 12h\n')
                                        
        else:
            se = SlurmEssentials(args, cfg)
            label=args.folders[0].replace('/','+')
            shortlabel=os.path.basename(args.folders[0])
            myjobname=f'froster:restore:{shortlabel}'
            email=cfg.read('general', 'email')
            se.add_line(f'#SBATCH --job-name={myjobname}')
            se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
            se.add_line(f'#SBATCH --mem=64G')
            se.add_line(f'#SBATCH --requeue')
            se.add_line(f'#SBATCH --output=froster-restore-{label}-%J.out')
            se.add_line(f'#SBATCH --mail-type=FAIL,REQUEUE,END')           
            se.add_line(f'#SBATCH --mail-user={email}')
            se.add_line(f'#SBATCH --time=1-0')            
            cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline            
            if not "--profile" in cmdline and args.awsprofile:            
                cmdline = cmdline.replace('/froster.py ', f'/froster --profile {args.awsprofile} ')
            else:
                cmdline = cmdline.replace('/froster.py ', '/froster ')
            if not args.folders[0] in cmdline:
                folders = '" "'.join(args.folders)
                cmdline=f'{cmdline} "{folders}"'
            if args.debug:
                print(f'Command line passed to Slurm:\n{cmdline}')
            se.add_line(cmdline)
            jobid = se.sbatch()
            print(f'Submitted froster restore job: {jobid}')
            print(f'Check Job Output:')
            print(f' tail -f froster-restore-{label}-{jobid}.out')

    elif args.subcmd in ['delete', 'del']:
    
        if args.debug:
            print ("delete:",args.awsprofile, args.folders)
        fld = '" "'.join(args.folders)
        if args.debug:
            print (f'default cmdline: froster.py delete "{fld}"')

        if not args.folders:
            TABLECSV=arch.archive_json_get_csv(['local_folder','s3_storage_class', 'profile'])
            if TABLECSV == None:
                print("No archives available.")
                return False
            app = TableArchive()
            retline=app.run()
            if not retline:
                return False
            if len(retline) < 2:
                print('Error: froster-archives table did not return result')
                return False
            if args.debug:
                print("dialog returns:",retline)
            args.folders.append(retline[0])
            if retline[2]: 
                cfg.awsprofile = retline[2]
                args.awsprofile = cfg.awsprofile
                cfg._set_env_vars(cfg.awsprofile)

        if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
            print(f'Profile "{args.awsprofile}" not found.')
            return False
        if not cfg.check_bucket_access(cfg.bucket):
            return False

        for fld in args.folders:
            fld = fld.rstrip(os.path.sep)
            # get archive storage location
            print (f'Deleting archived objects in {fld}, please wait ...', flush=True)
            rowdict = arch.archive_json_get_row(fld)
            if rowdict == None:
                print(f'Folder "{fld}" not in archive.')
                continue
            archive_folder = rowdict['archive_folder']

            # compare archive hashes with local hashfile
            rclone = Rclone(args,cfg)                
            hashfile = os.path.join(fld,'.froster.md5sum')
            if not os.path.exists(hashfile):
                print(f'Hashfile {hashfile} does not exist. \nCannot delete files in {fld}')
                continue
            ret = rclone.checksum(hashfile,archive_folder)
            if args.debug:
                print('*** RCLONE checksum ret ***:\n', ret, '\n')
            if ret['stats']['errors'] > 0:
                print('Last Error:', ret['stats']['lastError'])
                print('Checksum test was not successful.')
                return False
            
            # delete files if confirmed that hashsums are identical
            delete_files=[]
            with open(hashfile, 'r') as inp:
                for line in inp:
                    fn = line.strip().split('  ', 1)[1]
                    delete_files.append(fn)
            deleted_files=[]
            for dfile in delete_files:
                dpath = os.path.join(fld,dfile)
                if os.path.isfile(dpath):
                    try:
                        os.remove(dpath)
                        deleted_files.append(dfile)
                        if args.debug: print(f"File '{dpath}' deleted successfully.") 
                    except OSError as e:
                        print(f"Error deleting the file: {e}")
            if len(deleted_files) > 0:
                email = cfg.read('general', 'email')
                readme = os.path.join(fld,'Where-did-the-files-go.txt')
                with open(readme, 'w') as rme:
                    rme.write(f'The files in this folder have been moved to an archive!\n')
                    rme.write(f'\nArchive location: {archive_folder}\n')
                    rme.write(f'Archive profile (~/.aws): {cfg.awsprofile}\n')
                    rme.write(f'Archiver: {email}\n')
                    rme.write(f'Archive tool: https://github.com/dirkpetersen/froster\n')
                    rme.write(f'Deletion date: {datetime.datetime.now()}\n')
                    rme.write(f'\nFiles archived:\n')
                    rme.write('\n'.join(deleted_files))
                    rme.write(f'\n')
                print(f'Deleted files and wrote manifest to {readme}')
            else:
                print(f'No files were deleted.')

    if args.subcmd in ['mount', 'mnt', 'umount']:
        if args.debug:
            print ("delete:",args.awsprofile, args.mountpoint, args.folders)
        fld = '" "'.join(args.folders)

        if args.debug:
            print (f'default cmdline: froster.py mount "{fld}"')

        interactive=False
        if not args.folders:
            interactive=True
            TABLECSV=arch.archive_json_get_csv(['local_folder','s3_storage_class', 'profile'])
            if TABLECSV == None:
                print("No archives available.")
                return False
            app = TableArchive()
            retline=app.run()
            if not retline:
                return False
            if len(retline) < 2:
                print('Error: froster-archives table did not return result')
                return False
            if args.debug:
                print("dialog returns:",retline)
            args.folders.append(retline[0])
            if retline[2]: 
                cfg.awsprofile = retline[2]
                args.awsprofile = cfg.awsprofile
                cfg._set_env_vars(cfg.awsprofile)      

        if args.awsprofile and args.awsprofile not in cfg.get_aws_profiles():
            print(f'Profile "{args.awsprofile}" not found.')
            return False
        if not cfg.check_bucket_access(cfg.bucket):
            return False

        hostname = platform.node()
        for fld in args.folders:
            fld = fld.rstrip(os.path.sep)
            # get archive storage location
            rowdict = arch.archive_json_get_row(fld)
            if rowdict == None:
                print(f'Folder "{fld}" not in archive.')
                continue
            archive_folder = rowdict['archive_folder']

            rclone = Rclone(args,cfg)
            if args.mountpoint and os.path.isdir(args.mountpoint):
                fld=args.mountpoint 
            if args.unmount or args.subcmd == 'umount':
                print (f'Unmounting folder {fld} ... ', flush=True, end="")
                rclone.unmount(fld)
                print('Done!', flush=True)
            else:
                print (f'Mounting archive folder at {fld} ... ', flush=True, end="")
                pid = rclone.mount(archive_folder,fld)
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

class Archiver:
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.archive_json = os.path.join(cfg.config_root, 'froster-archives.json')
        x = self.cfg.read('general', 'min_index_folder_size_gib')
        self.thresholdGB = int(x) if x else 10
        x = self.cfg.read('general', 'min_index_folder_size_avg_mib')
        self.thresholdMB = int(x) if x else 10
        x = self.cfg.read('general', 'max_hotspots_display_entries')
        global MAXHOTSPOTS
        MAXHOTSPOTS = int(x) if x else 5000
        
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.grants = []

    def index(self, pwalkfolder):

        # move down to class 
        daysaged=[5475,3650,1825,1095,730,365,90,30]
        TiB=1099511627776
        #GiB=1073741824
        #MiB=1048576
    
        # Connect to an in-memory DuckDB instance
        con = duckdb.connect(':memory:')
        #con.execute('PRAGMA experimental_parallel_csv=TRUE;') # now standard 
        con.execute(f'PRAGMA threads={self.args.cores};')

        locked_dirs = ''
        with tempfile.NamedTemporaryFile() as tmpfile:
            with tempfile.NamedTemporaryFile() as tmpfile2:
                if not self.args.pwalkcsv:
                    #if not pwalkfolder:
                    #    print (" Error: Either pass a folder or a --pwalk-csv file on the command line.")
                    pwalkcmd = 'pwalk --NoSnap --one-file-system --header'
                    mycmd = f'{self.cfg.binfolder}/{pwalkcmd} "{pwalkfolder}" > {tmpfile2.name}' # 2> {tmpfile2.name}.err'
                    if self.args.debug:
                        print(f' Running {mycmd} ...', flush=True)
                    ret = subprocess.run(mycmd, shell=True, 
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if ret.returncode != 0:
                        print(f'pwalk run failed: {mycmd} Error:\n{ret.stderr}')
                        return False
                    lines = ret.stderr.decode('utf-8').splitlines()
                    locked_dirs = '\n'.join([l for l in lines if "Locked Dir:" in l]) 
                    pwalkcsv = tmpfile2.name
                else:
                    pwalkcsv = self.args.pwalkcsv
                with tempfile.NamedTemporaryFile() as tmpfile3:
                    # removing all files from pwalk output, keep only folders
                    mycmd = f'grep -v ",-1,0$" "{pwalkcsv}" > {tmpfile3.name}'
                    if self.args.debug:
                        print(f' Running {mycmd} ...', flush=True)
                    result = subprocess.run(mycmd, shell=True)
                    if result.returncode != 0:
                        print(f"Folder extraction failed: {mycmd}")
                        return False
                    # Temp hack: e.g. Revista_Española_de_Quimioterapia in Spellman
                    # Converting file from ISO-8859-1 to utf-8 to avoid DuckDB import error
                    # pwalk does already output UTF-8, weird, probably duckdb error 
                    mycmd = f'iconv -f ISO-8859-1 -t UTF-8 {tmpfile3.name} > {tmpfile.name}'
                    if self.args.debug:
                        print(f' Running {mycmd} ...', flush=True)
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
            if self.args.debug:
                print(f' Running SQL query on CSV file {tmpfile.name} ...', flush=True)
            rows = con.execute(sql_query).fetchall()
            # also query 'parent-inode' as pi,
            
            # Get the column names
            header = con.execute(sql_query).description

        totalbytes=0
        agedbytes=[]
        for i in daysaged:
            agedbytes.append(0)
        numhotspots=0

        mycsv = self._get_hotspots_path(pwalkfolder)
        if self.args.debug:
            print(f' Running filter and write results to CSV file {mycsv} ...', flush=True)

        with tempfile.NamedTemporaryFile() as tmpcsv:
            with open(tmpcsv.name, 'w') as f:
                writer = csv.writer(f, dialect='excel')
                writer.writerow([col[0] for col in header])
                # 0:Usr,1:AccD,2:ModD,3:GiB,4:MiBAvg,5:Folder,6:Grp,7:TiB,8:FileCount,9:DirSize
                for r in rows:
                    row = list(r)
                    if row[3] >= self.thresholdGB and row[4] >= self.thresholdMB:
                        row[0]=self.uid2user(row[0])                        
                        row[1]=self.daysago(self._get_newest_file_atime(row[5],row[1]))
                        row[2]=self.daysago(row[2])
                        row[3]=int(row[3])
                        row[4]=int(row[4])
                        row[6]=self.gid2group(row[6])
                        row[7]=int(row[7])
                        writer.writerow(row)
                        numhotspots+=1
                        totalbytes+=row[9]
                    for i in range(0,len(daysaged)):
                        if row[1] > daysaged[i]:
                            agedbytes[i]+=row[9]
            if numhotspots > 0:
                shutil.copyfile(tmpcsv.name,mycsv)

        if numhotspots > 0:
            # dedented multi-line retaining \n
            print(textwrap.dedent(f'''       
                Wrote {os.path.basename(mycsv)}
                with {numhotspots} hotspots >= {self.thresholdGB} GiB 
                with a total disk use of {round(totalbytes/TiB,3)} TiB
                '''), flush=True)
            lastagedbytes=0
            print(f'Histogram for {len(rows)} total folders processed:', flush=True)
            for i in range(0,len(daysaged)):
                if agedbytes[i] > 0 and agedbytes[i] != lastagedbytes:
                    # dedented multi-line removing \n
                    print(textwrap.dedent(f'''  
                    {round(agedbytes[i]/TiB,3)} TiB have not been accessed 
                    for {daysaged[i]} days (or {round(daysaged[i]/365,1)} years)
                    ''').replace('\n', ''), flush=True)
                lastagedbytes=agedbytes[i]
            print('')
        else:
            print(f'No folders larger than {self.thresholdGB} GiB found under {pwalkfolder}', flush=True)                

        if locked_dirs:
            print('\n'+locked_dirs, flush=True)
            print(textwrap.dedent(f'''
            \n   WARNING: You cannot access the locked folder(s) 
            above, because you don't have permissions to see
            their content. You will not be able to archive these
            folders until you have the permissions granted.
            '''), flush=True)
        if self.args.debug:
            print(' Done indexing!', flush=True)

    def archive(self, folder):

        source = os.path.abspath(folder)
        target = os.path.join(f':s3:{self.cfg.archivepath}',
                              source.lstrip(os.path.sep))

        if os.path.isfile(os.path.join(source,".froster.md5sum")):
            print(f'  The hashfile ".froster.md5sum" already exists in {source} from a previous archiving process.')
            print('  You need to manually rename the file before you can proceed.')
            print('  Without a valid ".froster.md5sum" in a folder you will not be able to use "froster" for restores')
            return False

        print ('  Generating hashfile .froster.md5sum ...')
        ret = self.gen_md5sums(source,'.froster.md5sum')
        if ret == 13: # cannot write to folder 
            return False
        elif not ret:
            print ('  Could not create hashfile .froster.md5sum.') 
            print ('  Perhaps there are no files or the folder does not exist?')
            return False
        hashfile = os.path.join(source,'.froster.md5sum')

        rclone = Rclone(self.args,self.cfg)
        #
        # create a simple file list from a hash file #tempfile.NamedTemporaryFile('w') as outp
        # weird: rclone does not copy with --files-from when executed from Python
        #with open(hashfile, 'r') as inp, tempfile.NamedTemporaryFile('w') as outp:
        #    for line in inp:
        #        file_name = line.strip().split('  ', 1)[1]                
        #        outp.write(f'{file_name}\n')
        #    ret = rclone.copy(source, target,'--files-from', outp.name) 
            
        print ('Copying files to archive ...')
        ret = rclone.copy(source,target,'--max-depth', '1', '--links',
                        '--exclude', '.froster.md5sum', 
                        '--exclude', '.froster-restored.md5sum', 
                        '--exclude', 'Where-did-the-files-go.txt'
                        )
        if self.args.debug:
            print('*** RCLONE copy ret ***:\n', ret, '\n')
        #print ('Message:', ret['msg'].replace('\n',';'))
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Copying was not successful.')
            return False
        
        ttransfers=ret['stats']['totalTransfers']
        tbytes=ret['stats']['totalBytes']
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

        ret = rclone.checksum(hashfile,target)
        if self.args.debug:
            print('*** RCLONE checksum ret ***:\n', ret, '\n')
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Checksum test was not successful.')
            return False

        # If success, write metadata to froster-archives.json database
        s3_storage_class=os.getenv('RCLONE_S3_STORAGE_CLASS','STANDARD')
        timestamp=datetime.datetime.now().isoformat()
        dictrow = {'local_folder': source, 'archive_folder': target,
                   's3_storage_class': s3_storage_class, 'profile': self.cfg.awsprofile, 
                   'timestamp': timestamp, 'timestamp_archive': timestamp, 
                   'user': getpass.getuser()
                   }
        self.archive_json_put_row(source, dictrow)        
        total=self.convert_size(tbytes)
        print(f'Source and archive are identical. {ttransfers} files with {total} transferred.')

    def test_write(self, directory):
        testpath=os.path.join(directory,'.froster.test')
        try:
            with open(testpath, "w") as f:
                f.write('just a test')
            os.remove(testpath)
            return True
        except PermissionError as e:
            if e.errno == 13:  # Check if error number is 13 (Permission denied)
                #print("Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                return 13
            else:
                print(f"An unexpected PermissionError occurred in {directory}:\n{e}")            
                return False
        except Exception as e:
            if e.errno == 2:
                #No such file or directory:
                return 2
            else:
                print(f"An unexpected error occurred in {directory}:\n{e}")
                return False

    def gen_md5sums(self, directory, hash_file, num_workers=4, no_subdirs=True):
        for root, dirs, files in os.walk(directory):
            if no_subdirs and root != directory:
                break            
            hashpath=os.path.join(root, hash_file)
            try:
                with open(hashpath, "w") as out_f:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                        tasks = {}
                        for filen in files:
                            file_path = os.path.join(root, filen)
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
            except PermissionError as e:
                if e.errno == 13:  # Check if error number is 13 (Permission denied)
                    print("Permission denied. Please ensure you have the necessary permissions to access the file or directory.")
                    return 13
                else:
                    print(f"An unexpected PermissionError occurred:\n{e}")            
                    return False
            except Exception as e:
                print(f"An unexpected error occurred:\n{e}")
                return False
            return True

    def restore(self, folder):

        # copied from archive
        rowdict = self.archive_json_get_row(folder)
        if rowdict == None:
            return False

        source = rowdict['archive_folder']
        target = rowdict['local_folder']
        s3_storage_class = rowdict['s3_storage_class']

        if s3_storage_class in ['DEEP_ARCHIVE', 'GLACIER']:
            sps = source.split('/', 1)
            bk = sps[0].replace(':s3:','')
            pr = f'{sps[1]}/' # trailing slash ensured 
            trig, rest, done = self.glacier_restore(bk, pr, 
                                    self.args.days, self.args.retrieveopt)
            print ('Triggered Glacier retrievals:',len(trig))
            print ('Currently retrieving from Glacier:',len(rest))
            print ('Not in Glacier:',len(done))
            if len(trig) > 0 or len(rest) > 0:
                # glacier is still ongoing, return # of pending ops                
                return len(trig)+len(rest)
            
        if self.args.nodownload:
            return -1
            
        rclone = Rclone(self.args,self.cfg)
            
        print ('Copying files from archive ...')
        ret = rclone.copy(source,target,'--max-depth', '1')
            
        if self.args.debug:
            print('*** RCLONE copy ret ***:\n', ret, '\n')
        #print ('Message:', ret['msg'].replace('\n',';'))
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Copying was not successful.')
            return False
            # lastError could contain: Object in GLACIER, restore first
        
        ttransfers=ret['stats']['totalTransfers']
        tbytes=ret['stats']['totalBytes']
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

        print ('Generating hashfile .froster-restored.md5sum ...')
        ret = self.gen_md5sums(target,'.froster-restored.md5sum')
        if ret == 13: # cannot write to folder 
            return False

        hashfile = os.path.join(target,'.froster-restored.md5sum')

        ret = rclone.checksum(hashfile,source)
        if self.args.debug:
            print('*** RCLONE checksum ret ***:\n', ret, '\n')
        if ret['stats']['errors'] > 0:
            print('Last Error:', ret['stats']['lastError'])
            print('Checksum test was not successful.')
            return False
        
        total=self.convert_size(tbytes)
        print(f'Target and archive are identical. {ttransfers} files with {total} transferred.')
        return -1
    
    def md5sumex(self, file_path):
        try:
            cmd = f'md5sum {file_path}'
            ret = subprocess.run(cmd, stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, Shell=True)                    
            if ret.returncode != 0:
                print(f'md5sum return code > 0: {cmd} Error:\n{ret.stderr}')
            return ret.stdout.strip() #, ret.stderr.strip()

        except Exception as e:
            print (f'md5sum Error: {str(e)}')
            return None, str(e)
                             
    def md5sum(self, file_path):
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()


    def something(self, var1, var2):
        return var1
    
    def uid2user(self,uid):
        # try to convert uid to user name
        try:
            return pwd.getpwuid(uid)[0]
        except:
            if self.args.debug:
                print(f'uid2user: Error converting uid {uid}')
            return uid

    def gid2group(self,gid):
        # try to convert gid to group name
        try:
            return grp.getgrgid(gid)[0]
        except:
            if self.args.debug:
                print(f' gid2group: Error converting gid {gid}')
            return gid

    def daysago(self,unixtime):
        # how many days ago is this epoch time ?
        if not unixtime: 
            if self.args.debug:
                print(' daysago: an integer is required (got type NoneType)')
            return 0
        diff=datetime.datetime.now()-datetime.datetime.fromtimestamp(unixtime)
        return diff.days
    
    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes/p, 3)
        return f"{s} {size_name[i]}"
    
    def archive_json_put_row(self, path_name, row_dict):
        data = {}
        if os.path.exists(self.archive_json):
            with open(self.archive_json, 'r') as file:
                try:
                    data = json.load(file)
                #except json.JSONDecodeError:             
                except:
                    print('Error in Archiver._archive_json_put_row():')
                    print(f'Cannot read {self.archive_json}, file corrupt?')
                    return None
        path_name = path_name.rstrip(os.path.sep) # remove trailing slash
        row_dict['local_folder'] = path_name #this is a key that can be changed
        data[path_name] = row_dict
        with open(self.archive_json, 'w') as file:
            json.dump(data, file, indent=4)

    def archive_json_get_row(self, path_name):
        if not os.path.exists(self.archive_json):
            return None        
        with open(self.archive_json, 'r') as file:            
            try:
                data = json.load(file)
            #except json.JSONDecodeError:             
            except:
                print('Error in Archiver._archive_json_get_row():')
                print(f'Cannot read {self.archive_json}, file corrupt?')
                return None
        path_name = path_name.rstrip(os.path.sep) # remove trailing slash
        if path_name in data:
            return data[path_name]
        else:
            return None

    def archive_json_get_csv(self, columns):
        if not os.path.exists(self.archive_json):
            return None    
        with open(self.archive_json, 'r') as file:
                try:
                    data = json.load(file)
                #except json.JSONDecodeError:             
                except:
                    print('Error in Archiver._archive_json_get_csv():')
                    print(f'Cannot read {self.archive_json}, file corrupt?')
                    return None
        # Sort data by timestamp in reverse order
        sorted_data = sorted(data.items(), key=lambda x: x[1]['timestamp'], reverse=True)
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
        #last_accessed_file = None
        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)
            if os.path.isfile(file_path):
                accessed_time = os.path.getatime(file_path)
                if last_accessed_time is None or accessed_time > last_accessed_time:
                    last_accessed_time = accessed_time
                    #last_accessed_file = file_path
        if last_accessed_time == None:
            last_accessed_time = folder_atime
        return last_accessed_time

    def _get_hotspots_path(self,folder):
        # get a full path name of a new hotspots file
        # based on a folder name that has been crawled
        hsfld = os.path.join(self.cfg.config_root, 'hotspots')
        os.makedirs(hsfld,exist_ok=True)
        return os.path.join(hsfld,self._get_hotspots_file(folder))

    def _get_hotspots_file(self,folder):
        # get a full path name of a new hotspots file
        # based on a folder name that has been crawled
        mountlist = self._get_mount_info()
        traildir = ''
        hsfile = folder.replace('/','+') + '.csv'
        for mnt in mountlist:
            if folder.startswith(mnt['mount_point']):
                traildir = self._get_last_directory(
                    mnt['mount_point'])
                hsfile = folder.replace(mnt['mount_point'],'')
                hsfile = hsfile.replace('/','+') + '.csv'
                hsfile = f'@{traildir}{hsfile}'
                if len(hsfile) > 255:
                    hsfile = f'{hsfile[:25]}.....{hsfile[-225:]}'
        return hsfile
    
    def _get_last_directory(self, path):
        # Remove any trailing slashes
        path = path.rstrip(os.path.sep)
        # Split the path by the separator
        path_parts = path.split(os.path.sep)
        # Return the last directory
        return path_parts[-1]
 
    def _get_mount_info(self,fs_types=None):
        file_path='/proc/self/mountinfo'
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
                mount_source_folder = mount_source.split(':')[-1] if ':' in mount_source else ''
                if fs_type in fs_types:
                    mountinfo_list.append({
                        'mount_source_folder': mount_source_folder,
                        'mount_point': mount_point,
                        'fs_type': fs_type,
                        'mount_source': mount_source,
                    })
        return mountinfo_list    
        
    def glacier_restore(self, bucket_name, prefix, keep_days=30, ret_opt="Bulk"):
        #this is dropping back to default creds, need to fix
        #print("AWS_ACCESS_KEY_ID:", os.environ['AWS_ACCESS_KEY_ID'])
        #print("AWS_PROFILE:", os.environ['AWS_PROFILE'])
        glacier_classes = {'GLACIER', 'DEEP_ARCHIVE'}
        try:
            # not needed here as profile comes from env
            #session = boto3.Session(profile_name=profile)
            #s3 = session.client('s3')
            s3 = boto3.client('s3')
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                print(f"Access denied for bucket '{bucket_name}'")
                print('Check your permissions and/or credentials.')
            else:
                print(f"An error occurred: {e}")
            return [], [], []
        triggered_keys = []
        restoring_keys = []
        restored_keys = []
        for page in pages:
            for obj in page['Contents']:
                object_key = obj['Key']
                # Check if there are additional slashes after the prefix,
                # indicating that the object is in a subfolder.
                remaining_path = object_key[len(prefix):]
                if '/' not in remaining_path:
                    header = s3.head_object(Bucket=bucket_name, Key=object_key)
                    if 'StorageClass' in header:
                        if not header['StorageClass'] in glacier_classes:
                            restored_keys.append(object_key)
                            continue
                    else:
                        continue 
                    if 'Restore' in header:
                        if 'ongoing-request="true"' in header['Restore']:
                            restoring_keys.append(object_key)
                            continue
                    try:
                        s3.restore_object(
                            Bucket=bucket_name,
                            Key=object_key,
                            RestoreRequest={
                                'Days': keep_days,
                                'GlacierJobParameters': {
                                    'Tier': ret_opt
                                }
                            }
                        )
                        triggered_keys.append(object_key)
                        if self.args.debug:
                            print(f'Restore request initiated for {object_key} using {ret_opt} retrieval.')
                    except botocore.exceptions.ClientError as e:
                        if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
                            print(f'Restore is already in progress for {object_key}. Skipping...')
                            restoring_keys.append(object_key)
                        else:
                            print(f'Error occurred for {object_key}: {e}')                    
                    except:
                        print(f'Restore request for {object_key} failed.')
        return triggered_keys, restoring_keys, restored_keys

    def glacier_restore_status(self, bucket_name, object_key):
        s3 = boto3.client('s3')
        response = s3.head_object(Bucket=bucket_name, Key=object_key)
        print('head response', response)
        if 'Restore' in response:
            return response['Restore'].find('ongoing-request="false"') > -1
        return False

    def download_restored_file(self, bucket_name, object_key, local_path):
        s3 = boto3.resource('s3')
        s3.Bucket(bucket_name).download_file(object_key, local_path)
        print(f'Downloaded {object_key} to {local_path}.')

    # initiate_restore(bucket_name, object_key, restore_days)    
    # while not check_restore_status(bucket_name, object_key):
    #     print('Waiting for restoration to complete...')
    #     time.sleep(60)  # Wait 60 seconds before checking again
    # download_restored_file(bucket_name, object_key, local_path)

class TableHotspots(App[list]):

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.zebra_stripes = True    
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        fh = open(SELECTEDFILE, 'r')
        rows = csv.reader(fh)
        table.add_columns(*next(rows))
        table.add_rows(itertools.islice(rows,MAXHOTSPOTS))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

class TableArchive(App[list]):

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.zebra_stripes = True
        table.cursor_type = "row"
        table.styles.max_height = "99vh"
        #table.fixed_rows = 1
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)        
        rows = csv.reader(io.StringIO(TABLECSV))
        table.add_columns(*next(rows))
        table.add_rows(itertools.islice(rows,MAXHOTSPOTS))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))


class Rclone:
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.rc = os.path.join(self.cfg.binfolder,'rclone')

    # ensure that file exists or nagging /home/dp/.config/rclone/rclone.conf

    #backup: rclone --verbose --files-from tmpfile --use-json-log copy --max-depth 1 ./tests/ :s3:posix-dp/tests4/ --exclude .froster.md5sum
    #restore: rclone --verbose --use-json-log copy --max-depth 1 :s3:posix-dp/tests4/ ./tests2
    #rclone copy --verbose --use-json-log --max-depth 1  :s3:posix-dp/tests5/ ./tests5
    #rclone --use-json-log checksum md5 ./tests/.froster.md5sum :s3:posix-dp/tests2/
    # storage tier for each file 
    #rclone lsf --csv :s3:posix-dp/tests4/ --format=pT
    # list without subdir 
    #rclone lsjson --metadata --no-mimetype --no-modtime --hash :s3:posix-dp/tests4
    #rclone checksum md5 ./tests/.froster.md5sum --verbose --use-json-log :s3:posix-dp/archive/home/dp/gh/froster/tests

    def _run_rc(self, command):

        command = self._add_opt(command, '--verbose')
        command = self._add_opt(command, '--use-json-log')
        if self.args.debug:
            print("Rclone command:", " ".join(command))
        try:
            ret = subprocess.run(command, capture_output=True, text=True, env=self.cfg.envrn)
            if ret.returncode != 0:
                #pass
                sys.stderr.write(f'*** Error, Rclone return code > 0:\n {command} Error:\n{ret.stderr}')
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
            
            #lines = ret.stderr.decode('utf-8').splitlines() #needed if you do not use ,text=True
            #locked_dirs = '\n'.join([l for l in lines if "Locked Dir:" in l]) 
            #print("   STDOUT:",ret.stdout)
            #print("   STDERR:",ret.stderr)
            #rclone mount --daemon
            return ret.stdout.strip(), ret.stderr.strip()

        except Exception as e:
            print (f'Rclone Error: {str(e)}')
            return None, str(e)

    def _run_bk(self, command):
        #command = self._add_opt(command, '--verbose')
        #command = self._add_opt(command, '--use-json-log')
        cmdline=" ".join(command)
        if self.args.debug:
            print(f'Rclone command: "{cmdline}"')
        try:
            ret = subprocess.Popen(command, preexec_fn=os.setsid, stdin=subprocess.PIPE, 
                        stdout=subprocess.PIPE, text=True, env=self.cfg.envrn)
            #_, stderr = ret.communicate(timeout=3)  # This does not work with rclone
            if ret.stderr:
                sys.stderr.write(f'*** Error in command "{cmdline}":\n {ret.stderr} ')
            return ret.pid
        except Exception as e:
            print (f'Rclone Error: {str(e)}')
            return None

    def copy(self, src, dst, *args):
        command = [self.rc, 'copy'] + list(args)
        command.append(src)  #command.append(f'{src}/')
        command.append(dst)
        out, err = self._run_rc(command)
        if out:
            print(f'rclone copy output: {out}')
        #print('ret', err)
        stats, ops = self._parse_log(err) 
        if stats:
            return stats[-1] # return the stats
        else:
            return []
    
        #b'{"level":"warning","msg":"Time may be set wrong - time from \\"posix-dp.s3.us-west-2.amazonaws.com\\" is -9m17.550965814s different from this computer","source":"fshttp/http.go:200","time":"2023-04-16T14:40:47.44907-07:00"}'    

    def checksum(self, md5file, dst, *args):
        #checksum md5 ./tests/.froster.md5sum
        command = [self.rc, 'checksum'] + list(args)
        command.append('md5')
        command.append(md5file)
        command.append(dst)
        #print("Command:", command)
        out, err = self._run_rc(command)
        if out:
            print(f'rclone checksum output: {out}')
        #print('ret', err)
        stats, ops = self._parse_log(err) 
        if stats:
            return stats[-1] # return the stats
        else:
            return []

    def mount(self, url, mountpoint, *args):
        if not shutil.which('fusermount3'):
            print('Could not find "fusermount3". Please install the "fuse3" OS package')
            return False
        if not url.endswith('/'): url+'/'
        mountpoint = mountpoint.rstrip(os.path.sep)
        command = [self.rc, 'mount'] + list(args)
        # might use older rclone, if fuse3 is not installed
        #if os.path.isfile('/usr/bin/rclone'):
        #    command = ['/usr/bin/rclone', 'mount'] + list(args)            
        #command.append('--daemon') # not reliable, just starting background process
        command.append('--allow-non-empty')
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
                ret = subprocess.run(cmd, capture_output=False, text=True, env=self.cfg.envrn)
            else:
                rclone_pids = self._get_pids('rclone')
                fld_pids = self._get_pids(mountpoint, True)
                common_pids = [value for value in rclone_pids if value in fld_pids]
                for pid in common_pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        if wait:
                            _, _ = os.waitpid(int(pid), 0)
                        return True
                    except PermissionError:
                        print(f'Permission denied when trying to send signal SIGTERM to rclone process with PID {pid}.')
                    except Exception as e:
                        print(f'An unexpected error occurred when trying to send signal SIGTERM to rclone process with PID {pid}: {e}') 
        else:
            print(f'\nError: Folder {mountpoint} is currently not used as a mountpoint by rclone.')
                
    def version(self):
        command = [self.rc, 'version']
        return self._run_rc(command)
    
    def _get_pids(self, process, full=False):
        process = process.rstrip(os.path.sep)
        if full:
            command = ['pgrep', '-f', process]
        else:
            command = ['pgrep', process]
        try:
            output = subprocess.check_output(command)
            pids = [int(pid) for pid in output.decode().split('\n') if pid]
            return pids
        except subprocess.CalledProcessError:
            # No rclone processes found
            return []

    def _is_mounted(self, folder_path):
        folder_path = os.path.realpath(folder_path)  # Resolve any symbolic links
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
        lines=strstderr.split('\n')
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
        self._add_lines_from_cfg()

    def add_line(self, line):
        if line:
            self.script_lines.append(line)

    def get_future_start_time(self, add_hours):
        now = datetime.datetime.now()        
        future_time = now + datetime.timedelta(hours=add_hours)
        return future_time.strftime("%Y-%m-%dT%H:%M")
    
    def _add_lines_from_cfg(self):
        slurm_lscratch = self.cfg.read('hpc','slurm_lscratch')
        lscratch_mkdir = self.cfg.read('hpc','lscratch_mkdir')
        lscratch_root  = self.cfg.read('hpc','lscratch_root')
        if slurm_lscratch:
            self.add_line(f'#SBATCH {slurm_lscratch}')
        self.add_line(f'{lscratch_mkdir}')
        if lscratch_root:
            self.add_line('export TMPDIR=%s/${SLURM_JOB_ID}' % lscratch_root)

    def _reorder_sbatch_lines(self, script_buffer):
        # we need to make sure that all #BATCH are at the top
        script_buffer.seek(0)
        lines = script_buffer.readlines()
        shebang_line = lines.pop(0)  # Remove the shebang line from the list of lines
        sbatch_lines = [line for line in lines if line.startswith("#SBATCH")]
        non_sbatch_lines = [line for line in lines if not line.startswith("#SBATCH")]
        reordered_script = io.StringIO()
        reordered_script.write(shebang_line)
        for line in sbatch_lines:
            reordered_script.write(line)
        for line in non_sbatch_lines:
            reordered_script.write(line)
        # add a local scratch teardown, if configured
        reordered_script.write(self.cfg.read('hpc','lscratch_rmdir'))
        reordered_script.seek(0)
        return reordered_script

        # # Example usage:
        # script_buffer = StringIO("""#!/bin/bash
        # echo "Hello, SLURM!"
        # #SBATCH --job-name=my_job
        # #SBATCH --output=my_output.log
        # echo "This is a test job."
        # """.strip())
        # reordered_script = reorder_sbatch_lines(script_buffer)
        # print(reordered_script.getvalue())

    def sbatch(self):
        script = io.StringIO()
        for line in self.script_lines:
            script.write(line + "\n")
        script.seek(0)
        oscript = self._reorder_sbatch_lines(script)
        output = subprocess.check_output('sbatch', shell=True, 
                    text=True, input=oscript.read())
        job_id = int(output.split()[-1])
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
            raise RuntimeError(f"Error running squeue: {result.stderr.strip()}")
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
        jobdict=self._scontrol_show_job(job_id)
        return jobdict['Comment']

    def job_comment_write(self, job_id, comment):
        # a comment can be maximum 250 characters, will be chopped automatically 
        args = ['update', f'JobId={str(job_id)}', f'Comment={comment}', str(job_id)]
        result = subprocess.run(['scontrol'] + args, 
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error running scontrol: {result.stderr.strip()}")

    def _scontrol_show_job(self, job_id):
        args = ["--oneliner", "show", "job", str(job_id)]
        result = subprocess.run(['scontrol'] + args, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error running scontrol: {result.stderr.strip()}")
        self.job_info = self._parse_scontrol_output(result.stdout)

    def _parse_scontrol_output(self, output):
        fields = output.strip().split()
        job_info = {}
        for field in fields:
            key, value = field.split('=', 1)
            job_info[key] = value
        return job_info

    def display_job_info(self):
        print(self.job_info)

class ConfigManager:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries 
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as 
    # multi-line files and dictionaries which are written to json

    def __init__(self, args):
        self.args = args
        self.home_dir = os.path.expanduser('~')
        self.config_root_local = os.path.join(self.home_dir, '.config', 'froster')
        self.config_root = self._get_config_root()
        self.binfolder = self.read('general', 'binfolder')
        self.homepaths = self._get_home_paths()
        self.awscredsfile = os.path.join(self.home_dir, '.aws', 'credentials')
        self.awsconfigfile = os.path.join(self.home_dir, '.aws', 'config')
        self.awsconfigfileshr = os.path.join(self.config_root, 'aws_config')
        self.bucket = self.read('general','bucket')
        self.archivepath = os.path.join( 
             self.bucket,
             self.read('general','archiveroot'))
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
        
    def _set_env_vars(self, profile):
        
        # Read the credentials file
        config = configparser.ConfigParser()
        config.read(self.awscredsfile)
        self.aws_region = self.get_aws_region(profile)

        if not config.has_section(profile):
            if self.args.debug:
                print (f'~/.aws/credentials has no section for profile {profile}')
            return False
        if not config.has_option(profile, 'aws_access_key_id'):
            if self.args.debug:
                print (f'~/.aws/credentials has no entry aws_access_key_id in section/profile {profile}')
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
            self.envrn['RCLONE_S3_STORAGE_CLASS'] = self.read('general','s3_storage_class')
            os.environ['RCLONE_S3_STORAGE_CLASS'] = self.read('general','s3_storage_class')
        else:
            prf=self.read('profiles',profile)
            self.envrn['RCLONE_S3_ENV_AUTH'] = 'true'
            self.envrn['RCLONE_S3_PROFILE'] = profile
            if isinstance(prf,dict):  # profile={'name': '', 'provider': '', 'storage_class': ''}
                self.envrn['RCLONE_S3_PROVIDER'] = prf['provider']
                self.envrn['RCLONE_S3_ENDPOINT'] = self.get_aws_s3_session_endpoint_url(profile)
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
        theroot=self.config_root_local
        rootfile = os.path.join(theroot, 'config_root')
        if os.path.exists(rootfile):
            with open(rootfile, 'r') as myfile:
                theroot = myfile.read().strip()
                if not os.path.isdir(theroot):
                    if not self.ask_yes_no(f'{rootfile} points to a shared config that does not exist. Do you want to configure {theroot} now?'):
                        print (f"Please remove file {rootfile} to continue with a single user config.")
                        sys.exit(1)
                        #raise FileNotFoundError(f'Config root folder "{theroot}" not found. Please remove {rootfile}')
        return theroot

    def _get_section_path(self, section):
        return os.path.join(self.config_root, section)

    def _get_entry_path(self, section, entry):
        if section:
            section_path = self._get_section_path(section)
            return os.path.join(section_path, entry)
        else:
            return os.path.join(self.config_root, entry)

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
        default=''
        section=''
        key=''
        if not question.endswith(':'):
            question += ':'
        question = f"*** {question} ***"
        if isinstance(defaults, list):
            print(question)
            for i, option in enumerate(defaults, 1):
                print(f'  ({i}) {option}')           
            while True:
                selected = input("  Enter the number of your selection: ")
                if selected.isdigit() and 1 <= int(selected) <= len(defaults):
                    return defaults[int(selected) - 1]
                else:
                    print("  Invalid selection. Please enter a number from the list.")
        elif defaults is not None:
            deflist=defaults.split('|')
            if len(deflist) == 3:
                section=deflist[1]
                key=deflist[2]
                default = self.read(section, key)
                if not default:
                    default = deflist[0]
            elif len(deflist) == 2:
                section=deflist[0]
                key=deflist[1]
                default = self.read(section, key)                                
            elif len(deflist) == 1:
                default = deflist[0]
            #if default:
            question += f"\n  [Default: {default}]"
        else:
            question += f"\n  [Default: '']"
        while True:
            #user_input = input(f"\033[93m{question}\033[0m ")
            user_input = input(f"{question} ")
            if not user_input:
                if default is not None:
                    if section:
                        self.write(section,key,default)                    
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
                            self.write(section,key,value)
                        return value
                    except ValueError:
                        print("Invalid input. Please enter a number.")
                elif type_check == 'string':
                    if not user_input.isnumeric():
                        if section:
                            self.write(section,key,user_input)
                        return user_input
                    else:
                        print("Invalid input. Please enter a string not a number")
                else:
                    if section:
                        self.write(section,key,user_input)
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
            dest_section_data = dict(dest_parser.items(section)) if dest_parser.has_section(section) else {}

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
            print(f"Missing entries in source from destination copied back to {src_file}")

    def _check_s3_credentials(self, profile='default', verbose=False):
        from botocore.exceptions import NoCredentialsError, EndpointConnectionError, ClientError
        try:
            if verbose:
                print(f'  Checking credentials for profile "{profile}" ... ', end='')
            session = boto3.Session(profile_name=profile)
            ep_url = self.get_aws_s3_session_endpoint_url(profile)
            s3_client = session.client('s3', endpoint_url=ep_url)            
            s3_client.list_buckets()
            return True
        except NoCredentialsError:
            print("No AWS credentials found. Please check your access key and secret key.")
        except EndpointConnectionError:
            print("Unable to connect to the AWS S3 endpoint. Please check your internet connection.")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            #error_code = e.response['Error']['Code']             
            if error_code == 'RequestTimeTooSkewed':
                print(f"The time difference between S3 storage and your computer is too high:\n{e}")
            elif error_code == 'InvalidAccessKeyId':                
                print(f"Error: Invalid AWS Access Key ID in profile {profile}:\n{e}")
            elif error_code == 'SignatureDoesNotMatch':                
                if "Signature expired" in str(e): 
                    print(f"Error: Signature expired. The system time of your computer is likely wrong:\n{e}")
                    return False
                else:
                    print(f"Error: Invalid AWS Secret Access Key in profile {profile}:\n{e}")         
            elif error_code == 'InvalidClientTokenId':
                print(f"Error: Invalid AWS Access Key ID or Secret Access Key !")                
            else:
                print(f"Error validating credentials for profile {profile}: {e}")
            print(f"Fix your credentials in ~/.aws/credentials for profile {profile}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred while validating credentials for profile {profile}: {e}")
            return False

    
    def get_aws_profiles(self):
        # get the full list of profiles from ~/.aws/ profile folder
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
            profile_name = section.replace("profile ", "") #.replace("default", "default")
            profiles.append(profile_name)
        # convert list to set and back to list to remove dups
        return list(set(profiles))

    def create_aws_configs(self,access_key=None, secret_key=None, region=None):

        aws_dir = os.path.join(self.home_dir, ".aws")

        if not os.path.exists(aws_dir):
            os.makedirs(aws_dir)

        if not os.path.isfile(self.awsconfigfile):
            if region:
                print(f'\nAWS config file {self.awsconfigfile} does not exist, creating ...')            
                with open(self.awsconfigfile, "w") as config_file:
                    config_file.write("[default]\n")
                    config_file.write(f"region = {region}\n")
                    config_file.write("\n")
                    config_file.write("[profile aws]\n")
                    config_file.write(f"region = {region}\n")

        if not os.path.isfile(self.awscredsfile):
            print(f'\nAWS credentials file {self.awscredsfile} does not exist, creating ...')
            if not access_key: access_key = input("Enter your AWS access key ID: ")
            if not secret_key: secret_key = input("Enter your AWS secret access key: ")            
            with open(self.awscredsfile, "w") as credentials_file:
                credentials_file.write("[default]\n")
                credentials_file.write(f"aws_access_key_id = {access_key}\n")
                credentials_file.write(f"aws_secret_access_key = {secret_key}\n")
                credentials_file.write("\n")
                credentials_file.write("[aws]\n")
                credentials_file.write(f"aws_access_key_id = {access_key}\n")
                credentials_file.write(f"aws_secret_access_key = {secret_key}\n")
            os.chmod(self.awscredsfile, 0o600)

    def set_aws_config(self, profile, key, value, service=''):
        if key == 'endpoint_url': 
            if value.endswith('.amazonaws.com'):
                return False
            else:
                value = f'{value}\nsignature_version = s3v4'
        config = configparser.ConfigParser()
        config.read(os.path.expanduser("~/.aws/config"))
        section=profile
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
        if profile != 'default' and not self.args.cfgfolder: #when moving cfg it still writes to old folder
            self.replicate_ini(f'profile {profile}',self.awsconfigfile,self.awsconfigfileshr)
        return True
    
    def get_aws_s3_endpoint_url(self, profile='default'):
        # non boto3 method, use get_aws_s3_session_endpoint_url instead
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
        
    def get_aws_s3_session_endpoint_url(self, profile='default'):
        # retrieve endpoint url through boto API, not configparser
        import botocore.session
        session = botocore.session.Session(profile=profile)
        config = session.full_config
        s3_config = config["profiles"][profile].get("s3", {})
        endpoint_url = s3_config.get("endpoint_url", None)
        #print('*** endpoint url ***:', endpoint_url)
        return endpoint_url

    def get_aws_region(self, profile='default'):
        try:
            session = boto3.Session(profile_name=profile)
            #print(f'* get_aws_region for profile {profile}:', session.region_name)
            return session.region_name
        except:
            if self.args.debug:
                print(f'  cannot retrieve AWS region for profile {profile}, no valid profile or credentials')
            return ""
    
    def get_aws_regions(self, profile='default', provider='AWS'):
        # returns a list of AWS regions 
        if provider == 'AWS':
            try:
                session = boto3.Session(profile_name=profile)
                regions = session.get_available_regions('ec2')
                # make the list a little shorter 
                regions = [i for i in regions if not i.startswith('ap-')]
                return sorted(regions, reverse=True)
            except:
                return ['us-west-2','us-west-1', 'us-east-1', '']
        elif provider == 'GCS':
            return ['us-west1', 'us-east1', '']
        elif provider == 'Wasabi':
            return ['us-west-1', 'us-east-1', '']
        elif provider == 'IDrive':
            return ['us-or', 'us-va', 'us-la', '']
                
    def check_bucket_access(self, bucket_name, profile='default'):
        from botocore.exceptions import ClientError
        if not self._check_s3_credentials(profile):
            print('check_s3_credentials failed. Please edit file ~/.aws/credentials')
            return False
        session = boto3.Session(profile_name=profile)
        ep_url = self.get_aws_s3_session_endpoint_url(profile)
        s3 = session.client('s3', endpoint_url=ep_url)
        
        try:
            # Check if bucket exists
            s3.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                print(f"Error: Access denied to bucket {bucket_name} for profile {self.awsprofile}. Check your permissions.")
            elif error_code == '404':
                print(f"Error: Bucket {bucket_name} does not exist in profile {self.awsprofile}.")
                print("run 'froster config' to create this bucket.")
            else:
                print(f"Error accessing bucket {bucket_name} in profile {self.awsprofile}: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred for profile {self.awsprofile}: {e}")
            return False

        # Test write access by uploading a small test file
        try:
            test_object_key = "test_write_access.txt"
            s3.put_object(Bucket=bucket_name, Key=test_object_key, Body="Test write access")
            #print(f"Successfully wrote test to {bucket_name}")

            # Clean up by deleting the test object
            s3.delete_object(Bucket=bucket_name, Key=test_object_key)
            #print(f"Successfully deleted test object from {bucket_name}")
            return True
        except ClientError as e:
            print(f"Error: cannot write to bucket {bucket_name} in profile {self.awsprofile}: {e}")
            return False

    def create_s3_bucket(self, bucket_name, profile='default'):
        from botocore.exceptions import BotoCoreError, ClientError      
        if not self._check_s3_credentials(profile, verbose=True):
            print(f"Cannot create bucket '{bucket_name}' with these credentials")
            print('check_s3_credentials failed. Please edit file ~/.aws/credentials')
            return False 
        region = self.get_aws_region(profile)
        session = boto3.Session(profile_name=profile)
        ep_url = self.get_aws_s3_session_endpoint_url(profile)
        s3_client = session.client('s3', endpoint_url=ep_url)        
        existing_buckets = s3_client.list_buckets()
        for bucket in existing_buckets['Buckets']:
            if bucket['Name'] == bucket_name:
                if self.args.debug:
                    print(f'S3 bucket {bucket_name} exists')
                return True
        try:
            response = s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
                )
            print(f"Created S3 Bucket '{bucket_name}'")
        except BotoCoreError as e:
            print(f"BotoCoreError: {e}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidBucketName':
                print(f"Error: Invalid bucket name '{bucket_name}'\n{e}")
            elif error_code == 'BucketAlreadyExists':
                pass
                #print(f"Error: Bucket '{bucket_name}' already exists.")
            elif error_code == 'BucketAlreadyOwnedByYou':
                pass
                #print(f"Error: You already own a bucket named '{bucket_name}'.")
            elif error_code == 'InvalidAccessKeyId':
                #pass
                print("Error: InvalidAccessKeyId. The AWS Access Key Id you provided does not exist in our records")
            elif error_code == 'SignatureDoesNotMatch':
                pass
                #print("Error: Invalid AWS Secret Access Key.")
            elif error_code == 'AccessDenied':
                print("Error: Access denied. Check your account permissions for creating S3 buckets")
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
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidBucketName':
                print(f"Error: Invalid bucket name '{bucket_name}'\n{e}")
            elif error_code == 'AccessDenied':
                print("Error: Access denied. Check your account permissions for creating S3 buckets")
            elif error_code == 'IllegalLocationConstraintException':
                print(f"Error: The specified region '{region}' is not valid.")
            elif error_code == 'InvalidLocationConstraint':
                if not ep_url:
                    # do not show this error with non AWS endpoints 
                    print(f"Error: The specified location-constraint '{region}' is not valid")
            else:
                print(f"ClientError: {e}")                        
        except Exception as e:            
            print(f"An unexpected error occurred: {e}")
            return False            
        return True
        
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

    def write(self, section, entry, value):
        entry_path = self._get_entry_path(section, entry)
        os.makedirs(os.path.dirname(entry_path), exist_ok=True)
        if value == '""':
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

    def read(self, section, entry):
        entry_path = self._get_entry_path(section, entry)
        if not os.path.exists(entry_path):
            return ""
            #raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')
        with open(entry_path, 'r') as entry_file:
            try:
                return json.load(entry_file)                
            except json.JSONDecodeError:
                pass
            except:
                print('Error in ConfigManager.read()')
        with open(entry_path, 'r') as entry_file:
                content = entry_file.read().splitlines()
                if len(content) == 1:
                    return content[0].strip()
                else:
                    return content.strip()

    def delete(self, section, entry):
        entry_path = self._get_entry_path(section, entry)
        if not os.path.exists(entry_path):
            raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')
        os.remove(entry_path)

    def delete_section(self, section):
        section_path = self._get_section_path(section)
        if not os.path.exists(section_path):
            raise FileNotFoundError(f'Config section "{section}" not found.')
        for entry in os.listdir(section_path):
            os.remove(os.path.join(section_path, entry))
        os.rmdir(section_path)

    def move_config(self,cfgfolder):
        if not cfgfolder and self.config_root == self.config_root_local:
                cfgfolder = self.prompt("Please enter the root where folder .config/froster will be created.", 
                                    os.path.expanduser('~'))
        if cfgfolder:
            new_config_root = os.path.join(os.path.expanduser(cfgfolder),'.config','froster')
        else:
            new_config_root = self.config_root
        old_config_root = self.config_root_local
        config_root_file = os.path.join(self.config_root_local,'config_root')
        
        if os.path.exists(config_root_file):
            with open(config_root_file, 'r') as f:
                old_config_root = f.read().strip()
        
        #print(old_config_root,new_config_root)
        if old_config_root == new_config_root:
            return True

        if not os.path.isdir(new_config_root):
            if os.path.isdir(old_config_root):
                shutil.move(old_config_root,new_config_root) 
                if os.path.isdir(old_config_root):
                    try:
                        os.rmdir(old_config_root)
                    except:
                        pass
                print(f'  Froster config moved to "{new_config_root}"\n')
            os.makedirs(new_config_root,exist_ok=True)
            if os.path.exists(self.awsconfigfile):
                self.replicate_ini('ALL',self.awsconfigfile,os.path.join(new_config_root,'aws_config'))
                print(f'  ~/.aws/config replicated to "{new_config_root}/aws_config"\n')  

        self.config_root = new_config_root

        os.makedirs(old_config_root,exist_ok=True)
        with open(config_root_file, 'w') as f:
            f.write(self.config_root)
            print(f'  Switched configuration path to "{self.config_root}"')

        return True

    def copy_compiled_binary_from_github(self,user,repo,compilecmd,binary,targetfolder):
        tarball_url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.tar.gz"
        response = requests.get(tarball_url, stream=True, allow_redirects=True)
        response.raise_for_status()
        with tempfile.TemporaryDirectory() as tmpdirname:
            reposfolder=os.path.join(tmpdirname,  f"{repo}-main")
            with tarfile.open(fileobj=response.raw, mode="r|gz") as tar:
                tar.extractall(path=tmpdirname)
                reposfolder=os.path.join(tmpdirname,  f"{repo}-main")
                os.chdir(reposfolder)
                result = subprocess.run(compilecmd, shell=True)
                if result.returncode == 0:
                    print(f"Compilation successful: {compilecmd}")
                    shutil.copy2(binary, targetfolder, follow_symlinks=True)
                    if not os.path.exists(os.path.join(targetfolder, binary)):
                        print(f'Failed copying {binary} to {targetfolder}')                
                else:
                    print(f"Compilation failed: {compilecmd}")

    def copy_binary_from_zip_url(self,zipurl,binary,subwildcard,targetfolder):
        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_file = os.path.join(tmpdirname,  "download.zip")
            response = requests.get(zipurl, verify=False, allow_redirects=True)
            with open(zip_file, 'wb') as f:
                f.write(response.content)
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(tmpdirname)
            binpath = glob.glob(f'{tmpdirname}{subwildcard}{binary}')[0]
            shutil.copy2(binpath, targetfolder, follow_symlinks=True)
            if os.path.exists(os.path.join(targetfolder, binary)):
                os.chmod(os.path.join(targetfolder, binary), 0o775)
            else:    
                print(f'Failed copying {binary} to {targetfolder}')

def parse_arguments():
    """
    Gather command-line arguments.
    """       
    parser = argparse.ArgumentParser(prog='froster ',
        description='A (mostly) automated tool for archiving large scale data ' + \
                    'after finding folders in the file system that are worth archiving.')
    parser.add_argument( '--debug', '-d', dest='debug', action='store_true', default=False,
        help="verbose output for all commands")
    parser.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute in the foreground. ")        
    parser.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine. (default=4)')
    parser.add_argument('--profile', '-p', dest='awsprofile', action='store', default='', 
        help='which AWS profile in ~/.aws/ should be used. default="aws"')
    parser.add_argument('--version', '-v', dest='version', action='store_true', default=False, 
        help='print Froster and Python version info')
    
    subparsers = parser.add_subparsers(dest="subcmd", help='sub-command help')
    # ***
    parser_config = subparsers.add_parser('config', aliases=['cnf'], 
        help=textwrap.dedent(f'''
            Bootstrap the configurtion, install dependencies and setup your environment.
            You will need to answer a few questions about your cloud and hpc setup.
        '''), formatter_class=argparse.RawTextHelpFormatter)
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
    parser_archive.add_argument('--larger', '-l', dest='larger', action='store', default=0, 
        help=textwrap.dedent(f'''
            Archive folders larger than <GiB>. This option
            works in conjunction with --age <days>. If both
            options are set froster will automatically archive
            all folder meeting these criteria, without prompting.
        '''))
    parser_archive.add_argument('--age', '-a', dest='age', action='store', default=0, 
         help=textwrap.dedent(f'''
            Archive folders older than <days>. This option
            works in conjunction with --larger <GiB>. If both
            options are set froster will automatically archive
            all folder meeting these criteria without prompting.
        '''))
    parser_archive.add_argument( '--age-mtime', '-m', dest='agemtime', action='store_true', default=False,
        help="Use modified file time (mtime) instead of accessed time (atime)")
    parser_archive.add_argument('folders', action='store', default=[],  nargs='*',
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
    parser_mount.add_argument( '--unmount', '-u', dest='unmount', action='store_true', default=False,
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

            In addition to the retrieval cost, AWS will charge you about $10/TiB/month for the
            duration you keep the data in S3.

            (costs from April 2023)
            '''))
    parser_restore.add_argument( '--no-download', '-l', dest='nodownload', action='store_true', default=False,
        help="skip download to local storage after retrieval from Glacier")
    parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to to restore (separated by space), ' +
                '')  
    
    if len(sys.argv) == 1:
        parser.print_help(sys.stdout)               

    return parser.parse_args()

if __name__ == "__main__":
    if not sys.platform.startswith('linux'):
        print('This software currently only runs on Linux x64')
        sys.exit(1)
    try:        
        args = parse_arguments()      
        if main():
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print('\nExit !')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
