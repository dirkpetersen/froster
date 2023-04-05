# Froster - yet another archiving tool
Froster is a tool that crawls your file system, suggests folders to archive and uploads your picks to Glacier, etc  

## Problem 

This problem may have been solved many times, but I have not found an easy OSS solution for large scale archiving to free up disk space on a primary storage system. Researchers, who have hundreds of terabytes or petabytes of data, need to make a decison what to archive and where to archive it to. Archiving processes can run for days and they can fail easily. They need to resume automatically until completed and be validated (e.g. checksum comparison with the source) and finally there needs to be some metadata when it was archived, and where the data went and where the original location was.

## Design 

1. First we need to crawl the file system that likely has billions of files to find data that is actually worth archiving. For this we will use the the well known [pwalk](https://github.com/fizwit/filesystem-reporting-tools), a multi-threaded parallel file system crawler that creates a large CSV file of all file metadata found. 
1. We want to focus on archiving folders instead of individual files as data that resides in the same folder will typically belong together. For this we will filter pwalk's CSV file with [DuckDB](https://duckdb.org) and get a list (CSV) of the largest folders sorted by size. 
1. We pass the CSV to an interactive tool such as [Textual](https://github.com/Textualize/textual/blob/main/tests/snapshot_tests/snapshot_apps/data_table_row_cursor.py) that can display a table and will allow you to pick a row that displays the folder you would like to archive (the code to return a row selection is missing in the example) 
1. Pass the folder to a tool like [Rclone](https://rclone.org) and execute a copy job in the background 
1. Since many researchers have access to a Slurm cluster, the initial implmentation would just submit a job via sbatch instead of using a local message queue. Slurm can automatically resubmit jobs that failed and we can also save some comments with `scontrol update job <jobid> Comment="My status update"`
1. Once the copy process is confirmed to have finished we put files with md5sums in the folders that have been archived. 
1. At the very end we put an index.html file that describes where the data went into the source folder

