#! /usr/bin/env python3

"""
Froster (almost) automates the challening task of 
archiving many Terabytes of data on HPC systems
"""
# internal modules
import sys, os, argparse, json, configparser, csv
import urllib3, datetime, tarfile, zipfile, textwrap
import concurrent.futures, hashlib, fnmatch, io
import shutil, tempfile, glob, shlex, subprocess
if sys.platform.startswith('linux'):
    import getpass, pwd, grp
# stuff from pypi
import requests, duckdb, boto3
from textual.app import App, ComposeResult
from textual.widgets import DataTable

__app__ = 'Froster command line archiving tool'
__version__ = '0.1'

VAR = os.getenv('MYVAR', 'default value')

def main():

    #test config manager 
    cfg = ConfigManager()
    arch = Archiver(args, cfg)
    # Write an entry
    #cfg.write('general', 'username', 'JohnDoe')
    #mylist = ['folder1', 'folder2', 'folder3']
    #mydict = {}
    #mydict['folder1']="43"
    #mydict['folder2']="42"

    #cfg.write('general', 'mylist', mylist)
    #cfg.write('general', 'mydict', mydict)

    # Read an entry
    #username = cfg.read('general', 'username')
    #print(username)  # Output: JohnDoe
    #print(cfg.read('general', 'mylist'))
    #print(cfg.read('general', 'mydict'))

    #print("home paths:",cfg.homepaths)

    # Delete an entry
    #cfg.delete('application', 'username')
    # Delete a section
    #config.delete_section('application')   


    if args.subcmd == 'config':
        print ("config")
        arch.config("one", "two")

        if len(cfg.homepaths) > 0:
            cfg.write('general', 'binfolder', cfg.homepaths[0])

        print(" Installing pwalk ...")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        #copy_compiled_binary_from_github('fizwit', 'filesystem-reporting-tools', 
        #        'gcc -pthread pwalk.c exclude.c fileProcess.c -o pwalk', 
        #        'pwalk', cfg.homepaths[0])

        print(" Installing rclone ... please wait ...")
        rclone_url = 'https://downloads.rclone.org/rclone-current-linux-amd64.zip'
        #copy_binary_from_zip_url(rclone_url, 'rclone', 
        #                       '/rclone-v*/',cfg.homepaths[0])

        # general setup 
        domain = cfg.prompt('Enter your domain name:','ohsu.edu|general|domain','string')
        cfg.prompt('Enter your email address:',f'{getpass.getuser()}@{domain}|general|email','string')
            
        # setup local scratch spaces, OHSU specific 
        cfg.write('hpc', 'slurm_lscratch', '--gres disk:1024') # get 1TB scratch space
        cfg.write('hpc', 'lscratch_mkdir', 'mkdir-scratch.sh') # optional
        cfg.write('hpc', 'lscratch_rmdir', 'rmdir-scratch.sh') # optional
        cfg.write('hpc', 'lscratch_root', '/mnt/scratch') # add slurm jobid at the end

        # cloud setup 
        cfg.write('general', 'aws_profile', 'default') # get 1TB scratch space

        bucket = cfg.prompt('Please enter the S3 bucket to archive to','general|bucket','string')
        archiveroot = cfg.prompt('Please enter the archive root path in your S3 bucket','archive|general|archiveroot','string')

        # need to fix
        #if not args.awsprofile:
        #    args.awsprofile = cfg.read('general', 'aws_profile')

    elif args.subcmd == 'index':
        if args.debug:
            print (" Command line:",args.cores, args.noslurm, 
                    args.pwalkcsv, args.folders,flush=True)

        if not args.folders:
            print('you must point to at least one folder in your command line')
            return False

        for fld in args.folders:
            if not os.path.isdir(fld):
                print(f'The folder {fld} does not exist. Check your command line!')
                return False
            
        if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
            for fld in args.folders:
                fld = fld.rstrip(os.path.sep)
                print (f'Indexing folder {fld}, please wait ...', flush=True)
                arch.index(fld)            
        else:
            se = SlurmEssentials(args, cfg)
            label=arch._get_hotspots_file(args.folders[0]).replace('.csv','')
            myjobname=f'froster:index:{label}'
            email=cfg.read('general', 'email')
            se.add_line(f'#SBATCH --job-name={myjobname}')
            se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
            se.add_line(f'#SBATCH --mem=64G')
            se.add_line(f'#SBATCH --output=froster-index-{label}-%J.out')
            se.add_line(f'#SBATCH --mail-type=FAIL,END')           
            se.add_line(f'#SBATCH --mail-user={email}')
            se.add_line(f'#SBATCH --time=1-0')
            se.add_line(f'ml python')            
            cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline
            se.add_line(f"python3 {cmdline}")
            jobid = se.sbatch()
            print(f'Submitted froster indexing job: {jobid}')
            print(f'Check Job Output:')
            print(f' tail -f froster-index-{label}-{jobid}.out')

    elif args.subcmd == 'archive':
        print ("archive:",args.cores, args.awsprofile, args.noslurm, args.nomd5sum, 
               args.larger, args.age, args.agemtime, args.folders)
        fld = '" "'.join(args.folders)
        print (f'default cmdline: froster.py archive "{fld}"')

        rclone = Rclone(args,cfg)

        if not args.folders:
            hsfolder = os.path.join(cfg.config_root, 'hotspots')
            csv_files = [f for f in os.listdir(hsfolder) if fnmatch.fnmatch(f, '*.csv')]
            if len(csv_files) == 0:
                print("No folders to archive in arguments and no Hotspots CSV files found!")
                return False

            # Sort the CSV files by their modification time in descending order (newest first)
            # HERE we only allow to select the latest csv file 
            csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(hsfolder, x)), reverse=True)
            # Open the newest CSV file
            newest_csv_path = os.path.join(hsfolder, csv_files[0])
            retline=[]
            with open(newest_csv_path, 'r') as csvfile:
                app = TableApp()
                retline=app.run()
            if len(retline) < 6:
                print('Error: Hotspots table did not return result')
                return False
            args.folders.append(retline[5])
        
        if not shutil.which('sbatch') or args.noslurm or os.getenv('SLURM_JOB_ID'):
            for fld in args.folders:
                fld = fld.rstrip(os.path.sep)
                print (f'Archiving folder {fld}, please wait ...', flush=True)
                #arch.archive(fld)
                ret = rclone.copy(fld,f':s3:{cfg.archivepath}/tests10/','--max-depth', '1')
                #print('rclone ret', ret)
                print ('Message:', ret['msg'].replace('\n',';'))
                if ret['stats']['errors'] > 0:
                    print('Last Error:', ret['stats']['lastError'])
                print('\n\n')
                print('Speed:', ret['stats']['speed'])
                print('Transfers:', ret['stats']['transfers'])
                print('Tot Transfers:', ret['stats']['totalTransfers'])
                print('Tot Bytes:', ret['stats']['totalBytes'])
                print('Tot Checks:', ret['stats']['totalChecks'])

                #   {'bytes': 0, 'checks': 0, 'deletedDirs': 0, 'deletes': 0, 'elapsedTime': 2.783003019, 
                #    'errors': 1, 'eta': None, 'fatalError': False, 'lastError': 'directory not found', 
                #    'renames': 0, 'retryError': True, 'speed': 0, 'totalBytes': 0, 'totalChecks': 0, 
                #    'totalTransfers': 0, 'transferTime': 0, 'transfers': 0}



        else:
            se = SlurmEssentials(args, cfg)
            label=args.folders[0]
            myjobname=f'froster:archive:{label}'
            email=cfg.read('general', 'email')
            se.add_line(f'#SBATCH --job-name={myjobname}')
            se.add_line(f'#SBATCH --cpus-per-task={args.cores}')
            se.add_line(f'#SBATCH --mem=64G')
            se.add_line(f'#SBATCH --output=froster-archive-{label}-%J.out')
            se.add_line(f'#SBATCH --mail-type=FAIL,END')           
            se.add_line(f'#SBATCH --mail-user={email}')
            se.add_line(f'#SBATCH --time=1-0')
            se.add_line(f'ml python')      
            cmdline = " ".join(map(shlex.quote, sys.argv)) #original cmdline
            se.add_line(f"python3 {cmdline}")
            jobid = se.sbatch()
            print(f'Submitted froster archiving job: {jobid}')
            print(f'Check Job Output:')
            print(f' tail -f froster-archive-{label}-{jobid}.out')

    elif args.subcmd == 'restore':
        print ("restore:",args.cores, args.noslurm, args.folders)
    elif args.subcmd == 'delete':
        print ("delete:",args.folders)


