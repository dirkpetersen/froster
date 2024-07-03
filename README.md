![image](https://user-images.githubusercontent.com/1427719/235330281-bd876f06-2b2a-46fc-8505-c065bb508973.png)


[![PyPI](https://img.shields.io/pypi/v/froster.svg)](https://pypi.org/project/froster/)
[![Downloads](https://img.shields.io/pypi/dm/froster.svg)](https://pypi.org/project/froster/)
[![License](https://img.shields.io/github/license/dirkpetersen/froster)](https://raw.githubusercontent.com/dirkpetersen/froster/main/LICENSE)
[![Python Version](https://img.shields.io/pypi/pyversions/froster.svg)](https://pypi.org/project/froster/)
[![PyPi Release Publish](https://github.com/dirkpetersen/froster/actions/workflows/pypi-release-publish.yml/badge.svg)](https://github.com/dirkpetersen/froster/actions/workflows/pypi-release-publish.yml)
[![Test "froster credentials"](https://github.com/dirkpetersen/froster/actions/workflows/test-credentials.yml/badge.svg)](https://github.com/dirkpetersen/froster/actions/workflows/test-credentials.yml)
[![Test basic features](https://github.com/dirkpetersen/froster/actions/workflows/test-basic-features.yml/badge.svg)](https://github.com/dirkpetersen/froster/actions/workflows/test-basic-features.yml)

Froster is a user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems. It currently supports these S3 providers: AWS, GCS, Wasabi, IDrive, Ceph, and Minio. Froster can efficiently crawl your Posix file system metadata, recommend folders for archiving, generate checksums, and upload your selections to Glacier or other S3-like storage. It can retrieve data back from the archive using a single command. Additionally, Froster can mount S3/Glacier storage inside your on-premise file system and also restore it to an AWS EC2 instance. 

</br>

## Installation pre-requisite: packages

### On Debian / Ubuntu

```
sudo apt update
sudo apt install -y curl python3 python3-pip python3-venv python3-dev gcc lib32gcc-s1 unzip fuse3
```

### On Fedora / CentOS / RHEL

```
sudo dnf update -y
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y curl python3 python3-pip python3-devel unzip fuse3
```

### On HPC machine

Please get in touch with your administrator to install these packages:
```
curl python3 python3-pip python3-venv python3.xx-devel gcc lib32gcc-s1 unzip fuse3
```

</br>


## Installation

To install Froster, execute the following command in your terminal:

```
curl -s https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh?$(date +%s) | bash

```

To check that everything is installed correctly, run `froster --info` or `froster --version` commands.
Check available commands on the help section `froster --help`


</br>

## Update

To update Froster, execute the same command from the [Installation section](#installation). 

Froster will prompt you once a week when a new update is available.
You can manually check if there is an update available by running the command:
```
froster update
``` 

</br>

## Configuration

To run Froster, you need to configure it first. Froster will guide you through the configuration with questions you need to answer. In most cases, you can accept default options by pressing enter.
To configure Froster, run the command:
```
froster config
```
If you have any doubts while configuring Froster, check the [Configuration sections explanation](#configuration-sections-explanation)

If you want a clean config file, run the config command with the `--reset` option:
```
froster config --reset
```

</br>

### Import and Export Configuration

If several users of the same team want to use Froster, they will have to configure the same profiles to work with the same configuration, buckets, endpoints, etc. To ease this configuration across teams, a user that has already configured Froster can export its configuration. This will export all configurations except for sensitive information: username, email, and credentials. To export a configuration, run the command:
```
froster config --export /folder/path
```

To import a configuration, run the command:
```
froster config --import /path/to/exported/config
```

Please note that the `froster config` command still needs to be executed, as username, email, and credentials still need to be configured.

</br>

## Basic usage of Froster

### Credentials

The credentials command checks that the current selected profile is correctly configured and has valid credentials.

```
froster credentials
``` 

### Index

The index command crawls your file system, looking for hotspots (i.e., folders with files larger than 1GB).
It uses a third-party tool called [filesystem-reporting-tools](https://github.com/fizwit/filesystem-reporting-tools), which uses parallel threads to crawl large filesystems efficiently.

This command is not strictly necessary for archiving, but it helps you to spot large folders that are potentially worth archiving. You can provide one or more folders separated by space:

```
froster index [folders...]
``` 

Check more options at `froster index --help`.

### Archive

The archive command uploads folders from the local filesystem to the default profile's S3 bucket. If one or more folders are provided, they will be archived. If no folder is provided, froster will allow you to select hotspots of previously indexed folders.

```
froster archive [folders...]
``` 
Check more options at `froster archive --help`.

**Note**: To change default profile use `froster --default-profile` command. To use a different profile for the current command, you can use the `--profile PROFILE` flag. Check these options at `froster --help`

### Delete

The delete command deletes previously archived folders. If one or more folders are provided, all of them will be deleted from the local filesystem ONLY after verifying that they have been successfully stored in the S3 server. If no folder is provided, froster will allow you to select a folder from previously successfully archived folders. It is worth noting that this command checks if the folders have been successfully uploaded to the S3 bucket. Please do NOT delete folders manually.
```
froster delete [folders...]
``` 
Check more options at `froster delete --help`.

### Restore

The restore command restores a previously deleted folder (i.e., deleted by using the `froster delete` command). This command will first trigger the folder retrieval if folders are stored in a DEEP_ARCHIVE storage class (See [AWS Storage Class guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html)). Once retrieval finishes, executing this command again will download files from the S3 bucket to the local filesystem.
```
froster restore [folders...]
``` 
Check more options at `froster restore --help`.

### Mount / Umount
The mount / umount command (u)mounts the remote S3 or Glacier storage in your local file system at the location of the original folder. If one or more folders are provided, they will be (u)mounted. If no folder is provided, froster will allow you to select folders of previously archived folders.
```
froster mount [folders...]
```
```
froster umount [folders...]
``` 
Check more options at `froster mount --help`.

***

## Table of Contents

* [Problem](#problem)
* [Motivation](#motivation)
* [Design](#design)
* [Preparing Froster](#preparing-froster)
  * [Configuring](#configuring)
  * [Configuration sections explanation](#configuration-sections-explanation)
  * [AWS configuration for teams](#aws-configuration-for-teams)
  * [Changing defaults with aliases](#changing-defaults-with-aliases)
* [Using Froster](#using-froster)    
  * [Standard usage](#standard-usage)
  * [Large scale use on HPC](#large-scale-use-on-hpc)
  * [Picking old and large data](#picking-old-and-large-data)
  * [Special use cases](#special-use-cases)
    * [Recursive operations](#recursive-operations)
    * [Tarring small files](#tarring-small-files)
    * [NIH Life Science metadata](#nih-life-sciences-metadata)
    <!-- * [Restore to cloud machine (EC2)](#restore-to-cloud-machine) -->
    * [Using desktop tools to browse S3 Glacier](#using-desktop-tools-to-browse-s3-glacier)
      * [Cloudberry Explorer](#cloudberry-explorer)
      * [Cyberduck](#cyberduck)
    * [More detailed file system analysis](#more-detailed-file-system-analysis)
* [Command line help](#command-line-help)
* [FAQ and Troubleshooting](#faq-and-troubleshooting)
* [Contributing](#contributing)
  * [Install Froster in development mode](#install-froster-in-development-mode)
  * [Froster development](#froster-development)
  * [Release new Froster version](#release-new-froster-version)
* [Commercial Solutions](#commercial-solutions)
* [Discontinuing Froster](#discontinuing-froster)

## Problem 

We have yet to find an easy-to-use, open-source solution for large-scale archiving intended to free up disk space on a primary storage system. Researchers, who may have hundreds of terabytes or even petabytes of data, must decide what to archive and where. Archiving processes can stretch for days and are susceptible to failure. These processes must be able to resume automatically until completion and need to be validated (for instance, through a checksum comparison with the source). Additionally, it's crucial to maintain some metadata regarding when the archiving occurred, where the data was transferred to, and the data's original location to restore it quickly.

## Motivation 

The main motivations behind the creation of `Froster` are:

- We were working with researchers to optimize their archiving processes. In doing so, we wanted to understand user workflows and identify the essential metadata to be captured. Thanks to Froster's compact codebase, it can be easily adapted to various needs. Metadata could be captured through an additional web interface. However, a web system often requires IT support and an extra layer of authentication. It might be simpler to gather such information through a [Textual TUI interface](https://www.textualize.io/projects/). A first [demo of this option is here](#nih-life-sciences-metadata). The insights gained through working with `Froster` will likely guide the development or acquisition of more advanced tools in the future. 

- HPC users often find AWS Glacier inaccessible or complex and perceive that it is expensive because of Egress fees. This is despite evidence that most data for most research users has not been touched in years. It seems that it is very difficult to build an on-premises archive solution with a lower TCO than AWS Glacier or similar offerings from other cloud providers such as IDrive E2

- Secure the archiving process via checksum verification. After every transfer, a checksum verifies the integrity of destination files, ensuring no data gets lost.


## Design 

1. First, we may need to crawl the file system, which sometimes has billions of files, to find data that is actually worth archiving. For this, Froster uses the well-known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all discovered file metadata.

1. Our focus is on archiving folders rather than individual files, as data in the same folder typically belongs together. To this end, we filter the pwalk's CSV file with [DuckDB](https://duckdb.org) and get a new list (CSV) of the largest folders sorted by size. (We call this a `Hotspots` file)

1. We pass this new list (CSV) to an interactive tool based on [Textual](https://textual.textualize.io/), which displays a table of folders alongside their total size in GiB, their average file sizes in MiB (MiBAvg), as well as their age in days since last accessed (AccD) and modified (ModD). Users can scroll down and right using the mouse and hitting enter will trigger the archiving of the selected folder.
   ![image](https://user-images.githubusercontent.com/1427719/230824467-6a6e5873-5a48-4656-8d75-42133a60ba30.png)

1. All files < 1 MiB size are moved to an archive called Froster.smallfiles.tar before uploading. You can also [avoid tarring](#tarring-small-files) 

1. We pass the folder to [Rclone](https://rclone.org) to execute a copy job in the background.

1. Many researchers with large datasets will have a Slurm cluster connected to their data storage system. This is ideal for long-running data copy jobs, and Slurm can automatically re-run copy jobs that fail. Researchers can also use the `--no-slurm` option to execute the job in the foreground. This is the default if Slurm is not installed on the Linux machine.

1. Before copying, we place files with checksums (e.g., `.froster.md5sum`) in the folders to be archived. This allows for an easy subsequent checksum comparison, providing the user with evidence that all data was correctly archived (through size and md5sum comparisons).

1. After files have been deleted from the source folder, we place a file named `Where-did-the-files-go.txt` in it. This file describes where the data was archived and provides instructions on how to retrieve it.

1. Optionally allow `archive --recursive` to enable archiving of entire folder trees. [More details here](#recursive-operations).

1. (Optional) Link to NIH metadata with the `archive --nih` option to link to life sciences research projects [More details here](#nih-life-sciences-metadata).

<!-- 1. Optionally restore to a cloud machine (AWS EC2 instance) with the `restore --aws` option to avoid egress fees. [More details here](#restore-to-cloud-machine), also please see [this discussion](https://github.com/dirkpetersen/froster/discussions/12). -->

## Preparing Froster 

### Configuring 

The config is mostly automated. You can just run `froster config` command. You need to answer a few questions for which you can accept defaults in most cases. 

When running `froster config`, you should confirm the default DEEP_ARCHIVE for `AWS S3 storage class` as this is currently the most cost-effective storage solution. It takes only 48-72 hours to retrieve your data with the least expensive retrieval option ('Bulk'). See [AWS Storage Class guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html). However, you can choose other [AWS S3 storage classes](https://rclone.org/s3/#s3-storage-class) supported by the rclone copy tool. 

Froster uses `~/.aws` files to store credentials, regions, and endpoints in the AWS standard way.

Check the [rclone S3 docs](https://rclone.org/s3/) to learn about different providers and endpoints.

Froster has been tested with numerous S3-compatible storage systems such as GCS, Wasabi, IDrive, Ceph, and Minio. At this time, only AWS supports the DEEP_ARCHIVE storage class.

### Configuration sections explanation

Down below, you will find an explanation of each configuration section:

- SET USER
  - Set your name. This information will be stored locally as metadata when archiving files.

- SET EMAIL
  - Set your email. This information will be stored locally as metadata when archiving files. Email is also used to notify about SLURM executions.

- SET SHARED
  - If set to yes, then enter the path to the shared folder. The shared folder will be used to store hotspots (output of `froster index <folder>` command) and the archiving database (file with all archived files). This is useful when Froster is used by more than one user. Current user hotspots will be copied to the new shared folder. The archiving database will ONLY be copied to the shared folder if no archiving database is already in the shared folder.
  - If set to no, hotspots and the archiving database will be stored in the local user filesystem.

- SET NIH
  - If set to yes, it allows you to create a link between the data you archive and the research project granted by a funding organization to increase the [FAIR level](https://the-turing-way.netlify.app/reproducible-research/rdm/rdm-fair.html) of an archived dataset. The National Institutes of Health (NIH) has maintained a large database of all publicly funded life sciences projects in the US since the 1980s at [NIH RePORTER](https://reporter.nih.gov).

- SET PROFILE
  - Profiles are Froster's most important configuration. You will need to have at least one configured profile to be able to archive folders to your S3 provider. Profiles store the following information:
    - Select profile: Configure an existing profile or create a new one.
    - Select S3 provider: Select the S3 provider for this profile. Currently supported S3 providers are AWS, GCS, Wasabi, IDrive, Ceph, and Minio. There is also a generic option called "Other," where you can configure a generic S3 provider.
    - Select credentials: Select the credentials for this profile or create new ones. These credentials will be used to authenticate to your S3 provider. They are stored in the ```~/.aws/credentials``` file.
    - Select region: Select the region for this profile or create a new one. ```-- no region --``` option will set the region to the value "default".
    - Select S3 bucket: Select the bucket for this profile or create a new one.
    - Enter directory inside S3 bucket: Enter the root folder where files will be archived for the selected S3 bucket.
    - Select the S3 storage class: Select the S3 storage class for this profile or create a new one. ```DEEP_ARCHIVE``` is currently the most cost-effective storage solution available. See [AWS Storage Class guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html)

- SET SLURM
  - Configure several SLURM options that will be passed to the SLURM script upon execution.

<!-- #### working with multiple users 

If we set a team configuration using `froster config /our/shared/froster/config` Froster knows 3 types of users or roles:

* **Data Stewards**: Users with full write access, they can delete/destroy data in the archive as well as in the local file system
* **Archive Users**: Data scientists with read-only access to the archive bucket, they can restore data or mount the archive into the local file system
* **Other Users**: Users without access to the archive cannot use froster with this team. However they can setup their own froster configuration using a different bucket and setup a new team. 

The team config requires correct permissions for the AWS bucket (archive) and in your shared Posix file system where the Froster configuration and json database resides. In the Posix file system we need a security group (e.g. an ActiveDirectory groups called data_steward_grp) to give the group of data stewards write access to the shared config. For this we execute 2 commands:

```
chgrp data_steward_grp /our/shared/froster/config
chmod 2775 /our/shared/froster/config
```

The chmod command ensures that the group of data stewards has write access while all other users have read only access to the configuration. Using 2775 instead of 0775 ensures that the group ownership is inherited to all sub-directories when running chmod (SETGID, This chmod command is run automatically each time you run `froster config`) -->

### AWS configuration for teams

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

### Changing defaults with aliases

Froster has several global options that you may prefer, but you don't like to type them all the time. We have `--no-slurm` (don't submit batch jobs even if Slurm is found), `--cores` (use a number of CPU cores that is different from the default 4), and `--profile` (use a different profile than default_profile for S3 related commands). You can create a command alias that uses these settings by default. For example, if you think that typing froster is too long and would like to rather type `fro` and use 8 cpu cores in the foreground with a custom profile named `myceph` you can simply enter this command in bash:

```
alias fro="froster --no-slurm --cores=8 --profile=myceph"
```

If you would like to keep this past the next login you can add this alias to the bottom of ~/.bashrc:

```
echo 'alias fro="froster --no-slurm --cores=8 --profile=myceph"' >> ~/.bashrc
```

<!-- #### advanced configuration 

Some advanced configuration settings are not offered through a user interface, but you can change them under `~/.froster/config`. For example,  `~/.froster/config/general` has one file per setting which makes it very easy to use the settings in shell scripts, for example when writing addon tools: 

```
DEFAULT_STORAGE_CLASS=$(cat ~/.froster/config/general/s3_storage_class)
```

a few advanced settings at ~/.froster/config/general deserve more explanation:

* min_index_folder_size_gib (Default: 10)

If the sum of all file sizes in one folder level is larger than this value in GiB that folder will be included in a hotspots file, which is generated using the `froster index` command  


* min_index_folder_size_avg_mib (Default: 10)

If the size of one folder level is at least min_index_folder_size_gib and if the average file size in that folder level is larger than this value in MiB that folder will be included in a hotspots file which is generated using the `froster index` command  

* max_hotspots_display_entries (Default: 5000)

The maximum number of entries that will be shown in the dialog once a hotspot file is selected after using the `froster archive` command.

* max_small_file_size_kib (Default: 1024)

If a file is smaller than this size, it will be moved to a file Froster.smallfiles.tar at the same folder level before uploading with the `froster archive` command. This is useful because Glacier consumes an overhead of about 40 KiB for each uploaded file. If you want to avoid tarring files set max_small_file_size_kib to 0. -->

## Using Froster 

### Standard usage

In its most simple form, Froster can archive a specific folder, delete the source, and restore the data interactively on a standalone Linux machine. 

For example, we have 2 files in a folder

```
vmachado@vmachado:~$ ls -la ~/Desktop/froster/csv

total 2008
-rw-rw-r--  1 vmachado vmachado 1126400 jul  1 17:19 9j6_3ne_medium_1.out
-rw-rw-r--  1 vmachado vmachado  921600 jul  1 17:19 9j6_rqu_small_1.out
```

Now let's archive this folder 

```
vmachado@vmachado:~$ froster archive ~/Desktop/froster/csv

ARCHIVING /home/vmachado/Desktop/froster/csv

    Generating Froster.allfiles.csv and tar small files...
        ...done

    Generating checksums...
        ...done

    Uploading Froster.allfiles.csv file...
        ...done

    Uploading files...
        ...done

    Verifying checksums...
        ...done

ARCHIVING SUCCESSFULLY COMPLETED

    PROVIDER:           "AWS"
    PROFILE:            "profile aws"
    ENDPOINT:           "https://s3.eu-west-2.amazonaws.com"
    LOCAL SOURCE:       "/home/vmachado/Desktop/froster/csv"
    S3 DESTINATION:     ":s3:froster-vmachado-test/froster/home/vmachado/Desktop/froster/csv"
```

Froster creates MD5 checksums for the files in the local folder, uploads them, and then compares the checksums in the archive with the local ones.

Now we delete the local data as we have evidence that the data is intact in the archive. We could execute `froster delete ~/csv`, but since the archiving process took a long time, we forgot which folder we needed to delete. We just run `froster delete` without the folder argument to see a list of archived folders and pick the one in which we want to delete files.

![image](https://user-images.githubusercontent.com/1427719/235413606-b24db72d-cb58-44cc-9754-175d0e4fca9e.png)


after the deletion is completed, we see that a manifest file was created that gives users some info.

```
vmachado@vmachado:~$ froster delete

DELETING /home/vmachado/Desktop/froster/csv...

    Verifying checksums...
        ...done

    Deleting files...
        ...done

DELETING SUCCESSFULLY COMPLETED

    LOCAL DELETED FOLDER:   /home/vmachado/Desktop/froster/csv
    AWS S3 DESTINATION:     :s3:froster-vmachado-test/froster/home/vmachado/Desktop/froster/csv

    Total files deleted:    2

    Manifest:               /home/vmachado/Desktop/froster/csv/Where-did-the-files-go.txt
```

The file has information that should allow other users to find out where the data went and who to contact to get it back. It is important to understand that before deletion, Froster will compare the checksums of each file that was archived with the file in the archive and will only delete local files that have an identical copy in the archive. The manifest file and the checksum comparison are good reasons why you should always let Froster handle the data deletion instead of deleting the source folder manually.

```
vmachado@vmachado:~$ cat /home/dp/csv/Where-did-the-files-go.txt

The files in this folder have been moved to an AWS S3 archive!

Archive location: :s3:froster-vmachado-test/froster/home/vmachado/Desktop/froster/csv
Archive aws profile: profile aws
Archiver user: vmachado
Archiver email: your@email.com
froster-archives.json: /home/vmachado/.local/share/froster/froster-archives.json
Archive tool: https://github.com/dirkpetersen/froster
Restore command: froster restore "/home/vmachado/Desktop/froster/csv"
Deletion date: 2024-07-01 17:23:19.917602


First 10 files deleted this time:
9j6_3ne_medium_1.out, Froster.smallfiles.tar

Please see more metadata in Froster.allfiles.csv file

You can use "visidata" or "vd" tool to help you visualize Froster.allfiles.csv file

```

After a folder has been deleted and you wish to view the file names in the archive, simply execute `froster mount`. Then, select the folder you want to access. Froster will then mount the bucket location to the folder that was deleted. This allows you to see file and folder names, along with their modification dates. Additionally, you can view the `Froster.allfiles.csv` file using any editor or the `visidata` / `vd` tool. This particular file contains metadata for all files in the folders, including those archived in a .tar format. If you haven't used the DEEP_ARCHIVE or GLACIER S3 archive tiers, you can also copy individual files or access them through your existing pipelines. Remember to use froster umount to unmount the folder when done. 

```
vd /home/vmachado/Desktop/froster/csv
froster mount
froster umount
```

The `visidata` tool can display but also manipulate csv files:
![image](https://github.com/dirkpetersen/froster/assets/1427719/279103d4-50c5-4393-9dec-66976922d79a)


After a while you may want to restore the data. Again, you forgot the actual folder location and invoke `froster restore` without the folder argument to see the same dialog with a list of achived folders. Select a folder and hit "Enter" to restore immediatelty.

 
```
vmachado@vmachado:~$ froster restore
 
RESTORING /home/vmachado/Desktop/froster/csv

    Triggered Glacier retrievals: 2
    Currently retrieving from Glacier: 0
    Retrieved from Glacier: 0
    Not in Glacier: 1


    Glacier retrievals pending. Depending on the storage class and restore mode run this command again in:
        Expedited mode: ~ 5 minuts

        Standard mode: ~ 12 hours

        Bulk mode: ~ 48 hours

        
NOTE: You can check more accurate times in the AWS S3 console
```

If you use the DEEP_ARCHIVE (default) or GLACIER AWS S3 storage classes, the first execution of `froster restore` will initiate a Glacier retrieval. This retrieval will copy the data in the background from the Glacier archive to the S3 One Zone-IA storage class which costs about $10 per TiB/month and keep it there for 30 days by default (you can change this to something like 7 days with `froster restore --days 7`). Wait for 12 hours and run the `froster restore` command again. If all data has been retrieved (which means both "Triggered Glacier retrievals" and "Currently retrieving from Glacier" show 0) the restore to the original folder location will proceed. As an alternative to running `froster restore` a second time, you can use `froster mount` which allows you to access individual files once they have been retrieved from Glacier.

```
dp@grammy:~$ froster restore

RESTORING /home/vmachado/Desktop/froster/csv

    Triggered Glacier retrievals: 0
    Currently retrieving from Glacier: 0
    Retrieved from Glacier: 2
    Not in Glacier: 1

    Downloading files...
        ...done

    Generating checksums...
        ...done

    Verifying checksums...
        ...done

    Untarring Froster.smallfiles.tar... 
        ...done

RESTORATION OF /home/vmachado/Desktop/froster/csv COMPLETED SUCCESSFULLY
```

Note that if you restore from AWS S3 to on-premises, you may be subject to AWS data egress charges (up to $90 per TiB downloaded, or $20 per TiB with AWS DirectConnect), unless your organization has negotiated an [AWS data egress waiver](https://aws.amazon.com/blogs/publicsector/data-egress-waiver-available-for-eligible-researchers-and-institutions/).

### Large scale use on HPC

If you have hundreds of terabytes or even petabytes of data in billions of files, you may not be able to easily locate data that is worth archiving. Among hundreds of thousands of folders, there are typically only a few hundred that make up most of your storage consumption. We call these folders 'Hotspots,' and to find them, you use the `froster index` command and pass the root directory of your lab data. 

```
[user@login ~]$ froster index /home/vmachado/data_2

SLURM JOB

  ID: 2251
  Type: index
  Check status: "squeue -j 2251"
  Check output: "tail -n 100 -f /home/.local/shared/froster/slurm/froster-index@+home+vmachado+data_2-2251.out"
  Cancel the job: "scancel 2251"

```

we can see the status of the job and then use the suggested tail command to see how the indexing is progressing, we can see that the job finished successfully  

```
[user@login ~]$ tail -n 100 -f /home/.local/shared/froster/slurm/froster-index@+home+vmachado+data_2-2251.out

INDEXING /home/vmachado/data_2

Hotspots file: /home/vmachado/shared_dir/hotspots/+home+vmachado+data_2.csv
    with 0 hotspots >= 1 GiB
    with a total disk use of 0.0 TiB

Total folders processed: 3

INDEXING SUCCESSFULLY COMPLETED
```

now we run the `froster archive` command without entering folder names on the command line. We just created a csv folder for testing that contains 3 csv files with a total of about 1.1 GiB data. We pick this csv folder. It shows that it has been accessed 0 days ago (column AccD) because we just created it.  


![image](https://user-images.githubusercontent.com/1427719/233419009-6a375fe4-541d-4ac6-9ba3-7916b89eabb1.png)


![image](https://github.com/dirkpetersen/froster/assets/1427719/c772cbe3-8329-4c55-9611-7bb1e152c67e)


```
[user@login ~]$ froster archive /home/vmachado/data_2

SLURM JOB

  ID: 2252
  Type: archive
  Check status: "squeue -j 2252"
  Check output: "tail -n 100 -f /home/.local/shared/froster/slurm/froster-archive@+home+vmachado+data_2-2252.out"
  Cancel the job: "scancel 2252"

```

Once the archive job has been completed, you should receive an email from your Slurm system.

### Picking old and large data 

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

Folders with large amounts of small files have always been problematic to manage, as they can degrade a storage system's metadata performance, and copying many of them is very slow. Since Glacier objects have an overhead of 40K per uploaded file, storage consumption can quickly get out of hand if not properly managed, as a folder with 1 million tiny files would require an additional 40GB storage capacity.

Froster addresses this by moving all small files < 1 MiB to a Tar archive called Froster.smallfiles.tar in each folder.
Froster.smallfiles.tar is created before uploading. When restoring data Froster.smallfiles.tar is automatically extracted and then removed. You do not need to know anything about Froster.smallfiles.tar as you will only see Froster.smallfiles.tar in the S3-like object store after it has been deleted from the local file system. If you browse the objectstore with a tool such as [Cyberduck](#using-cyberduck-to-browse-glacier) you will see a file Froster.allfiles.csv along with Froster.smallfiles.tar. The CSV file contains a list of all filenames and metadata, including the ones that were tarred to provide additional transparency.
 
To avoid tarring, use this command: `froster archive—- notar` option.

```
echo 0 > ~/.froster/config/general/max_small_file_size_kib
```

#### NIH Life Sciences metadata

In many cases, we would like to create a link between the data we archive and the research project granted by a funding organization to increase the [FAIR level](https://the-turing-way.netlify.app/reproducible-research/rdm/rdm-fair.html) of an archived dataset. The National Institutes of Health (NIH) has maintained a large database of all publicly funded life sciences projects in the US since the 1980s at [NIH RePORTER](https://reporter.nih.gov). Froster uses the [RePORTER API](https://api.reporter.nih.gov) to allow you to search for grants and link them to your datasets.

To invoke the search interface configure it as default on the `froster config` SET_NIH section or use the --nih option with `archive` subcommand

```
froster archive --nih [folders...]
```

![image](https://github.com/dirkpetersen/froster/assets/1427719/b8a69cc0-8e23-44ee-9234-4d4f45a8834c)


You can search multiple times. Once you find the grant you are looking for, hit TAB and use the allow keys to select the grant and confirm with enter

<!-- #### Restore to cloud machine 

In some cases, you may want to restore rarely needed data from Glacier to a cloud machine on EC2. The most frequent use case is to save AWS Egress fees. Use the --aws option with the restore sub-command to create a new ec2 instance with enough local disk space to restore your data there: `froster restore --aws ~/archtest/data1`

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

After the instance is created, simply run `froster ssh` to login to the last EC2 instance you created or (if you have created multiple machines) `froster ssh <ip-address>`. Once logged in, use the up-arrow key to list the folder where data should be restored. (Note the data may not be there yet). The environment you find has Conda (with Python and R) as well as Docker and Apptainer/Singularity installed. 

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

In addition, you can click the link (often ctrl+click) to a Jupyter Lab Notebook, which has Python and R Kernels installed. You will find a symbolic link starting 'restored-' in your home directory that points to your data. How should this EC2 instance be configured? Please [participate in this discussion](https://github.com/dirkpetersen/froster/discussions/12) 

![image](https://github.com/dirkpetersen/froster/assets/1427719/1837511c-69ec-4b90-b408-a34833c3a68d)
 -->

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

`froster index` runs `pwalk` to create a large csv file with all file system information but this file is immediately deleted after running the index and all detailed file information is lost. You can save that original file (warning: it can be huge) using the `--pwalk-copy` option and then analyze that data later. You can then use `visidata` (command: vd) to view the csv file (hit q to quit `visidata`)

```
froster index --pwalk-copy ~/my_department.csv /shared/my_department
vd ~/my_department.csv
```

## Command line help 

Each of the sub-commands has a help option, for example `froster archive --help`
 
### froster --help

```
dp@grammy:~$ froster --help

usage: froster  [-h] [-c CORES] [-d] [-D] [-i] [-l] [-m MEMORY] [-n] [-p PROFILE] [-v]
                {credentials,crd,config,cnf,index,idx,archive,arc,delete,del,mount,umount,restore,rst,update,upd} ...

A user-friendly archiving tool for teams that move data between high-cost POSIX file systems and low-cost S3-like object storage systems

positional arguments:
  {credentials,crd,config,cnf,index,idx,archive,arc,delete,del,mount,umount,restore,rst,update,upd}
                        sub-command help

options:
  -h, --help            show this help message and exit
  -c CORES, --cores CORES
                        Number of cores to be allocated for the machine. (default=4)
  -d, --debug           verbose output for all commands
  -D, --default-profile
                        Select default profile
  -i, --info            print froster and packages info
  -l, --log-print       Print the log file to the screen
  -m MEMORY, --mem MEMORY
                        Amount of memory to be allocated for the machine in GB. (default=64)
  -n, --no-slurm        do not submit a Slurm job, execute in the foreground.
  -p PROFILE, --profile PROFILE
                        User this profile for the current session
  -v, --version         print froster version
```

### froster config --help
 
```
dp@grammy:~$ froster config --help

usage: froster config [-h] [-p] [-r] [-i IMPORT_CONFIG] [-e EXPORT_CONFIG]

Froster configuration bootstrap. This command will guide you through the
configuration of Froster. You can also import and export configurations.

options:
  -h, --help            show this help message and exit
  -p, --print           Print the current configuration
  -r, --reset           Delete the current configuration and start over
  -i IMPORT_CONFIG, --import IMPORT_CONFIG
                        Import a given configuration file
  -e EXPORT_CONFIG, --export EXPORT_CONFIG
                        Export the current configuration to the given directory
```

### froster index --help
 
```
dp@grammy:~$ froster index --help

usage: froster index [-h] [-f] [-p] [-y PWALKCOPY] [folders ...]

Scan a file system folder tree using 'pwalk' and generate a hotspots CSV file
that lists the largest folders. As this process is compute intensive the
index job will be automatically submitted to Slurm if the Slurm tools are
found.

positional arguments:
  folders               Folders you would like to index (separated by space), using the pwalk file system crawler 

options:
  -h, --help            show this help message and exit
  -f, --force           Force indexing
  -p, --permissions     Print read and write permissions for the provided folder(s)
  -y PWALKCOPY, --pwalk-copy PWALKCOPY
                        Directory where the pwalk CSV file should be copied to.
```
 
### froster archive --help

```
dp@grammy:~$ froster archive --help

usage: froster archive [-h] [-f] [-l LARGER] [-o OLDER] [--newer NEWER] [-n] [-i NIHREF] [-m] [-r] [-s] [-t] [-d] [folders ...]

Select from a list of large folders, that has been created by 'froster index', and
archive a folder to S3/Glacier. Once you select a folder the archive job will be
automatically submitted to Slurm. You can also automate this process

positional arguments:
  folders               folders you would like to archive (separated by space), the last folder in this list is the target   

options:
  -h, --help            show this help message and exit
  -f, --force           Force archiving of a folder that contains the .froster.md5sum file
  -l LARGER, --larger LARGER
                        
                        Archive folders larger than <GiB>. This option
                        works in conjunction with --older <days>. If both
                        options are set froster will print a command that
                        allows you to archive all matching folders at once.
  -o OLDER, --older OLDER
                        
                        Archive folders that have not been accessed more than
                        <days>. (optionally set --mtime to select folders that
                        have not been modified more than <days>). This option
                        works in conjunction with --larger <GiB>. If both
                        options are set froster will print a command that
                        allows you to archive all matching folders at once.
  --newer NEWER, -w NEWER
                        
                        Archive folders that have been accessed within the last 
                        <days>. (optionally set --mtime to select folders that
                        have not been modified more than <days>). This option
                        works in conjunction with --larger <GiB>. If both 
                        options are set froster will print a command that 
                        allows you to archive all matching folders at once.
  -n, --nih             Search and Link Metadata from NIH Reporter
  -i NIHREF, --nih-ref NIHREF
                        Use NIH Reporter reference for the current archive
  -m, --mtime           Use modified file time (mtime) instead of accessed time (atime)
  -r, --recursive       Archive the current folder and all sub-folders
  -s, --reset           
                        This will not download any data, but recusively reset a folder
                        from previous (e.g. failed) archiving attempt.
                        It will delete .froster.md5sum and extract Froster.smallfiles.tar
  -t, --no-tar          Do not move small files to tar file before archiving
  -d, --dry-run         Execute a test archive without actually copying the data
```

### froster delete --help
 
```
dp@grammy:~$ froster delete --help

usage: froster delete [-h] [-r] [folders ...]

Remove data from a local filesystem folder that has been confirmed to
be archived (through checksum verification). Use this instead of deleting manually

positional arguments:
  folders          folders (separated by space) from which you would like to delete files, you can only delete files that have been archived

options:
  -h, --help       show this help message and exit
  -r, --recursive  Delete the current archived folder and all archived sub-folders
```

### froster {mount|umount} --help

```
dp@grammy:~$ froster mount --help
usage: froster mount [-h] [-a] [-l] [-m MOUNTPOINT] [folders ...]

Mount or unmount the remote S3 or Glacier storage in your local file system
at the location of the original folder.

positional arguments:
  folders               archived folders (separated by space) which you would like to mount.

options:
  -h, --help            show this help message and exit
  -a, --aws             Mount folder on new EC2 instance instead of local machine
  -l, --list            List all mounted folders
  -m MOUNTPOINT, --mount-point MOUNTPOINT
                        pick a custom mount point, this only works if you select a single folder.
```

### froster restore --help
 
```
fdp@grammy:~$ froster restore --help
usage: froster restore [-h] [-a] [-d DAYS] [-i INSTANCETYPE] [-l] [-m] [-o RETRIEVEOPT] [-r] [folders ...]

Restore data from AWS Glacier to AWS S3 One Zone-IA. You do not need
to download all data to local storage after the restore is complete.
Just use the mount sub command.

positional arguments:
  folders               folders you would like to to restore (separated by space)

options:
  -h, --help            show this help message and exit
  -a, --aws             Restore folder on new AWS EC2 instance instead of local machine
  -d DAYS, --days DAYS  Number of days to keep data in S3 One Zone-IA storage at $10/TiB/month (default: 30)
  -i INSTANCETYPE, --instance-type INSTANCETYPE
                        The EC2 instance type is auto-selected, but you can pick any other type here
  -l, --no-download     skip download to local storage after retrieval from Glacier
  -m, --monitor         Monitor EC2 server for cost and idle time.
  -o RETRIEVEOPT, --retrieve-opt RETRIEVEOPT
                        
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
  -r, --recursive       Restore the current archived folder and all archived sub-folders
```

<!-- ### froster ssh --help  (froster scp --help)

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
``` -->

## FAQ and Troubleshooting

<!-- ### Error: Permission denied (publickey,gssapi-keyex,gssapi-with-mic)

This error can occur when using `froster restore --aws`. To resolve this problem delete or rename the ssh key `~/.froster/config/cloud/froster-ec2.pem` (or froster-ec2.pem in your shared config location) -->

### Why can't I use Froster to archive to Google Drive, Sharepoint/OneDrive, etc ?

Today, Froster only supports S3 compatible stores, but it could be adapted to support more as it is using Rclone underneath, which supports almost everything. The annoying thing with end-user file-sharing services such as Drive/OneDrive/Sharepoint is that you need to have an OAuth authentication token, and this needs to be re-generated often. This is not user-friendly on an HPC machine without GUI and web browser, and on a standard Linux machine, it is still not super smooth. 
Another adjustment is needed: you have perhaps seen that the tool creates a tar file for each directory. Currently, only files < 1MB are tarred up (this can be changed). At least for Sharepoint, one wants to create larger tar archives as the number of total files is limited in Sharepoint. If you are interested in this please submit an issue. 



## Contributing

### Install Froster in development mode 

If you want to develop Froster features, you can install it in --editable mode.
This allows you to modify the package source code and see the changes directly without having to reinstall the package.

To install Froster in --editable mode follow these steps:

1. Download the repository
```
git clone https://github.com/dirkpetersen/froster.git
```

1. Go to the downloaded repository
``` 
cd froster
``` 

1. Create a virtual environment
``` 
python3 -m venv .venv
```

1. Activate virtual environment
``` 
source .venv/bin/activate
```

1. Set LOCAL_INSTALL environment variable to true
```
export LOCAL_INSTALL=true
``` 

1. execute the install.sh script
``` 
./install.sh
``` 

Now Froster is installed in --editable mode inside the virtual environment.
Any changes to the source code will be immediately reflected without needing to reinstall froster.
Beware that ```froster --version``` takes the version from the package metadata (pyproject.toml). Therefore Froster's version will only be updated if reinstalled. This only affects to version printing value.

> **Note**: If you want to develop and debug Froster using [VS Code](https://code.visualstudio.com/), you should create the virtual environment via VS Code following these instructions: [Python environments in VS Code](https://code.visualstudio.com/docs/python/environments). Delete any previous virtual enviroments and let VS Code create the environment, otherwise you will experiencie some inconsistencies while debugging. Follow the rest installation instructions. Now you can debug froster by pressing `F5` or via the command palette. You can also debug by giving CLI command parameters.

### Froster development

For developing on Froster, please follow the standard convention of Fork and Pull Request. More information in Github's manual [Contributing to a project](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project)


### Release new Froster version

Froster's releases to [PyPi](https://pypi.org/search/?q=froster) are automatically handled by GitHub Actions.
A release in the [Froster's Github repository](https://github.com/dirkpetersen/froster) will trigger the Release Github Actions Workflow and it will upload the new release package to [PyPi](https://pypi.org/search/?q=froster).

After the new Froster development, the Froster version MUST be increased.
To increase the Froster version update the [pyproject.toml version](https://github.com/dirkpetersen/froster/blob/2ac87cc3b2438cffb874ca436fbe565abf272dab/pyproject.toml#L7). The Froster's version follows this convention: `v<Major>.<Minor>.<Subminor>`

When to increase each value?
- Major: Introduce breaking changes or major new features.
- Minor: Add functionality in a backward-compatible manner.
- Subminor: Make backward-compatible bug fixes or small improvements.

Steps to release a new version of Froster:
1. Go to [Froster's release site](https://github.com/dirkpetersen/froster/releases)

1. "Draft a new release"

1. Make sure the target branch is "main"

1. Make sure you `"Choose a tag",` follow version tag convention: `v<Major>.<Minor>.<Subminor>`

1. Make sure to select `"+ Create new tag vXX.XX.XX on publish"`

1. Go to bottom page and tick `Set as the latest release`

1. Press `Publish release` button

> **Warning**: Even though the new package version is immediately released and shown as available in [PyPi](https://pypi.org/search/?q=froster), it takes a few minutes to actually update the package in the PyPi servers. Please wait ~5 minutes before updating Froster, or you will likely be installing the old version.

## Commercial solutions 

You can self-install Froster in a few seconds without requiring root access, and you can collaborate well in small teams. However, since Froster requires you to have write access to all folders and at least read access to all files you manage, it will not scale to many users. If you are looking for feature-rich software managed by IT, you should consider an Enterprise solution such as [Starfish](https://starfishstorage.com).
Froster is a good on-ramp to Starfish. If many users in your organization end up using Froster, it is time to consider Starfish as an alternative, but if fewer than a handful of users find Froster useful, you may be able to defer your Starfish project until you have a critical mass. You can access many advanced Starfish features through a web browser while Froster has a simple CLI/TUI interface.

## Discontinuing Froster  

All good things inevitably come to an end. Consider what you might encounter when attempting to restore your data 15 years from now. While AWS Glacier and Rclone will still exist, we cannot guarantee the continued maintenance of components like Textual or DuckDB, or even Froster itself. However, even if certain tools fade away, you can always rely on utilities like Rclone or [Cyberduck](#using-cyberduck-to-browse-glacier) (for smaller amounts of data) to retrieve your data, as it is kept in its original format.   

Alternatively, the shell script [s3-restore.sh](https://github.com/dirkpetersen/froster/blob/main/s3-restore.sh) simplifies this process, driving Rclone with the appropriate settings. Using the command `s3-restore.sh list`, you can view all folders archived in the JSON database. Default localtion of Froster JSON database is: `~/.local/share/froster/froster-archives.json`. This path may have changed if you are using a shared configuration. Check the `Where-did-the-files-go.txt` manifest for more information on the folder's metadata. 

To restore a specific folder, simply use the command followed by the desired path, for example: `s3-restore.sh /my/shared/folder`. It's worth noting that system administrators might hesitate to endorse tools written in programming languages they aren't familiar with, such as Python. Fortunately, `s3-restore.sh` is a straightforward bash shell script, easily customizable to suit specific needs. 

Note: You need to populate the environment variables for `s3-restore.sh` script to work. Check out the first lines of the script
