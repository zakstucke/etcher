import etcher as etch

from ..helpers import cli


def test_cli_version():
    """Confirm the etch version command works correctly.

    - `etch --version` works
    - `etch version` works
    """
    assert cli.run(["etch", "--version"]) == "etch {}".format(etch.__version__)
    assert cli.run(["etch", "version"]) == "etch {}".format(etch.__version__)
