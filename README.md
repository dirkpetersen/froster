![image](https://user-images.githubusercontent.com/1427719/235330281-bd876f06-2b2a-46fc-8505-c065bb508973.png)

Froster is a user-friendly archiving tool for teams that move data between higher cost Posix file systems and lower cost S3-like object storage systems such as AWS Glacier. Froster crawls your Posix file system metadata, recommends folders for archiving, generates checksums, and uploads your selections to Glacier or other S3-like storage. It can retrieve data back from the archive using a single command. Additionally, Froster can mount S3/Glacier storage inside your on-premise file system and also restore to an AWS EC2 instance. 

</br>

## Installation pre-requisite: packages

### On Debian/Ubuntu

```
sudo apt-get update
sudo apt-get install -y curl pipx gcc lib32gcc-s1 unzip fuse3
```

### On RHEL 

```
sudo yum update
sudo yum install -y curl pipx gcc lib32gcc-s1 unzip fuse3 python3-devel
```

### On HPC machine

Please contact your administrator to install these packages:
```
curl pipx gcc lib32gcc-s1 unzip fuse3 python3.xx-devel
```

</br>


## Installation

After you installed the pre-requisites, close and open the terminal again to refresh the environment.
To install Froster, execute the following command into your terminal:

```
curl -s https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh?$(date +%s) | bash

```

## Update (TODO)

</br>

## Table of Contents

* [Problem](#problem)
  * [Motivation](#motivation)
* [Design](#design)
* [Preparing Froster](#preparing-froster)
  * [Installing](#installing)
  * [Configuring](#configuring)
    * [Changing defaults with aliases](#changing-defaults-with-aliases)
    * [Working with multiple users](#working-with-multiple-users)
      * [AWS configuration for teams](#aws-configuration-for-teams)
    * [Advanced configuration](#advanced-configuration)
* [Using Froster](#using-froster)    
  * [Standard usage](#standard-usage)
  * [Large scale use on HPC](#large-scale-use-on-hpc)
    * [Picking old and large data](#picking-old-and-large-data)
  * [Special use cases](#special-use-cases)
    * [Recursive operations](#recursive-operations)
    * [Tarring small files](#tarring-small-files)
    * [NIH Life Science metadata](#nih-life-sciences-metadata)
    * [Restore to cloud machine (EC2)](#restore-to-cloud-machine)
    * [Using desktop tools to browse S3 Glacier](#using-desktop-tools-to-browse-s3-glacier)
      * [Cloudberry Explorer](#cloudberry-explorer)
      * [Cyberduck](#cyberduck)
    * [More detailed file system analysis](#more-detailed-file-system-analysis)
* [Command line help](#command-line-help)
* [FAQ and Troubleshooting](#faq-and-troubleshooting)
* [Commercial Solutions](#commercial-solutions)
* [Discontinuing Froster](#discontinuing-froster)

## Problem 

We have yet to find an easy to use, open-source solution for large-scale archiving intended to free up disk space on a primary storage system. Researchers, who may have hundreds of terabytes or even petabytes of data, need to decide what to archive and where to archive it. Archiving processes can stretch on for days and are susceptible to failure. These processes must be able to resume automatically until completion, and need to be validated (for instance, through a checksum comparison with the source). Additionally, it's crucial to maintain some metadata regarding when the archiving occurred, where the data was transferred to, and the original location of the data to be able to restore it quickly.
A specific issue with AWS Glacier is its current implementation as a backend to S3. Only the Glacier features that S3 does not support require the use of a special Glacier API. This fact is often not well documented in how-to guides.

### Motivation 

There were three motivations behind the creation of `Froster`:

- We were working with researchers to optimize their archiving processes. In doing so, we wanted to understand user workflows and identify the essential metadata to be captured. Thanks to Froster's compact codebase, it can be easily adapted to various needs. Metadata could potentially be captured through an additional web interface. However, a web system often requires IT support and an extra layer of authentication. It might be simpler to gather such information through a [Textual TUI interface](https://www.textualize.io/projects/). A first [demo of this option is here](#nih-life-sciences-metadata). The insights gained through working with `Froster` will likely guide the development or acquisition of more advanced tools in the future. 

- HPC users often find AWS Glacier inaccessible or complex and have a preception that it is expensive because of Egress fees. This is despite evidence that most data for most research users has not been touched in years. It seems that it is very difficult to build an on premises archive solution with a lower TCO than AWS Glacier or similar offerings from other cloud providers such as IDrive E2 

- Around the time we were discussing data archiving, ChatGPT4 had just been released. We wanted to assemble a few scripts to explore the best approaches. With ChatGPT4 and Github copilot handling a significant portion of Python coding, nearly 50% of Froster's code was autogenerated. As a result, Froster quickly transformed into a practical tool. The logo was autogenerated by https://www.brandcrowd.com/

## Design 

1. First, we may need to crawl the file system that sometimes has billions of files to find data that is actually worth archiving. For this, Froster uses the well-known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all discovered file metadata.
1. Our focus is on archiving folders rather than individual files, as data that resides in the same folder typically belongs together. To this end, we filter the pwalk's CSV file with [DuckDB](https://duckdb.org), and get a new list (CSV) of the largest folders sorted by size. (We call this a `Hotspots` file)
1. We pass this new list (CSV) to an interactive tool based on [Textual](https://textual.textualize.io/), which displays a table of folders alongside their total size in GiB, their average file sizes in MiB (MiBAvg), as well as their age in days since last accessed (AccD) and modified (ModD). Users can scroll down and right using the mouse, and hitting enter will trigger the archiving of the selected folder.
   ![image](https://user-images.githubusercontent.com/1427719/230824467-6a6e5873-5a48-4656-8d75-42133a60ba30.png)
1. All files < 1 MiB size are moved to an archive called Froster.smallfiles.tar prior to uploading. You can also [avoid tarring](#tarring-small-files) 
1. We pass the folder to [Rclone](https://rclone.org) to execute a copy job in the background.
1. Many researchers with very large datasets will have a Slurm cluster connected to their data storage system. This is ideal for long-running data copy jobs, and Slurm can automatically re-run copy jobs that failed. Researchers can also use the `--no-slurm` option to execute the job in the foreground. This is the default if Slurm is not installed on the Linux machine.
1. Prior to copying, we place files with checksums (e.g., `.froster.md5sum`) in the folders to be archived. This allows for an easy subsequent checksum comparison, providing the user with evidence that all data was correctly archived (through size and md5sum comparisons).
1. After files have been deleted from the source folder, we place a file named `Where-did-the-files-go.txt` in the source folder. This file describes where the data was archived, along with instructions on how to retrieve the data.
1. Optionally allow `archive --recursive` to enable archiving of entire folder trees (CLI only option). [More details here](#recursive-operations).
1. Optionally link to NIH metadata with the `archive --nih` option to link to life sciences research projects [More details here](#nih-life-sciences-metadata).
1. Optionally restore to a cloud machine (AWS EC2 instance) with the `restore --aws` option to avoid egress fees. [More details here](#restore-to-cloud-machine), also please see [this discussion](https://github.com/dirkpetersen/froster/discussions/12).

## Preparing Froster 

### configuring 

The config is mostly automated (just run `froster config`) but you need to answer a few questions for which you can accept defaults in most cases. 
Sometimes the 'rclone' download times out, and you need to hit ctrl+c and start `froster config` again. Froster can manage the [AWS credentials/profiles](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html) that are utilized by the AWS CLI and other tools. 

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

When running `froster config`, you should confirm the default DEEP_ARCHIVE for `AWS S3 storage class` as this is currently the most cost-effective storage solution available. It takes only 5-12 hours to retrieve your data with the least expensive retrieval option ('Bulk'). However, you can choose other [AWS S3 storage classes](https://rclone.org/s3/#s3-storage-class) supported by the rclone copy tool. 

Please note that Froster expects a profile named 'default', 'aws', or 'AWS' in ~/.aws/credentials, which will be used for the Amazon cloud (AWS). If Froster finds other profiles, it will ask you questions about providers, regions, and endpoints. If you do not wish to configure additional 3rd party storage providers, you can simply hit "n" multiple times. Please check the [rclone S3 docs](https://rclone.org/s3/) to learn about different providers and endpoints.

It's important to note that Froster uses the same bucket name for S3 and all S3-compatible storage systems it supports. This streamlines the process if data needs to be migrated between multiple storage systems. The selected bucket will be created if it does not exist, and encryption will be applied (at least in AWS).

Froster has been tested with numerous S3-compatible storage systems such as GCS, Wasabi, IDrive, Ceph, and Minio. At this time, only AWS supports the DEEP_ARCHIVE storage class.


#### working with multiple users 

If we setup a team configuration using `froster config /our/shared/froster/config` Froster knows 3 types of users or roles:

* **Data Stewards**: Users with full write access, they can delete/destroy data in the archive as well as in the local file system
* **Archive Users**: Data scientists with read only access to the archive bucket, they can restore data or mount the archive into the local file system
* **Other Users**: Users without access to the archive cannot use froster with this team. However they can setup their own froster configuration using a different bucket and setup a new team. 

The team config requires correct permissions for the AWS bucket (archive) and in your shared Posix file system where the Froster configuration and json database resides. In the Posix file system we need a security group (e.g. an ActiveDirectory groups called data_steward_grp) to give the group of data stewards write access to the shared config. For this we execute 2 commands:

```
chgrp data_steward_grp /our/shared/froster/config
chmod 2775 /our/shared/froster/config
```

The chmod command ensures that the group of data stewards has write access while all other users have read only access to the configuration. Using 2775 instead of 0775 ensures that the group ownership is inherited to all sub-directories when running chmod (SETGID, This chmod command is run automatically each time you run `froster config`)

##### AWS configuration for teams

You typically use AWS Identity and Access Management (IAM) to set up policies for S3. You can define permissions at a granular level, such as by specifying individual API actions or using resource-level permissions for specific S3 buckets and objects.

Here's a step-by-step guide for a simple permission setup for Data Stewards and Archive Users using the IAM Management Console:

1. Open the IAM console at https://console.aws.amazon.com/iam/ and login with an administrative user account.
1. Create User Groups: It's easier to manage permissions by grouping users. Create two groups: ReadWriteGroup and ReadOnlyGroup. Add the Data Stewards to ReadWriteGroup and the Archive Users to ReadOnlyGroup
1. Create one each IAM Policy (JSON Files) for ReadWriteGroup and ReadOnlyGroup. The s3:RestoreObject action allows users to restore data from Glacier.
1. Attach Policies to Groups: In the IAM console, select the ReadWriteGroup group, click on "Add permissions" and then "Attach policies". Create a new policy using the first JSON, and attach it to this group. Do the same for ReadOnlyGroup using the second JSON.

Policy ReadWriteGroup:
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject",
                "s3:RestoreObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}

```

Policy ReadOnlyGroup:
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket",
                "s3:RestoreObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}

```

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

Some advanced configuration settings are not offered through a user inferface but you can change them under `~/.froster/config`. For example,  `~/.froster/config/general` has one file per setting which makes it very easy to use the settings in shell scripts, for example when writing addon tools: 

```
DEFAULT_STORAGE_CLASS=$(cat ~/.froster/config/general/s3_storage_class)
```

a few advanced settings at ~/.froster/config/general deserve more explanation:

* min_index_folder_size_gib (Default: 10)

If the sum of all file sizes in one folder level is larger than this value in GiB that folder will be included in a hotspots file which is generated using the `froster index` command  


* min_index_folder_size_avg_mib (Default: 10)

If the size of one folder level is at least min_index_folder_size_gib and if the average file size in that folder level is larger than this value in MiB that folder will be included in a hotspots file which is generated using the `froster index` command  

* max_hotspots_display_entries (Default: 5000)

The maximum number of entries that will be shown in the dialog once a hotspots file is selected after using the `froster archive` command.

* max_small_file_size_kib (Default: 1024)

If a file is smaller than this size, it will be moved to a file Froster.smallfiles.tar at the same folder level before uploading with the `froster archive` command. This is useful because Glacier consumes an overhead of about 40 KiB for each uploaded file. If you want to avoid tarring files set max_small_file_size_kib to 0.

## Using Froster 

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
Restore command: froster restore "/home/dp/csv"
Deletion date: 2023-04-19 20:55:15.701141

First 10 files archived:
myfile3.csv, myfile1.csv, myfile2.csv

First 10 files deleted this time:
myfile3.csv, myfile1.csv, myfile2.csv

Please see more metadata in Froster.allfiles.csv

```

After a folder has been deleted and you wish to view the file names in the archive, simply execute `froster mount`. Then, select the folder you want to access. Froster will then mount the bucket location to the folder that was deleted. This allows you to see file and folder names, along with their modification dates. Additionally, you can view the `Froster.allfiles.csv` file using any editor or the `visidata` / `vd` tool. This particular file contains metadata for all files in the folders, including those archived in a .tar format. If you haven't used the DEEP_ARCHIVE or GLACIER S3 archive tiers, you can also copy individual files or access them through your existing pipelines. Remember to use froster umount to unmount the folder when done. 

```
vd /home/dp/csv/Froster.allfiles.csv
froster mount
froster umount
```

The `visidata` tool can display but also manipulate csv files:
![image](https://github.com/dirkpetersen/froster/assets/1427719/279103d4-50c5-4393-9dec-66976922d79a)


After a while you may want to restore the data. Again, you forgot the actual folder location and invoke `froster restore` without the folder argument to see the same dialog with a list of achived folders. Select a folder and hit "Enter" to restore immediatelty.

 
```
dp@grammy:~$ froster restore
 
Restoring folder /home/dp/csv, please wait ...
Triggered Glacier retrievals: 3
Currently retrieving from Glacier: 0
Retrieved from Glacier: 0
Not in Glacier: 0
Glacier retrievals pending, run this again in 5-12h
```

If you use the DEEP_ARCHIVE (default) or GLACIER AWS S3 storage classes, the first execution of `froster restore` will initiate a Glacier retrieval. This retrieval will copy the data in the background from the Glacier archive to the S3 One Zone-IA storage class which costs about $10 per TiB/month and keep it there for 30 days by default (you can change this to something like 7 days with `froster restore --days 7`). Wait for 5-12 hours and run the `froster restore` command again. If all data has been retrieved (which means both "Triggered Glacier retrievals" and "Currently retrieving from Glacier" show 0) the restore to the original folder location will proceed. As an alternative to running `froster restore` a second time, you can use `froster mount` which allows you to access individual files once they have been retrieved from Glacier.

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
0.013 TiB have not been accessed for 365 days (or 1.0 years)
0.028 TiB have not been accessed for 30 days (or 0.1 years)
2023-04-20 08:29:11-07:00 rmdir-scratch.sh info: Preparing to clean scratch space for job 22218558
2023-04-20 08:29:11-07:00 rmdir-scratch.sh info: Deleting directory /mnt/scratch/22218558 for job 22218558
```

now we run the `froster archive` command without entering folder names on the command line. We just created a csv folder for testing that contains 3 csv files with a total of about 1.1 GiB data. We pick this csv folder. It shows that it has been accessed 0 days ago (column AccD) because we just created it.  


![image](https://user-images.githubusercontent.com/1427719/233419009-6a375fe4-541d-4ac6-9ba3-7916b89eabb1.png)


![image](https://github.com/dirkpetersen/froster/assets/1427719/c772cbe3-8329-4c55-9611-7bb1e152c67e)


```
[user@login ~]$ froster archive
Submitted froster archiving job: 22218563
Check Job Output:
 tail -f froster-archive-+home+gscratch+dpcri+csv-22218563.out
```

Once the archive job has completed you should receive an email from your Slurm system.

#### Picking old and large data 

Now let's take it to the next level. Small datasets are not really worth archiving as the cost of storing them is low .... and if we started archiving data that was just used last week, some users would get really angry with us. This means our task is pretty clear: First we are looking for datasets that are large and old. In the example below we want to identify datasets that have not been touched in 3 years (1095 days) and that are larger than 1 TiB (1024 GiB without subfolders). We are executing `froster archive --older 1095 --larger 1024`. As you can see, this produces an output command that you can copy and paste directly into the shell of your HPC login node to submit an archiving batch job. In this case you will save more than 50 TiB of disk space with a few seconds of labor even though the archiving job may take days to run. 

```
froster archive --older 1095 --larger 1024

Processing hotspots file /home/users/dp/.froster/config/hotspots/@XxxxermanLab.csv!

Run this command to archive all selected folders in batch mode:

froster archive \
"/home/groups/XxxxermanLab/xxxriti/tabulation-virus2" \
"/home/groups/XxxxermanLab/xxxsojd/KIR6.2_collaboration" \
"/home/groups/XxxxermanLab/xxxtofia/ER-alpha/WildType_Estradiol_Pose1_BrokenH12_WExplore" \
"/home/groups/XxxxermanLab/xxxriti/estrogen-receptor" \
"/home/groups/XxxxermanLab/xxxsojd/covid_we_data" \
"/home/groups/XxxxermanLab/xxxsojd/covid_data/we_data" \
"/home/groups/XxxxermanLab/xxxtossh/lc8-allostery-study/gromacs/7D35/7D35-comparison/singly-bound-structure/md_5us" \
"/home/groups/XxxxermanLab/xxxtossh/lc8-allostery-study/gromacs/7D35/7D35-comparison/doubly-bound-structure/md_5us" \
"/home/groups/XxxxermanLab/xxxtossh/lc8-allostery-study/gromacs/7D35/7D35-comparison/apo-structure/md_5us" \
"/home/groups/XxxxermanLab/xxxperma/cell/live_cell/mcf10a/batch_17nov20/wctm/17nov20" \
"/home/groups/XxxxermanLab/xxxperma/cell/live_cell/mcf10a/ligcomb_17jun21"

Total space to archive: 54,142 GiB
```

Note: you can also use `--newer xxx --larger yyy to identify files that have only been added recently`


### Special use cases

#### Recursive operations

By default, Froster ignores sub-folders, as only files that reside directly in a chosen folder will be archived. There are two reasons for this: First, if your goal is cost reduction rather than data management, most folders are small and not worth archiving. We want to focus on the few large folders (Hotspots) that make a difference. Secondly, many storage administrators are uncomfortable with users moving hundreds of terabytes. If an entire folder tree can be archived with a single command, it may create bottlenecks in the network or storage systems.
However, you can use the `archive --recursive` option with the archive command to include all sub-folders

#### Tarring small files

Folders with large amounts of small files have always been problematic to manage as they can degrade the metadata performance of a storage system and copying many of them is very slow. Since Glacier objects have an overhead of 40K per uploaded file, storage consumption can get quickly out of hand if not properly managed as a folder with 1 million tiny files would require an addional 40GB storage capacity.

Froster addresses this by moving all small files < 1 MiB to to a Tar archive called Froster.smallfiles.tar in each folder.
Froster.smallfiles.tar is created prior to uploading. When restoring data Froster.smallfiles.tar is automatically extracted and then removed. You do not need to know anything about Froster.smallfiles.tar as you will only see Froster.smallfiles.tar in the S3 like objectstore after it has been deleted from the local file system. If you browse the objectstore with a tool such as [Cyberduck](#using-cyberduck-to-browse-glacier) you will see a file Froster.allfiles.csv along with Froster.smallfiles.tar. The CSV file contains a list of all filenames and metadata including the ones that were tarred to provide addional transparency.
 
To avoid tarring you can set max_small_file_size_kib to 0 using this command. The default is 1024 (KiB) or you can use the `archive --notar` option.

```
echo 0 > ~/.froster/config/general/max_small_file_size_kib
```

#### NIH Life Sciences metadata

In many cases we would like to create a link between the data we archive and the research project granted by a funding organization to increase the [FAIR level](https://the-turing-way.netlify.app/reproducible-research/rdm/rdm-fair.html) of an archived dataset. The National Institutes of Health (NIH) maintains a large database of all publicly funded life sciences projects in the US since the 1980s at [NIH RePORTER](https://reporter.nih.gov). Froster uses the [RePORTER API](https://api.reporter.nih.gov) to allow you to search for grants and link them to your datasets.

To invoke the search interface use the --nih option with `archive` subcommand

```
froster archive --nih
```

![image](https://github.com/dirkpetersen/froster/assets/1427719/b8a69cc0-8e23-44ee-9234-4d4f45a8834c)


You can search multiple times. Once you found the grant you are looking for hit TAB and use the allow keys to select the grant and confirm with enter

#### Restore to cloud machine 

In some cases you may want to restore rarely needed data from Glacier to a cloud machine on EC2. The most frequent use case is to save AWS Egress fees. Use the --aws option with the restore sub-command to create a new ec2 instance with enough local disk space to restore your data there: `froster restore --aws ~/archtest/data1`

```
dp@grammy:~$ froster restore --aws ~/archtest/data1
Total data in all folders: 1.30 GiB
Chosen Instance: c5ad.large
Using Image ID: ami-0a6c63f0325635301
Launching instance i-08028464562bbxxxx ... please wait ...
|████████████████████████████████████████████████--| 96.7%
Security Group "sg-0b648aca16f7c5efd" attached.
Instance IP: 34.222.33.xxx
 Waiting for ssh host to become ready ...
 will execute 'froster restore /home/dp/archtest/data1' on 34.222.33.xxx ...
 Warning: Permanently added '34.222.33.xxx' (ECDSA) to the list of known hosts.
 Executed bootstrap and restore script ... you may have to wait a while ...
 but you can already login using "froster ssh"
Sent email "Froster restore on EC2" to dp@domain.edu!
```

After the instance is created simply run `froster ssh` to login to the last EC2 instance you created or (if you have created multiple machines) `froster ssh <ip-address>`. Once logged in, use the up-arrow key to list the folder where data should be restored to. (Note the data may not be there yet). The environment you find has Conda (with Pytohn and R) as well as Docker and Apptainer/Singularity installed. 

```
dp@grammy:~$ froster ssh
Connecting to 34.222.33.xxx ...

   ,     #_
   ~\_  ####_
  ~~  \_#####\
  ~~     \###|
  ~~       \#/ ___   Amazon Linux 2023 (ECS Optimized)
   ~~       V~' '->
    ~~~         /
      ~~._.   _/
         _/ _/
       _/m/'

For documentation, visit http://aws.amazon.com/documentation/ecs
Last login: Thu Oct 26 09:41:12 2023 from xxx.xxx.221.46
Access JupyterLab:
 http://34.222.33.xxx:8888/lab?token=d453d8aec274c43eb703031c97xxxxxxxxxxxxxxxxxxxx
type "conda deactivate" to leave current conda environment
(base) ec2-user@froster:~$
```

In addition you can click the link (often ctrl+click) to a Jupyter Lab Notebook which has Python and R Kernels installed. You will find a symbolic link starting 'restored-' in your home directory that points to your data. How should this EC2 instance be configured? Please [participate in this discussion](https://github.com/dirkpetersen/froster/discussions/12) 

![image](https://github.com/dirkpetersen/froster/assets/1427719/1837511c-69ec-4b90-b408-a34833c3a68d)


#### Using desktop tools to browse S3 Glacier

##### Cloudberry Explorer

Cloudberry Explorer is a GUI tool to browse, upload and transfer data from AWS S3/Glacier.

* Download Cloudberry Explorer for [Windows](https://www.msp360.com/explorer/windows/) or [Mac](https://www.msp360.com/explorer/mac/)
* Launch and select Amazon S3

![image](https://github.com/dirkpetersen/froster/assets/1427719/71ac8ba9-15d3-4763-b044-73ccd69579ba)

* Enter your credentials and pick your preferred region under 'Advanced'

![image](https://github.com/dirkpetersen/froster/assets/1427719/88b14c0c-2c00-4518-a9ab-48f2a96d8d4e)


##### Cyberduck

[Cyberduck](https://cyberduck.io/download/) is anonther GUI tool to browse, upload and transfer data from AWS S3/Glacier. When creating a new Bookmark, pick the `S3 (with timestamps)` service. If it does not show up in the list pick `More Options...` at the bottom of the list and then search for `timestamps` in Profiles. This ensures that you can see the original modification date of the uploaded files while browsing and not the date they were uploaded to S3/Glacier. All files called `Froster.allfiles.csv` are not stored in Glacier but S3 and you can just mark the file and hit the `Edit` button in the toolbar or run ctrl+k to open that file with the default tool for csv files on your computer (this is often Excel)

![image](https://github.com/dirkpetersen/froster/assets/1427719/48f0e21b-1717-4f9a-9fd5-b3bed110487e)


#### More detailed file system analysis 

`froster index` runs pwalk to create a large csv file with all file system information but this file is immedatly deleted after running index and all detailed file information ist lost. You can save that original file (warning: it can be huge) using the `--pwalk-copy` option and then analyse that data later. You can then use visidata (command: vd) to view the csv file (hit q to quit visidata)

```
froster index --pwalk-copy ~/my_department.csv /shared/my_department
vd ~/my_department.csv
```

## FAQ and Troubleshooting

### Error: Permission denied (publickey,gssapi-keyex,gssapi-with-mic)

This error can occur when using `froster restore --aws`. To resolve this problem delete or rename the ssh key `~/.froster/config/cloud/froster-ec2.pem` (or froster-ec2.pem in your shared config location)

### Why can't I use Froster to archive to Google Drive, Sharepoint/OneDrive, etc ?

Today Froster only supports S3 compatible stores, but it could be adopted to support more as it is using rclone underneath which supports almost everything. The annoying thing with end user file sharing services such as Drive/OneDrive/Sharepoint is that you need to have an oauth authentication token and this needs to be re-generated often. This is not user friendly on an HPC machine without GUI and web browser and on a standard linux machine it is still not super smooth. 
Another adjustment needed: you have perhaps seen that the tool creates a tar file for each directory. Currently only files < 1MB are tarred up (this can be changed). At least for Sharepoint one wants to create larger tar archives as the number of total files is limited in Sharepoint. If you are interested in this please submit an issue. 

## Command line help 

Each of the sub commands has a help option, for example `froster archive --help`
 
### froster --help

```
dp@grammy:~$ froster
usage: froster  [-h] [--debug] [--no-slurm] [--cores CORES] [--profile aws_profile] [--version]
                {config,cnf,index,idx,archive,arc,delete,del,mount,umount,restore,rst,ssh,scp} ...

A (mostly) automated tool for archiving large scale data after finding folders in the file system that
are worth archiving.

positional arguments:
  {config,cnf,index,idx,archive,arc,delete,del,mount,umount,restore,rst,ssh,scp}
                        sub-command help
    config (cnf)        Bootstrap the configurtion, install dependencies and setup your environment. You
                        will need to answer a few questions about your cloud and hpc setup.
    index (idx)         Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file
                        that lists the largest folders. As this process is compute intensive the index
                        job will be automatically submitted to Slurm if the Slurm tools are found.
    archive (arc)       Select from a list of large folders, that has been created by 'froster index',
                        and archive a folder to S3/Glacier. Once you select a folder the archive job will
                        be automatically submitted to Slurm. You can also automate this process
    delete (del)        Remove data from a local filesystem folder that has been confirmed to be archived
                        (through checksum verification). Use this instead of deleting manually
    mount (umount)      Mount or unmount the remote S3 or Glacier storage in your local file system at
                        the location of the original folder.
    restore (rst)       Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need to download
                        all data to local storage after the restore is complete. Just use the mount sub
                        command.
    ssh (scp)           Login to an AWS EC2 instance to which data was restored with the --aws option

optional arguments:
  -h, --help            show this help message and exit
  --debug, -d           verbose output for all commands
  --no-slurm, -n        do not submit a Slurm job, execute in the foreground.
  --cores CORES, -c CORES
                        Number of cores to be allocated for the machine. (default=4)
  --profile aws_profile, -p aws_profile
                        which AWS profile in ~/.aws/ should be used. default="aws"
  --version, -v         print Froster and Python version info

For example, use one of these commands:
  froster config
  froster index /your/lab/root
  froster archive
or you can use one of these:
  'froster delete', 'froster mount' or 'froster restore'
```

### froster config --help
 
```
dp@grammy:~$ froster config  --help
usage: froster config [-h] [--index] [--monitor <email@address.org>] [cfgfolder]

positional arguments:
  cfgfolder             configuration root folder where .froster/config will be created (default=~ home directory)

optional arguments:
  -h, --help            show this help message and exit
  --index, -i           configure froster for indexing only, don't ask addional questions.
  --monitor <email@address.org>, -m <email@address.org>
                        setup froster as a monitoring cronjob on an ec2 instance and notify an email address
```

### froster index --help
 
```
dp@grammy:~$ froster index  --help
usage: froster index [-h] [--pwalk-csv PWALKCSV] [--pwalk-copy PWALKCOPY] [folders ...]

positional arguments:
  folders               folders you would like to index (separated by space), using the pwalk file system crawler

optional arguments:
  -h, --help            show this help message and exit
  --pwalk-csv PWALKCSV, -p PWALKCSV
                        If someone else has already created CSV files using pwalk you can enter a specific pwalk CSV file here and are not required to run the time consuming pwalk.
  --pwalk-copy PWALKCOPY, -y PWALKCOPY
                        Create this backup copy of a newly generated pwalk CSV file. By default the pwalk csv file will only be gnerated in temp space and then deleted.
```
 
### froster archive --help

```
dp@grammy:~$ froster archive --help
usage: froster archive [-h] [--larger LARGER] [--older OLDER] [--mtime] [--recursive] [--no-tar] [--nih]
                       [--dry-run]
                       [folders ...]

positional arguments:
  folders               folders you would like to archive (separated by space), the last folder in this list is the target

optional arguments:
  -h, --help            show this help message and exit
  --larger LARGER, -l LARGER

                        Archive folders larger than <GiB>. This option
                        works in conjunction with --older <days>. If both
                        options are set froster will print a command that
                        allows you to archive all matching folders at once.
  --older OLDER, -o OLDER

                        Archive folders that have not been accessed more than
                        <days>. (optionally set --mtime to select folders that
                        have not been modified more than <days>). This option
                        works in conjunction with --larger <GiB>. If both
                        options are set froster will print a command that
                        allows you to archive all matching folders at once.
  --mtime, -m           Use modified file time (mtime) instead of accessed time (atime)
  --recursive, -r       Archive the current folder and all sub-folders
  --no-tar, -t          Do not move small files to tar file before archiving
  --nih, -n             Search and Link Metadata from NIH Reporter
```

### froster delete --help
 
```
usage: froster delete [-h] [folders ...]

positional arguments:
  folders     folders (separated by space) from which you would like to delete files, you can only delete files that have been archived

optional arguments:
  -h, --help  show this help message and exit
```

### froster mount --help

```
froster mount --help
usage: froster mount [-h] [--mount-point MOUNTPOINT] [--aws] [--unmount] [folders ...]

positional arguments:
  folders               archived folders (separated by space) which you would like to mount.

optional arguments:
  -h, --help            show this help message and exit
  --mount-point MOUNTPOINT, -m MOUNTPOINT
                        pick a custom mount point, this only works if you select a single folder.
  --aws, -a             Mount folder on new EC2 instance instead of local machine
  --unmount, -u         unmount instead of mount, you can also use the umount sub command instead.
```

### froster restore --help
 
```
froster restore --help
usage: froster restore [-h] [--days DAYS] [--retrieve-opt RETRIEVEOPT] [--aws]
                       [--instance-type INSTANCETYPE] [--monitor] [--no-download]
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

                        In addition to the retrieval cost, AWS will charge you about
                        $10/TiB/month for the duration you keep the data in S3.
                        (Costs in Summer 2023)
  --aws, -a             Restore folder on new EC2 instance instead of local machine
  --instance-type INSTANCETYPE, -i INSTANCETYPE
                        The EC2 instance type is auto-selected, but you can pick any other type here
  --monitor, -m         Monitor EC2 server for cost and idle time.
  --no-download, -l     skip download to local storage after retrieval from Glacier
```

### froster ssh --help  (froster scp --help)

```
dp@grammy:~$ froster ssh  --help
usage: froster ssh [-h] [--list] [--terminate <hostname>] [sshargs ...]

positional arguments:
  sshargs               multiple arguments to ssh/scp such as hostname or user@hostname oder folder

optional arguments:
  -h, --help            show this help message and exit
  --list, -l            List running Froster AWS EC2 instances
  --terminate <hostname>, -t <hostname>
                        Terminate AWS EC2 instance with this public IP Address or instance id
```

## Commercial solutions 

You can self-install Froster in a few seconds without requiring root access and you can collaborate well in small teams. However, since Froster requires you having write access to all folders and at least read access to all files you manage, it will not scale to many users. If you are rather looking for a feature rich software managed by IT, you should consider an Enterprise solution such as [Starfish](https://starfishstorage.com).
Froster is a good on-ramp to Starfish. If many users in your organization end up using Froster, it is time considering Starfish as an alternative but if fewer than a handful users find Froster useful, you may be able to defer your Starfish project until you have a critical mass. You can access many advanced Starfish features through a web browser while Froster has a simple CLI/TUI interface.

## Discontinuing Froster  

All good things inevitably come to an end. Consider what you might encounter when attempting to restore your data 15 years from now. While AWS Glacier and Rclone will still exist, we cannot guarantee the continued maintenance of components like Textual or DuckDB, or even Froster itself. However, even if certain tools fade away, you can always rely on utilities like Rclone or [Cyberduck](#using-cyberduck-to-browse-glacier) (for smaller amounts of data) to retrieve your data, as it is kept in its original format.   

Alternatively, the shell script [s3-restore.sh](https://github.com/dirkpetersen/froster/blob/main/s3-restore.sh) simplifies this process, driving Rclone with the appropriate settings. Using the command `s3-restore.sh list`, you can view all folders archived in the JSON database `foster-archives.json` (default location: `~/.froster/config/`). To restore a specific folder, simply use the command followed by the desired path, for example: `s3-restore.sh /my/shared/folder`. It's worth noting that system administrators might hesitate to endorse tools written in programming languages they aren't familiar with, such as Python. Fortunately, `s3-restore.sh` is a straightforward bash shell script, easily customizable to suit specific needs. Note: You may have to change the AWS profile in `s3-restore.sh` to a profile you find under `~/.aws`