class Rclone:
    def __init__(self, args, cfg):
        self.rc = 'rclone'

    # ensure that file exists or nagging /home/dp/.config/rclone/rclone.conf

    #backup: rclone --verbose --use-json-log copy --max-depth 1 ./tests/ :s3:posix-dp/tests4/ --exclude .froster.md5sum
    #restore: rclone --verbose --use-json-log copy --max-depth 1 :s3:posix-dp/tests4/ ./tests2
    #rclone copy --verbose --use-json-log --max-depth 1 :s3:posix-dp/tests5/ ./tests5
    #rclone --use-json-log checksum md5 ./tests/.froster.md5sum :s3:posix-dp/tests2/
    # storage tier for each file 
    #rclone lsf --csv :s3:posix-dp/tests4/ --format=pT
    # list without subdir 
    #rclone lsjson --metadata --no-mimetype --no-modtime --hash :s3:posix-dp/tests4


    def _run_rc(self, command):
        try:
            ret = subprocess.run(command, stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, text=True)                    
            if ret.returncode != 0:
                pass
                #sys.stderr.write(f'*** Error, Rclone return code > 0:\n {command} Error:\n{ret.stderr}')
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
            
            #lines = ret.stderr.decode('utf-8').splitlines()
            #locked_dirs = '\n'.join([l for l in lines if "Locked Dir:" in l]) 
            return ret.stdout.strip(), ret.stderr.strip()

        except Exception as e:
            print (f'Rclone Error: {str(e)}')
            return None, str(e)
        
    def copy(self, src, dst, *args):
        command = [self.rc, 'copy'] + list(args)
        command = self._add_opt(command, '--verbose')
        command = self._add_opt(command, '--use-json-log')
        command.append(src)
        command.append(dst)
        #print("Command:", command)
        out, err = self._run_rc(command)
        if out:
            print(f'rclone copy ouput: {out}')
        #print('ret', err)
        stats, ops = self._parse_log(err) 
        return stats[-1] # return the stats
    
        #b'{"level":"warning","msg":"Time may be set wrong - time from \\"posix-dp.s3.us-west-2.amazonaws.com\\" is -9m17.550965814s different from this computer","source":"fshttp/http.go:200","time":"2023-04-16T14:40:47.44907-07:00"}'    

    def version(self):
        command = [self.rc, 'version']
        return self._run_rc(command)
    
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



