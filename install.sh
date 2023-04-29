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
  if [[ -n ${LMOD_ROOT} ]]; then
    printf "Lmod detected, trying to load the default Lmod Python ... "
    ml python > /dev/null 2>&1
    ml Python > /dev/null 2>&1
    echo "Done!"
    if [[ $(python3 -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
      printf "The default Lmod Python is older than 3.${PMIN}. Trying Python/3.${PMIN} ... "
      ml python/3.${PMIN} > /dev/null 2>&1
      ml Python/3.${PMIN} > /dev/null 2>&1
      echo "Done!"
      if [[ $(python3 -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
        echo "Failed to load Python 3.${PMIN}. Please load a Python module >= 3.${PMIN} manually."
        exit
      fi
    fi
  else
    echo "please load a diffent Python >= 3.${PMIN} and try again"
    if [[ -n ${SPACK_ROOT} ]]; then
      printf "Spack detected, you can also run 'spack load python'"
    fi
    exit
  fi
fi
### Installing froster in a Virtual Envionment. 
printf "Installing virtual environment ~/.local/share/froster ... "
if [[ -d ~/.local/share/froster ]]; then
  rm -rf ~/.local/share/froster.bak
  echo "Renaming existing froster install to ~/.local/share/froster.bak "
  mv ~/.local/share/froster ~/.local/share/froster.bak
fi
mkdir -p ~/.local/share/froster
mkdir -p ~/.local/bin
export VIRTUAL_ENV_DISABLE_PROMPT=1
python3 -m venv ~/.local/share/froster
source ~/.local/share/froster/bin/activate
echo "Done!"
printf "Installing packages ... "
curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ~/.local/share/froster/requirements.txt \
      && python3 -m pip --disable-pip-version-check \
         install --upgrade -r ~/.local/share/froster/requirements.txt
Echo "Done!"

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
echo -e "\n\n\nFroster installed! Run one the these commands:"
echo "froster --help"
echo "froster index /your/folder"
echo "froster archive"

