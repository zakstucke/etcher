import typing as tp
from pathlib import Path

import pytest

from ..helpers import cli
from ..helpers.tmp_file_manager import TmpFileManager
from ..helpers.types import InputConfig
from ..helpers.utils import check_single, remove_template


def test_single_basic():
    with TmpFileManager() as manager:
        check_single(
            manager,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
            "Hello, {{ var }}!",
            "Hello, World!",
        )


@pytest.mark.parametrize(
    "filename,should_match,expected_out",
    [
        ("test.etch.txt", True, "test.txt"),
        ("test.etch", True, "test"),
        (".etch.test", True, ".test"),
        ("test.etcher.txt", False, ""),
        ("test.txt", False, ""),
    ],
)
def test_correct_matching(filename: str, should_match: bool, expected_out: str):
    """Confirm middle and end matchers both work, and things that shouldn't match don't."""
    with TmpFileManager() as manager:
        # This shouldn't match the default .etch. matcher:
        manager.tmpfile(content="", full_name=filename)
        result = cli.render(manager.root_dir, manager.create_cfg({}))
        written = result["debug"]["written"]
        if should_match:
            assert len(written) == 1
            assert Path(written[0]).name == expected_out
        else:
            assert len(written) == 0


def test_multiple_mixed_templates():
    """Check multiple templates in the search directory are handled."""
    with TmpFileManager() as manager:
        src1 = "Hello, {{ var }}!"
        src2 = "Goodbye, {{ var }}!"
        template_1 = manager.tmpfile(content=src1, suffix=".etch.txt")
        template_2 = manager.tmpfile(content=src2, suffix=".etch.txt")

        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )

        assert len(result["debug"]["written"]) == 2

        with open(remove_template(template_1), "r") as file:
            assert file.read() == "Hello, World!"

        with open(remove_template(template_2), "r") as file:
            assert file.read() == "Goodbye, World!"


@pytest.mark.parametrize(
    "desc,config_creator",
    [
        (
            "ignore_file direct name",
            lambda manager: {
                "ignore_files": [manager.tmpfile(content="test.etch.txt").name],
            },
        ),
        (
            "ignore_file subdir",
            lambda manager: {
                "ignore_files": [manager.tmpfile(content="subdir/").name],
            },
        ),
        (
            "ignore_file wildmatch",
            lambda manager: {
                "ignore_files": [manager.tmpfile(content="*.txt").name],
            },
        ),
        (
            "exclude direct name",
            lambda manager: {
                "exclude": ["test.etch.txt"],
            },
        ),
        (
            "exclude subdir",
            lambda manager: {
                "exclude": ["subdir/"],
            },
        ),
        (
            "exclude wildmatch",
            lambda manager: {
                "exclude": ["*.txt"],
            },
        ),
    ],
)
def test_ignore(desc: str, config_creator: tp.Callable[[TmpFileManager], InputConfig]):
    """Confirm both ignore_files and exclude are respected when enabled."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"

        # Placing the template in a subdir so works with some of the test configurations:
        template = manager.tmpfile(
            content=contents, parent=manager.tmpdir(name="subdir"), full_name="test.etch.txt"
        )

        # Should be excluded:
        result = cli.render(
            manager.root_dir,
            manager.create_cfg(
                {
                    "context": {"static": {"var": {"value": "World"}}},
                    **config_creator(manager),
                }
            ),
        )
        assert result["debug"]["written"] == []

        # Should be included when ignore config isn't there:
        result = cli.render(
            manager.root_dir,
            manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
        )
        assert result["debug"]["written"] == [remove_template(template)]


def test_ignorefile_overriden_in_exclude():
    """Confirm an exclude whitelist pattern overrides an ignore file."""
    with TmpFileManager() as manager:
        contents = "Hello, {{ var }}!"
        template = manager.tmpfile(content=contents, full_name="test.etch.txt")

        # Should be excluded when exclude isn't set (matches ignore file):
        result = cli.render(
            manager.root_dir,
            manager.create_cfg(
                {
                    "context": {"static": {"var": {"value": "World"}}},
                    "ignore_files": [manager.tmpfile(content="*.txt").name],
                }
            ),
        )
        assert result["debug"]["written"] == []

        # Should be included when exclude whitelister for the template is set (overrides ignore file):
        result = cli.render(
            manager.root_dir,
            manager.create_cfg(
                {
                    "context": {"static": {"var": {"value": "World"}}},
                    "ignore_files": [manager.tmpfile(content="*.txt").name],
                    "exclude": ["!test.etch.txt"],
                }
            ),
        )

        assert result["debug"]["written"] == [remove_template(template)]