class Archiver:
    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.url = 'https://api.reporter.nih.gov/v2/projects/search'
        self.grants = []

    def config(self, var1, var2):
        return var1
    
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

    def gen_md5sums(self, directory, hash_file, num_workers=4, no_subdirs=True):
        for root, dirs, files in os.walk(directory):
            if no_subdirs and root != directory:
                break

            with open(os.path.join(root, hash_file), "w") as out_f:
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                    tasks = {}
                    for filen in files:
                        file_path = os.path.join(root, filen)
                        if os.path.isfile(file_path) and filen != os.path.basename(hash_file):
                            task = executor.submit(self.md5sum, file_path)
                            tasks[task] = file_path

                    for future in concurrent.futures.as_completed(tasks):
                        filen = os.path.basename(tasks[future])
                        md5 = future.result()
                        out_f.write(f"{md5}  {filen}\n")
    
    def index(self, pwalkfolder):

        # move down to class 
        daysaged=[5475,3650,1825,1095,730,365,90,30]
        thresholdGB=1
        TiB=1099511627776
        GiB=1073741824
        
        # Connect to an in-memory DuckDB instance
        con = duckdb.connect(':memory:')
        con.execute('PRAGMA experimental_parallel_csv=TRUE;')
        con.execute(f'PRAGMA threads={self.args.cores};')

        locked_dirs = ''
        with tempfile.NamedTemporaryFile() as tmpfile:
            with tempfile.NamedTemporaryFile() as tmpfile2:
                if not self.args.pwalkcsv:
                    #if not pwalkfolder:
                    #    print (" Error: Either pass a folder or a --pwalk-csv file on the command line.")
                    pwalkcmd = 'pwalk --NoSnap --one-file-system --header'
                    mycmd = f'{pwalkcmd} "{pwalkfolder}" > {tmpfile2.name}' # 2> {tmpfile2.name}.err'
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
                    if row[9] >= thresholdGB*GiB:
                        row[0]=self.uid2user(row[0])                        
                        row[1]=self.daysago(self._get_newest_file_atime(row[5],row[1]))
                        row[2]=self.daysago(row[2])
                        row[6]=self.gid2group(row[6])
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
                with {numhotspots} hotspots >= {thresholdGB} GiB 
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
        else:
            print(f'No folders larger than {thresholdGB} GiB found under {pwalkfolder}', flush=True)                

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
                
    def archive(self, var1, var2):
        pass

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
    
    def _get_newest_file_atime(self, folder_path, folder_atime=None):
        # Because the folder atime is reset when crawling we need
        # to lookup the atime of the last accessed file in this folder
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            if self.args.debug and not self.args.pwalkcsv:
                print(f" Invalid folder path: {folder_path}")
            return folder_atime
        last_accessed_time = None
        last_accessed_file = None
        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)
            if os.path.isfile(file_path):
                accessed_time = os.path.getatime(file_path)
                if last_accessed_time is None or accessed_time > last_accessed_time:
                    last_accessed_time = accessed_time
                    last_accessed_file = file_path
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
    
        def initiate_restore(self, bucket_name, object_key, rdays=30, retrieval_opt="Bulk"):
            s3 = boto3.client('s3')
            s3.restore_object(
                Bucket=bucket_name,
                Key=object_key,
                RestoreRequest={
                    'Days': rdays,
                    'GlacierJobParameters': {
                        'Tier': retrieval_opt
                    }
                }
            )
        #print(f'Restore request initiated for {object_key} using {retrieval_option} retrieval.')

        def check_restore_status(self, bucket_name, object_key): #object key is tha the filename and path 
            s3 = boto3.client('s3')
            response = s3.head_object(Bucket=bucket_name, Key=object_key)
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

