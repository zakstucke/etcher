import re
import typing as tp

import pytest

from .helpers import cli
from .helpers.tmp_file_manager import TmpFileManager


def test_incorrect_config():
    """Confirm raises nicely on invalid toml, or unknown config."""
    with TmpFileManager() as manager:
        # Invalid toml file:
        with pytest.raises(ValueError, match="Invalid toml"):
            cli.render(manager.root_dir, manager.tmpfile("lafdldfa//$$ : foo ", suffix=".toml"))

        # Unknown top level param:
        with pytest.raises(ValueError, match=re.escape("[root]: Unknown property: 'foo'.")):
            cli.render(manager.root_dir, manager.tmpfile("foo = 'bar'", suffix=".toml"))

        # Unknown ctx type:
        with pytest.raises(ValueError, match=re.escape("[context]: Unknown property: 'dsfs'.")):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "[context]\n[context.dsfs]\nFOO = { value = 'bar' }\n",
                    suffix=".toml",
                ),
            )

        # Unknown coerce type for any ctx type:
        for ctx_type, extra_args in [
            ("static", {"value": "1"}),
            ("env", {"env_name": "'FOO'"}),
            ("cli", {"commands": ["'echo 1'"]}),
        ]:
            with pytest.raises(
                ValueError,
                match=re.escape(
                    "[context.{}.FOO.coerce]: Expected one of ['json', 'str', 'int', 'float', 'bool'].".format(
                        ctx_type
                    )
                ),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "[context]\n[context.{}]\nFOO = {{ coerce = 'dsfs', {} }}\n".format(
                            ctx_type,
                            ", ".join(f"{k} = {v}" for k, v in extra_args.items()),
                        ),
                        suffix=".toml",
                    ),
                )

        # None dict format for any ctx type:
        for ctx_type in ["static", "env", "cli"]:
            with pytest.raises(
                ValueError,
                match=re.escape("[context.{}.FOO]: Expected a table.".format(ctx_type)),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "[context]\n[context.{}]\nFOO = 'bar'\n".format(ctx_type),
                        suffix=".toml",
                    ),
                )

        # Missing 'value' for static ctx or 'commands' for cli:
        for ctx_type, key_name in [("static", "value"), ("cli", "commands")]:
            with pytest.raises(
                ValueError,
                match=re.escape(
                    "[context.{}.FOO.{}]: This property is required.".format(
                        ctx_type,
                        key_name,
                    )
                ),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "[context]\n[context.{}]\nFOO = {{}}\n".format(ctx_type),
                        suffix=".toml",
                    ),
                )

        # 'value' is empty string/null for static / env 'default':
        for ctx_type, key_name in [("static", "value"), ("env", "default")]:
            with pytest.raises(
                ValueError,
                match=re.escape(
                    "[context.{}.FOO.{}]: Cannot be an empty string.".format(ctx_type, key_name)
                ),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "[context]\n[context.{}]\nFOO = {{ {} = '' }}\n".format(ctx_type, key_name),
                        suffix=".toml",
                    ),
                )

        # Unknown key for static/env/cli:
        for ctx_key in ["static", "env", "cli"]:
            with pytest.raises(
                ValueError,
                match=re.escape("[context.{}.FOO]: Unknown property: 'bar'.".format(ctx_key)),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "[context]\n[context.{}]\nFOO = {{ bar = 'baz' }}\n".format(ctx_key),
                        suffix=".toml",
                    ),
                )

        # Ignore/exclude/setup_commands wrong type:
        for cfg_key in ["ignore_files", "exclude", "setup_commands"]:
            with pytest.raises(
                ValueError,
                match=re.escape("[{}]: Expected an array.".format(cfg_key)),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "{} = 'foo'\n".format(cfg_key),
                        suffix=".toml",
                    ),
                )

        # 'commands' is an empty array:
        with pytest.raises(
            ValueError,
            match=re.escape("[context.cli.FOO.commands]: MinItems condition is not met."),
        ):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "[context]\n[context.cli]\nFOO = { commands = [] }\n",
                    suffix=".toml",
                ),
            )

        # 'commands' isn't an array of strings:
        with pytest.raises(
            ValueError,
            match=re.escape("[context.cli.FOO.commands.0]: Expected a string."),
        ):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "[context]\n[context.cli]\nFOO = { commands = [3] }\n",
                    suffix=".toml",
                ),
            )

        # 'commands' isn't an array:
        with pytest.raises(
            ValueError,
            match=re.escape("[context.cli.FOO.commands]: Expected an array."),
        ):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "[context]\n[context.cli]\nFOO = { commands = 1 }\n",
                    suffix=".toml",
                ),
            )

        # Ignore/exclude arrays but not all strings:
        for cfg_key in ["ignore_files", "exclude"]:
            with pytest.raises(
                ValueError,
                match=re.escape("[{}.1]: Expected a string.".format(cfg_key)),
            ):
                cli.render(
                    manager.root_dir,
                    manager.tmpfile(
                        "{} = ['foo', {{ bar = 'baz' }}]\n".format(cfg_key),
                        suffix=".toml",
                    ),
                )

        # Engine wrong type:
        with pytest.raises(
            ValueError,
            match=re.escape("[engine]: Expected a table."),
        ):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "engine = 1",
                    suffix=".toml",
                ),
            )

        # 'env_name' isn't a string:
        with pytest.raises(
            ValueError,
            match=re.escape("[context.env.FOO.env_name]: Expected a string."),
        ):
            cli.render(
                manager.root_dir,
                manager.tmpfile(
                    "[context]\n[context.env]\nFOO = { env_name = 1 }\n",
                    suffix=".toml",
                ),
            )


