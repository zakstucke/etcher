#!/bin/bash

# Stop on error:
set -e

update () {
    copier update --trust --a .copier-projects-answers.yml $@
}

# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
