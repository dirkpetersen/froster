#! /bin/bash

# Make sure script ends as soon as an error arises
set -e

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

#####################
### ERROR HANDLER ###
#####################

# Define error handler function
trap 'catch $? $BASH_COMMAND' EXIT

catch() {

    if [ "$1" != "0" ]; then
        echo -e "\nError: $2: Installation failed!\n"

        # Restore (if any) backed up froster config files
        if [[ -d ${froster_config_backup_dir} ]]; then
            mv -f ${froster_config_backup_dir} ${froster_config_dir} >/dev/null 2>&1
        fi

        # Restore (if any) backed up froster data files
        if [[ -d ${froster_data_backup_dir} ]]; then
            mv -f ${froster_data_backup_dir} ${froster_data_dir} >/dev/null 2>&1
        fi

        rm -rf ${pwalk_path} >/dev/null 2>&1
        rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1
    fi
}

spinner() {
    pid=$1
    spin='-\|/'
    i=0

    while kill -0 $pid 2>/dev/null; do
        i=$(((i + 1) % 4))

        # If we are in a github actions workflow, we don't want to print the spinner
        if [ "$GITHUB_ACTIONS" != "true" ]; then
            printf "\r${spin:$i:1}"
        fi

        sleep .1
    done

    # If we are in a github actions workflow, we don't want to print this return line
    if [ "$GITHUB_ACTIONS" != "true" ]; then
        printf "\r"
    fi
}

#################
### FUNCTIONS ###
#################

