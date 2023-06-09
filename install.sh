#! /bin/bash

PMIN="8" # python3 minor version = 3.8)

echo ""
echo "Installing Froster, please wait ..."
### checking for correct Python verion 
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
python3 -m venv ~/.local/share/froster
source ~/.local/share/froster/bin/activate
echo "Done!"
echo "Installing packages required by Froster ... "
curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ~/.local/share/froster/requirements.txt \
      && python3 -m pip --disable-pip-version-check \
         install --upgrade -r ~/.local/share/froster/requirements.txt
echo "Done!"

curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster.py \
        -o ~/.local/bin/froster.py

curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster \
        -o ~/.local/bin/froster

chmod +x ~/.local/bin/froster

DIR_IN_PATH=$(IFS=:; for dir in $PATH; do if [[ $dir == $HOME* ]]; then echo $dir; break; fi; done)

if [[ -d ${DIR_IN_PATH} ]]; then
  if ! [[ -e ${DIR_IN_PATH}/froster ]]; then
    ln -s ~/.local/bin/froster ${DIR_IN_PATH}/froster
  fi
else
  echo "No folders in PATH in your home folder. Please add ~/.local/bin to your PATH and try again."
fi
froster --help
echo -e "\n\n  Froster installed! Run 'froster --help' or this order of commands:\n"
echo "  froster config"
echo "  froster index /your/folder"
echo "  froster archive"

