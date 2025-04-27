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
    #local base_dir=$(mktemp -d -t "froster.XXX")
    local base_dir=$(mktemp -d "froster.XXX")
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

    # Create directory symlinks
    ln -s "${subdir1_name}_subdir" "$base_dir/link_to_subdir1"
    touch -h -d '100 days ago' "$base_dir/link_to_subdir1"
    ln -s ".." "$base_dir/link_to_parent"
    touch -h -d '100 days ago' "$base_dir/link_to_parent"

    # Create file symlinks to existing files in the base directory
    # Find some target files first (handle potential errors if no files match)
    target_medium=$(ls -1 "$base_dir"/main_*_medium_*.out 2>/dev/null | head -n 1)
    target_small=$(ls -1 "$base_dir"/main_*_small_*.out 2>/dev/null | head -n 1)
    target_script=$(ls -1 "$base_dir"/main_*_script.sh 2>/dev/null | head -n 1)

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

