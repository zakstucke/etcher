import json
import re
import typing as tp
from pathlib import Path

import etcher as etch
import pytest
from etcher._process import _DEFAULT_TEMPLATE_MATCHER, _get_lockfile_path

from .tmp_file_manager import TmpFileManager


def test_single_inplace():
    with TmpFileManager() as manager:
        _check_single(manager, "Hello, {{ var }}!", "Hello, World!", {"var": "World"})


@pytest.mark.parametrize(
    "flag,should_hit",
    [
        ("!etch:child ", True),  # Simple space
        ("  \n\n   !etch:child\n\n    ", True),  # Whitespace before and after should all be fine
        (
            # Real content before shouldn't match, preventing the need for escaping when using in e.g. docs.
            "sdfsdfsd !etch:child",
            False,
        ),
    ],
)
def test_single_child(flag: str, should_hit: bool):
    with TmpFileManager() as manager:
        src = "Hello, {{ var }}!"
        # No suffix needed when being used with a child:
        template = manager.tmpfile(content=src)
        contents = f"{flag}{str(template)}"
        context = {"var": "World"}
        if should_hit:
            _check_single(manager, contents, "Hello, World!", context)
        else:
            assert etch.process(manager.root_dir, context, writer=manager.writer)["written"] == []


def test_direct_file():
    """Should raise error when direct file passed."""
    with TmpFileManager() as manager:
        template = manager.tmpfile(content="Hello, {{ var }}!", suffix=".etch.txt")
        with pytest.raises(ValueError, match="Please specify a directory to search instead"):
            etch.process(template, {"var": "World"}, writer=manager.writer)


def test_custom_matchers():
    """Confirm custom name matcher and child matcher works."""
    with TmpFileManager() as manager:
        extra_config: "dict[str, tp.Any]" = {
            "template_matcher": re.compile(r"ROOT"),
            "child_flag": "!IAMCHILD",
        }

        # In-place:
        _check_single(
            manager,
            "Hello, {{ var }}!",
            "Hello, World!",
            {"var": "World"},
            extra_config=extra_config,
            filename_matcher=re.compile("ROOT"),
        )

    with TmpFileManager() as manager:
        # Child:
        src = "Hello, {{ var }}!"
        # No suffix needed when being used with a child:
        template = manager.tmpfile(content=src)
        _check_single(
            manager,
            f"!IAMCHILD {str(template)}",
            "Hello, World!",
            {"var": "World"},
            extra_config=extra_config,
            filename_matcher=re.compile("ROOT"),
        )


def test_custom_jinja_config():
    """Confirm jinja customisation works."""
    with TmpFileManager() as manager:
        extra_config: "dict[str, dict[str, str]]" = {
            "jinja": {
                "variable_start_string": "[[",
                "variable_end_string": "]]",
            },
        }

        # In-place:
        _check_single(
            manager,
            "Hello, [[ var ]]!",
            "Hello, World!",
            {"var": "World"},
            extra_config=extra_config,
        )

    with TmpFileManager() as manager:
        # Child:
        src = "Hello, [[ var ]]!"
        # No suffix needed when being used with a child:
        template = manager.tmpfile(content=src)
        _check_single(
            manager,
            f"!etch:child {str(template)}",
            "Hello, World!",
            {"var": "World"},
            extra_config=extra_config,
        )


def test_missing_src_template():
    """Nice error when child is pointing to an invalid template."""
    with TmpFileManager() as manager:
        manager.tmpfile(content="!etch:child madeup.txt", suffix=".etch.txt")
        with pytest.raises(FileNotFoundError, match="Could not find source template at"):
            etch.process(
                manager.root_dir,
                {"var": "World"},
                writer=manager.writer,
            )


