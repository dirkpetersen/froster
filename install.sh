#! /bin/bash

PMINOR="8" #Python3 minor version = 3.8)

echo ""
echo "Installing Froster, please wait ..."
if [[ -n ${LMOD_ROOT} ]]; then 
  ml python
fi
P3=$(which python3)
if [[ -z ${P3} ]]; then
  echo "python3 could not be found."
  exit
fi
V=$(${P3} -c 'import sys; print(sys.version[:4])')
MINOR=$(echo "$V" | cut -d'.' -f2)
if [[ ${MINOR} -lt ${PMINOR} ]]; then
  echo "Python >= 3.${PMINOR} required and your default ${P3} is version ${V}"
  exit
fi 

mkdir -p ~/.local/share/froster
mkdir -p ~/.local/bin
export VIRTUAL_ENV_DISABLE_PROMPT=1
python3 -m venv ~/.local/share/froster
source ~/.local/share/froster/bin/activate

curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ~/.local/share/froster/requirements.txt \
      && python3 -m pip install -r ~/.local/share/froster/requirements.txt

curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster.py \
        -o ~/.local/bin/froster.py

curl -Ls https://raw.githubusercontent.com/dirkpetersen/froster/main/froster \
        -o ~/.local/bin/froster

chmod +x ~/.local/bin/froster
ln -s ~/.local/bin/froster ~/bin/froster

echo ""
echo "Froster installed!. Run 'froster --help'"
