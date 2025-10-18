#! /bin/bash

# Make sure script ends as soon as an error arises
set -e

# Parse command line arguments
VERBOSE=false
FROSTER_VERSION=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE=true
            shift
            ;;
        --version)
            FROSTER_VERSION="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo ""
            echo "Usage: $0 [--verbose] [--version VERSION]"
            echo "  --verbose           Show detailed installation output"
            echo "  --version VERSION   Install specific version (e.g., 0.21.0)"
            echo ""
            exit 1
            ;;
    esac
done

# Function to conditionally redirect output
redirect_output() {
    if [ "$VERBOSE" = true ]; then
        cat
    else
        cat >/dev/null 2>&1
    fi
}

#################
### VARIABLES ###
#################

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}

date_YYYYMMDDHHMMSS=$(date +%Y%m%d%H%M%S) # Get the current date in YYYYMMDD format

froster_data_dir=${XDG_DATA_HOME}/froster
froster_all_data_backups=${XDG_DATA_HOME}/froster_backups
froster_data_backup_dir=${froster_all_data_backups}/froster_${date_YYYYMMDDHHMMSS}.bak

froster_config_dir=${XDG_CONFIG_HOME}/froster
froster_all_config_backups=${XDG_CONFIG_HOME}/froster_backups
froster_config_backup_dir=${froster_all_config_backups}/froster_${date_YYYYMMDDHHMMSS}.bak
version_regex='^[0-9]+\.[0-9]+\.[0-9]+$'

##################################
### AUTO-DETECT LOCAL INSTALL  ###
##################################

# Auto-detect development environment if LOCAL_INSTALL not already set
if [ -z "$LOCAL_INSTALL" ]; then
    if [ -n "$VIRTUAL_ENV" ] && [ -f "pyproject.toml" ]; then
        LOCAL_INSTALL=true
        echo ""
        echo "Auto-detected development environment:"
        echo "  - Virtual environment: $VIRTUAL_ENV"
        echo "  - Source directory: $(pwd)"
        echo "  - Installing in editable mode with pip"
        echo ""
    elif [ -n "$VIRTUAL_ENV" ] && [ ! -f "pyproject.toml" ]; then
        echo ""
        echo "WARNING: You are installing froster inside a virtual environment."
        echo ""
        echo "  Virtual environment: $VIRTUAL_ENV"
        echo ""
        echo "  Froster is designed as a global CLI tool and is best installed"
        echo "  system-wide using pipx (which creates an isolated environment)."
        echo ""
        echo "  Installing in a venv means froster will only be available when"
        echo "  that specific virtual environment is activated."
        echo ""
        echo "  Recommended: Deactivate your venv and run this script again."
        echo "    $ deactivate"
        echo "    $ ./install.sh"
        echo ""
        read -p "Continue with venv installation anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Installation cancelled."
            exit 1
        fi
        # User chose to proceed in venv - mark as venv install (not development)
        VENV_INSTALL=true
        echo ""
        echo "Proceeding with pip installation from PyPI into venv..."
        echo ""
    fi
fi

#####################
### ERROR HANDLER ###
#####################

# Define error handler function
trap 'catch $? $BASH_COMMAND' EXIT

catch() {

    if [ "$1" != "0" ]; then
        echo -e "\nError: $2: Installation failed!\n"
        echo "Your config and data remain safe in:"
        echo "  Config: ${froster_config_dir}"
        echo "  Data: ${froster_data_dir}"
        echo ""

        # Clean up temporary installation files
        rm -rf ${pwalk_path} >/dev/null 2>&1
        rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1
    fi
}

# spinner() {
#     pid=$1
#     spin='-\|/'
#     i=0

#     while kill -0 $pid 2>/dev/null; do
#         i=$(((i + 1) % 4))

#         # If we are in a github actions workflow, we don't want to print the spinner
#         if [ "$GITHUB_ACTIONS" != "true" ]; then
#             printf "\r${spin:$i:1}"
#         fi

#         sleep .1
#     done

#     # If we are in a github actions workflow, we don't want to print this return line
#     if [ "$GITHUB_ACTIONS" != "true" ]; then
#         printf "\r"
#     fi
# }

