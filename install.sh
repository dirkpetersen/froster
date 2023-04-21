#! /bin/bash

PMINOR="8" #Python3 minor version = 3.8)

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
export VIRTUAL_ENV_DISABLE_PROMPT=1
python3 -m venv ~/.local/share/froster
source ~/.local/share/froster/bin/activate
mytemp=$(mktemp -d)
curl -L https://raw.githubusercontent.com/dirkpetersen/froster/main/requirements.txt \
        -o ${mytemp}/requirements.txt \
      && python3 -m pip install -r ${mytemp}/requirements.txt && rm ${mytemp}/requirements.txt

