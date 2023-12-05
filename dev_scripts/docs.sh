#!/bin/bash
set -e # Exit on error



build () {




    # Build the docs locally:
    pdm run -p ./docs mkdocs build
}

serve () {



    # Use port 8080 as 8000 & 3000 are commonly used by other dev processes
    # When any of these files/folders change, rebuild the docs:
    DOCS_PASS=passwordpassword pdm run -p ./docs mkdocs serve --dev-addr localhost:8080 -w ./docs \
        -w ./py_rust \
        -w ./CODE_OF_CONDUCT.md -w ./README.md -w ./CONTRIBUTING.md -w ./LICENSE.md -w ./mkdocs.yml -w ./docs/python_autodoc.py
}

# Has to come at the end of these files:
source ./dev_scripts/_scr_setup/setup.sh "$@"
