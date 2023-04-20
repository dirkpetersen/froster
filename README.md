# Froster - yet another archiving tool
Froster is a tool that crawls your file system, suggests folders to archive and uploads your picks to Glacier, etc  

## Problem 

This problem may have been solved many times, but I have not found an easy OSS solution for large scale archiving to free up disk space on a primary storage system. Researchers, who have hundreds of terabytes or petabytes of data, need to make a decison what to archive and where to archive it to. Archiving processes can run for days and they can fail easily. They need to resume automatically until completed and be validated (e.g. checksum comparison with the source) and finally there needs to be some metadata when it was archived, and where the data went and where the original location was.

## Design 

1. First we need to crawl the file system that likely has billions of files to find data that is actually worth archiving. For this we will use the the well known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all file metadata found. 
1. We want to focus on archiving folders instead of individual files as data that resides in the same folder will typically belong together. For this we will filter pwalk's CSV file with [DuckDB](https://duckdb.org) and get a new list (CSV) of the largest folders sorted by size. 
1. We pass the new list (CSV) to an [interactive tool](https://github.com/dirkpetersen/froster/blob/main/froster.py#L153) based on [Textual](https://textual.textualize.io/) that displays a table with folders along with their total size in GiB and their average file sizes in MiB (MiBAvg) along with their age in days since last accessed (AccD) and modified (ModD). You can scroll down and right using your mouse and if you hit enter it will select that folder for archiving.
![image](https://user-images.githubusercontent.com/1427719/230824467-6a6e5873-5a48-4656-8d75-42133a60ba30.png)
1. If the average file size in the folder is small (size TBD) we will archive the folder (tar.gz) before uploading 
1. Pass the folder to a tool like [Rclone](https://rclone.org) and execute a copy job in the background 
1. Since many researchers have access to a Slurm cluster, the initial implmentation would just submit a job via sbatch instead of using a local message queue. Slurm can automatically resubmit jobs that failed and we can also save some comments with `scontrol update job <jobid> Comment="My status update"` . You can also use the --no-slurm argument to execute the job in the foreground. This is the default if slurm is not installed on the current system. 
1. Once the copy process is confirmed to have finished we put files with md5sums in the folders that have been archived. 
1. The user must evidence that all data was archived correctly (size and md5sum comparison) 
1. At the end we put an index.html file in the source folder that describes where the data was archived to along with instructions how to get the data back


## using Froster 

### configuring 

The config is mostly automated but you need to answer a few questions for which you can accept defaults in most cases. 
Sometimes the 'rclone' download times out, and you need to hit ctrl+c and start `froster config` again.

```
dp@grammy:~$ froster config
config
 Installing pwalk ...
Compilation successful: gcc -pthread pwalk.c exclude.c fileProcess.c -o pwalk
 Installing rclone ... please wait ... Done!

*** Asking a few questions ***
*** For most you can just hit <Enter> to accept the default. ***

Enter your domain name: mydomain.edu
  [Default: domain.edu]
Enter your email address: first.last@domain.edu
  [Default: username@domain.edu]
Please enter your S3 storage provider:
  [Default: AWS]
Please enter the S3 bucket to archive to:
  [Default: froster]
Please enter the archive root path in your S3 bucket:
  [Default: archive]
Please enter the AWS S3 Storage class:
  [Default: STANDARD]
Please enter the AWS profile in ~/.aws:
  [Default: default]
Please enter your AWS region for S3:
  [Default: us-west-2]
```

### Standard usage

In its most simple form you can use Froster to archive a specific folder, delete the source and restore the data interactively on a standalone Linux machine. 

For example we have 3 csv files in a folder

```
dp@grammy:~$ ls -la ~/csv

total 840
-rw-rw---- 1 dp dp 347712 Apr  4 06:08 myfile1.csv
-rw-rw---- 1 dp dp 507443 Apr  4 06:08 myfile2.csv
-rw-rw---- 1 dp dp   1370 Apr 19 17:10 myfile3.csv
```

Now let's archive this folder 

```
dp@grammy:~$ froster archive ~/csv

Archiving folder /home/dp/csv, please wait ...
Generating hashfile .froster.md5sum ...
Copying files to archive ...
Source and archive are identical. 3 files with 836.45 KiB transferred.
```

Froster creates md5 checksums for the files in the local folder, uploads the files and then compares the checksums in the archive with the local ones.

Now we delete the local data as we have evidence that the data is intact in the archive. We could execute `froster archive ~/csv` but, since the archiving process took a long time, we forgot which folder we needed to delete. We just run `froster delete` without the folder argument to see a list of archived folders and pick the one we want to delete.

![image](https://user-images.githubusercontent.com/1427719/233254490-4f965142-f162-48ae-b235-0a9b12af3a09.png)

after the deletion is completed, we see that a manifest file was created that gives users some info.

```
dp@grammy:~$ froster delete
Deleting archived objects in /home/dp/csv, please wait ...
Deleted files and wrote manifest to /home/dp/csv/Where-did-the-files-go.txt
```

The file has information that should allow other users to find out where the data went and who to contact to get it back

```
dp@grammy:~$ cat /home/dp/csv/Where-did-the-files-go.txt

The files in this folder have been moved to an archive!

Archive location: :s3:froster/archive/home/dp/csv
Archiver: username@domain.edu
Archive Tool: https://github.com/dirkpetersen/froster
Deletion date: 2023-04-19 20:55:15.701141

Files deleted:
myfile3.csv
myfile1.csv
myfile2.csv
```

After a while you may want to restore the data. Again, you forgot the actual folder location and invoke `froster restore` without the folder argument to see the same dialog with a list of achived folders. Select a folder and hit <Enter> to restore immediatelty.

```
dp@grammy:~$ froster restore
Restoring folder /home/dp/csv, please wait ...
Copying files from archive ...
Generating hashfile .froster-restored.md5sum ...
Target and archive are identical. 3 files with 836.45 KiB transferred.
```

Note that if you restore from AWS S3 to on-premises, you may be subject to AWS data egress charges (up to $90 per TiB downloaded), unless your organization has negotiated an [AWS data egress waiver](https://aws.amazon.com/blogs/publicsector/data-egress-waiver-available-for-eligible-researchers-and-institutions/).


### help 

each of the sub commands has a help option, for example `froster archive --help`

```
dp@grammy:~$ froster
usage: froster  [-h] [--debug] {config,cnf,index,idx,archive,arc,restore,rst,delete,del} ...

A (mostly) automated tool for archiving large scale data after finding folders in the file system that are worth
archiving.

positional arguments:
  {config,cnf,index,idx,archive,arc,restore,rst,delete,del}
                        sub-command help
    config (cnf)        Bootstrap the configurtion, install dependencies and setup your environment. You will need
                        to answer a few questions about your cloud setup.
    index (idx)         Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file that lists the
                        largest folders. As this process is compute intensive the index job will be automatically
                        submitted to Slurm if the Slurm tools are found.
    archive (arc)       Select from a list of large folders, that has been created by 'froster index', and archive a
                        folder to S3/Glacier. Once you select a folder the archive job will be automatically
                        submitted to Slurm. You can also automate this process
    restore (rst)       This command restores data from AWS Glacier to AWS S3 One Zone-IA. You do not need to
                        download all data to local storage after the restore is complete. Just mount S3.
    delete (del)        This command removes data from a local filesystem folder that has been confirmed to be
                        archived (through checksum verification). Use this instead of deleting manually

optional arguments:
  -h, --help            show this help message and exit
  --debug, -g           verbose output for all commands
```

