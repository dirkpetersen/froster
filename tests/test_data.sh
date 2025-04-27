#!/bin/bash

# test script creates test data, runs through all froster
# sub commands and removes data from bucket and /tmp


set -e

script_path="$(readlink -f "$0")"
script_dir="$(dirname "$script_path")"

script_dir="$(dirname "$(readlink -f "$0")")"

# Function to generate a random string
random_string() {
    local length=${1:-8}
    LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w "$length" | head -n 1
}

# Function to create a sparse file of a given size
create_sparse_file() {
    local filename=$1
    local size_mb=$2
    local path=$3
    # Use truncate for potentially better performance and compatibility
    truncate -s "${size_mb}M" "$path/$filename"
    # dd if=/dev/zero of="$path/$filename" bs=1M count=0 seek="$size_mb" status=none
}

# Function to set file access and modification times
set_file_times() {
    local filepath=$1
    local days_ago=$2
    touch -a -d "$days_ago days ago" "$filepath"
    touch -m -d "$days_ago days ago" "$filepath"
}

# Function to create files within a directory
create_files_in_dir() {
    local dir_path=$1
    local prefix=$2
    local days_ago=100 # Approx 3 months

    # Create some files with different sizes and ages
    create_sparse_file "${prefix}_$(random_string)_large_$(random_string).bin" 1500 "$dir_path" # 1.5 GB -> Use MB for size
    create_sparse_file "${prefix}_$(random_string)_medium_$(random_string).out" 50 "$dir_path"  # 50 MB
    create_sparse_file "${prefix}_$(random_string)_small_$(random_string).txt" 1 "$dir_path"    # 1 MB
    echo "This is a script file" > "$dir_path/${prefix}_$(random_string)_script.sh"

    # Set timestamps for all created files/dirs in this path
    # Use find -exec touch directly for simplicity and potentially better handling of many files
    find "$dir_path" -mindepth 1 -maxdepth 1 -exec touch -a -d "$days_ago days ago" {} +
    find "$dir_path" -mindepth 1 -maxdepth 1 -exec touch -m -d "$days_ago days ago" {} +
}

# Main function to generate the test data structure
generate_test_data() {
    local base_dir_name="froster_test_data_$(random_string)"
    # Ensure mktemp uses a safe pattern and directory
    local random_suffix=$(random_string 3) # Generate a 3-char random string
    local base_dir="./froster.data.${random_suffix}" # Define the directory name in the current dir
    mkdir "$base_dir" # Create the directory

    # Create main directory files
    create_files_in_dir "$base_dir" "main"

    # Create subdirectories and files within them
    local subdir1_name="subdir1_$(random_string)"
    local subdir2_name="subdir2_$(random_string)"
    mkdir "$base_dir/$subdir1_name"
    mkdir "$base_dir/$subdir2_name"
    create_files_in_dir "$base_dir/$subdir1_name" "sub1"
    create_files_in_dir "$base_dir/$subdir2_name" "sub2"

    # Create a deeper subdirectory
    local subsubdir_name="subsubdir_$(random_string)"
    mkdir "$base_dir/$subdir1_name/$subsubdir_name"
    create_files_in_dir "$base_dir/$subdir1_name/$subsubdir_name" "subsub"

    # Create directory symlinks
    ln -s "${subdir1_name}" "$base_dir/link_to_subdir1"
    touch -h -d '100 days ago' "$base_dir/link_to_subdir1"
    ln -s ".." "$base_dir/link_to_parent"
    touch -h -d '100 days ago' "$base_dir/link_to_parent"

    # Create file symlinks to existing files in the base directory
    # Use find for more robust file searching
    local target_medium=$(find "$base_dir" -maxdepth 1 -name 'main_*_medium_*.out' -print -quit)
    local target_small=$(find "$base_dir" -maxdepth 1 -name 'main_*_small_*.txt' -print -quit)
    local target_script=$(find "$base_dir" -maxdepth 1 -name 'main_*_script.sh' -print -quit)


    # Create links only if target files were found
    if [ -n "$target_medium" ]; then
        ln -s "$(basename "$target_medium")" "$base_dir/link_to_medium_file"
        touch -h -d '100 days ago' "$base_dir/link_to_medium_file"
    fi
    if [ -n "$target_small" ]; then
        ln -s "$(basename "$target_small")" "$base_dir/link_to_small_file"
        touch -h -d '100 days ago' "$base_dir/link_to_small_file"
    fi
    if [ -n "$target_script" ]; then
        ln -s "$(basename "$target_script")" "$base_dir/link_to_script_file"
        touch -h -d '100 days ago' "$base_dir/link_to_script_file"
    fi

    # Return the path to the created base directory
    echo "$base_dir"
}

# Execute the function which echoes the created folder path
generate_test_data

