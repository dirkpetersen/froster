#! /bin/bash

# Make sure script ends as soon as an error arises
set -e

#####################
### ERROR HANDLER ###
#####################

# Define error handler function
set -e

trap 'catch $? $BASH_COMMAND' EXIT

catch() {
    if [ "$1" != "0" ]; then
        # error handling goes here
        echo "Error: $2: exit code $1"
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

    # Check if git is installed (pipx installation requirement)
    # TODO: Get rid of this requirement once froster is in PyPi repository
    if [[ -z $(command -v git) ]]; then
        echo "Error: git is not installed."
        echo
        echo "Please install git"
        echo "In most linux distros you can install the latest version of git by running the following commands:"
        echo "  sudo apt update"
        echo "  sudo apt install -y git"
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
}

# Backup older installations (if any)
backup_old_installation() {

    echo
    echo "Backing up older froster installation (if any)..."

    # Back up (if any) older froster data files
    if [[ -d ${HOME}/.local/share/froster ]]; then
        mv -f ${HOME}/.local/share/froster ${HOME}/.local/share/froster.bak
        echo "Data back up at ${HOME}/.local/share/froster.bak"
    fi

    # Back up (if any) older froster configurations
    if [[ -d ${HOME}/.config/froster ]]; then
        mv -f ${HOME}/.config/froster ${HOME}/.config/froster.bak
        echo "Config back up at ${HOME}/.config/froster.bak"
    fi

    # Remove old files
    rm -f ${HOME}/.local/bin/froster
    rm -f ${HOME}/.local/bin/froster.py
    rm -f ${HOME}/.local/bin/s3-restore.py

    echo "  ...older froster installation backed up"
}

# Install froster
install_froster() {

    echo
    echo "Installing latest version of froster..."

    pipx ensurepath >/dev/null 2>&1
    # TODO: Update path once froster is in PyPi repository
    pipx install git+https://github.com/HPCNow/froster.git@develop >/dev/null 2>&1

    echo "  ...froster installed"
}

# Install pwalk
install_pwalk() {

    echo
    echo "Installing third-party dependency: pwalk... "

    # Variables of pwalk third-party tool froster is using
    pwalk_commit=1df438e9345487b9c51d1eea3c93611e9198f173 # update this commit when new pwalk version released
    pwalk_repository=https://github.com/fizwit/filesystem-reporting-tools/archive/${pwalk_commit}.tar.gz
    pwalk_path=filesystem-reporting-tools-${pwalk_commit}

    # Gather pwalk repository files
    curl -s -L ${pwalk_repository} | tar xzf - >/dev/null 2>&1

    # Compile pwalk tool and put exec file in froster's binaries folder
    gcc -pthread ${pwalk_path}/pwalk.c ${pwalk_path}/exclude.c ${pwalk_path}/fileProcess.c -o ${pwalk_path}/pwalk >/dev/null 2>&1

    # Move pwalk to froster's binaries folder
    mv ${pwalk_path}/pwalk ${HOME}/.local/pipx/venvs/froster/bin/pwalk >/dev/null 2>&1

    # Delete downloaded pwalk files
    rm -rf ${pwalk_path} >/dev/null 2>&1

    echo "  ...pwalk installed"
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

    # Download the rclone zip file
    curl -LO $rclone_url >/dev/null 2>&1

    # Extract the zip file
    unzip rclone-current-linux-*.zip >/dev/null 2>&1

    # Move rclone to froster's binaries folder
    mv rclone-v*/rclone ${HOME}/.local/pipx/venvs/froster/bin/rclone >/dev/null 2>&1

    # Remove the downloaded zip file
    rm -rf rclone-current-linux-*.zip rclone-v*/ >/dev/null 2>&1

    echo "  ...rclone installed"
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

echo
echo "Installation complete!"

echo
echo "You will need to open a new terminal or refresh your current terminal session using:"
echo "  source ~/.bashrc"
echo