class TableApp(App[list]):

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.cursor_type = "row"
        #table.fixed_columns = 1
        #table.fixed_rows = 1
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        rows = csv.reader(self.get_csv()) #or io.StringIO(CSV)
        #rows = csv.reader(io.StringIO(CSV))
        table.add_columns(*next(rows))
        table.add_rows(rows)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

    def get_csv(self):
        home_dir = os.path.expanduser('~')
        hsfolder = os.path.join(home_dir,'.config','froster', 'hotspots')
        csv_files = [f for f in os.listdir(hsfolder) if fnmatch.fnmatch(f, '*.csv')]
        # Sort the CSV files by their modification time in descending order (newest first)
        csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(hsfolder, x)), reverse=True)
        # Open the newest CSV file
        newest_csv_path = os.path.join(hsfolder, csv_files[0])
        print(newest_csv_path)
        return open(newest_csv_path, 'r')

#if __name__ == "__main__":
#    app = TableApp()
#    print(app.run())


def parse_arguments():
    """
    Gather command-line arguments.
    """       
    parser = argparse.ArgumentParser(prog='froster ',
        description='A (mostly) automated tool for archiving large scale data ' + \
                    'after finding folders in the file system that are worth archiving.')
    parser.add_argument( '--debug', '-g', dest='debug', action='store_true', default=False,
        help="verbose output for all commands")

    subparsers = parser.add_subparsers(dest="subcmd", help='sub-command help')
    # ***
    parser_config = subparsers.add_parser('config', aliases=['cnf'], 
        help=textwrap.dedent(f'''
            Bootstrap the configurtion, install dependencies and setup your environment.
            You will need to answer a few questions about your cloud setup.
        '''), formatter_class=argparse.RawTextHelpFormatter)
    # ***
    parser_index = subparsers.add_parser('index', aliases=['idx'], 
        help=textwrap.dedent(f'''
            Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file 
            that lists the largest folders. As this process is compute intensive the 
            index job will be automatically submitted to Slurm if the Slurm tools are
            found.
        '''), formatter_class=argparse.RawTextHelpFormatter) 
    parser_index.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")
    parser_index.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the index. (default=4) ')
    parser_index.add_argument('--pwalk-csv', '-p', dest='pwalkcsv', action='store', default='', 
        help='If someone else has already created CSV files using pwalk ' +
             'you can enter a specific pwalk CSV file here and are not ' +
             'required to run the time consuming pwalk.' +
             '')
    parser_index.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to index (separated by space), ' +
                'using thepwalk file system crawler ')
    # ***
    parser_archive = subparsers.add_parser('archive', aliases=['arc'], 
        help=textwrap.dedent(f'''
            Select from a list of large folders, that has been created by 'froster index', and 
            archive a folder to S3/Glacier. Once you select a folder the archive job will be 
            automatically submitted to Slurm. You can also automate this process 

        '''), formatter_class=argparse.RawTextHelpFormatter) 
    parser_archive.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_archive.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')
    parser_archive.add_argument('--aws-profile', '-p', dest='awsprofile', action='store', default='', 
        help='which AWS profile from ~/.aws/profiles should be used')
    parser_archive.add_argument( '--no-md5sum', '-s', dest='nomd5sum', action='store_true', default=False,
        help="show the technical contact / owner of the machine")
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
    parser_restore = subparsers.add_parser('restore', aliases=['rst'],
        help=textwrap.dedent(f'''
            This command restores data from AWS Glacier to AWS S3 One Zone-IA. You do not need
            to download all data to local storage after the restore is complete. Just mount S3.
        '''), formatter_class=argparse.RawTextHelpFormatter) 
    parser_restore.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_restore.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')
    parser_restore.add_argument('--days', '-d', dest='cores', action='store', default=30,
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
    parser_restore.add_argument( '--download', '-l', dest='download', action='store_true', default=False,
        help="download to local storage after retrieval")
    parser_restore.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to to restore (separated by space), ' +
                'the last folder in this list is the target  ')
    # ***
    parser_download = subparsers.add_parser('download', aliases=['rst'],
        help=textwrap.dedent(f'''
            This command downloads data from a S3 compatible object store to your local filesystem. 
            If you are downloading from a cloud to your local network, egress fees may apply. 
        '''), formatter_class=argparse.RawTextHelpFormatter)        
    parser_download.add_argument( '--no-slurm', '-n', dest='noslurm', action='store_true', default=False,
        help="do not submit a Slurm job, execute index directly")        
    parser_download.add_argument('--cores', '-c', dest='cores', action='store', default='4', 
        help='Number of cores to be allocated for the machine.')
    parser_download.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to to restore (separated by space), ' +
                'the last folder in this list is the target  ')
    # ***
    parser_delete = subparsers.add_parser('delete', aliases=['del'],
        help=textwrap.dedent(f'''
            This command removes data from a local filesystem folder that has been confirmed to 
            be archived (through checksum verification). Use this instead of deleting manually
        '''), formatter_class=argparse.RawTextHelpFormatter) 
    parser_delete.add_argument('folders', action='store', default=[],  nargs='*',
        help='folders you would like to delete (separated by space), ' +
               'you can only delete folders that are archived')

            # For example, AWS charges about $90/TiB for downloads. You can avoid these costs by 
            # requesting a Data Egress Waiver from AWS, which waives your Egress fees in the amount
            # of up to 15%% of your AWS bill. (costs from April 2023)

    return parser.parse_args()

