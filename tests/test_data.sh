#!/bin/bash

# test script creates test data, runs through all froster
# sub commands and removes data from bucket and /tmp


set -e

script_path="$(readlink -f "$0")"
script_dir="$(dirname "$script_path")"

script_dir="$(dirname "$(readlink -f "$0")")"

# Execute the function and capture the returned folder path
created_folder=$(generate_test_data)

echo "Test data folder: $created_folder"

