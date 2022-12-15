#!/bin/bash

# colors
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# if .env exists, exit
if [ -d ".env" ]; then
  echo -e "${RED}Error: .env already exists. For reinstallation, please delete .env and run this script again.${NC}" >&2
  exit 1
fi

# check if python3 is installed
if ! [ -x "$(command -v python3)" ]; then
  echo -e "${RED}Error: python3 is not installed.${NC}" >&2
  exit 1
fi

# check if pip3 is installed
if ! [ -x "$(command -v pip3)" ]; then
  echo -e "${RED}Error: pip3 is not installed.${NC}" >&2
  exit 1
fi

# create virtual environment
echo -e "${CYAN}Creating virtual environment at .env${NC}"
python3 -m venv .env

# update pip
echo -e "${CYAN}Updating pip${NC}"
.env/bin/pip3 install -U pip -q 

# install requirements
echo -e "${CYAN}Installing requirements${NC}"
.env/bin/pip3 install -r requirements.txt -q

# finish
echo -e "${GREEN}Installation complete. To activate the virtual environment, run 'source .env/bin/activate'.${NC}"
echo -e "${GREEN}To deactivate the virtual environment, run 'deactivate'.${NC}"
echo -e "${GREEN}To run the application, run './run.sh'.${NC}"
