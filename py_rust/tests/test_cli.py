import os
import pathlib
import subprocess  # nosec
import typing as tp
from unittest import mock

import etcher as etch
import pytest
import typer
from etcher.main import main
from typer.testing import CliRunner

from .test_process import _remove_template
from .tmp_file_manager import TmpFileManager


def test_entrypoint():
    """Test the CLI entry point works."""
    with TmpFileManager() as manager:
        config = manager.tmpfile(
            """
context:
    - FOO: 'Hello, World!'
    - BAR:
        - type: cli
        - value: echo "Goodbye, World!"
jinja:
    - block_start_string: "[?"
    - block_end_string: "?]"
    - variable_start_string: '[['
    - variable_end_string: ']]'
""",
            suffix=".yml",
        )
        src = "[[ FOO ]]\n[[ BAR ]]"

        # Because the template has the suffix, it should render inplace, but the child should also use it and render:
        template = manager.tmpfile(src, suffix=".etch.txt")
        template_path = pathlib.Path(template).relative_to(manager.root_dir)
        child = manager.tmpfile(f"[? include '{template_path}' ?]", suffix=".etch.txt")

        app = typer.Typer()
        app.command()(main)
        CliRunner().invoke(app, ["-r", manager.root_dir, "-c", str(config), "-v"])

        expected = "Hello, World!\nGoodbye, World!"
        with open(_remove_template(template), "r") as file:
            assert file.read() == expected
        with open(_remove_template(child), "r") as file:
            assert file.read() == expected


@pytest.mark.parametrize(
    "env,config_var,yaml,expected",
    [
        (
            {},
            "context",
            """
context:
    - FOO:
        type: cli
        value: echo "Hello, World!"
""",
            {"FOO": "Hello, World!"},
        ),
        (
            {},
            "context",
            """
context:
    - FOO:
        type: cli
        value:
            - echo "Ignore me I'm different!"
            - echo "Hello, World!"
""",
            {"FOO": "Hello, World!"},
        ),
        (
            {},
            "context",
            """
context:
    - FOO:
        type: static
        value: "Hello, World!"
""",
            {"FOO": "Hello, World!"},
        ),
        (
            {"BAR": "abc"},
            "context",
            """
context:
    - FOO:
        type: env
        value: BAR
""",
            {"FOO": "abc"},
        ),
        # Should still use env var if available despite default given:
        (
            {"BAR": "abc"},
            "context",
            """
context:
    - FOO:
        - type: env
        - value: BAR
        - default: True
""",
            {"FOO": "abc"},
        ),
        # Should only use default when no env var:
        (
            {},
            "context",
            """
context:
    - FOO:
        - type: env
        - value: BAR
        - default: True
""",
            {"FOO": True},
        ),
        (
            {},
            "context",
            """
context:
    - FOO:
        type: cli
        value: echo "Hello, World!"
    - BAR:
        type: cli
        value: echo "Goodbye, World!"
    - BAZ: 'INLINE'
""",
            {"FOO": "Hello, World!", "BAR": "Goodbye, World!", "BAZ": "INLINE"},
        ),
        ({}, "ignore_files", """ignore_files: .gitignore""", [".gitignore"]),
        (
            {},
            "ignore_files",
            """ignore_files: [.gitignore, ".dockerignore"]""",
            [".gitignore", ".dockerignore"],
        ),
        ({}, "exclude", """- exclude: '.*'""", [".*"]),
        ({}, "exclude", """- exclude: ['.*', foo.bar]""", [".*", "foo.bar"]),
        (
            {},
            "exclude",
            """exclude:
                    - '.*'
                    - foo.bar""",
            [".*", "foo.bar"],
        ),
        ({}, "jinja", """jinja: {'trim_blocks': True}""", {"trim_blocks": True}),
        (
            {},
            "jinja",
            """jinja: {'trim_blocks': True, 'lstrip_blocks': True}""",
            {"trim_blocks": True, "lstrip_blocks": True},
        ),
        (
            {},
            "jinja",
            """jinja:
            trim_blocks: True
            lstrip_blocks: True
        """,
            {"trim_blocks": True, "lstrip_blocks": True},
        ),
    ],
)
def test_read_config(env: "dict[str, str]", config_var: str, yaml: str, expected: str):
    """Confirm various yaml config setups are all read and processed correctly."""
    with TmpFileManager() as manager:
        with mock.patch.dict(os.environ, env):
            assert (
                etch.read_config(
                    manager.tmpfile(
                        yaml,
                        suffix=".yml",
                    ),
                )[config_var]
                == expected
            )


