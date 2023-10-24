#! /bin/bash

# A simple script for restoring data that has been archived with Froster.
# Use this script if you find that Froster is not working or no longer 
# maintained. The only dependencies of this script are rclone and jq.
# This script should work until the end of times !
# 
# Report issues here: https://github.com/dirkpetersen/froster/issues

export RCLONE_S3_PROFILE=aws # or ${AWS_PROFILE} or change this to the AWS profile you want to use
export RCLONE_S3_REGION=us-west-2 # or change this to the AWS region you want to use
export RCLONE_S3_PROVIDER=AWS # or change this to another S3 provider (e.g. Ceph for on-premises)
export RCLONE_S3_ENV_AUTH=true # use AWS environment variables and settings from ~/.aws
#export RCLONE_S3_ENDPOINT='https://s3.us-west-2.amazonaws.com'
TAR_FILENAME="Froster.smallfiles.tar"

if [[ -z $(which rclone) ]]; then
    echo "rclone not installed or not in PATH. Check here: https://rclone.org/downloads"
    exit 1
fi

if [[ -z $(which jq) ]]; then
    echo "jq not installed or not in PATH. Check here: https://jqlang.github.io/jq/download/"
    exit 1
fi

PROFS=$(grep '^\[' ~/.aws/credentials | tr -d '[]')
if ! echo "${PROFS}" | grep -q "\<${RCLONE_S3_PROFILE}\>"; then
  echo "${RCLONE_S3_PROFILE} profile not found in ~/.aws/credentials. Change RCLONE_S3_PROFILE var."
  exit 1
fi
echo "Using ~/.aws profile: ${RCLONE_S3_PROFILE}"

# check if this is a shared config 
CFG_ROOT=~/.config/froster
if [[ -e ${CFG_ROOT}/config_root ]]; then
  CFG_ROOT=$(cat ${CFG_ROOT}/config_root)
  if [[ ! -d ${CFG_ROOT} ]]; then
    echo "Config root ${CFG_ROOT} not found"
    exit 1
  fi
fi

FOLDERS=$(jq -r .[].local_folder ${CFG_ROOT}/froster-archives.json)

if [[ $1 == "list" ]] || [[ -z $1 ]] ; then
  echo "Available local folders:"
  echo "$FOLDERS"
  echo -e "\nUsage: $0 <local_folder>"  
  exit
fi

FLD=$1
FLD="${FLD%/}" # remove trailing slash if any
if ! echo "${FOLDERS}" | grep -q "^${FLD}$"; then
  echo "Folder ${FLD}" not found in DB
  exit 1
fi

ARCHIVE_FOLDER=$(jq -r '."'${FLD}'".archive_folder' ${CFG_ROOT}/froster-archives.json)
if [[ -z $ARCHIVE_FOLDER ]]; then
  echo "archive_folder not found in DB for ${FLD}"
  exit 1
fi
S3_CLASS=$(jq -r '."'${FLD}'".s3_storage_class' ${CFG_ROOT}/froster-archives.json)
if [[ -z $S3_CLASS ]]; then
  echo "s3_storage_class not found in DB for ${FLD}"
  exit 1
fi
PROFILE=$(jq -r '."'${FLD}'".profile' ${CFG_ROOT}/froster-archives.json)
if [[ -z $PROFILE ]]; then
  echo "profile not found in DB for ${FLD}"
  exit 1
fi
ARCHIVE_MODE=$(jq -r '."'${FLD}'".archive_mode' ${CFG_ROOT}/froster-archives.json)
if [[ -z $PROFILE ]]; then
  echo "archive_mode not found in DB for ${FLD}"
  exit 1
fi
[ "${ARCHIVE_MODE}" == "null" ] && ARCHIVE_MODE="Single"

BUCKET="${ARCHIVE_FOLDER#*:s3:}"
BUCKET="${BUCKET%%/*}"
PREFIX="${ARCHIVE_FOLDER#*/}/"

# echo ${ARCHIVE_FOLDER}
# echo ${S3_CLASS}
# echo ${ARCHIVE_MODE}
# echo ${BUCKET}
# echo ${PREFIX}

DEPTH=''
if [[ "${ARCHIVE_MODE}" == "Single" ]]; then
  DEPTH='--max-depth=1'
fi

## If data is in Glacier, retrieve it first before restoring
if [[ "${S3_CLASS}" == "GLACIER" ]] || [[ "${S3_CLASS}" == "DEEP_ARCHIVE" ]]; then
  echo "Checking Glacier retrieve (${ARCHIVE_MODE}) ... "
  rclone backend restore ${DEPTH} -o priority=Bulk -o lifetime=30 ${ARCHIVE_FOLDER} > ~/.rclone-glacier-restore.json
  status_list=$(jq -r .[].Status ~/.rclone-glacier-restore.json)
  if echo "$status_list" | grep -q "RestoreAlreadyInProgress"; then
    echo "Retrieve: Glacier retrieve in progress, try 5-12 hours after restore was initiated."
    exit 1
  else
    echo "Retrieve: Glacier retrieve initiated."
    if [[ "${ARCHIVE_MODE}" == "Recursive" ]]; then
      sleep 5 
    fi
  fi
  if [[ "${ARCHIVE_MODE}" == "Recursive" ]]; then # --max-depth does not seem to work with backend restore-status, fix later
    rclone backend restore-status ${DEPTH} ${ARCHIVE_FOLDER} > ~/.rclone-glacier-restore.json
    status_list=$(jq -r .[].RestoreStatus.IsRestoreInProgress ~/.rclone-glacier-restore.json)
    if echo "$status_list" | grep -xq "true"; then
      echo "Retrieve Status: Glacier restore still in progress, try 5-12 hours after restore was initiated."
      exit 1
    fi
  fi 
fi

if [[ ! -d ${FLD} ]]; then
  echo "Target folder ${FLD} does not exist."
  exit 1
fi

## Restoring from S3 to local folder
echo "Restoring from ${ARCHIVE_FOLDER} to ${FLD} ..."
rclone copy --checksum --progress --verbose ${ARCHIVE_FOLDER} ${FLD} ${DEPTH}

## Comparing S3 with local folder 
echo "Running Checksum comparison, hit ctrl+c to cancel ... "
rclone check --verbose --exclude='.froster.md5sum' ${ARCHIVE_FOLDER} ${FLD} ${DEPTH}

## After restore we must check if there are any files to untar
# Find all tar files and store them in an array
mapfile -t tar_files < <(find "${FLD}" -type f -name "${TAR_FILENAME}")
cdir=$(pwd)
# Iterate over the list of tar files
for tar_file in "${tar_files[@]}"; do
  # Get the directory of the tar file
  dir=$(dirname "$tar_file")
  # Change to the directory
  cd "$dir" || continue
  # Untar the file
  if tar -xf "$tar_file"; then
    echo "Successfully extracted: $tar_file"
    # Delete the tar file
    rm -f "$tar_file"
    echo "Deleted: $tar_file"
  else
    echo "Failed to extract: $tar_file"
  fi
  # Change back to the original directory
  cd - > /dev/null || return
done
cd "$cdir" 
