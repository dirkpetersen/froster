#! /bin/bash

PMIN="8" #Python3 minor version = 3.8)

echo ""
echo "Installing Froster, please wait ..."
P3=$(which python3)
if [[ -z ${P3} ]]; then
  echo "python3 could not be found, please install first"
  exit
fi
if [[ $(${P3} -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
  echo "Python >= 3.${PMIN} required and your default ${P3} is too old."
  if [[ -n ${LMOD_ROOT} ]]; then
    echo "LMOD detected, trying to load Python..."
    ml python > /dev/null 2>&1
    ml Python/3.8 > /dev/null 2>&1
    if [[ $(python3 -c "import sys; print(sys.version_info >= (3,${PMIN}))") == "False" ]]; then
      echo "Python >= 3.${PMIN} required but the active python3 is too old."
      exit
    fi 
    printf "Done!"
  else
    echo "please load a diffent Python >= 3.${PMIN} and try again"
    exit
  fi
fi
echo "Install virtual environment ~/.local/share/froster ... "
rm -rf ~/.local/share/froster.bak
mv ~/.local/share/froster ~/.local/share/froster.bak
mkdir -p ~/.local/share/froster
mkdir -p ~/.local/bin
export VIRTUAL_ENV_DISABLE_PROMPT=1
python3 -m venv ~/.local/share/froster
source ~/.local/share/froster/bin/activate
printf "Done!"
echo "Installing packages ... "
curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ~/.local/share/froster/requirements.txt \
      && python3 -m pip install --upgrade -r ~/.local/share/froster/requirements.txt
printf "Done!"

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

echo ""
echo "Froster installed! Run 'froster --help'"

