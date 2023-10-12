#! /bin/bash

PMIN="8" # python3 minor version = 3.8)

froster_update() {
  curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster.py \
        -o ~/.local/bin/froster.py

  curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster \
        -o ~/.local/bin/froster

  chmod +x ~/.local/bin/froster  
}
echo ""
umask 0002
if [[ $1 == "update" ]]; then
  echo -e "  Updating Froster, please wait ...\n"
  froster_update
  froster --version
  echo -e "\n  Froster updated! Run 'froster --help'\n"  
  exit
fi 
echo "Installing Froster, please wait ..."
### checking for correct Python version 
P3=$(which python3)
if [[ -z ${P3} ]]; then
  echo "python3 could not be found, please install Python >= 3.${PMIN} first"
  exit
fi
if [[ $(${P3} -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
  echo "Python >= 3.${PMIN} required and your default ${P3} is too old."
  printf "Trying to load Python through the modules system ... "
  module load python > /dev/null 2>&1
  module load Python > /dev/null 2>&1
  echo "Done!"
  printf "Starting Python from default module ... "
  if [[ $(python3 -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
    echo "Done!"
    printf "The default Python module is older than 3.${PMIN}. Trying Python/3.${PMIN} ... "
    module load python/3.${PMIN} > /dev/null 2>&1
    module load Python/3.${PMIN} > /dev/null 2>&1
    echo "Done!"
    printf "Starting Python 3.${PMIN} from module ... "
    if [[ $(python3 -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
      echo "Failed to load Python 3.${PMIN}. Please load a Python module >= 3.${PMIN} manually."
      exit
    fi
    echo "Done!"
  else 
    echo "Done!"
  fi
fi
### Fixing a potentially broken LD_LIBRARY_PATH
P3=$(which python3)
P3=$(readlink -f ${P3})
unset LIBRARY_PATH PYTHONPATH
export LD_LIBRARY_PATH=${P3%/bin/python3*}/lib:${LD_LIBRARY_PATH}
LD_LIBRARY_PATH=${LD_LIBRARY_PATH%:}
### Installing froster in a Virtual Envionment. 
if [[ -d ~/.local/share/froster ]]; then
  rm -rf ~/.local/share/froster.bak
  echo "Renaming existing froster install to ~/.local/share/froster.bak "
  mv ~/.local/share/froster ~/.local/share/froster.bak
fi
printf "Installing virtual environment ~/.local/share/froster ... "
mkdir -p ~/.local/share/froster
mkdir -p ~/.local/bin
export VIRTUAL_ENV_DISABLE_PROMPT=1
# Check if 'ensurepip' is available, or use old virtualenv
if python3 -c "import ensurepip" &> /dev/null; then
  python3 -m venv ~/.local/share/froster
else
  python3 -m pip install --upgrade virtualenv
  python3 -m virtualenv ~/.local/share/froster
fi
source ~/.local/share/froster/bin/activate
echo "Done!"
echo "Installing packages required by Froster ... "
curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ~/.local/share/froster/requirements.txt \
      && python3 -m pip --disable-pip-version-check \
         install --upgrade -r ~/.local/share/froster/requirements.txt
echo "Done!"

froster_update

~/.local/bin/froster --help
echo -e "\n\n  Froster installed! Run 'froster --help' or this order of commands:\n"
echo "  froster config"
echo "  froster index /your/folder"
echo "  froster archive"
                        
deactivate

# check if there is a folder in PATH inside my home directory 
DIR_IN_PATH=$(IFS=:; for dir in $PATH; do if [[ $dir == $HOME* ]]; then echo $dir; break; fi; done)

if [[ -d ${DIR_IN_PATH} ]]; then
  if ! [[ -e ${DIR_IN_PATH}/froster ]]; then
    ln -s ~/.local/bin/froster ${DIR_IN_PATH}/froster
  fi
else
  # "No folders in your home folder are in PATH, so unfortunately we need to clutter your ~/.bashrc
  HOME=~
  if ! grep -q "export PATH=\$PATH:~/.local/bin" "${HOME}/.bashrc"; then
    # Append the export statement to .bashrc
    echo "export PATH=\$PATH:~/.local/bin" >> "${HOME}/.bashrc"
    echo ""
    echo " ~/.local/bin added to PATH in .bashrc"
    echo " Please logout/login again or run: source ~/.bashrc"
  fi
fi

