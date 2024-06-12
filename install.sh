#! /bin/bash

# Make sure script ends as soon as an error arises
set -e

#################
### VARIABLES ###
#################

date_YYYYMMDDHHMMSS=$(date +%Y%m%d%H%M%S) # Get the current date in YYYYMMDD format

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}

#####################
### ERROR HANDLER ###
#####################

# Define error handler function
trap 'catch $? $BASH_COMMAND' EXIT

catch() {
    if [ "$1" != "0" ]; then
        # error handling goes here
        echo "Error: $2: exit code $1"

        echo
        echo "Rolling back installation..."

        if pipx list >/dev/null 2>&1 | grep 'froster'; then
            pipx uninstall froster >/dev/null 2>&1
        fi

        # Restore (if any) backed up froster config files
        if [[ -d ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak ]]; then
            mv -f ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak ${XDG_CONFIG_HOME}/froster >/dev/null 2>&1
        fi

        # Restore (if any) backed up froster data files
        if [[ -d ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak ]]; then
            mv -f ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak ${XDG_DATA_HOME}/froster >/dev/null 2>&1
        fi

        rm -rf ${pwalk_path} >/dev/null 2>&1
        rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1
        echo "...done"

        echo
        echo "Installation failed!"
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
check_apt_dependencies() {

    # Check if curl is installed
    if [[ -z $(command -v curl) ]]; then
        echo "Error: curl is not installed."
        echo
        echo "In most linux distros you can install the latest version of curl by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y curl"
        echo
        exit 1
    fi

    # Check if pipx is installed
    if [[ -z $(command -v pipx) ]]; then
        echo "Error: pipx is not installed."
        echo
        echo "Please install pipx"
        echo "In most linux distros you can install the latest version of pipx by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y pipx"
        echo "  pipx ensurepath"
        echo
        exit 1
    fi

    # Check if gcc is installed
    if [[ -z $(command -v gcc) ]]; then
        echo "Error: gcc is not installed."
        echo
        echo "Please install gcc"
        echo "In most linux distros you can install the latest version of gcc by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y gcc"
        echo
        exit 1
    fi

    # Check if lib32gcc-s1 is installed (pwalk compilation requirement)
    if [[ $(dpkg -l lib32gcc-s1 >/dev/null 2>&1) ]]; then
        echo "Error: lib32gcc-s1 is not installed."
        echo
        echo "Please install lib32gcc-s1"
        echo "In most linux distros you can install the latest version of lib32gcc-s1 by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y lib32gcc-s1"
        echo
        exit 1
    fi

    # Check if unzip is installed (rclone requirement)
    if [[ -z $(command -v unzip) ]]; then
        echo "Error: unzip is not installed."
        echo
        echo "Please install unzip"
        echo "In most linux distros you can install the latest version of unzip by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y unzip"
        echo
        exit 1
    fi

    # Check if fuse3 is installed
    if [[ -z $(command -v fusermount3) ]]; then
        echo "Error: fusermount3 is not installed."
        echo
        echo "Please install fuse3"
        echo "In most linux distros you can install the latest version of fuse3 by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y fuse3"
        echo
        exit 1
    fi

}

# Backup older installations (if any) but keep the froster-archive.json and config.ini files
backup_old_installation() {

    echo
    echo "Backing up older froster installation (if any)..."

    # Back up (if any) older froster data files
    if [[ -d ${XDG_DATA_HOME}/froster ]]; then

        # Copy the froster directory to froster_YYYYMMDD.bak
        cp -rf ${XDG_DATA_HOME}/froster ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak

        echo "    Data back up at ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak"
    fi

    # Back up (if any) older froster configurations
    if [[ -d ${XDG_CONFIG_HOME}/froster ]]; then

        # Move the froster config directory to froster.bak
        cp -rf ${XDG_CONFIG_HOME}/froster ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak

        echo "    Config back up at ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak"
    fi

    echo "...older froster installation backed up"

    # Check if froster is already installed, if so uninstall it
    if which froster >/dev/null 2>&1; then
        echo
        echo "Uninstalling existing froster installation..."

        if pip list | grep froster >/dev/null 2>&1; then
            pip uninstall froster >/dev/null 2>&1 &
            spinner $!
        fi

        if pipx list | grep froster >/dev/null 2>&1; then
            # If froster is installed with pipx, uninstall it and ignore errors
            # sometime pipx uninstall fails with error code 1 if PIPX_HOME is set, but froster is still uninstalled
            pipx uninstall froster >/dev/null 2>&1 &
            spinner $!
        fi

        echo "...froster uninstalled"
    fi

    # Keep the froster-archives.json file (if any)
    if [[ -f ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/froster-archives.json ]]; then
        # Create the froster directory if it does not exist
        mkdir -p ${XDG_DATA_HOME}/froster

        # Copy the froster-archives.json file to the data directory
        cp -f ${XDG_DATA_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/froster-archives.json ${XDG_DATA_HOME}/froster/froster-archives.json
    fi

    # Remove old files
    rm -rf ${XDG_DATA_HOME}/froster
    rm -rf ${XDG_CONFIG_HOME}/froster
    rm -f ${HOME}/.local/bin/froster
    rm -f ${HOME}/.local/bin/froster.py
    rm -f ${HOME}/.local/bin/s3-restore.py
}

install_froster() {

    # Ensure  ~/.local/bin is in the PATH
    pipx ensurepath >/dev/null 2>&1

    echo
    echo "Installing latest version of froster..."

    if [ "$LOCAL_INSTALL" = "true" ]; then
        echo "  Installing from the current directory"
        pip install . >/dev/null 2>&1 &
        spinner $!
    else
        echo "  Installing from PyPi package repository"
        pipx install froster >/dev/null 2>&1 &
        spinner $!
    fi

    # Keep the config.ini file (if any)
    if [[ -f ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/config.ini ]]; then
        # Create the froster directory if it does not exist
        mkdir -p ${XDG_CONFIG_HOME}/froster

        # Copy the config file to the data directory
        cp -f ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/config.ini ${XDG_CONFIG_HOME}/froster/config.ini
    fi

    # Keep the froster-archives.json file (if any)
    if [[ -f ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/froster-archives.json ]]; then
        # Create the froster directory if it does not exist
        mkdir -p ${XDG_DATA_HOME}/froster

        # Copy the froster-archives.json file to the data directory
        cp -f ${XDG_CONFIG_HOME}/froster_${date_YYYYMMDDHHMMSS}.bak/froster-archives.json ${XDG_DATA_HOME}/froster/froster-archives.json
    fi

    echo "...froster installed"
}

get_froster_dir() {
    local froster_dir

    if [ -f "${XDG_DATA_HOME}/pipx/venvs/froster/bin/froster" ]; then
        froster_dir=$(dirname "$(readlink -f "${XDG_DATA_HOME}/pipx/venvs/froster/bin/froster")")

    elif [ -f "${HOME}/.local/pipx/venvs/froster/bin/froster" ]; then
        froster_dir=$(dirname "$(readlink -f "${HOME}/.local/pipx/venvs/froster/bin/froster")")

    elif [ -f "${PIPX_HOME}/venvs/froster/bin/froster" ]; then
        froster_dir=$(dirname "$(readlink -f "${PIPX_HOME}/venvs/froster/bin/froster")")

    elif [ -f "${HOME}/.local/bin/froster" ]; then
        froster_dir=$(dirname "$(readlink -f "${HOME}/.local/bin/froster")")

    elif [ -f "/usr/local/bin/froster" ]; then
        froster_dir=$(dirname "$(readlink -f "/usr/local/bin/froster")")
    else
        froster_path=$(which froster)

        if [ -n "$froster_path" ]; then
            froster_dir=$(dirname "$(readlink -f "$froster_path")")
        else
            echo "Error: pipx installation path not found."
            exit 1
        fi
    fi

    echo "$froster_dir"
}

install_pwalk() {

    echo
    echo "Installing third-party dependency: pwalk... "

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

    # Move pwalk to froster's binaries folder
    echo "    Moving pwalk to froster's binaries folder"
    froster_dir=$(get_froster_dir)
    mv ${pwalk_path}/pwalk ${froster_dir}/pwalk >/dev/null 2>&1

    # Delete downloaded pwalk files
    echo "    Cleaning up pwalk installation files"
    rm -rf ${pwalk_path} >/dev/null 2>&1

    echo "...pwalk installed"
}

# Install rclone
install_rclone() {

    echo
    echo "Installing third-party dependency: rclone... "

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

    # Move rclone to froster's binaries folder
    echo "    Moving rclone to froster's binaries folder"
    froster_dir=$(get_froster_dir)
    mv rclone-v*/rclone ${froster_dir}/rclone >/dev/null 2>&1

    # Remove the downloaded zip file
    echo "    Cleaning up rclone installation files"
    rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1

    echo "...rclone installed"
}

############
### CODE ###
############

# Check linux package dependencies
check_apt_dependencies

# Set rw permissions on anyone in file's group
umask 0002

# Backup old installation (if any)
backup_old_installation

# Install froster
install_froster

# Install pwalk
install_pwalk

# Install rclone
install_rclone

# Get the installed froster version
froster_dir=$(get_froster_dir)
version=$(${froster_dir}/froster -v | awk '{print $2}')

# Print success message
echo
echo "froster $version has been successfully installed!"

# Print post-installation instructions
echo
echo "You will need to open a new terminal or refresh your current terminal session by running command:"
echo "  source ~/.bashrc"
echo