def test_multiple_mixed_templates():
    """Check multiple templates in the search directory are handled."""
    with TmpFileManager() as manager:
        src1 = "Hello, {{ var }}!"
        src2 = "Goodbye, {{ var }}!"
        template_1 = manager.tmpfile(content=src1, suffix=".etch.txt")
        template_2 = manager.tmpfile(content=src2)  # This one used as a child
        child = manager.tmpfile(content=f"!etch:child {str(template_2)}", suffix=".etch.txt")

        assert (
            len(
                etch.process(
                    manager.root_dir,
                    {"var": "World"},
                    writer=manager.writer,
                )["written"]
            )
            == 2
        )

        assert (
            manager.files_created == 5
        )  # 2 compiled, both templates and the child placeholder original

        with open(_remove_template(template_1), "r") as file:
            assert file.read() == "Hello, World!"

        with open(_remove_template(child), "r") as file:
            assert file.read() == "Goodbye, World!"


def test_gitignore():
    """Check gitignore is respected when not disabled."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"
        template = manager.tmpfile(content=contents, suffix=".etch.txt")

        gitignore = manager.tmpfile(content=str(template.name))

        # Gitignore enabled, shouldn't match:
        assert (
            etch.process(
                manager.root_dir,
                {"var": "World"},
                ignore_files=[gitignore],
                writer=manager.writer,
            )["written"]
            == []
        )

        # Gitignore disabled, should match:
        assert etch.process(
            manager.root_dir,
            {"var": "World"},
            writer=manager.writer,
        )["written"] == [_remove_template(template)]

        assert (
            manager.files_created == 3
        ), "Should have created the template, the gitignore, and one compiled file when gitignore disabled."

        # Should raise custom error when path to gitignore wrong:
        with pytest.raises(FileNotFoundError, match="Could not find git-style ignore file at"):
            etch.process(
                manager.root_dir,
                {"var": "World"},
                ignore_files=["madeup"],
                writer=manager.writer,
            )


def test_unrecognised_root():
    """Check an unrecognized root raises."""
    # Check dir:
    with pytest.raises(FileNotFoundError):
        etch.process(
            "./madeup/",
            {"var": "World"},
        )

    # Check file:
    with pytest.raises(FileNotFoundError):
        etch.process(
            "./madeup.txt",
            {"var": "World"},
        )


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
        result = etch.process(manager.root_dir, {"var": var1}, writer=manager.writer)
        assert result["written"] == [_remove_template(template)]
        out_file = Path(result["written"][0])

        # Simulate some formatting outside of etch, shouldn't affect the results:
        with open(out_file, "w") as file:
            file.write(f"Hello, \n\n{var1}!")

        num_writes = manager.files_created
        last_update = Path(result["written"][0]).stat().st_mtime

        # Second run:
        result = etch.process(manager.root_dir, {"var": var2}, writer=manager.writer, force=force)
        if should_write:
            assert result["written"] == [_remove_template(template)]
            assert manager.files_created == num_writes + 1
            assert out_file.stat().st_mtime > last_update
        else:
            assert result["written"] == []
            assert manager.files_created == num_writes
            assert out_file.stat().st_mtime == last_update


@pytest.mark.parametrize(
    "lock_contents,",
    [
        "avjsfhds",  # Not valid json
        "[]",  # valid, but not a dict as expected
    ],
)
def test_corrupt_lockfile(lock_contents: str):
    """Automatic resetting of the lockfile isn't valid json, or its contents are in the wrong format."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"

        template = manager.tmpfile(content=contents, suffix=".etch.txt")

        # Corrupt the lockfile:
        lockfile_path = _get_lockfile_path(manager.root_dir)
        with open(lockfile_path, "w") as file:
            file.write(lock_contents)

        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert result["written"] == [_remove_template(template)]
        assert manager.files_created == 2

        # Should have managed to recreate the lockfile:
        with open(lockfile_path, "r") as file:
            assert json.load(file) == {
                # Should be a relative path:
                str(template.relative_to(manager.root_dir)): "Hello, World!",
            }

        # If the template is deleted and etch is run again, it should be removed from the lockfile:
        template.unlink()
        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert result["written"] == []

        with open(lockfile_path, "r") as file:
            assert json.load(file) == {}


