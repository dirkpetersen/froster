#! /usr/bin/env python3

"""
Froster (almost) automates the challening task of 
archiving many Terabytes of data on HPC systems
"""
import sys, os, stat, argparse, json, configparser, requests
import tarfile, zipfile, subprocess, shutil, tempfile
import duckdb, csv, rclone, urllib3, glob, pwd, datetime

__app__ = 'Froster command line archiving tool'
__version__ = '0.1'

VAR = os.getenv('MYVAR', 'default value')
HOMEDIR = os.path.expanduser("~")

def main():

    #test config manager 
    cfg = ConfigManager()
    # Write an entry
    cfg.write('general', 'username', 'JohnDoe')
    mylist = ['folder1', 'folder2', 'folder3']
    mydict = {}
    mydict['folder1']="43"
    mydict['folder2']="42"

    cfg.write('general', 'mylist', mylist)
    cfg.write('general', 'mydict', mydict)

    # Read an entry
    username = cfg.read('general', 'username')
    print(username)  # Output: JohnDoe
    print(cfg.read('general', 'mylist'))
    print(cfg.read('general', 'mydict'))

    print("home paths:",cfg.homepaths)

    # Delete an entry
    #cfg.delete('application', 'username')
    # Delete a section
    #config.delete_section('application')   

    arch = Archiver(args.debug, "test")
    if args.subcmd == 'config':
        print ("config")
        arch.config("one", "two")

        if len(cfg.homepaths) > 0:
            cfg.write('general', 'binfolder', cfg.homepaths[0])

        print(" Installing pwalk ...")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        copy_compiled_binary_from_github('fizwit', 'filesystem-reporting-tools', 
                'gcc -pthread pwalk.c exclude.c fileProcess.c -o pwalk', 
                'pwalk', cfg.homepaths[0])
        
        print(" Installing rclone ... please wait ...")
        rclone_url = 'https://downloads.rclone.org/rclone-current-linux-amd64.zip'
        copy_binary_from_zip_url(rclone_url, 'rclone', 
                               '/rclone-v*/',cfg.homepaths[0])
        

    elif args.subcmd == 'index':
        print ("index:",args.cores, args.noslurm, args.pwalkcsv, args.folders)
        arch.index("one", "two")

        daysaged=[5475,3650,1825,1095,730,365,90,30]
        thresholdGB=1
        TiB=1099511627776
        GiB=1073741824

        # Connect to an in-memory DuckDB instance
        con = duckdb.connect(':memory:')

        with tempfile.NamedTemporaryFile() as tmpfile:
            # removing all files from pwalk output
            mycmd = f'grep -v ",-1,0$" "{args.pwalkcsv}" > {tmpfile.name}'
            result = subprocess.run(mycmd, shell=True)
            if result.returncode != 0:
                print(f"Folder extraction failed: {mycmd}")
        
            sql_query = f"""SELECT UID as User, GID as Group, 
                            st_atime as NoAccDays, st_mtime as NoModDays,
                            pw_fcount as FileCount, pw_dirsum as DirSize, 
                            pw_dirsum/1099511627776 as TiB,
                            pw_dirsum/1073741824 as GiB, 
                            pw_dirsum/1048576/pw_fcount as MiBAvg,
                            filename as Folder
                        FROM read_csv_auto('{tmpfile.name}', ignore_errors=1)
                        WHERE pw_fcount > -1 AND pw_dirsum > 0
                        ORDER BY pw_dirsum Desc
                    """  # pw_dirsum > 1073741824
            rows = con.execute(sql_query).fetchall()

            # Get the column names
            header = con.execute(sql_query).description

        # Write the result back to a new CSV file
        mycsv = 'hotspots.csv'

        totalbytes=0
        agedbytes=[]
        for i in daysaged:
            agedbytes.append(0)
        numhotspots=0

        with open(mycsv, 'w') as f:
            writer = csv.writer(f, dialect='excel')
            writer.writerow([col[0] for col in header])
            for r in rows:
                row = list(r)
                row[2]=days(row[2])
                if row[5] >= thresholdGB*GiB:
                    row[0]=getusr(row[0])
                    row[1]=getgrp(row[1])
                    row[3]=days(row[3])
                    writer.writerow(row)
                    numhotspots+=1
                    totalbytes+=row[5]
                for i in range(0,len(daysaged)):
                    if row[2] > daysaged[i]:
                        agedbytes[i]+=row[5]

        print(f" \nWrote {mycsv} with {numhotspots} hotspots >= {thresholdGB} GiB with a total disk use of {round(totalbytes/TiB,3)} TiB")
        lastagedbytes=0
        print(f' \nHistogram for {len(rows)} total folders processed:')
        for i in range(0,len(daysaged)):
            if agedbytes[i] > 0 and agedbytes[i] != lastagedbytes:
                print(f"  {round(agedbytes[i]/TiB,3)} TiB have not been accessed for {daysaged[i]} days (or {round(daysaged[i]/365,1)} years)")
            lastagedbytes=agedbytes[i]

    elif args.subcmd == 'archive':
        print ("archive:",args.cores, args.noslurm, args.md5sum, args.folders)
    elif args.subcmd == 'restore':
        print ("restore:",args.cores, args.noslurm, args.folders)
    elif args.subcmd == 'delete':
        print ("delete:",args.folders)

    #if args:
    #   arch.queryByProject(args.projects)

def getusr(uid):
    try:
        return pwd.getpwuid(uid)[0]
    except:
        return uid

