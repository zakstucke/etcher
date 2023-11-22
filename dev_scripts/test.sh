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

# Runs pre-commit and all the static analysis stat_* functions:
qa () {
    # Runs the second time in case the first one only failed due to auto fixes:
    pre-commit run --color=always --all-files || pre-commit run --color=always --all-files

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