# Check all needed apt dependencies to install froster
check_dependencies() {

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

# Backup older installations (if any) but keep the froster-archive.json and config.ini files
backup_old_installation() {

    # Make sure we did not left any backup files from previous updates.
    # Move all backups to the data or config backup directories
    mkdir -p ${froster_all_data_backups}
    mkdir -p ${froster_all_config_backups}
    find ${XDG_DATA_HOME} -maxdepth 1 -type d -name "froster_*.bak" -print0 | xargs -0 -I {} mv {} $froster_all_data_backups
    find ${XDG_CONFIG_HOME} -maxdepth 1 -type d -name "froster_*.bak" -print0 | xargs -0 -I {} mv {} $froster_all_config_backups


    # Back up (if any) older froster data files
    if [[ -d ${froster_data_dir} ]]; then

        echo -e "\nBacking Froster data folder ..."

        # Copy the froster directory to froster_YYYYMMDD.bak
        cp -rf ${froster_data_dir} ${froster_data_backup_dir}

        echo "    source: ${froster_data_dir}"
        echo "    destination: ${froster_data_backup_dir}"

        echo "...data backed up"
    fi

    # Back up (if any) older froster configurations
    if [[ -d ${froster_config_dir} ]]; then

        echo -e "\nBacking Froster config folder ..."

        echo "    source: ${froster_config_dir}"
        echo "    destination: ${froster_config_backup_dir}"

        # Move the froster config directory to froster.bak
        cp -rf ${froster_config_dir} ${froster_config_backup_dir}

        echo "...config backed up"
    fi
}

install_pipx() {

    echo -e "\nInstalling pipx..."

    # Check if pipx is installed
    if [[ -z $(command -v pipx) ]]; then

        # Install or upgrade pipx
        echo "  Installing pipx via pip"
        python3 -m pip install --upgrade pipx >/dev/null 2>&1

        # Ensure path for pipx
        echo "  Ensuring path for pipx"
        if [[ $(command -v pipx) ]]; then
            pipx ensurepath >/dev/null 2>&1
        else
            $HOME/.local/bin/pipx ensurepath >/dev/null 2>&1
        fi
        
        echo "...pipx installed"
    else
        echo "...pipx already installed"

        echo -e "\nUpgrading pipx..."
        pipx upgrade pipx >/dev/null 2>&1 &
        spinner $!
        echo "...pipx upgraded"

        echo -e "\nEnsuring path for pipx..."
        pipx ensurepath >/dev/null 2>&1
        echo "...path ensured"
    fi

    # Check if PIPX_BIN_DIR is set and not empty, otherwise default to ~/.local/bin
    PIPX_BIN_DIR="${PIPX_BIN_DIR:-$HOME/.local/bin}"
    echo -e "\nAdding $PIPX_BIN_DIR to PATH for this installation session"
    export PATH="$PATH:$PIPX_BIN_DIR"
}

install_froster() {

    echo -e "\nRemoving old froster files..."
    rm -rf ${froster_data_dir}
    rm -rf ${froster_config_dir}
    rm -f ${HOME}/.local/bin/froster
    rm -f ${HOME}/.local/bin/froster.py
    rm -f ${HOME}/.local/bin/s3-restore.py
    echo "...old froster files removed"

    if [ "$LOCAL_INSTALL" = "true" ]; then
        echo -e "\nInstalling Froster from the current directory in --editable mode..."
        pip install -e . >/dev/null 2>&1 &
        spinner $!
        echo "...Froster installed"
    else
        if pipx list | grep froster >/dev/null 2>&1; then
            echo -e "\nUninstalling old Froster..."
            pipx uninstall froster >/dev/null 2>&1
            echo "...old Froster uninstalled"
        fi

        echo -e "\nInstalling Froster from PyPi package repository"
        pipx install froster >/dev/null 2>&1 &
        spinner $!
        echo "...Froster installed"
    fi

    # Keep the config.ini file (if any)
    if [[ -f ${froster_config_backup_dir}/config.ini ]]; then
        # Create the froster directory if it does not exist
        mkdir -p ${froster_config_dir}

        # Copy the config file to the data directory
        cp -f ${froster_config_backup_dir}/config.ini ${froster_config_dir}
    fi

    # Keep the froster-archives.json file (if any)
    if [[ -f ${froster_data_backup_dir}/froster-archives.json ]]; then
        # Create the froster directory if it does not exist
        mkdir -p ${froster_data_dir}

        # Copy the froster-archives.json file to the data directory
        cp -f ${froster_data_backup_dir}/froster-archives.json ${froster_data_dir}
    fi
}

install_pwalk() {

    echo -e "\nInstalling third-party dependency: pwalk... "

    if ! curl -s --head https://github.com | grep "HTTP/2 200" > /dev/null; then
        echo "rclone downloads page https://downloads.rclone.org is not reachable. Please check your firewall settings."
        exit 1
    fi

    # Variables of pwalk third-party tool froster is using
    pwalk_commit=1df438e9345487b9c51d1eea3c93611e9198f173 # update this commit when new pwalk version released
    pwalk_repository=https://github.com/fizwit/filesystem-reporting-tools/archive/${pwalk_commit}.tar.gz
    pwalk_path=filesystem-reporting-tools-${pwalk_commit}

    # Delete previous downloaded pwalk files (if any)
    rm -rf ${pwalk_path} >/dev/null 2>&1

    # Gather pwalk repository files
    echo "    Downloading pwalk files"
    curl -s -L ${pwalk_repository} | tar xzf - >/dev/null 2>&1 &
    spinner $!

    # Compile pwalk tool and put exec file in froster's binaries folder
    echo "    Compiling pwalk"
    gcc -pthread ${pwalk_path}/pwalk.c ${pwalk_path}/exclude.c ${pwalk_path}/fileProcess.c -o ${pwalk_path}/pwalk >/dev/null 2>&1 &
    spinner $!

    # Get the froster's binaries folder
    froster_dir=$(dirname "$(readlink -f $(which froster))")
    echo "    Moving pwalk to froster's binaries folder"
    
    # Move pwalk to froster's binaries folder
    mv ${pwalk_path}/pwalk ${froster_dir}/pwalk >/dev/null 2>&1
    echo "    Installed pwalk at ${froster_dir}/pwalk"

    # Delete downloaded pwalk files
    echo "    Cleaning up pwalk installation files"
    rm -rf ${pwalk_path} >/dev/null 2>&1

    echo "...pwalk installed"
}

# Install rclone
install_rclone() {

    echo -e "\nInstalling third-party dependency: rclone... "

    if ! curl -s --head https://downloads.rclone.org | grep "HTTP/2 200" > /dev/null; then
        echo "rclone downloads page https://downloads.rclone.org is not reachable. Please check your firewall settings."
        exit 1
    fi


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
    rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1

    # Download the rclone zip file
    echo "    Downloading rclone files"
    curl -LO $rclone_url >/dev/null 2>&1 &
    spinner $!

    # Extract the zip file
    echo "    Extracting rclone files"
    unzip rclone-current-linux-*.zip >/dev/null 2>&1 &
    spinner $!

    # Get the froster's binaries folder
    froster_dir=$(dirname "$(readlink -f $(which froster))")
    echo "    Moving rclone to froster's binaries folder"

    # Move rclone to froster's binaries folder
    mv rclone-v*/rclone ${froster_dir}/rclone >/dev/null 2>&1
    echo "    Installed rclone at ${froster_dir}/rclone"

    # Remove the downloaded zip file
    echo "    Cleaning up rclone installation files"
    rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1

    echo "...rclone installed"
}

############
### CODE ###
############

# Check linux package dependencies
check_dependencies

# Set rw permissions on anyone in file's group
umask 0002

# Backup old installation (if any)
backup_old_installation

# Get the current directory and change to a new temporary directory
curdir=$(pwd) && tmpdir=$(mktemp -d -t froster.XXX) && cd "$tmpdir"

# Install pipx
install_pipx

# Install froster
install_froster

# Install pwalk
install_pwalk

# Install rclone
install_rclone

# back to PWD 
cd $curdir

# Get the installed froster version
version=$(froster -v | awk '{print $2}')

# Print success message
echo -e "\n\nSUCCESS!"

echo -e "\nFroster version: $version"
echo -e "Installation path: $(which froster)"

# Print post-installation instructions
echo -e "\n\nYou will need to open a new terminal or refresh your current terminal session by running command:"
echo -e "  source ~/.bashrc\n"