spinner() {
    arg="$1"
    spin='-\\|/'
    i=0

    check_condition() {
        if [[ "$arg" =~ ^[0-9]+$ ]]; then
            # Numeric: assume it's a PID
            ! kill -0 "$arg" 2>/dev/null
        elif [[ "$arg" == /* ]]; then
            # Starts with /: assume it's a file path
            [ -e "$arg" ]
        else
            # Otherwise: check if command is in PATH
            command -v "$arg" >/dev/null 2>&1
        fi
    }

    while ! check_condition; do
        i=$(( (i + 1) % 4 ))
        # If we are in a GitHub Actions workflow, we don't want to print the spinner
        if [ "$GITHUB_ACTIONS" != "true" ]; then
            printf "\r%s" "${spin:$i:1}"
        fi
        sleep .1
    done

    # If we are in a GitHub Actions workflow, we don't want to print this return line
    if [ "$GITHUB_ACTIONS" != "true" ]; then
        printf "\r"
    fi
}


#################
### FUNCTIONS ###
#################

# Check all needed apt dependencies to install froster
check_dependencies() {

    PIPX_BIN_DIR="${PIPX_BIN_DIR:-$HOME/.local/bin}"

    # Check if ~/.local/bin is in PATH
    local_bin_in_path=false
    if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
        local_bin_in_path=true
    else
        echo -e "\nAdding $PIPX_BIN_DIR to PATH for this installation session"
    fi
    export PATH="$PATH:$PIPX_BIN_DIR"

    # Check if curl is installed
    if [[ -z $(command -v curl) ]]; then
        echo "Error: curl is not installed."
        echo
        echo "Please install curl by running the following commands:"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y curl"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y curl"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

    # Check if python3 is installed
    if [[ -z $(command -v python3) ]]; then
        echo "Error: python3 is not installed."
        echo
        echo "Please install python3 by running the following commands:"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y python3"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y python3"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

    # Check python3 version is 3.8 or higher
    python3_version=$(python3 --version | awk '{print $2}')
    required_version="3.8"

    if [[ $(printf '%s\n' "$required_version" "$python3_version" | sort -V | head -n1) != "$required_version" ]]; then 
        echo "Error: python3 version is $python3_version, but froster requires Python 3.8 or higher."
        echo
        echo "Please install Python 3.8 or higher by running the following commands:"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y python3"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y python3"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

    # Check if gcc is installed
    if [[ -z $(command -v gcc) ]]; then
        echo "Error: gcc is not installed."
        echo
        echo "Please install gcc"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y gcc"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y gcc"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

    # Check if unzip is installed (rclone requirement)
    if [[ -z $(command -v unzip) ]]; then
        echo "Error: unzip is not installed."
        echo
        echo "Please install unzip"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y unzip"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y unzip"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

    # Check if fuse3 is installed
    if [[ -z $(command -v fusermount3) ]]; then
        echo "Error: fusermount3 is not installed."
        echo
        echo "Please install fuse3"
        echo "  On Debian / Ubuntu based systems:"
        echo "    apt update"
        echo "    apt install -y fuse3"
        echo
        echo "  On Fedora / CentOS / RHEL based systems:"
        echo "    dnf update"
        echo "    dnf install -y fuse3"
        echo
        echo "  Other HPC based systems: Contact your administrator to install this package."
        echo
        exit 1
    fi

}

# Get the actual location of froster-archives.json by reading config
get_data_file_location() {
    local config_file="$1"
    local default_location="${XDG_DATA_HOME}/froster/froster-archives.json"

    # If no config exists, return default location
    if [[ ! -f "$config_file" ]]; then
        echo "$default_location"
        return
    fi

    # Try to read shared data directory from config
    # Config format: [general] section with shared_data_dir key
    local shared_dir=$(grep -A 10 "^\[general\]" "$config_file" 2>/dev/null | grep "^shared_data_dir" | cut -d'=' -f2 | tr -d ' ')

    if [[ -n "$shared_dir" && -d "$shared_dir" ]]; then
        echo "${shared_dir}/froster-archives.json"
    else
        echo "$default_location"
    fi
}

# Check if we should restore from backup (for users affected by previous buggy installer)
check_and_restore_from_backup() {
    local config_file="${froster_config_dir}/config.ini"
    local data_file_location

    # Determine where froster-archives.json should be
    data_file_location=$(get_data_file_location "$config_file")

    # Check if BOTH main files are missing
    local config_missing=false
    local data_missing=false

    if [[ ! -f "$config_file" ]]; then
        config_missing=true
    fi

    if [[ ! -f "$data_file_location" ]]; then
        data_missing=true
    fi

    # If at least one file exists, no restore needed
    if [[ "$config_missing" == false || "$data_missing" == false ]]; then
        return 0
    fi

    # Both files are missing, look for backups
    echo -e "\nChecking for previous Froster backups..."

    # Find the most recent backup directory that has BOTH files
    local latest_backup=""
    local backup_config_file=""
    local backup_data_file=""

    # Search for backups in reverse chronological order (newest first)
    for backup_dir in $(find ${froster_all_config_backups} -maxdepth 1 -type d -name "froster_*.bak" 2>/dev/null | sort -r); do
        local test_config="${backup_dir}/config.ini"

        # Check if config exists in this backup
        if [[ ! -f "$test_config" ]]; then
            continue
        fi

        # Get data location from this backup's config
        local test_data_location=$(get_data_file_location "$test_config")

        # Check if we can find the data file in corresponding data backup
        local backup_timestamp=$(basename "$backup_dir" | sed 's/froster_\(.*\)\.bak/\1/')
        local corresponding_data_backup="${froster_all_data_backups}/froster_${backup_timestamp}.bak"

        # Construct potential data file path in backup
        local test_data="${corresponding_data_backup}/froster-archives.json"

        # Also check if data was in a shared location mentioned in backup config
        if [[ "$test_data_location" != "${XDG_DATA_HOME}/froster/froster-archives.json" ]]; then
            # Data might be in shared location, but we can't restore shared data
            # Only check local backup
            test_data="${corresponding_data_backup}/froster-archives.json"
        fi

        if [[ -f "$test_data" ]]; then
            # Found a backup with BOTH files
            latest_backup="$backup_dir"
            backup_config_file="$test_config"
            backup_data_file="$test_data"
            break
        fi
    done

    # If we found a complete backup, ask user
    if [[ -n "$latest_backup" ]]; then
        local backup_date=$(basename "$latest_backup" | sed 's/froster_\([0-9]\{8\}\)\([0-9]\{6\}\)\.bak/\1 \2/' | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\) \([0-9]\{2\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3 \4:\5:\6/')

        echo ""
        echo "==========================================="
        echo "  Froster Backup Found"
        echo "==========================================="
        echo ""
        echo "Your config and data files are missing, but we found a backup from:"
        echo "  Date: $backup_date"
        echo ""
        echo "Backup location:"
        echo "  Config: $backup_config_file"
        echo "  Data:   $backup_data_file"
        echo ""
        echo -n "Would you like to restore these files? (yes/no): "
        read -r response
        echo ""

        if [[ "$response" =~ ^[Yy]([Ee][Ss])?$ ]]; then
            echo "Restoring from backup..."

            # Create directories if needed
            mkdir -p "${froster_config_dir}"
            mkdir -p "$(dirname "$data_file_location")"

            # Restore config
            cp -f "$backup_config_file" "$config_file"
            echo "  ✓ Config restored to: $config_file"

            # Restore data
            cp -f "$backup_data_file" "$data_file_location"
            echo "  ✓ Data restored to: $data_file_location"

            echo ""
            echo "Backup restoration completed successfully!"
            echo ""
        else
            echo "Skipping backup restoration. You can manually restore later from:"
            echo "  $latest_backup"
            echo ""
        fi
    fi
}

# Create backup directories for user reference (optional safety net)
# NOTE: Config and data are NEVER deleted, so backups are just for user peace of mind
backup_old_installation() {

    # Make sure we did not left any backup files from previous updates.
    # Move all backups to the data or config backup directories
    mkdir -p ${froster_all_data_backups}
    mkdir -p ${froster_all_config_backups}
    find ${XDG_DATA_HOME} -maxdepth 1 -type d -name "froster_*.bak" -print0 2>/dev/null | xargs -0 -I {} mv {} $froster_all_data_backups 2>/dev/null || true
    find ${XDG_CONFIG_HOME} -maxdepth 1 -type d -name "froster_*.bak" -print0 2>/dev/null | xargs -0 -I {} mv {} $froster_all_config_backups 2>/dev/null || true


    # Create a reference backup of data (optional, for user peace of mind)
    if [[ -d ${froster_data_dir} ]]; then

        echo -e "\nCreating reference backup of Froster data folder..."

        # Copy the froster directory to froster_YYYYMMDD.bak
        cp -rf ${froster_data_dir} ${froster_data_backup_dir}

        echo "    source: ${froster_data_dir}"
        echo "    destination: ${froster_data_backup_dir}"

        echo "...reference backup created"
    fi

    # Create a reference backup of config (optional, for user peace of mind)
    if [[ -d ${froster_config_dir} ]]; then

        echo -e "\nCreating reference backup of Froster config folder..."

        echo "    source: ${froster_config_dir}"
        echo "    destination: ${froster_config_backup_dir}"

        # Copy the froster config directory to backup
        cp -rf ${froster_config_dir} ${froster_config_backup_dir}

        echo "...reference backup created"
    fi
}

install_pipx() {

    # Skip pipx installation for LOCAL_INSTALL since we use pip directly
    if [ "$LOCAL_INSTALL" = "true" ]; then
        echo -e "\nSkipping pipx (using pip for local development install)..."
        return 0
    fi

    # Skip pipx installation for VENV_INSTALL since we use pip from PyPI
    if [ "$VENV_INSTALL" = "true" ]; then
        echo -e "\nSkipping pipx (using pip for venv install)..."
        return 0
    fi

    echo -e "\nInstalling pipx..."

    # Try installing pipx - handle both regular and virtual environments
    if python3 -m pip install --user pipx 2>&1 | redirect_output; then
        : # Success with --user flag
    elif python3 -m pip install --user --break-system-packages pipx 2>&1 | redirect_output; then
        : # Success with --break-system-packages flag
    elif python3 -m pip install pipx 2>&1 | redirect_output; then
        : # Success without --user flag (works in venv)
    else
        echo "...pipx installation failed"
        return 1
    fi

    # Verify pipx is working
    pipx_version=$(python3 -m pipx --version 2> /dev/null)
    if [[ $pipx_version =~ $version_regex ]]; then
        python3 -m pipx ensurepath 2>&1 | redirect_output
        echo "...pipx installed (version $pipx_version)"
    else
        echo "...warning: could not verify pipx version, continuing anyway"
    fi

}

install_froster() {

    echo -e "\nRemoving old froster binaries only (keeping config and data)..."
    # ONLY remove executables, NEVER touch user config or data
    rm -f ${HOME}/.local/bin/froster
    rm -f ${HOME}/.local/bin/froster.py
    rm -f ${HOME}/.local/bin/s3-restore.py
    echo "...old froster binaries removed"

    if [ "$LOCAL_INSTALL" = "true" ]; then

        echo "  Installing from the current directory"
        echo -e "\nInstalling Froster from the current directory in --editable mode..."
        python3 -m pip install --force -e . >/dev/null 2>&1 &  #>/dev/null 2>&1
        spinner "froster"

    elif [ "$VENV_INSTALL" = "true" ]; then

        echo "  Installing from PyPI into virtual environment"
        # Install specific version if provided, otherwise install latest
        if [[ -n "$FROSTER_VERSION" ]]; then
            echo -e "\nInstalling Froster version ${FROSTER_VERSION} from PyPI..."
            python3 -m pip install froster==${FROSTER_VERSION} 2>&1 | redirect_output &
            spinner $!
            echo "...Froster ${FROSTER_VERSION} installed"
        else
            echo -e "\nInstalling latest Froster from PyPI..."
            python3 -m pip install froster 2>&1 | redirect_output &
            spinner $!
            echo "...Froster installed"
        fi

    else

        echo "  Installing from PyPi package repository"

        if pipx list | grep froster >/dev/null 2>&1; then
            echo -e "\nUninstalling old Froster..."
            pipx uninstall froster >/dev/null 2>&1
            echo "...old Froster uninstalled"
        fi

        # Install specific version if provided, otherwise install latest
        if [[ -n "$FROSTER_VERSION" ]]; then
            echo -e "\nInstalling Froster version ${FROSTER_VERSION} from PyPi..."
            python3 -m pipx install froster==${FROSTER_VERSION} 2>&1 | redirect_output
            echo "...Froster ${FROSTER_VERSION} installed"
        else
            echo -e "\nInstalling latest Froster from PyPi package repository..."
            python3 -m pipx install froster 2>&1 | redirect_output
            echo "...Froster installed"
        fi
    fi

    # Wait until 'froster' command is available in PATH
    echo "    Verifying froster command availability..."
    while ! command -v froster >/dev/null 2>&1; do
        sleep 1
    done
    echo "    ...froster command verified."

    # Config and data directories are NEVER deleted, they persist across upgrades
    # Users' settings and archive database remain intact
}

install_pwalk() {

    echo -e "\nInstalling third-party dependency: pwalk... "

    if ! curl -s --head https://github.com | grep "HTTP/2 200" > /dev/null; then
        echo "Pwalk downloads page https://github.com is not reachable. Please check your firewall settings."
        exit 1
    fi

    # Get the current directory and change to a new temporary directory
    curdir=$(pwd) && tmpdir=$(mktemp -d -t froster.XXX) && cd "$tmpdir"    

    # Variables of pwalk third-party tool froster is using
    pwalk_commit=1df438e9345487b9c51d1eea3c93611e9198f173 # update this commit when new pwalk version released
    pwalk_repository=https://github.com/fizwit/filesystem-reporting-tools/archive/${pwalk_commit}.tar.gz
    pwalk_path=filesystem-reporting-tools-${pwalk_commit}

    # Delete previous downloaded pwalk files (if any)
    rm -rf ${pwalk_path} 2>&1 | redirect_output

    # Gather pwalk repository files
    echo "    Downloading pwalk files"
    curl -s -L ${pwalk_repository} | tar xzf - 2>&1 | redirect_output &
    spinner $!

    # Compile pwalk tool and put exec file in froster's binaries folder
    echo "    Compiling pwalk"
    gcc -pthread ${pwalk_path}/pwalk.c ${pwalk_path}/exclude.c ${pwalk_path}/fileProcess.c -o ${pwalk_path}/pwalk 2>&1 | redirect_output &
    spinner $!

    # Get the froster's binaries folder
    froster_dir=$(dirname "$(readlink -f $(which froster))")
    echo "    Moving pwalk to froster's binaries folder"
    
    # Move pwalk to froster's binaries folder
    mv ${pwalk_path}/pwalk ${froster_dir}/pwalk

    # Verify pwalk was moved successfully
    if [ ! -f "${froster_dir}/pwalk" ]; then
        echo "Error: Failed to move pwalk to ${froster_dir}/pwalk" >&2
        exit 1
    fi

    echo "    Installed pwalk at ${froster_dir}/pwalk"

    # Delete downloaded pwalk files
    echo "    Cleaning up pwalk installation files"
    rm -rf ${pwalk_path} >/dev/null 2>&1
    
    # back to PWD 
    cd $curdir

    echo "...pwalk installed"
}

# Install rclone
install_rclone() {

    echo -e "\nInstalling third-party dependency: rclone... "

    if ! curl -s --head https://downloads.rclone.org | grep "HTTP/2 200" > /dev/null; then
        echo "rclone downloads page https://downloads.rclone.org is not reachable. Please check your firewall settings."
        exit 1
    fi

    # Get the current directory and change to a new temporary directory
    curdir=$(pwd) && tmpdir=$(mktemp -d -t froster.XXX) && cd "$tmpdir"    


    # Check the architecture of the system
    arch=$(uname -m)

    # Get the rclone download URL based on the architecture
    if [[ "$arch" == "x86_64" ]] || [[ "$arch" == "amd64" ]]; then
        rclone_url='https://downloads.rclone.org/rclone-current-linux-amd64.zip'

    elif [[ "$arch" == "arm" ]] || [[ "$arch" == "arm64" ]] || [[ "$arch" == "aarch64" ]]; then
        rclone_url='https://downloads.rclone.org/rclone-current-linux-arm64.zip'

    else
        echo "Unsupported architecture: ${arch}"
        exit 1
    fi

    # Remove previous downloaded zip file (if any)
    rm -rf rclone-current-linux-*.zip rclone-v*/ 2>&1 | redirect_output

    # Download the rclone zip file
    echo "    Downloading rclone files"
    curl -LO $rclone_url 2>&1 | redirect_output &
    spinner $!

    # Extract the zip file
    echo "    Extracting rclone files"
    unzip rclone-current-linux-*.zip 2>&1 | redirect_output &
    spinner $!

    # Get the froster's binaries folder
    froster_dir=$(dirname "$(readlink -f $(which froster))")
    echo "    Moving rclone to froster's binaries folder"

    # Move rclone to froster's binaries folder
    mv rclone-v*/rclone ${froster_dir}/rclone 2>&1 | redirect_output
    echo "    Installed rclone at ${froster_dir}/rclone"

    # Remove the downloaded zip file
    echo "    Cleaning up rclone installation files"
    rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1

    # back to PWD 
    cd $curdir

    echo "...rclone installed"
}

############
### CODE ###
############

# Check linux package dependencies
check_dependencies

# Set rw permissions on anyone in file's group
umask 0002

# Check if we need to restore from backup (for users hit by previous buggy installer)
check_and_restore_from_backup

# Backup old installation (if any)
backup_old_installation

# Install pipx
install_pipx

# Install froster
install_froster

# Install pwalk
install_pwalk

# Install rclone
install_rclone

# Get the installed froster version
version=$(froster -v | awk '{print $2}')

# Print success message
echo -e "\n\nSUCCESS!"

echo -e "\nFroster version: $version"
echo -e "Installation path: $(which froster)"


# Refresh Terminal
if [[ "$local_bin_in_path" = false ]]; then
    echo
    echo "You will need to open a new terminal or refresh your current terminal session by running command:"
    echo "  source ~/.bashrc && source ~/.profile"
    echo
fi

