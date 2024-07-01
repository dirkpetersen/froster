#!/bin/bash

# A simple script for restoring data that has been archived with Froster.
# Use this script if you find that Froster is not working or no longer
# maintained. The only dependencies of this script are rclone and jq.
# This script should work until the end of times !
#
# Report issues here: https://github.com/dirkpetersen/froster/issues

#################
# CONFIGURATION #
#################

# These varibles need to be populated with the correct values
# You can get some of these values from the Where-did-the-files-go.txt manifest file
# You need to configure the profile or both the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.

# WARNING: RCLONE does not inform you when the command fails due to incorrect credentials. It just freezes
# and you have to kill the process. Make sure you have the correct credentials or the correct profile before running this script
# Check your AWS PROFILE at ~/.aws/credentials and ~/.aws/config
# The output of rclone command should be shown in a few minuts

export RCLONE_S3_PROVIDER=
export RCLONE_S3_ENDPOINT=
export RCLONE_S3_REGION=
export RCLONE_S3_LOCATION_CONSTRAINT=
export RCLONE_S3_PROFILE=
export AWS_ACCESS_KEY_ID=
export AWS_SECRET_ACCESS_KEY=

export RCLONE_S3_ENV_AUTH=true

TAR_FILENAME="Froster.smallfiles.tar"
FROSTER_ARCHIVE_DEFAULT="${HOME}/.local/share/froster/froster-archives.json"

tmp_folder="${TMPDIR:-/tmp}"

RESTORE_OUTPUT="${tmp_folder}/froster_restore${1//\//_}.output"
RESTORE_STATUS_OUTPUT="${tmp_folder}/froster_restore_status${1//\//_}.output"


#############
# FUNCTIONS #
#############

print_usage() {
  echo
  echo "[*] Usage";
  echo "------------------------------------";
  echo "  s3-restore.sh {DIRECTORY_PATH} ";
  echo "     Diretory that want to restore";
  echo ""
  echo "  s3-restore.sh list";
  echo "     List available local folders";
  echo
  exit 0
}

check_dependencies(){

  if [[ -z $(which rclone) ]]; then
    echo -e "\nrclone not installed or not in PATH. Check here: https://rclone.org/downloads\n"
    exit 1
  fi
  
  if [[ -z $(which jq) ]]; then

    echo -e "\njq not installed or not in PATH. Check here: https://jqlang.github.io/jq/download/\n"
    exit 1
  fi
}


check_environment() {
  if [[ -z $RCLONE_S3_PROVIDER ]]; then
    echo -e "\nRCLONE_S3_PROVIDER not set. Set it in the environment or in the script.\n"
    echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
    exit 1
  fi

  if [[ -z $RCLONE_S3_ENDPOINT && $RCLONE_S3_PROVIDER != "AWS" ]]; then
    echo -e "\nRCLONE_S3_ENDPOINT not set. Set it in the environment or in the script.\n"
    echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
    exit 1
  fi

  if [[ -z $RCLONE_S3_REGION ]]; then
    echo -e "\nWARNING: RCLONE_S3_REGION not set. Set it in the environment or in the script.\n"
    echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
  fi

  if [[ -z $RCLONE_S3_LOCATION_CONSTRAINT ]]; then
    echo -e "\n WARNING: RCLONE_S3_LOCATION_CONSTRAINT not set. Set it in the environment or in the script.\n"
    echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
  fi

  if [[ -z $RCLONE_S3_PROFILE ]]; then
    if [[ -z $AWS_ACCESS_KEY_ID || -z $AWS_SECRET_ACCESS_KEY ]]; then
      echo -e "\nAWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set. Set it in the environment or in the script.\n"
      echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
      exit 1
    else
      echo -e "\nRCLONE_S3_PROFILE not set. Set it in the environment or in the script.\n"
      echo -e "You may get this information from the Where-did-the-files-go.txt manifest file\n"
      exit 1
    fi
  fi
}


