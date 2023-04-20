# Froster - yet another archiving tool
Froster is a tool that crawls your file system, suggests folders to archive, uploads your picks to Glacier, and retrieves it back.

## Problem 

This problem may have been solved many times, but I have not found an easy open source solution for large scale archiving to free up disk space on a primary storage system. Researchers, who have hundreds of terabytes or petabytes of data, need to make a decison what to archive and where to archive it to. Archiving processes can run for days and they can fail easily. They need to resume automatically until completed and be validated (e.g. checksum comparison with the source) and finally there needs to be some metadata when it was archived, and where the data went and where the original location was.

## Design 

1. First we need to crawl the file system that likely has billions of files to find data that is actually worth archiving. For this we will use the the well known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all file metadata found. 
1. We want to focus on archiving folders instead of individual files as data that resides in the same folder will typically belong together. For this we will filter pwalk's CSV file with [DuckDB](https://duckdb.org) and get a new list (CSV) of the largest folders sorted by size. 
1. We pass the new list (CSV) to an [interactive tool] based on [Textual](https://textual.textualize.io/) that displays a table with folders along with their total size in GiB and their average file sizes in MiB (MiBAvg) along with their age in days since last accessed (AccD) and modified (ModD). You can scroll down and right using your mouse and if you hit enter it will select that folder for archiving.
![image](https://user-images.githubusercontent.com/1427719/230824467-6a6e5873-5a48-4656-8d75-42133a60ba30.png)
1. If the average file size in the folder is small (size TBD) we will archive the folder (tar.gz) before uploading (not yet implemented) 
1. Pass the folder to a tool like [Rclone](https://rclone.org) and execute a copy job in the background. 
1. Nowadays most researchers with very large datasets will have a Slurm cluster connected to their data storage system. This is ideal for long running data copy jobs as Slurm can automatically re-run copy jobs that failed. You can also use the `--no-slurm` option to execute the job in the foreground. This is the default, if slurm is not installed on your Linux machine. 
1. Prior to copying, we put files with checksums (e.g. `.froster.md5sum`) in the folders that are to be archived to allow for an easy subsequent checksum comparison as the user must have evidence, that all data was archived correctly (size and md5sum comparison) 
1. After files have been deleted from the source folder, we put a file `Where-did-the-files-go.txt` in the source folder that describes where the data was archived to, along with instructions how to get the data back. 
1. WARNING: The current implementaton of Froster ignores sub-folders as only files that reside direcly in a chosen folder will be archived. There are two reasons for it: 1. If your goal is cost reduction rather than data management, most folders are small and are not worth archiving. We want to focus on the few large folders (Hotspots) that make a difference. 2. Many storage administrators are uncomfortable with users moving hundreds of terabytes. If an entire folder tree can be achived with a single command, it may create bottlenecks in the network or storage systems. 

## using Froster 

### configuring 

The config is mostly automated but you need to answer a few questions for which you can accept defaults in most cases. 
Sometimes the 'rclone' download times out, and you need to hit ctrl+c and start `froster config` again.

```
dp@grammy:~$ froster config

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
Please enter the AWS S3 storage class: 
  [Default: DEEP_ARCHIVE]
Please enter the AWS profile in ~/.aws:
  [Default: default]
Please enter your AWS region for S3:
  [Default: us-west-2]
```

When running `froster config` you should confirm the default DEEP_ARCHIVE for `AWS S3 storage class` as this is currently the lowest cost storage solution available and it takes only 12 hours to retrieve your data with the lowest cost retrieval option ('Bulk'). However, you can choose other [AWS S3 storage classes](https://rclone.org/s3/#s3-storage-class) supported by the rclone copy tool.

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

Now we delete the local data as we have evidence that the data is intact in the archive. We could execute `froster delete ~/csv` but, since the archiving process took a long time, we forgot which folder we needed to delete. We just run `froster delete` without the folder argument to see a list of archived folders and pick the one in which we want to delete files.

![image](https://user-images.githubusercontent.com/1427719/233254490-4f965142-f162-48ae-b235-0a9b12af3a09.png)

after the deletion is completed, we see that a manifest file was created that gives users some info.

```
dp@grammy:~$ froster delete

Deleting archived objects in /home/dp/csv, please wait ...
Deleted files and wrote manifest to /home/dp/csv/Where-did-the-files-go.txt
```

The file has information that should allow other users to find out where the data went and who to contact to get it back. It is important to understand that before deletion, Froster will compare the checksums of each file that was archived with the file in the archive and will only delete local files that have an identical copy in the archive. The manifest file and the checksum comparison are good reasons why you should always let Froster handle the data deletion instead of deleting the source folder manually.

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
Triggered Glacier retrievals: 3
Currently retrieving from Glacier: 0
Not in Glacier: 0

Glacier retrievals pending, run this again in up to 12h
```

If you use the DEEP_ARCHIVE (default) or GLACIER AWS S3 storage classes, the first execution of `froster restore` will initiate a Glacier retrieval. This retrieval will copy the data in the background from the Glacier archive to the S3 One Zone-IA storage class which costs about $10 per TiB/month and keep it there for 30 days by default (you can change this to something like 7 days with `froster restore --days 7`. Wait for 5-12 hours and run the `froster restore` command again. If all data has been retrieved, the restore to the original folder location will proceed. 

```
dp@grammy:~$ froster restore
Restoring folder /home/dp/csv, please wait ...
Copying files from archive ...
Generating hashfile .froster-restored.md5sum ...
Target and archive are identical. 3 files with 836.45 KiB transferred.
```

Note that if you restore from AWS S3 to on-premises, you may be subject to AWS data egress charges (up to $90 per TiB downloaded), unless your organization has negotiated an [AWS data egress waiver](https://aws.amazon.com/blogs/publicsector/data-egress-waiver-available-for-eligible-researchers-and-institutions/).


### help 

Each of the sub commands has a help option, for example `froster archive --help`
 
#### froster --help

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
 
#### froster index --help
 
```
dp@grammy:~$ froster index --help
 
usage: froster index [-h] [--no-slurm] [--cores CORES] [--pwalk-csv PWALKCSV] [folders ...]

positional arguments:
  folders               folders you would like to index (separated by space), using thepwalk file system crawler

optional arguments:
  -h, --help            show this help message and exit
  --no-slurm, -n        do not submit a Slurm job, execute index directly
  --cores CORES, -c CORES
                        Number of cores to be allocated for the index. (default=4)
  --pwalk-csv PWALKCSV, -p PWALKCSV
                        If someone else has already created CSV files using pwalk you can enter a specific pwalk CSV file here and are not required to run the time consuming pwalk.
```
 
#### froster archive --help

```
dp@grammy:~$ froster archive --help
 
usage: froster archive [-h] [--no-slurm] [--cores CORES] [--aws-profile AWSPROFILE] [--larger LARGER] [--age AGE] [--age-mtime]
                       [folders ...]

positional arguments:
  folders               folders you would like to archive (separated by space), the last folder in this list is the target

optional arguments:
  -h, --help            show this help message and exit
  --no-slurm, -n        do not submit a Slurm job, execute index directly
  --cores CORES, -c CORES
                        Number of cores to be allocated for the machine. (default=4)
  --aws-profile AWSPROFILE, -p AWSPROFILE
                        which AWS profile from ~/.aws/profiles should be used
  --larger LARGER, -l LARGER

                        Archive folders larger than <GiB>. This option
                        works in conjunction with --age <days>. If both
                        options are set froster will automatically archive
                        all folder meeting these criteria, without prompting.
  --age AGE, -a AGE
                        Archive folders older than <days>. This option
                        works in conjunction with --larger <GiB>. If both
                        options are set froster will automatically archive
                        all folder meeting these criteria without prompting.
  --age-mtime, -m       Use modified file time (mtime) instead of accessed time (atime)
```
 
#### froster restore --help
 
```
dp@grammy:~$ froster restore --help
 
usage: froster restore [-h] [--no-slurm] [--cores CORES] [--aws-profile AWSPROFILE] [--days DAYS] [--retrieve-opt RETRIEVEOPT]
                       [--no-download]
                       [folders ...]

positional arguments:
  folders               folders you would like to to restore (separated by space),

optional arguments:
  -h, --help            show this help message and exit
  --no-slurm, -n        do not submit a Slurm job, execute index directly
  --cores CORES, -c CORES
                        Number of cores to be allocated for the machine. (default=4)
  --aws-profile AWSPROFILE, -p AWSPROFILE
                        which AWS profile from ~/.aws/profiles should be used
  --days DAYS, -d DAYS  Number of days to keep data in S3 One Zone-IA storage at $10/TiB/month (default: 30)
  --retrieve-opt RETRIEVEOPT, -r RETRIEVEOPT

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
  --no-download, -l     skip download to local storage after retrieval from Glacier
```
 
#### froster delete --help
 
```
dp@grammy:~$ froster delete --help
 
usage: froster delete [-h] [--aws-profile AWSPROFILE] [folders ...]

positional arguments:
  folders               folders (separated by space) from which you would like to delete files, you can only delete files that have been archived

optional arguments:
  -h, --help            show this help message and exit
  --aws-profile AWSPROFILE, -p AWSPROFILE
                        which AWS profile from ~/.aws/profiles should be used
```
