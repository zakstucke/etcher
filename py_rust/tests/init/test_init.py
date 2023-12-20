import os

import pytest

from ..helpers import cli
from ..helpers.tmp_file_manager import TmpFileManager


def test_cli_init():
    """Confirm the etch init command works correctly.

    - Produces a valid file that can be used straight away.
    - Errs if default config already exists.
    - Includes .gitignore in ignore_files only if exists.
    """
    for use_gitignore in [True, False]:
        with TmpFileManager() as manager:
            if use_gitignore:
                manager.tmpfile("", full_name=".gitignore")

            cli.init(manager.root_dir)

            # Should have been created:
            config_path = os.path.join(manager.root_dir, "etch.config.toml")
            assert os.path.exists(config_path)

            with open(config_path, "r") as file:
                contents = file.read()
                if use_gitignore:
                    assert 'ignore_files = [".gitignore"]' in contents
                else:
                    assert (
                        "ignore_files = [] # Couldn't find a .gitignore, not adding by default. Recommended if available."
                        in contents
                    )

            # The variables in the example conf loaded:
            manager.tmpfile("{{ FOO }} {{ BAR }} {{ BAZ }}", full_name="ree.etch.txt")

            # Should run successfully:
            cli.render(manager.root_dir)

            # Should have been created:
            assert os.path.exists(os.path.join(manager.root_dir, "ree.txt"))
            with open(os.path.join(manager.root_dir, "ree.txt"), "r") as file:
                assert file.read() == "foo bar 1"

            # Should err second time as already exists:
            with pytest.raises(
                ValueError,
                match="Config file already exists at the default location: './etch.config.toml'.",
            ):
                cli.init(manager.root_dir)