def test_incorrect_config():
    """Confirm can automatically handle yaml/yml, but raises on invalid yaml, or unknown config."""
    with TmpFileManager() as manager:
        assert etch.read_config(
            manager.tmpfile(
                """ignore_files: .gitignore""",
                suffix=".yaml",
            ),
        )["ignore_files"] == [".gitignore"]

        with pytest.raises(ValueError, match="Config file must be a YAML file"):
            etch.read_config(
                manager.tmpfile(
                    """ignore_files: .gitignore""",
                    suffix=".json",
                ),
            )

        with pytest.raises(FileNotFoundError, match="Could not find config file"):
            etch.read_config(
                "not/a/real/path.yml",
            )

        with pytest.raises(ValueError, match="Unknown config key: 'unknown'"):
            etch.read_config(
                manager.tmpfile("""unknown: 'foo'""", suffix=".yml"),
            )

        # Missing value when full syntax used:
        with pytest.raises(ValueError, match="Missing 'value' key"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                        FOO:
                            - type: static""",
                    suffix=".yml",
                ),
            )

        # Unknown type when full syntax used:
        with pytest.raises(ValueError, match="Unknown context var type"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                        FOO:
                            - type: foo
                            - value: 'bar'""",
                    suffix=".yml",
                ),
            )

        # Unknown coerce type:
        with pytest.raises(ValueError, match="Unknown coercion type"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                        FOO:
                            - type: static
                            - value: 'bar'
                            - as: foo""",
                    suffix=".yml",
                ),
            )


def test_missing_env_var():
    """Confirm missing env vars included in context raise nice error."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Could not find environment variable"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                    FOO:
                        - type: env
                        - value: sdfjkdshfs""",
                    suffix=".yml",
                )
            )


def test_failing_cli_errs():
    """Make sure errors in cli scripts are raised."""
    # Should error when script actually errs:
    with TmpFileManager() as manager:
        with pytest.raises(subprocess.CalledProcessError, match="returned non-zero exit status"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                    FOO:
                        - type: cli
                        - value: './dev_scripts/initial_setup.sh I_DONT_EXIST'""",
                    suffix=".yml",
                )
            )

    # Should error when script returns nothing (implicit None)
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Implicit None, final cli script returned nothing"):
            etch.read_config(
                manager.tmpfile(
                    """context:
                    FOO:
                        - type: cli
                        - value: 'echo "hello" >/dev/null'""",
                    suffix=".yml",
                )
            )


@pytest.mark.parametrize(
    "as_type,input_val,expected",
    [
        ("str", "123", "123"),
        ("int", "123", 123),
        ("int", "123.34", 123),
        ("float", "123.456", 123.456),
        ("bool", "true", True),
        ("bool", "True", True),
        ("bool", "y", True),
        ("bool", "false", False),
        ("json", '{"foo": "bar"}', {"foo": "bar"}),
    ],
)
def test_valid_coersion(as_type: tp.Any, input_val: tp.Any, expected: tp.Any):
    """Confirm value conversion works correctly when valid in all input types."""
    with TmpFileManager() as manager:
        yml_versions = [
            f"""context:
                FOO:
                    - type: static
                    - value: {input_val}
                    - as: {as_type}""",
            f"""context:
                FOO:
                    - type: env
                    - value: FOO
                    - as: {as_type}""",
            """context:
                FOO:
                    - type: cli
                    - value: 'echo "{}"'
                    - as: {}""".format(input_val.replace('"', '\\"'), as_type),
        ]
        os.environ["FOO"] = input_val
        for yml_version in yml_versions:
            assert (
                etch.read_config(
                    manager.tmpfile(
                        yml_version,
                        suffix=".yml",
                    ),
                )["context"]["FOO"]
                == expected
            )


@pytest.mark.parametrize(
    "as_type,input_val",
    [
        ("bool", "truee"),
        ("bool", "yess"),
        ("json", '{"foo"sdafsd'),
    ],
)
def test_invalid_coersion(as_type: str, input_val: str):
    """Confirm nice error when value conversion fails."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Could not convert value"):
            etch.read_config(
                manager.tmpfile(
                    f"""context:
                        FOO:
                            - type: static
                            - value: '{input_val}'
                            - as: {as_type}""",
                    suffix=".yml",
                ),
            )