def test_lockfile_only_write_when_needed():
    """Confirm the lockfile isn't re-written when nothing's changed. This would break pre-commit."""
    with TmpFileManager() as manager:
        contents1 = "Hello, {{ var }}!"
        contents2 = "Goodbye, {{ var }}!"
        template1 = manager.tmpfile(content=contents1, suffix=".etch.txt")
        template2 = manager.tmpfile(content=contents2, suffix=".etch.txt")

        # First run should create rendered files and lockfile:
        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert set(result["written"]) == set(
            [_remove_template(template1), _remove_template(template2)]
        )
        assert manager.files_created == 4

        lock_stat = Path(_get_lockfile_path(manager.root_dir)).stat()

        # Second run should change nothing the lockfile should be the same as well.
        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert result["written"] == []
        assert manager.files_created == 4

        # Lockfile edit time shouldn't have changed:
        assert Path(_get_lockfile_path(manager.root_dir)).stat().st_mtime == lock_stat.st_mtime

        # Modify one of the templates and delete the other, check lockfile is updated:
        with open(template1, "w") as file:
            file.write("Updated, {{ var }}!")
        template2.unlink()
        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert result["written"] == [_remove_template(template1)]
        assert manager.files_created == 5
        with open(_get_lockfile_path(manager.root_dir), "r") as file:
            assert json.load(file) == {
                str(template1.relative_to(manager.root_dir)): "Updated, World!",
            }


def test_two_existing_children_same_root():
    """Check a bug where the second child wouldn't update as the lockfile had been updated at that point if the files existed beforehand."""
    with TmpFileManager() as manager:
        template = manager.tmpfile(content="Hello, {{ var }}!")
        child_1 = manager.tmpfile(content=f"!etch:child {template}", suffix=".etch.txt")
        child_2 = manager.tmpfile(content=f"!etch:child {template}", suffix=".etch.txt")

        # Run first time with a var, so both children are written:
        result = etch.process(manager.root_dir, {"var": "World"}, writer=manager.writer)
        assert set(result["written"]) == set([_remove_template(child_1), _remove_template(child_2)])

        # Make sure they both update now the var has changed:
        result = etch.process(manager.root_dir, {"var": "Goodbye"}, writer=manager.writer)
        assert set(result["written"]) == set([_remove_template(child_1), _remove_template(child_2)])
        with open(_remove_template(child_1), "r") as file:
            assert file.read() == "Hello, Goodbye!"
        with open(_remove_template(child_2), "r") as file:
            assert file.read() == "Hello, Goodbye!"


def _check_single(
    manager: TmpFileManager,
    contents: str,
    expected: str,
    context: "dict[str, tp.Any]",
    filename_matcher: "re.Pattern[str]" = _DEFAULT_TEMPLATE_MATCHER,
    extra_config: "tp.Optional[dict[str, tp.Any]]" = None,
):
    template = manager.tmpfile(content=contents, suffix=f".{filename_matcher}.txt")

    before_files = manager.files_created
    result = etch.process(
        manager.root_dir,
        context,
        writer=manager.writer,
        **(extra_config if extra_config is not None else {}),
    )

    # Should return the correct compiled file:
    assert result["written"] == [_remove_template(template, filename_matcher)]
    assert result["identical"] == []

    # Original shouldn't have changed:
    with open(template, "r") as file:
        assert contents == file.read()

    # Compiled should match expected:
    with open(result["written"][0], "r") as file:
        assert file.read() == expected

    # Should only have created one file:
    files_created = manager.files_created - before_files
    assert files_created == 1


def _remove_template(
    filepath: Path, filename_matcher: "re.Pattern[str]" = _DEFAULT_TEMPLATE_MATCHER
) -> Path:
    match = filename_matcher.search(filepath.name)
    assert match is not None
    return filepath.with_name(filepath.name.replace(match.group(0), ""))
