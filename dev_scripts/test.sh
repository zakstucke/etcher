#!/bin/bash

# Stop on error:
set -e

all () {
    echo "QA..."
    ./dev_scripts/test.sh qa

    echo "Python..."
    ./dev_scripts/test.sh py




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

    ./dev_scripts/test.sh pyright

}

py () {
    cd ./py/
    # Check for COVERAGE=False/false, which is set in some workflow runs to make faster:
    if [[ "$COVERAGE" == "False" ]] || [[ "$COVERAGE" == "false" ]]; then
        echo "COVERAGE=False/false, not running coverage"
        pdm run pytest $@
    else
        pdm run coverage run --parallel -m pytest $@
        pdm run coverage combine
        pdm run coverage report
    fi
    cd ..
}

pyright () {
    cd ./py/
    pdm run pyright .
    cd ..
}




docs () {
    DOCS_PASS=passwordpassword ./dev_scripts/docs.sh build
}

# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
