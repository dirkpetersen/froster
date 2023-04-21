# Python Rclone Script with Telegram and InfluxDB Reporting
# - This Script backups your data to any rclone location (see rclone.org)
# - You can execute scripts, commands and database dumps before running a single rclone command
# - It sends automatic error reports and summaries
# - It saves all statistics and operations to an Influx database
# - The data can be used for visualizations in e.g. Grafana
# - You can automate it by using cron

# Created by: Luca Koroll - https://github.com/lucanello
# Last update: 2021-07-04

import json
import os
import requests
import datetime
import math
import subprocess

from influxdb import InfluxDBClient

# Set to True if you want to make a test run
dryrun = False

# Specify logfile directory (where temporary logs are saved)
logfiledir = '/root/'
# Specify host tag for Influx data, used for filtering if you backup several hosts
host = 'vhost'

# Specify extra options, if you want to filter for example (see the calls below, where they are used)
opts = ['--local-no-check-updated', '--delete-excluded', '--exclude-from=excluded.txt']

# Specify your Influx and Telegram credentials
influxclient = InfluxDBClient('host', 8086, 'db_user', 'db_pass', 'db_name')
telegram_token = "123456789:AAABBBCCCDDDEEEFFFGGGHHHIII"
telegram_chat_id = "-123456789"

result_msg = []


def rclone(source, target, configfile=None, transfers=48, dryrun=False, extra_opts=None, mode='sync', db_export=None,
           db_export_location=None, pre_cmd=None):
    # Construct logfilepath
    logfilepath = os.path.join(logfiledir + source.replace('/', '_') + '-rclone.log')
    # Construct rclone sync command
    basecmd = ('rclone ' + str(mode) + ' --transfers=' + str(transfers) + ' --log-file=' + str(logfilepath) +
               ' --use-json-log ' + '--log-level=INFO --stats=90m --fast-list').split()
    # Add dry-run for testing purposes
    basecmd.append('--dry-run') if dryrun else ''
    # Add explicit config if given
    basecmd.append('--config=' + str(configfile)) if configfile else ''
    # Add extra options
    if extra_opts:
        basecmd.extend(extra_opts)
    # Add source and target
    basecmd.append(str(source))
    basecmd.append(str(target))
    try:
        # Execute pre command
        if pre_cmd:
            result = subprocess.run(pre_cmd)
            if result.returncode != 0:
                raise Exception("Error in pre command: " + str(result))
        # Execute database export
        if db_export:
            with open(db_export_location, "w") as outfile:
                result = subprocess.run(db_export, stdout=outfile)
            if result.returncode != 0:
                raise Exception("Error in database export: " + str(result))
        # Execute command
        result = subprocess.run(basecmd)
        if result.returncode != 0:
            with open(logfilepath, 'r') as file:
                data = file.read()
            raise Exception(str(data) + " when executing: " + str(result))
        # Parse logfile
        checks, transfers, bytes = parse_log(logfilepath, source, target)
        # Remove log
        os.remove(logfilepath)
        # Append to result message
        statistic = "\n  ⤷ Checks: " + str(checks) + ", Transfers: " + str(transfers) + ", Bytes: " + \
                    str(convert_size(bytes))
        icon = "✅ " if transfers > 0 else "🆗 "
        result_msg.append(icon + source + " -> " + target + statistic)
    except BaseException as e:
        notify_telegram(("<b>🚨 ERROR in Backup occurred 🚨</b>\n<i>Source</i>: %s\n<i>Target</i>: %s\n<i>Error</i>: %s"
                         % (source, target, str(e))))
        result_msg.append("❌ " + source + " -> " + target)



def parse_log(logfile, source, target):
    with open(logfile) as f:
        data = [json.loads(line.rstrip()) for line in f if line[0] == "{"]
    stats = []
    operations = []
    for obj in data:
        if 'accounting/stats' in obj['source']:
            stats.append(obj)
        elif 'operations/operations' in obj['source']:
            operations.append(obj)
    for obj in stats:
        obj['stats']['speed'] = float(obj['stats']['speed'])
        json_body = [
            {
                "measurement": "stats",
                "tags": {
                    "host": host,
                    "level": obj['level'],
                    "log_entry_source": obj['source'],
                    "source": source,
                    "target": target
                },
                "time": obj['time'],
                "fields": obj['stats']
            }
        ]
        if not dryrun:
            influxclient.write_points(json_body)
    for obj in operations:
        json_body = [
            {
                "measurement": "operations",
                "tags": {
                    "host": host,
                    "level": obj['level'],
                    "log_entry_source": obj['source'],
                    "objType": obj['objectType'],
                    "msg": obj['msg'],
                    "source": source,
                    "target": target
                },
                "time": obj['time'],
                "fields": {
                    "obj": obj['object']
                }
            }
        ]
        if not dryrun:
            influxclient.write_points(json_body)
    return stats[0]['stats']['totalChecks'], stats[0]['stats']['totalTransfers'], stats[0]['stats']['totalBytes']


def notify_telegram(text):
    params = {"parse_mode": "HTML", "chat_id": telegram_chat_id, "text": text}
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    requests.post(url, params=params)


def convert_size(size_bytes):
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])


if __name__ == '__main__':
    start = datetime.datetime.now()

    # Using extra options (specified in the beginning)
    rclone('/source/folder', 'target:folder/', dryrun=dryrun,
                extra_opts=opts)
    
    # Add another extra option 
    rclone('/source/folder', 'target:folder/', dryrun=dryrun,
                extra_opts=opts + ['--min-age=30m'])

    # Backup a database which is dumped in before
    # with rclone(..., db_expot=command, db_export_location=location) you can execute a dump to the given location
    db_export_cmd = '/usr/bin/mysqldump --no-tablespaces --skip-dump-date --single-transaction -h localhost -u db_user -pdb_pass db_name'
    rclone('/source/folder', 'target:folder/',
           dryrun=dryrun, extra_opts=opts, mode='copy',
           db_export=db_export_cmd.split(), db_export_location='/dump/target/db_export.sql')

    # Run a general command in before
    # I am using this for gitea backups for example
    pre_cmd = 'bash /sample/script.sh'
    rclone('/source/folder', 'target:folder/',
           dryrun=dryrun, pre_cmd=pre_cmd.split())

    end = datetime.datetime.now()
    duration = end - start

    # Send Telegram notification
    notify_telegram(("<b>Backup Statistics:</b>\n\n%s\n\n<i>Start Time</i>: %s\n<i>End Time</i>: %s\n<i>Duration</i>: %s minutes" %
                     ("\n\n".join(result_msg), start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"),
                      divmod(duration.total_seconds(), 60)[0])))