class ConfigManager:
    # we write all config entries as files to '~/.config'
    # to make it easier for bash users to read entries 
    # with a simple var=$(cat ~/.config/froster/section/entry)
    # entries can be strings, lists that are written as 
    # multi-line files and dictionaries which are written to json

    def __init__(self):
        self.home_dir = os.path.expanduser('~')
        self.config_root = self._get_config_root()
        self.homepaths = self._get_home_paths()
        self.awscredsfile = os.path.join(self.home_dir, '.aws', 'credentials')
        self.awsconfigfile = os.path.join(self.home_dir, '.aws', 'config')
        self.archivepath = os.path.join(
             self.read('general','bucket'),
             self.read('general','archiveroot'))
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
        
    def _get_config_root(self):
        theroot=os.path.join(self.home_dir, '.config', 'froster')
        rootfile = os.path.join(theroot, 'config_root')
        if os.path.exists(rootfile):
            with open(rootfile, 'r') as myfile:
                theroot = myfile.read()
                if not os.path.isdir(theroot):
                    raise FileNotFoundError(f'Config root folder "{theroot}" not found. Please remove {rootfile}')
        return theroot

    def _get_section_path(self, section):
        return os.path.join(self.config_root, section)

    def _get_entry_path(self, section, entry):
        section_path = self._get_section_path(section)
        return os.path.join(section_path, entry)

    def prompt(self, question, defaults=None, type_check=None):
        # Prompts for user input and writes it to config 
        # defaults are up to 3 pipe separated strings: 
        # if there is only one string this is the default 
        # if there are 2 strings they represent section 
        # and key name of the config entry and if there are 
        # 3 strings the last 2 represent section 
        # and key name of the config file and the first is
        # the default if section and key name are empty
        default=''
        section=''
        key=''
        if not question.endswith(':'):
            question += ':'
        if defaults is not None:
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
            if default:
                question += f"\n  [Default: {default}]"
        while True:
            user_input = input(f"\033[93m{question}\033[0m ")
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
    
    def create_aws_configs(self,access_key=None, secret_key=None, region=None):

        if not access_key: access_key = input("Enter your AWS access key ID: ")
        if not secret_key: secret_key = input("Enter your AWS secret access key: ")
        if not region: region = input("Enter your AWS region (e.g., us-west-2): ")

        aws_dir = os.path.join(self.home_dir, ".aws")

        if not os.path.exists(aws_dir):
            os.makedirs(aws_dir)

        with open(self.awsconfigfile, "w") as config_file:
            config_file.write("[default]\n")
            config_file.write(f"region = {region}\n")
            config_file.write("\n")
            config_file.write("[aws]\n")
            config_file.write(f"region = {region}\n")

        with open(self.awscredsfile, "w") as credentials_file:
            credentials_file.write("[default]\n")
            credentials_file.write(f"aws_access_key_id = {access_key}\n")
            credentials_file.write(f"aws_secret_access_key = {secret_key}\n")
            credentials_file.write("\n")
            credentials_file.write("[aws]\n")
            credentials_file.write(f"aws_access_key_id = {access_key}\n")
            credentials_file.write(f"aws_secret_access_key = {secret_key}\n")
        os.chmod(self.awscredsfile, 0o600)

        print("AWS configuration files created successfully.")

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

class SlurmEssentials:
    # submitted to https://github.com/amq92/simple_slurm/issues/18 for inclusion
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
        command = "scontrol"
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

#if __name__ == "__main__":
#    se = SlurmEssentials()
#    se.add_line('#SBATCH --job-name=my_job')
#    se.add_line('sleep 600')
#    jobid = se.sbatch()
#    se.job_comment_write(jobid, "Lovely Comment") # 
#    print('Job Comment:', se.job_comment_read(jobid))
#    se.squeue()
#    se.print_jobs()

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
    #if not sys.platform.startswith('linux'):
    #    print('This software currently only runs on Linux x64')
    #    sys.exit(1)
    try:
        args = parse_arguments()        
        main()
    except KeyboardInterrupt:
        print('\nExit !')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
