import json
import os
import time
import typing as tp
from unittest import mock

import etcher as etch
import pytest

from .helpers import cli
from .helpers.tmp_file_manager import TmpFileManager
from .helpers.types import InputConfig
from .helpers.utils import check_single


def cfg_str(config: InputConfig) -> str:
    return etch._toml_update("", update=config)


@pytest.mark.parametrize(
    "env,config_var,cfg_str,expected",
    [
        (
            {},
            "context",
            cfg_str(
                {
                    "context": {
                        "cli": {
                            "FOO": {
                                "commands": ['echo "Hello, World!"'],
                            }
                        }
                    }
                }
            ),
            {"FOO": "Hello, World!"},
        ),
        (
            {},
            "context",
            cfg_str(
                {
                    "context": {
                        "cli": {
                            "FOO": {
                                "commands": [
                                    'echo "Ignore me I\'m different!"',
                                    'echo "Hello, World!"',
                                ]
                            }
                        }
                    }
                }
            ),
            {"FOO": "Hello, World!"},
        ),
        (
            {},
            "context",
            cfg_str({"context": {"static": {"FOO": {"value": "Hello, World!"}}}}),
            {"FOO": "Hello, World!"},
        ),
        (
            {"FOO": "abc"},
            "context",
            cfg_str({"context": {"env": {"FOO": {}}}}),
            {"FOO": "abc"},
        ),
        (
            {"BAR": "def"},
            "context",
            cfg_str({"context": {"env": {"FOO": {"env_name": "BAR"}}}}),
            {"FOO": "def"},
        ),
        # Should still use env var if available despite default given:
        (
            {"FOO": "abc"},
            "context",
            cfg_str({"context": {"env": {"FOO": {"default": True}}}}),
            {"FOO": "abc"},
        ),
        # Should only use default when no env var:
        (
            {},
            "context",
            cfg_str({"context": {"env": {"FOO": {"env_name": "BAR", "default": True}}}}),
            {"FOO": True},
        ),
        (
            {},
            "context",
            cfg_str(
                {
                    "context": {
                        "cli": {
                            "FOO": {
                                "commands": ['echo "Hello, World!"'],
                            },
                            "BAR": {
                                "commands": ['echo "Goodbye, World!"'],
                            },
                        },
                        "static": {"BAZ": {"value": "INLINE"}},
                    },
                }
            ),
            {"FOO": "Hello, World!", "BAR": "Goodbye, World!", "BAZ": "INLINE"},
        ),
        (
            {},
            "ignore_files",
            cfg_str({"ignore_files": ["ignorefile.txt"]}),
            lambda root_dir: [os.path.join(root_dir, "ignorefile.txt")],
        ),
        ({}, "exclude", cfg_str({"exclude": [".*", "foo.bar"]}), [".*", "foo.bar"]),
        ({}, "setup_commands", cfg_str({"setup_commands": ["npm i"]}), ["npm i"]),
        (
            {},
            "engine",
            cfg_str(
                {
                    "engine": {
                        "allow_undefined": True,
                        "keep_trailing_newline": False,
                    }
                }
            ),
            {
                "allow_undefined": True,
                "keep_trailing_newline": False,
                "block_start": "{%",
                "block_end": "%}",
                "variable_start": "{{",
                "variable_end": "}}",
                "comment_start": "{#",
                "comment_end": "#}",
                "custom_extensions": [],
            },
        ),
    ],
)
def test_read_config(
    env: "dict[str, str]",
    config_var: str,
    cfg_str: str,
    expected: tp.Union[str, tp.Callable[[str], tp.List[str]]],
):
    """Confirm various config setups are all read and processed correctly."""
    with TmpFileManager() as manager:
        with mock.patch.dict(os.environ, env):
            # Make sure a .gitignore exists as one of the variations needs it:
            if config_var == "ignore_files":
                manager.tmpfile("foo", full_name="ignorefile.txt")

            final_expected = expected(manager.root_dir) if callable(expected) else expected

            assert (
                cli.render(manager.root_dir, manager.tmpfile(cfg_str, suffix=".toml"))["debug"][
                    "config"
                ][config_var]
                == final_expected
            )


def test_setup_commands():
    """Confirm setup commands are run correctly."""
    with TmpFileManager() as manager:
        tmpfile = manager.tmpfile("foo", suffix=".txt")

        assert os.path.exists(tmpfile)

        check_single(
            manager,
            manager.create_cfg({"setup_commands": ["rm {}".format(tmpfile)]}),
            "",
            "",
        )

        # Should have been deleted by setup command:
        assert not os.path.exists(tmpfile)


def test_parallelized_context_cli_commands():
    """Confirm cli commands are processed in parallel for different variables.

    External commands are one of the slowest parts of the system, etch should attempts to remedy by running different ctx commands in parallel.
    """
    with TmpFileManager() as manager:
        before = time.time()
        check_single(
            manager,
            manager.create_cfg(
                {
                    "context": {
                        "cli": {
                            "FOO": {
                                "commands": [
                                    "sleep 0.5",
                                    'echo "MY_FOO"',
                                ],
                            },
                            "BAR": {
                                "commands": [
                                    "sleep 0.5",
                                    'echo "MY_BAR"',
                                ],
                            },
                            "BAZ": {
                                "commands": [
                                    "sleep 0.5",
                                    'echo "MY_BAZ"',
                                ],
                            },
                            "QUX": {
                                "commands": [
                                    "sleep 0.5",
                                    'echo "MY_QUX"',
                                ],
                            },
                        }
                    }
                }
            ),
            "{{ FOO }} {{ BAR }} {{ BAZ }} {{ QUX }}",
            "MY_FOO MY_BAR MY_BAZ MY_QUX",
        )
        time_taken = time.time() - before
        # Should be just above 0.5, but allow decent leeway:
        assert time_taken < 1


@pytest.mark.parametrize(
    "as_type,input_val,expected",
    [
        ("str", "123", "123"),
        ("int", "123", 123),
        ("int", "123.34", 123),
        ("int", 123.34, 123),
        ("float", "123.456", 123.456),
        ("bool", "true", True),
        ("bool", "True", True),
        ("bool", "y", True),
        ("bool", "false", False),
        ("json", json.dumps({"foo": "bar"}), {"foo": "bar"}),
    ],
)
def test_valid_coercion(as_type: tp.Any, input_val: tp.Any, expected: tp.Any):
    """Confirm value conversion works correctly when valid in all input types."""
    with TmpFileManager() as manager:
        # Test static, cli and env variants:

        assert (
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {"context": {"static": {"FOO": {"value": input_val, "coerce": as_type}}}}
                ),
            )["debug"]["config"]["context"]["FOO"]
            == expected
        )

        tmpfile = manager.tmpfile(str(input_val), suffix=".txt")
        assert (
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "cli": {
                                "FOO": {
                                    "commands": ["cat {}".format(tmpfile)],
                                    "coerce": as_type,
                                }
                            }
                        }
                    }
                ),
            )["debug"]["config"]["context"]["FOO"]
            == expected
        )

        with mock.patch.dict(
            os.environ,
            {
                "FOO": str(input_val),
            },
        ):
            assert (
                cli.render(
                    manager.root_dir,
                    manager.create_cfg(
                        {"context": {"env": {"FOO": {"env_name": "FOO", "coerce": as_type}}}},
                    ),
                )["debug"]["config"]["context"]["FOO"]
                == expected
            )
