import typing as tp
from pathlib import Path

import etcher as etch
import pytest

from .tmp_file_manager import TmpFileManager

"""
- Gitignore respected
- Exclude respected
- Real writer
"""


def test_single_inplace():
    with TmpFileManager() as manager:
        _check_single(manager, "Hello, {{ var }}!", "Hello, World!", {"var": "World"})

        # Also should work if direct file is passed:
        _check_single(
            manager, "Hello, {{ var }}!", "Hello, World!", {"var": "World"}, template_direct=True
        )


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


def test_missing_src_template():
    """Nice error when child is pointing to an invalid template."""
    with TmpFileManager() as manager:
        manager.tmpfile(content="!etch:child madeup.txt", suffix=".etch.txt")
        with pytest.raises(FileNotFoundError, match="Could not find source template at"):
            etch.process(
                manager.root_dir,
                {"var": "World"},
                gitignore_path=None,
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
                    gitignore_path=None,
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
            gitignore_path=gitignore,
            writer=manager.writer,
        )

        # Gitignore disabled, should match:
        assert [_remove_template(template)] == etch.process(
            template,
            {"var": "World"},
            gitignore_path=None,
            writer=manager.writer,
        )

        assert (
            manager.files_created == 3
        ), "Should have created the template, the gitignore, and one compiled file when gitignore disabled."

        # Should raise custom error when path to gitignore wrong:
        with pytest.raises(FileNotFoundError, match="Could not find gitignore file at"):
            etch.process(
                manager.root_dir,
                {"var": "World"},
                gitignore_path="madeup",
                writer=manager.writer,
            )


def test_real_writer():
    """All other tests use a fake writer for auto cleanup, check the real default write works."""
    try:
        with open("./tmp_template.etch.txt", "w") as file:
            file.write("Hello, {{ var }}!")
        result = etch.process(
            "./tmp_template.etch.txt",
            {"var": "World"},
            gitignore_path=None,
        )
        assert result == [Path("./tmp_template.txt")]
        with open("./tmp_template.txt", "r") as file:
            assert file.read() == "Hello, World!"
    finally:
        Path("./tmp_template.etch.txt").unlink(missing_ok=True)
        Path("./tmp_template.txt").unlink(missing_ok=True)


def test_unrecognised_root():
    """Check an unrecognized root raises."""
    # Check dir:
    with pytest.raises(FileNotFoundError):
        etch.process(
            "./madeup/",
            {"var": "World"},
            gitignore_path=None,
        )

    # Check file:
    with pytest.raises(FileNotFoundError):
        etch.process(
            "./madeup.txt",
            {"var": "World"},
            gitignore_path=None,
        )


def test_no_match():
    """Check no match returns empty list."""
    # Dir:
    assert (
        etch.process(
            "./tests/",
            {"var": "World"},
            gitignore_path=None,
        )
        == []
    )

    # File:
    assert (
        etch.process(
            "./tests/test_process.py",
            {"var": "World"},
            gitignore_path=None,
        )
        == []
    )


def _check_single(
    manager: TmpFileManager,
    contents: str,
    expected: str,
    context: "dict[str, tp.Any]",
    template_direct: bool = False,
):
    template = manager.tmpfile(content=contents, suffix=".etch.txt")

    before_files = manager.files_created
    result = etch.process(
        manager.root_dir if not template_direct else template,
        context,
        gitignore_path=None,
        writer=manager.writer,
    )

    # Should return the correct compiled file:
    assert result == [_remove_template(template)]

    # Original shouldn't have changed:
    with open(template, "r") as file:
        assert contents == file.read()

    # Compiled should match expected:
    with open(result[0], "r") as file:
        assert file.read() == expected

    # Should only have created one file:
    files_created = manager.files_created - before_files
    assert files_created == 1


def _remove_template(filepath: Path) -> Path:
    return Path(str(filepath).replace(".etch.", "."))
