![image](https://user-images.githubusercontent.com/1427719/235330281-bd876f06-2b2a-46fc-8505-c065bb508973.png)

Froster is a user-friendly archiving tool for teams that move data between higher cost Posix file systems and lower cost S3-like object storage systems such as AWS Glacier. Froster can scan your Posix file system metadata, recommend folders for archiving, generate checksums, and upload your selections to Glacier or other S3-like storage. It can retrieve data back from the archive using a single command. Additionally, Froster can mount S3/Glacier storage onto your on-premise file system and manage the [boto3 credentials/profiles](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html) that are utilized by the AWS CLI and other tools.

## Table of Contents
* [Problem](#problem)
  * [Motivation](#motivation)
* [Design](#design)
* [Using Froster](#using-froster)
  * [Installing](#installing)
  * [Configuring](#configuring)
    * [Changing defaults with aliases](#changing-defaults-with-aliases)
    * [Advanced configuration](#advanced-configuration)
  * [Standard usage](#standard-usage)
  * [Large scale use on HPC](#large-scale-use-on-hpc)
* [Command line help](#command-line-help)

## Problem 

This problem may have already been addressed many times, but I've yet to find an easy, open-source solution for large-scale archiving intended to free up disk space on a primary storage system. Researchers, who may have hundreds of terabytes or even petabytes of data, need to decide what to archive and where to archive it. Archiving processes can stretch on for days and are susceptible to failure. These processes must be able to resume automatically until completion, and need to be validated (for instance, through a checksum comparison with the source). Additionally, it's crucial to maintain some metadata regarding when the archiving occurred, where the data was transferred to, and the original location of the data.
A specific issue with AWS Glacier is its current implementation as a backend to S3. Only the Glacier features that S3 does not support necessitate the use of a Glacier API. This fact is often not well documented in many how-to guides.

### Motivation 

There were two motivations behind the creation of `Froster``:

- We were working with researchers to optimize their archiving processes. In doing so, we wanted to understand user workflows and identify the essential metadata to be captured. Thanks to Froster's compact codebase, it can be easily adapted to various needs. Metadata could potentially be captured through an additional web interface. However, a web system often requires IT support and an extra layer of authentication. It might be simpler to gather such information through a [Textual TUI interface](https://github.com/mitosch/textual-select). The insights gained through working with `Froster`` will likely guide the development or acquisition of more robust tools in the future.

- Around the time we were discussing data archiving, ChatGPT4 had just been released. We wanted to assemble a few scripts to explore the best approaches. With ChatGPT4 handling a significant portion of Python coding, nearly 50% of Froster's code was autogenerated. As a result, Froster quickly transformed into a practical tool. The logo was autogenerated by https://www.brandcrowd.com/.

- HPC users often find AWS Glacier inaccessible or complex and have a preception that it is expensive because of Egress fees. This is despite evidence that large amounts of data may not have been touched in years. It seems that it is very difficult to build an on premises archive solution with a lower TCO than AWS Glacier (or similar offerings from other cloud providers. 

## Design 

1. First, we need to crawl the file system that likely has billions of files to find data that is actually worth archiving. For this, we use the well-known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all discovered file metadata.
1. Our focus is on archiving folders rather than individual files, as data that resides in the same folder typically belongs together. To this end, we filter the pwalk's CSV file with [DuckDB](https://duckdb.org), yielding a new list (CSV) of the largest folders sorted by size.
1. We pass this new list (CSV) to an interactive tool based on [Textual](https://textual.textualize.io/), which displays a table of folders alongside their total size in GiB, their average file sizes in MiB (MiBAvg), as well as their age in days since last accessed (AccD) and modified (ModD). Users can scroll down and right using the mouse, and hitting enter will trigger the archiving of the selected folder.
   ![image](https://user-images.githubusercontent.com/1427719/230824467-6a6e5873-5a48-4656-8d75-42133a60ba30.png)
1. All files < 1 MiB size are moved to an archive called Froster.smallfiles.tar prior to uploading. To avoid tarring you can set max_small_file_size_kib to 0.
1. We pass the folder to [Rclone](https://rclone.org) to execute a copy job in the background.
1. Many researchers with very large datasets will have a Slurm cluster connected to their data storage system. This is ideal for long-running data copy jobs, and Slurm can automatically re-run copy jobs that failed. Users can also use the `--no-slurm` option to execute the job in the foreground. This is the default if Slurm is not installed on the Linux machine.
1. Prior to copying, we place files with checksums (e.g., `.froster.md5sum`) in the folders to be archived. This allows for an easy subsequent checksum comparison, providing the user with evidence that all data was correctly archived (through size and md5sum comparisons).
1. After files have been deleted from the source folder, we place a file named `Where-did-the-files-go.txt` in the source folder. This file describes where the data was archived, along with instructions on how to retrieve the data.
1. By default, Froster ignores sub-folders, as only files that reside directly in a chosen folder will be archived. There are two reasons for this: First, if your goal is cost reduction rather than data management, most folders are small and not worth archiving. We want to focus on the few large folders (Hotspots) that make a difference. Secondly, many storage administrators are uncomfortable with users moving hundreds of terabytes. If an entire folder tree can be archived with a single command, it may create bottlenecks in the network or storage systems.
However, you can use the `--recursive` option with the archive command to include all sub-folders

## using Froster 

### Installing 

Just pipe this curl command to bash: 

```
curl https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh | bash
```

### configuring 

The config is mostly automated (just run `froster config`) but you need to answer a few questions for which you can accept defaults in most cases. 
Sometimes the 'rclone' download times out, and you need to hit ctrl+c and start `froster config` again. 

If you would like to work on the same configuration and database with other users, you can put those in a shared folder by answering 'yes' to "Do you want to collaborate?" or by running `froster config /your/shared/folder` any time. If you start with a personal configuration and change to a shared configuration at a later time the personal configuration will automatically be migrated to the shared folder.

```
dp@grammy:~$ froster config

 Installing pwalk ...
Compilation successful: gcc -pthread pwalk.c exclude.c fileProcess.c -o pwalk
 Installing rclone ... please wait ... Done!

*** Asking a few questions ***
*** For most you can just hit <Enter> to accept the default. ***

  Do you want to collaborate with other users on archive and restore? [y/N] n
*** Enter your email address: ***
  [Default: dp@mydomain.edu] first.last@domain.edu
*** Please confirm/edit S3 bucket name to be created in all used profiles.: ***
  [Default: froster-first-last-domain-edu]
*** Please confirm/edit the archive root path inside your S3 bucket: ***
  [Default: archive]
*** Please confirm/edit the AWS S3 Storage class: ***
  [Default: DEEP_ARCHIVE]
*** Please select AWS S3 region (e.g. us-west-2 for Oregon): ***
  (1) us-west-2
  (2) us-west-1
  (3) us-east-2
  (4) us-east-1
  (5) sa-east-1
  (6) me-south-1
  (7) me-central-1
  (8) eu-west-3
  .
  .
  Enter the number of your selection: 1
*** Please confirm/edit the AWS S3 region: ***
  [Default: us-west-2]

  Verify that bucket 'froster-first-last-domain-edu' is configured ...
  Checking credentials for profile "aws" ... Done.
Created S3 Bucket 'froster-first-last-domain-edu'
Applied AES256 encryption to S3 bucket 'froster-first-last-domain-edu'
  Checking credentials for profile "default" ... Done.

Found additional profiles in ~/.aws and need to ask a few more questions.

Do you want to configure profile "moin"? [Y/n] n
Do you want to configure profile "idrive"? [Y/n] y
*** S3 Provider for profile "idrive": ***
  (1) S3
  (2) GCS
  (3) Wasabi
  (4) IDrive
  (5) Ceph
  (6) Minio
  (7) Other
  Enter the number of your selection: 4
*** Confirm/edit S3 region for profile "idrive": ***
  [Default: us-or]
*** S3 Endpoint for profile "idrive" (e.g https://s3.domain.com): ***
  [Default: https://v2u8.or.idrivee2-42.com]
  Checking credentials for profile "idrive" ... Done.
Created S3 Bucket 'froster-first-last-domain-edu'
Applied AES256 encryption to S3 bucket 'froster-first-last-domain-edu'
Do you want to configure profile "wasabi"? [Y/n] y
*** S3 Provider for profile "wasabi": ***
  (1) S3
  (2) GCS
  (3) Wasabi
  (4) IDrive
  (5) Ceph
  (6) Minio
  (7) Other
  Enter the number of your selection: 3
*** Confirm/edit S3 region for profile "wasabi": ***
  [Default: us-west-1]
*** S3 Endpoint for profile "wasabi" (e.g https://s3.domain.com): ***
  [Default: https://s3.us-west-1.wasabisys.com]
  Checking credentials for profile "wasabi" ... Done.
Created S3 Bucket 'froster-first-last-domain-edu'

*** And finally a few questions how your HPC uses local scratch space ***
*** This config is optional and you can hit ctrl+c to cancel any time ***
*** If you skip this, froster will use HPC /tmp which may have limited disk space  ***

*** How do you request local scratch from Slurm?: ***
  [Default: --gres disk:1024]
*** Is there a user script that provisions local scratch?: ***
  [Default: mkdir-scratch.sh]
*** Is there a user script that tears down local scratch at the end?: ***
  [Default: rmdir-scratch.sh]
*** What is the local scratch root ?: ***
  [Default: /mnt/scratch]

Done!    
```

When running `froster config`, you should confirm the default DEEP_ARCHIVE for `AWS S3 storage class` as this is currently the most cost-effective storage solution available. It takes only 6 hours to retrieve your data with the least expensive retrieval option ('Bulk'). However, you can choose other [AWS S3 storage classes](https://rclone.org/s3/#s3-storage-class) supported by the rclone copy tool. 

Please note that Froster expects a profile named 'default', 'aws', or 'AWS' in ~/.aws/credentials, which will be used for Amazon cloud. If Froster finds other profiles, it will ask you questions about providers, regions, and endpoints. If you do not wish to configure additional 3rd party storage providers, you can simply hit "n" multiple times. Please check the [rclone S3 docs](https://rclone.org/s3/) to learn about different providers and endpoints.

It's important to note that Froster uses the same bucket name for S3 and all S3-compatible storage systems it supports. This streamlines the process if data needs to be migrated between multiple storage systems. The selected bucket will be created if it does not exist, and encryption will be applied (at least in AWS).

Froster has been tested with numerous S3-compatible storage systems such as GCS, Wasabi, IDrive, Ceph, and Minio. At this time, only AWS supports the DEEP_ARCHIVE storage class.


#### Changing defaults with aliases

Froster has a number of global options that you may prefer but you don't like to type them all the time. We have `--no-slurm` (don't submit batch jobs even if Slurm is found), `--cores` (use a number of CPU cores that is different from the default 4) and `--profile` (use a different ~/.aws profile for example if you have your own S3 storage). You can create a command alias that uses these settings by default. For example, if you think that typing froster is too long and would like to rather type `fro` and use 8 cpu cores in the foreground with a custom profile named `myceph` you can simply enter this command in bash:

```
alias fro="froster --no-slurm --cores=8 --profile=myceph"
```

If you would like to keep this past the next login you can add this alias to the bottom of ~/.bashrc:

```
echo 'alias fro="froster --no-slurm --cores=8 --profile=myceph"' >> ~/.bashrc
```

#### advanced configuration 

Some advanced configuration settings are not offered through a user inferface but you can change them under `~/.config/froster`. For example,  `~/.config/froster/general` has one file per setting which makes it very easy to use the settings in shell scripts, for example when writing addon tools: 

```
DEFAULT_STORAGE_CLASS=$(cat ~/.config/froster/general/s3_storage_class)
```

a few advanced settings at ~/.config/froster/general deserve more explanation:

* min_index_folder_size_gib (Default: 10)

If the sum of all file sizes in one folder level is larger than this value in GiB that folder will be included in a hotspots file which is generated using the `froster index` command  


* min_index_folder_size_avg_mib (Default: 10)

If min_index_folder_size_gib is true and if the average file size in one folder level is larger than this value in MiB that folder will be included in a hotspots file which is generated using the `froster index` command  

* max_hotspots_display_entries (Default: 5000)

The maximum number of entries that will be shown in the dialog once a hotspots file is selected after using the `froster archive` command.

* max_small_file_size_kib (Default: 1024)

If a file is smaller than this size, it will be moved to a file Froster.smallfiles.tar at the same folder level before uploading when running the `froster archive` command. This is useful because Glacier consumes an overhead of about 40 KiB for each uploaded file. If you want to avoid tarring files set max_small_file_size_kib to 0.


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

![image](https://user-images.githubusercontent.com/1427719/235413606-b24db72d-cb58-44cc-9754-175d0e4fca9e.png)


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
Archive profile (~/.aws): default
Archiver: username@domain.edu
Archive Tool: https://github.com/dirkpetersen/froster
Deletion date: 2023-04-19 20:55:15.701141

Files deleted:
myfile3.csv
myfile1.csv
myfile2.csv
```

Shortly after a folder has been deleted you need to grab a single file from the archive. For this you simply execute `froster mount` and select the folder you would like to access. Now you can copy single files or access them with your existing pipelines. Use `froster umount` to unmount the folder.

```
froster mount
```

After a while you may want to restore the data. Again, you forgot the actual folder location and invoke `froster restore` without the folder argument to see the same dialog with a list of achived folders. Select a folder and hit "Enter" to restore immediatelty.

 
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

Note that if you restore from AWS S3 to on-premises, you may be subject to AWS data egress charges (up to $90 per TiB downloaded, or $20 per TiB with AWS DirectConnect), unless your organization has negotiated an [AWS data egress waiver](https://aws.amazon.com/blogs/publicsector/data-egress-waiver-available-for-eligible-researchers-and-institutions/).

### Large scale use on HPC

If you have hundreds of terabytes or even petabtyes of data in billions of files you may not be able to easily locate data that is worth archiving. Among hundreds of thousands of folders there are typically only a few hundred that make up most of your storage consumption. We call these folders 'Hotspots' and to find them you use the `froster index` command and pass the root directory of your lab data. 

```
[user@login ~]$ froster index /home/gscratch/dpcri
Submitted froster indexing job: 22218558
Check Job Output:
 tail -f froster-index-@gscratch+dpcri-22218558.out
```

we can see the status of the job 

```
[user@login ~]$ squeue --me
             JOBID PART         NAME     USER ST       TIME  TIME_LEFT NOD CPU TRES_PER_ MIN_ NODELIST(REASON)
          22218560 exac froster:index:dp user  R       0:07   23:59:53   1   4 gres:disk  64G node-2-0
```

and then use the suggested tail command to see how the indexing is progressing, we can see that the job finished successfully  

```
[user@login ~]$ tail -f froster-index-@gscratch+dpcri-22218558.out
2023-04-20 08:28:22-07:00 mkdir-scratch.sh info: Preparing scratch space for job 22218558
2023-04-20 08:28:22-07:00 mkdir-scratch.sh info: /mnt/scratch/22218558 has been created
Indexing folder /home/exacloud/gscratch/dpcri, please wait ...

Wrote @gscratch+dpcri.csv
with 6 hotspots >= 1 GiB
with a total disk use of 0.08 TiB

Histogram for 37111 total folders processed:
0.013 TiB have not been accessed for 5475 days (or 15.0 years)
0.028 TiB have not been accessed for 30 days (or 0.1 years)
2023-04-20 08:29:11-07:00 rmdir-scratch.sh info: Preparing to clean scratch space for job 22218558
2023-04-20 08:29:11-07:00 rmdir-scratch.sh info: Deleting directory /mnt/scratch/22218558 for job 22218558
```

now we run the `froster archive` command without entering folder names on the command line. We created a csv folder for testing that contains 3 csv files with a total of about 1.1 GiB data. We pick this csv folder. It shows that it has been accessed 0 days ago because we just created it.  


![image](https://user-images.githubusercontent.com/1427719/233419009-6a375fe4-541d-4ac6-9ba3-7916b89eabb1.png)


```
[user@login ~]$ froster archive
Submitted froster archiving job: 22218563
Check Job Output:
 tail -f froster-archive-+home+gscratch+dpcri+csv-22218563.out
```


## Command line help 

Each of the sub commands has a help option, for example `froster archive --help`
 
#### froster --help

```
dp@grammy:~$ froster

usage: froster  [-h] [--debug] [--no-slurm] [--cores CORES] [--profile AWSPROFILE]
                {config,cnf,index,idx,archive,arc,restore,rst,delete,del,mount,umount} ...

A (mostly) automated tool for archiving large scale data after finding folders in the file
system that are worth archiving.

positional arguments:
  {config,cnf,index,idx,archive,arc,restore,rst,delete,del,mount,umount}
                        sub-command help
    config (cnf)        Bootstrap the configurtion, install dependencies and setup your
                        environment. You will need to answer a few questions about your cloud
                        setup.
    index (idx)         Scan a file system folder tree using 'pwalk' and generate a hotspots
                        CSV file that lists the largest folders. As this process is compute
                        intensive the index job will be automatically submitted to Slurm if
                        the Slurm tools are found.
    archive (arc)       Select from a list of large folders, that has been created by
                        'froster index', and archive a folder to S3/Glacier. Once you select
                        a folder the archive job will be automatically submitted to Slurm.
                        You can also automate this process
    restore (rst)       Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need
                        to download all data to local storage after the restore is complete.
                        Just use the mount sub command.
    delete (del)        Remove data from a local filesystem folder that has been confirmed to
                        be archived (through checksum verification). Use this instead of
                        deleting manually
    mount (umount)      Mount or unmount the remote S3 or Glacier storage in your local file
                        system at the location of the original folder.

optional arguments:
  -h, --help            show this help message and exit
  --debug, -g           verbose output for all commands
  --no-slurm, -n        do not submit a Slurm job, execute in the foreground.
  --cores CORES, -c CORES
                        Number of cores to be allocated for the machine. (default=4)
  --profile AWSPROFILE, -p AWSPROFILE
                        which AWS profile from "profiles" or "credentials" in ~/.aws/ should
                        be used
```

#### froster config --help
 
```
dp@grammy:~$ froster config --help

./froster config --help
usage: froster config [-h]

optional arguments:
  -h, --help  show this help message and exit
```

#### froster index --help
 
```
dp@grammy:~$ froster index --help
 
usage: froster index [-h] [--pwalk-csv PWALKCSV] [folders ...]

positional arguments:
  folders               folders you would like to index (separated by space), using the pwalk file system crawler

optional arguments:
  -h, --help            show this help message and exit
  --pwalk-csv PWALKCSV, -p PWALKCSV
                        If someone else has already created CSV files using pwalk you can enter a specific pwalk CSV file here and are not required to run the time consuming pwalk
```
 
#### froster archive --help

```
dp@grammy:~$ ./froster archive --help

usage: froster archive [-h] [--larger LARGER] [--age AGE] [--age-mtime]
                       [--recursive] [--no-tar]
                       [folders ...]

positional arguments:
  folders               folders you would like to archive (separated by space), the last folder in this list is the target

optional arguments:
  -h, --help            show this help message and exit
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
  --recursive, -r       Archive the current folder and all sub-folders
  --no-tar, -n          Do not move small files to tar file before archiving
```

#### froster delete --help
 
```
usage: froster delete [-h] [folders ...]

positional arguments:
  folders     folders (separated by space) from which you would like to delete files, you can only delete files that have been archived

optional arguments:
  -h, --help  show this help message and exit
```

#### froster mount --help

```
dp@grammy:~$ froster mount --help

usage: froster mount [-h] [--mount-point MOUNTPOINT] [--unmount] [folders ...]

positional arguments:
  folders               archived folders (separated by space) which you would like to mount.

optional arguments:
  -h, --help            show this help message and exit
  --mount-point MOUNTPOINT, -m MOUNTPOINT
                        pick a custom mount point, this only works if you select a single folder.
  --unmount, -u         unmount instead of mount, you can also use the umount sub command instead.
```

#### froster restore --help
 
```
dp@grammy:~$ froster restore --help
 
usage: froster restore [-h] [--days DAYS] [--retrieve-opt RETRIEVEOPT] [--no-download]
                       [folders ...]

positional arguments:
  folders               folders you would like to to restore (separated by space),

optional arguments:
  -h, --help            show this help message and exit
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
