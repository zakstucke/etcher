#!/bin/bash

# Stop on error:
set -e

_ensure_dasel () {
    # Check if dasel is installed:
    if ! command -v dasel &> /dev/null
    then
        echo "dasel could not be found"
        echo "Installing dasel..."

        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install dasel
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # https://daseldocs.tomwright.me/installation#windows
            curl -sSLf "$(curl -sSLf https://api.github.com/repos/tomwright/dasel/releases/latest | grep browser_download_url | grep linux_amd64 | grep -v .gz | cut -d\" -f 4)" -L -o dasel && chmod +x dasel
            mv ./dasel /usr/local/bin/dasel
        else
            echo "Unsupported OS: $OSTYPE"
            exit 1
        fi
    fi
}

# Prints the current python package version
ver_py () {
    # Suppressing stdout (but not err in case something goes wrong) as the echo from this fn is used to determine version in scripts
    _ensure_dasel > /dev/null

    # -w- means string output with no quotes etc, got from https://github.com/TomWright/dasel/issues/339
    echo $(dasel -w=- -f ./python/pyproject.toml ".project.version")
}

# Takes in the version to bump to as only argument
ver_py_update () {
    _ensure_dasel

    dasel put -t=string -v="$1" -f ./python/pyproject.toml ".project.version"

    # Update lockfile:
    pdm update -p ./python --no-sync
}





# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
