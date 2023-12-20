#!/bin/bash

# Stop on error:
set -e

all () {
    echo "QA..."
    ./dev_scripts/test.sh qa



    echo "Python Rust..."
    ./dev_scripts/test.sh py_rust


    echo "Docs..."
    ./dev_scripts/test.sh docs
}

pre_till_success () {
    # Run pre-commit on all files repetitively until success, but break if not done in 5 gos
    index=0
    success=false

    # Trap interrupts and exit instead of continuing the loop
    trap "echo Exited!; exit;" SIGINT SIGTERM

    while [ $index -lt 5 ]; do
        index=$((index+1))
        echo "pre-commit attempt $index"
        if pre-commit run --all-files; then
            success=true
            break
        fi
    done

    if [ "$success" = true ]; then
        echo "pre-commit succeeded"
    else
        echo "pre-commit failed 5 times, something's wrong. Exiting"
        exit 1
    fi
}

# Runs pre-commit and all the static analysis stat_* functions:
qa () {
    pre_till_success


}



py_rust () {
    # Build the package up to date in the specific virtualenv:
    ./dev_scripts/py_rust.sh install py_rust/.venv

    cd py_rust

    # Activate the target venv: (runs from windows in CI too)
    if [[ "$OSTYPE" == "msys" ]]; then
        source .venv/Scripts/activate
    else
        source .venv/bin/activate
    fi

    cd .. # This type of stuff could be fixed with hellscript
    ./dev_scripts/utils.sh py_install_if_missing pytest
    cd py_rust

    cargo test
    python -m pytest $@

    deactivate
    cd ..
}


docs () {
    DOCS_PASS=passwordpassword ./dev_scripts/docs.sh build
}

# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
