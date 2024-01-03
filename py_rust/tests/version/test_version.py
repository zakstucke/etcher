import etcher as etch
import pytest

from ..helpers import cli


@pytest.mark.parametrize(
    "args",
    [
        # Make sure all supported versions act the same:
        ["--version"],
        ["-V"],
        ["version"],
    ],
)
def test_cli_version(args: list[str]):
    """Confirm the etch version command works correctly."""
    res = cli.run(["etch", *args])
    assert res.startswith("etch {}".format(etch.__version__)), res
    # Should be including the path to the executable in brackets at the end:
    assert res.endswith("etch)"), res