list_local_folders(){
  
  if [[ ! -f ${FROSTER_ARCHIVE_DEFAULT} ]]; then
    echo -e "\nDefault froster database ${FROSTER_ARCHIVE_DEFAULT} not found\n"
  else

    FOLDERS=$(jq -r '.[].local_folder' ${FROSTER_ARCHIVE_DEFAULT})
      echo -e "\nAvailable local folders to restore found in: ${FROSTER_ARCHIVE_DEFAULT}:\n"
      echo "$FOLDERS"
      echo 
      exit
  fi
}

restore_rclone(){

  #Set varibles
  DIRECTORY_PATH=$1
  DIRECTORY_PATH="${DIRECTORY_PATH%/}"  # remove trailing slash if any
  MANIFEST_FILE_NAME="Where-did-the-files-go.txt"
  ARCHIVE_MANIFEST="${DIRECTORY_PATH}/${MANIFEST_FILE_NAME}"
  
  #Check the manifest file exist
  if [[ -d $DIRECTORY_PATH ]]; then
    if [[ ! -f "${ARCHIVE_MANIFEST}" ]]; then
      echo -e "\t[-] Manifest ${ARCHIVE_MANIFEST} not found\n"
      exit 1
    fi
  else
    echo -e "\t[-] $DIRECTORY_PATH Directory not found\n"
    exit 1
  fi
  
  echo -e "\n\t[*] Restore ${DIRECTORY_PATH} \n"
  echo -e "\n\t[*] Setting Parameters \n"
  

  # Get profiles from ~/.aws/credentials file
  PROFS=$(grep '^\[' ~/.aws/credentials | tr -d '[]')

  # Check if the profile exists in ~/.aws/credentials
  if ! echo "${PROFS}" | grep -q "\<${RCLONE_S3_PROFILE}\>"; then
    if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
      echo -e "\t[-]${RCLONE_S3_PROFILE} profile not found in ~/.aws/credentials. Add credentials to restore.conf.\n"
      exit 1
    else
      echo -e "\t\t[+] Using configured AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY as AWS credentials\n"
    fi
  else
    echo -e "\t\t[+] Using ~/.aws/credentials profile:${RCLONE_S3_PROFILE}"
  fi
  
  #Get froster-archives.json
  FROSTER_ARCHIVE=$(grep "froster-archives.json" ${ARCHIVE_MANIFEST} | cut -d ' ' -f2)

  # Get the archive mode
  ARCHIVE_MODE=$(jq --arg DIRECTORY_PATH "$DIRECTORY_PATH" '.[$DIRECTORY_PATH].archive_mode' ${FROSTER_ARCHIVE})
    
  #Get parametrization from froster-archives.json
  if [[ -z "${ARCHIVE_MODE}" || "${ARCHIVE_MODE}" == "null"  ]]; then
    echo "[-] archive_mode not found in ${FROSTER_ARCHIVE} for ${DIRECTORY_PATH}"
    exit 1
  else
    echo -e "\t\t[+] archive_mode:${ARCHIVE_MODE}"
  fi
  
  # Get the archive folder
  ARCHIVE_FOLDER=$(jq -r --arg DIRECTORY_PATH "$DIRECTORY_PATH" '.[$DIRECTORY_PATH].archive_folder' ${FROSTER_ARCHIVE})
  if [[ -z $ARCHIVE_FOLDER ]]; then
    echo "[-] archive_folder not found in ${FROSTER_ARCHIVE} for ${DIRECTORY_PATH}"
    exit 1
  else
    echo -e "\t\t[+] archive_folder:\"${ARCHIVE_FOLDER}\""
  fi
  
  # Get the storage class
  S3_CLASS=$(jq -r --arg DIRECTORY_PATH "$DIRECTORY_PATH" '.[$DIRECTORY_PATH].s3_storage_class' ${FROSTER_ARCHIVE})
  if [[ -z $S3_CLASS ]]; then
    echo "[-] s3_class not found in ${S3_CLASS} for ${DIRECTORY_PATH}"
    exit 1
  else
    echo -e "\t\t[+] s3_class:${S3_CLASS}"
  fi
  
  # Aesthetic print
  echo
  
  # If data is in Glacier, retrieve it first before restoring
  if [[ "${S3_CLASS}" == "GLACIER" ]] || [[ "${S3_CLASS}" == "DEEP_ARCHIVE" ]]; then

    echo "Folder archived in ${S3_CLASS} mode."

    echo -e "\nRetrieving from Glacier...\n"

    # Execute the restore command
    rclone backend restore --max-depth=1 -o priority=Bulk -o lifetime=30 ${ARCHIVE_FOLDER} > ${RESTORE_OUTPUT}

    # Get the status of each file
    statuses=$(jq -r '.[].Status' ${RESTORE_OUTPUT})

    # Variable to store the status of the restore
    all_ok=true

    # Iterate over each status value to check if Retrieve status is "OK"
    for status in $statuses; do
        if [[ "$status" != "OK" && "$status" != "Not GLACIER or DEEP_ARCHIVE storage class" ]]; then
            all_ok=false
            break
        fi
    done

    if $all_ok; then
      echo -e "\nGlacier retrieve initiated."
      echo -e "Execute the same command again 48 hours after restore was initiated.\n"
      exit 0
    else 
      # Retrieval already initiated

      # Execute the restore-status command
      rclone backend restore-status --max-depth=1 -o priority=Bulk -o lifetime=30 ${ARCHIVE_FOLDER} > ${RESTORE_STATUS_OUTPUT}

      # Get the restore status of each file
      statuses=$(jq -r '.[].RestoreStatus.IsRestoreInProgress' ${RESTORE_STATUS_OUTPUT})

      # Variables to store the status of the restore
      all_true=true
      all_false=true

      # Check if IsRestoreInProgress keys are all true or all false
      for status in $statuses; do
          if [[ "$status" == "true" ]]; then
              all_false=false
          else
              all_true=false
          fi

          # if both are false, we can break the loop
          if ! $all_true && ! $all_false; then
              break
          fi
      done

      if $all_true; then
        echo -e "\nRetrieve: Glacier retrieve in progress, try again 48 hours after restore was initiated.\n"
        exit 0
      elif $all_false; then
        # If all files have been restored, we can proceed with the restore
        # This path is the only one that goes though the restore process
        echo -e "\nRetrieve: Glacier retrieve finished."
      else
        echo -e "\nRetrieve: Only some files have been retrieved. Glacier retrieve in progress, try again 48 hours after restore was initiated.\n"
        exit 0
      fi
    fi
  fi

  ### Restoring from S3 to local folder
  echo "Restoring from ${ARCHIVE_FOLDER} to ${DIRECTORY_PATH} ..."
  rclone copy --checksum --progress --verbose ${ARCHIVE_FOLDER} ${DIRECTORY_PATH} ${DEPTH}
  
  ### Comparing S3 with local folder
  echo "Running Checksum comparison, hit ctrl+c to cancel ... "
  rclone check --verbose --exclude='.froster.md5sum' ${ARCHIVE_FOLDER} ${DIRECTORY_PATH} ${DEPTH}
  
  ### After restore we must check if there are any files to untar
  ## Find all tar files and store them in an array
  mapfile -t tar_files < <(find "${DIRECTORY_PATH}" -type f -name "${TAR_FILENAME}")
  #cdir=$(pwd)
  ## Iterate over the list of tar files
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
    cd - >/dev/null || return
  done
  cd "$cdir"
}

########
# MAIN #
########

check_dependencies

check_environment

if [[ -z $1 ]]; then
  print_usage
elif [[ $1 == 'list' ]]; then
  list_local_folders
else
  restore_rclone "$1"
fi
