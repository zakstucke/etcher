import typing as tp
from pathlib import Path

import etcher as etch
import pytest

from .tmp_file_manager import TmpFileManager


def test_single_inplace():
    with TmpFileManager() as manager:
        _check_single(manager, "Hello, {{ var }}!", "Hello, World!", {"var": "World"})


@pytest.mark.parametrize(
    "flag,",
    [
        "!etch:child ",  # Simple space
        "     !etch:child\n\n    ",  # Newlines etc
    ],
)
def test_single_child(flag: str):
    with TmpFileManager() as manager:
        src = "Hello, {{ var }}!"
        # No suffix needed when being used with a child:
        template = manager.tmpfile(content=src)
        _check_single(manager, f"{flag} {str(template)}", "Hello, World!", {"var": "World"})


def test_direct_file():
    """Should work when a template/child is passed directly."""
    with TmpFileManager() as manager:
        # In-place:
        _check_single(
            manager, "Hello, {{ var }}!", "Hello, World!", {"var": "World"}, template_direct=True
        )

        # Child:
        src = "Hello, {{ var }}!"
        # No suffix needed when being used with a child:
        template = manager.tmpfile(content=src)
        _check_single(
            manager,
            f"!etch:child {str(template)}",
            "Hello, World!",
            {"var": "World"},
            template_direct=True,
        )


def test_custom_matchers():
    """Confirm custom name matcher and child matcher works."""
    with TmpFileManager() as manager:
        extra_config: "dict[str, str]" = {
            "template_matcher": "ROOT",
            "child_flag": "!IAMCHILD",
        }

        # In-place:
        _check_single(
            manager,
            "Hello, {{ var }}!",
            "Hello, World!",
            {"var": "World"},
            extra_config=extra_config,
            filename_matcher="ROOT",
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
            filename_matcher="ROOT",
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
                )
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
        assert [] == etch.process(
            template,
            {"var": "World"},
            ignore_files=[gitignore],
            writer=manager.writer,
        )

        # Gitignore disabled, should match:
        assert [_remove_template(template)] == etch.process(
            template,
            {"var": "World"},
            writer=manager.writer,
        )

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


def test_no_match():
    """Check no match returns empty list."""
    # Dir:
    assert (
        etch.process(
            "./tests/",
            {"var": "World"},
        )
        == []
    )

    # File:
    assert (
        etch.process(
            "./tests/test_process.py",
            {"var": "World"},
        )
        == []
    )


def _check_single(
    manager: TmpFileManager,
    contents: str,
    expected: str,
    context: "dict[str, tp.Any]",
    filename_matcher: str = "etch",
    template_direct: bool = False,
    extra_config: "tp.Optional[dict[str, tp.Any]]" = None,
):
    template = manager.tmpfile(content=contents, suffix=f".{filename_matcher}.txt")

    before_files = manager.files_created
    result = etch.process(
        manager.root_dir if not template_direct else template,
        context,
        writer=manager.writer,
        **(extra_config if extra_config is not None else {}),
    )

    # Should return the correct compiled file:
    assert result == [_remove_template(template, filename_matcher)]

    # Original shouldn't have changed:
    with open(template, "r") as file:
        assert contents == file.read()

    # Compiled should match expected:
    with open(result[0], "r") as file:
        assert file.read() == expected

    # Should only have created one file:
    files_created = manager.files_created - before_files
    assert files_created == 1


def _remove_template(filepath: Path, filename_matcher: str = "etch") -> Path:
    return Path(str(filepath).replace(f".{filename_matcher}.", "."))