def test_missing_env_var():
    """Confirm missing env vars included in context raise nice error when no default."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Could not find environment variable"):
            cli.render(
                manager.root_dir,
                manager.create_cfg({"context": {"env": {"FOO": {"env_name": "sdgfhs"}}}}),
            )


def test_failing_cli_errs():
    """Make sure errors in cli scripts are raised."""
    # Should error when script actually errs:
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Command returned non-zero exit status"):
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "cli": {
                                "FOO": {"commands": ["./dev_scripts/initial_setup.sh I_DONT_EXIST"]}
                            }
                        }
                    }
                ),
            )

    # Should error when script returns nothing (implicit None)
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Implicit None. Final cli script returned nothing."):
            tmpfile = manager.tmpfile("", suffix=".txt")
            cli.render(
                manager.root_dir,
                manager.create_cfg({"context": {"cli": {"FOO": {"commands": [f"cat {tmpfile}"]}}}}),
            )


@pytest.mark.parametrize(
    "as_type,input_val",
    [
        ("bool", "truee"),
        ("bool", "yess"),
        ("json", '{"foo"sdafsd'),
    ],
)
def test_invalid_coersion(
    as_type: tp.Literal["str", "int", "float", "bool", "json"], input_val: str
):
    """Confirm nice error when value conversion fails."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Failed to coerce to type"):
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "static": {"FOO": {"value": f"'{input_val}'", "coerce": as_type}}
                        }
                    },
                ),
            )


def test_unrecognised_root():
    """Check an unrecognized root raises."""
    with TmpFileManager() as manager:
        # Check dir:
        with pytest.raises(ValueError, match="Root path does not exist:"):
            cli.render(
                "./madeup/",
                manager.create_cfg(
                    {"context": {"static": {"var": {"value": "World"}}}},
                ),
            )


def test_unrecognised_ignore_file():
    """Check an unrecognized ignore file raises."""
    with TmpFileManager() as manager:
        # Should raise custom error when path to gitignore wrong:
        with pytest.raises(ValueError, match="does not exist."):
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "static": {"var": {"value": "World"}},
                        },
                        "ignore_files": ["madeup.txt"],
                    },
                ),
            )

        # Raise an error when its a directory:
        wrong_dir = manager.tmpdir()
        with pytest.raises(ValueError, match="is not a file."):
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "static": {"var": {"value": "World"}},
                        },
                        "ignore_files": [str(wrong_dir)],
                    },
                ),
            )


def test_unrecognised_user_extension():
    """Should error if can't find the file specified."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="does not exist."):
            cli.render(
                manager.root_dir,
                manager.create_cfg(
                    {
                        "context": {
                            "static": {"var": {"value": "World"}},
                        },
                        "engine": {"custom_extensions": ["madeup.py"]},
                    },
                ),
            )


def test_direct_file():
    """Should raise error when direct file passed."""
    with TmpFileManager() as manager:
        template = manager.tmpfile(content="Hello, {{ var }}!", suffix=".etch.txt")
        with pytest.raises(ValueError, match="Root path is not a directory:"):
            cli.render(
                template,
                manager.create_cfg(
                    {
                        "context": {
                            "static": {"var": {"value": "World"}},
                        },
                    },
                ),
            )