def getgrp(gid):
    try:
        return grp.getgrgid(gid)[0]
    except:
        return gid

def days(unixtime):
    diff=datetime.datetime.now()-datetime.datetime.fromtimestamp(unixtime)
    return diff.days


class Archiver:
    def __init__(self, verbose, active):
        self.verbose = verbose
        self.active = active
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.grants = []

    def config(self, var1, var2):
        return var1

    def index(self, var1, var2):    
        return var1

    def something(self, var1, var2):    
        return var1


def parse_arguments():
    """
    Gather command-line arguments.
    """       
    parser = argparse.ArgumentParser(prog='froster ',
        description='a tool for archiving large scale data ' + \
                    'after finding it')
    parser.add_argument( '--debug', '-g', dest='debug', action='store_true', default=False,
        help="verbose output for all commands")

    subparsers = parser.add_subparsers(dest="subcmd", help='sub-command help')
    # ***
    parser_config = subparsers.add_parser('config', aliases=['cnf'], 
        help='edit configuration interactively')
    # ***
    parser_index = subparsers.add_parser('index', aliases=['idx'], 
        help='create a database of sub-folders to select from.')
    parser_index.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=True,
        help="do not submit a Slurm job, execute index directly")
    parser_index.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the index. (default=4) ')
    parser_index.add_argument('--pwalk-csv', '-p', dest='pwalkcsv', action='store', default='', 
        help='If someone else has already created csv files using pwalk ' +
             'you can enter that folder here and do not require to run ' +
             'the time consuming pwalk. \n' +
             'You can also pass a specific CSV file instead of a folder' +
             '')
    parser_index.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to index (separated by space), ' +
                'using thepwalk file system crawler ')
    # ***
    parser_archive = subparsers.add_parser('archive', aliases=['arc'], 
        help='archive folder to object store')
    parser_archive.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_archive.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')                                
    parser_archive.add_argument( '--md5sum', '-m', dest='md5sum', action='store_true', default=False,
        help="show the technical contact / owner of the machine")
    parser_archive.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to archive (separated by space), ' +
                'the last folder in this list is the target   ')
    # ***
    parser_restore = subparsers.add_parser('restore', aliases=['rst'], 
        help='restore folder from object store')
    parser_restore.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_restore.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')                                
    parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to to restore (separated by space), ' +
                'the last folder in this list is the target  ')
    # ***
    parser_delete = subparsers.add_parser('delete', aliases=['del'],
        help='Select folders to delete after they have been archived')
    parser_delete.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to delete (separated by space), ' +
               'you can only delete folders that are archived')

    return parser.parse_args()

class ConfigManager:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries 
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as 
    # multi-line files and dictionaries which are written to json

    def __init__(self):
        self.home_dir = os.path.expanduser('~')
        self.config_dir = os.path.join(self.home_dir, '.config', 'froster')
        self.awscredsfile = os.path.join(self.home_dir, '.aws', 'credentials')
        self.homepaths = self._get_home_paths()
        self._set_env_vars("default")
        
    def _set_env_vars(self, profile):
        
        # Read the credentials file
        config = configparser.ConfigParser()
        config.read(self.awscredsfile)

        if not config.has_section(profile):
            print (f'~/.aws/credentials has no section {profile}')
            return
        if not config.has_option(profile, 'aws_access_key_id'):
            print (f'~/.aws/credentials has no entry aws_access_key_id in section {profile}')
            return
        
        # Get the AWS access key and secret key from the specified profile
        aws_access_key_id = config.get(profile, 'aws_access_key_id')
        aws_secret_access_key = config.get(profile, 'aws_secret_access_key')

        # Set the environment variables for creds 
        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        os.environ['RCLONE_S3_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['RCLONE_S3_SECRET_ACCESS_KEY'] = aws_secret_access_key

        # Set the environment variables for other defaults 
        os.environ['RCLONE_S3_PROVIDER'] = 'AWS'
        #os.environ['RCLONE_S3_STORAGE_CLASS'] = 'DEEP_ARCHIVE'
        #os.environ['RCLONE_S3_LOCATION_CONSTRAINT'] = 'us-west-2'

    def _get_home_paths(self):
        path_dirs = os.environ['PATH'].split(os.pathsep)
        # Filter the directories in the PATH that are inside the home directory
        dirs_inside_home = {
            directory for directory in path_dirs
            if directory.startswith(self.home_dir) and os.path.isdir(directory)
        }
        return sorted(dirs_inside_home, key=len)
        
    def _get_section_path(self, section):
        return os.path.join(self.config_dir, section)

    def _get_entry_path(self, section, entry):
        section_path = self._get_section_path(section)
        return os.path.join(section_path, entry)

    def write(self, section, entry, value):
        entry_path = self._get_entry_path(section, entry)

        os.makedirs(os.path.dirname(entry_path), exist_ok=True)
        
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
            raise FileNotFoundError(f'Config entry "{entry}" in section "{section}" not found.')
 
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
                    return content

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


def copy_compiled_binary_from_github(user, repo, compilecmd, binary, targetfolder):
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

def copy_binary_from_zip_url(zipurl,binary,subwildcard,targetfolder):
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

if __name__ == "__main__":
    if not sys.platform.startswith('linux'):
        print('This software currently only runs on Linux x64')
        sys.exit(1)
    try:
        args = parse_arguments()        
        main()
    except KeyboardInterrupt:
        print('Exit !')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
