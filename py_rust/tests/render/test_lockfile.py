import json
from pathlib import Path

import etcher as etch
import pytest

from ..helpers import cli
from ..helpers.tmp_file_manager import TmpFileManager
from ..helpers.utils import get_lockfile_path, remove_template


@pytest.mark.parametrize(
    "var1,var2,should_write,force",
    [
        # No change so shouldn't write:
        ("World", "World", False, False),
        # Change, so should write:
        ("World", "FOO", True, False),
        # Force should always re-write:
        ("World", "World", True, True),
    ],
)
def test_lockfile_caching(var1: str, var2: str, should_write: bool, force: bool):
    """Confirm lockfile functions as it should when valid."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"

        template = manager.tmpfile(content=contents, suffix=".etch.txt")
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": var1}}}}),
        )
        assert result["debug"]["written"] == [remove_template(template)]
        out_file = Path(result["debug"]["written"][0])

        # Simulate some formatting outside of etch, shouldn't affect the results:
        with open(out_file, "w") as file:
            file.write(f"Hello, \n\n{var1}!")

        last_update = Path(result["debug"]["written"][0]).stat().st_mtime

        # Second run:
        result = cli.render(
            manager.root_dir,
            manager.create_cfg(
                {"context": {"static": {"var": {"value": var2}}}},
            ),
            force=force,
        )
        if should_write:
            assert result["debug"]["written"] == [remove_template(template)]
            assert out_file.stat().st_mtime > last_update
        else:
            assert result["debug"]["written"] == []
            assert out_file.stat().st_mtime == last_update


@pytest.mark.parametrize(
    "lock_contents,",
    [
        "avjsfhds",  # Not valid json
        "[]",  # valid, but not a dict as expected
        '{"version": "0.0.0", "files": {}}',  # valid, but wrong version
    ],
)
def test_corrupt_lockfile(lock_contents: str):
    """Automatic resetting of the lockfile isn't valid json, or its contents are in the wrong format."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"

        template = manager.tmpfile(content=contents, suffix=".etch.txt")

        # Corrupt the lockfile:
        lockfile_path = get_lockfile_path(manager.root_dir)
        with open(lockfile_path, "w") as file:
            file.write(lock_contents)

        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert result["debug"]["written"] == [remove_template(template)]

        # Should have managed to recreate the lockfile:
        with open(lockfile_path, "r") as file:
            assert json.load(file) == {
                "version": etch.__version__,  # type: ignore
                "files": {
                    str(template.relative_to(manager.root_dir)): etch._hash_contents(
                        "Hello, World!"
                    ),
                },
            }

        # If the template is deleted and etch is run again, it should be removed from the lockfile:
        template.unlink()
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert result["debug"]["written"] == []

        with open(lockfile_path, "r") as file:
            assert json.load(file) == {
                "version": etch.__version__,  # type: ignore
                "files": {},
            }


def test_lockfile_only_write_when_needed():
    """Confirm the lockfile isn't re-written when nothing's changed. This would break pre-commit."""
    with TmpFileManager() as manager:
        contents1 = "Hello, {{ var }}!"
        contents2 = "Goodbye, {{ var }}!"
        template1 = manager.tmpfile(content=contents1, suffix=".etch.txt")
        template2 = manager.tmpfile(content=contents2, suffix=".etch.txt")

        # First run should create rendered files and lockfile:
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert set(result["debug"]["written"]) == set(
            [remove_template(template1), remove_template(template2)]
        )

        lock_stat = Path(get_lockfile_path(manager.root_dir)).stat()

        # Second run should change nothing the lockfile should be the same as well.
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert result["debug"]["written"] == []

        # Lockfile edit time shouldn't have changed:
        assert Path(get_lockfile_path(manager.root_dir)).stat().st_mtime == lock_stat.st_mtime

        # Modify one of the templates and delete the other, check lockfile is updated:
        with open(template1, "w") as file:
            file.write("Updated, {{ var }}!")
        template2.unlink()
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert result["debug"]["written"] == [remove_template(template1)]
        with open(get_lockfile_path(manager.root_dir), "r") as file:
            assert json.load(file) == {
                "version": etch.__version__,  # type: ignore
                "files": {
                    # Should be relative to the root_dir as that's where the lockfile is stored:
                    str(template1.relative_to(manager.root_dir)): etch._hash_contents(
                        "Updated, World!"
                    ),
                },
            }
