#!/bin/bash

# test script creates test data, runs through all froster
# sub commands and removes data from bucket and /tmp


set -e

script_path="$(readlink -f "$0")"
script_dir="$(dirname "$script_path")"

# Function to create a random 3-character string
random_string() {
    cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 3 | head -n 1
}

# Function to create a sparse file
create_sparse_file() {
    local file_name=$1
    local size=$2
    truncate -s "$size" "$file_name"
    set_file_times "$file_name"
}

# Function to set atime and mtime of a file to 100 days ago
set_file_times() {
    local file_name=$1
    touch -d '100 days ago' "$file_name"
}

generate_test_data() {
    # Create a random directory using mktemp with the updated command
    local base_dir=$(mktemp -d -t "froster.XXX")
    #echo "Base directory: $base_dir"

    # Function to create sparse files in a directory with unique names
    create_files_in_dir() {
        local dir=$1
        local prefix=$2

        # Create a few sparse files
        for i in {1..3}; do
            create_sparse_file "$dir/${prefix}_$(random_string)_medium_$i.out" "1100K"
            create_sparse_file "$dir/${prefix}_$(random_string)_small_$i.out" "900K"
        done

        # Create an executable file
        local script_name="${prefix}_$(random_string)_script.sh"
        touch "$dir/$script_name"
        chmod +x "$dir/$script_name"
        set_file_times "$dir/$script_name"
    }

    # Create unique subdirectories with unique names
    local subdir1_name=$(random_string)
    local subdir2_name=$(random_string)
    local subdir1="$base_dir/${subdir1_name}_subdir"
    local subdir2="$subdir1/${subdir2_name}_subdir"
    mkdir -p "$subdir1"
    mkdir -p "$subdir2"

    # Create sparse files and an executable script in the main directory
    create_files_in_dir "$base_dir" "main"

    # Create a sparse large file and other files only in the first subdirectory
    create_sparse_file "$subdir1/large_$(random_string).out" "1G"
    create_files_in_dir "$subdir1" "${subdir1_name}"

    # Create sparse files and an executable script in the second subdirectory
    create_files_in_dir "$subdir2" "${subdir2_name}"

    # Return the path of the created folder
    echo "$base_dir"
}

# Execute the function and capture the returned folder path
created_folder=$(generate_test_data)
echo "Test data folder: $created_folder"

script_dir=~/.local/bin

if ! [[ -f $script_dir/froster ]]; then
  curl -s https://raw.githubusercontent.com/dirkpetersen/froster/main/install.sh | bash
fi

testbucket='froster-'$(cat /dev/urandom | tr -dc 'a-z' | fold -w 5 | head -n 1)
echo "Using test bucket $testbucket"

cfgbucket=''
if [[ -f ~/.config/froster/general/bucket ]]; then
  cfgbucket=$(cat ~/.config/froster/general/bucket)
fi
echo "$testbucket" > ~/.config/froster/general/bucket

export RCLONE_S3_PROFILE=aws # or ${AWS_PROFILE} or change this to the AWS profile you want to use
export RCLONE_S3_REGION=us-west-2 # or change this to the AWS region you want to use
export RCLONE_S3_PROVIDER=AWS # or change this to another S3 provider (e.g. Ceph for on-premises)
export RCLONE_S3_ENV_AUTH=true # use AWS environment variables and settings from ~/.aws

rclone --log-level error mkdir ":s3:$testbucket"

echo "Running in ${script_dir} ..."

echo -e "\n*** froster config --index"
${script_dir}/froster --no-slurm config --index
echo -e "\n*** froster index $created_folder:"
${script_dir}/froster --no-slurm index "$created_folder"
echo "*** froster archive $created_folder:"
${script_dir}/froster --no-slurm archive "$created_folder"
echo "*** froster delete $created_folder:"
${script_dir}/froster --no-slurm delete "$created_folder"
echo "*** froster mount $created_folder:"
${script_dir}/froster --no-slurm mount "$created_folder"
echo "Wait 3 sec for mount to finish"
sleep 3
echo -e "\n*** froster umount $created_folder:"
${script_dir}/froster --no-slurm umount "$created_folder"
echo -e "\n*** froster restore $created_folder:"
${script_dir}/froster --no-slurm restore "$created_folder"

if [[ -n $cfgbucket ]]; then
  echo "$cfgbucket" > ~/.config/froster/general/bucket
fi

echo "deleting bucket s3://$testbucket"
rclone --log-level error purge ":s3:${testbucket}${created_folder}"
# only deletes bucket if created_folder was the only content in bucket
rclone --log-level error rmdirs ":s3:$testbucket"

echo "deleting test data in $created_folder"

rm -rf $created_folder

