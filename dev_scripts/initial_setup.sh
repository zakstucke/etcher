#!/bin/bash

# Stop on error:
set -e

initial_setup () {

    # Make sure the prettier subdir package is all installed:
    cd ./prettier
    npm install
    cd ..

    # Install pre-commit if not already:
    pipx install pre-commit || true
    pre-commit install

    echo "Setting up docs..."
    cd docs
    # PDM_IGNORE_ACTIVE_VENV just in case running from inside a venv, don't want to use it:
    PDM_IGNORE_ACTIVE_VENV=True pdm install
    cd ..

    echo "Setting up python..."
    cd py
    pdm install -G:all
    cd ..


}

# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
