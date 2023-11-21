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
setup:
    - export BAR='Goodbye, World!'
context:
    - FOO: 'Hello, World!'
    - BAR
jinja:
    - variable_start_string: '[['
    - variable_end_string: ']]'
""",
            suffix=".yml",
        )
        src = "[[ FOO ]]\n[[ BAR ]]"

        # Because the template has the suffix, it should render inplace, but the child should also use it and render:
        template = manager.tmpfile(src, suffix=".etch.txt")
        child = manager.tmpfile(f"!etch:child {template}", suffix=".etch.txt")

        app = typer.Typer()
        app.command()(main)
        CliRunner().invoke(app, ["-r", manager.root_dir, "-c", str(config), "-v"])

        expected = "Hello, World!\nGoodbye, World!"
        with open(_remove_template(template), "r") as file:
            assert file.read() == expected
        with open(_remove_template(child), "r") as file:
            assert file.read() == expected


@pytest.mark.parametrize(
    "config_var,yaml,expected",
    [
        (
            "context",
            """
setup: 'export FOO=\"Hello, World!\"'
context: FOO
""",
            {"FOO": "Hello, World!"},
        ),
        (
            "context",
            """
setup:
    - 'export FOO=\"Hello, World!\"'
    - 'export BAR=\"Goodbye, World!\"'
context:
    - FOO
    - BAR
    - BAZ: 'INLINE'
""",
            {"FOO": "Hello, World!", "BAR": "Goodbye, World!", "BAZ": "INLINE"},
        ),
        # Without specifying the var in context, shouldn't show up:
        ("context", """setup: 'export FOO=\"Hello, World!\"'""", {}),
        ("ignore_files", """ignore_files: .gitignore""", [".gitignore"]),
        (
            "ignore_files",
            """ignore_files: [.gitignore, ".dockerignore"]""",
            [".gitignore", ".dockerignore"],
        ),
        ("exclude", """- exclude: '.*'""", [".*"]),
        ("exclude", """- exclude: ['.*', foo.bar]""", [".*", "foo.bar"]),
        (
            "exclude",
            """exclude:
                    - '.*'
                    - foo.bar""",
            [".*", "foo.bar"],
        ),
        ("jinja", """jinja: {'trim_blocks': True}""", {"trim_blocks": True}),
        (
            "jinja",
            """jinja: {'trim_blocks': True, 'lstrip_blocks': True}""",
            {"trim_blocks": True, "lstrip_blocks": True},
        ),
        (
            "jinja",
            """jinja:
            - trim_blocks: True
            - lstrip_blocks: True
        """,
            {"trim_blocks": True, "lstrip_blocks": True},
        ),
        ("child_flag", """child_flag: '!IAMCHILD'""", "!IAMCHILD"),
        ("template_matcher", """template_matcher: 'ROOT'""", "ROOT"),
    ],
)
def test_read_config(config_var: str, yaml: str, expected: str):
    """Confirm various yaml config setups are all read and processed correctly."""
    with TmpFileManager() as manager:
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
    """Confirm can automatically handle yaml/yml, but raises on everything else."""
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
                printer=lambda msg: None,
            )


def test_wildcard_env():
    """Confirm a wildcard in context includes all env vars in context."""
    with TmpFileManager() as manager:
        config = etch.read_config(
            manager.tmpfile(
                """context: '*'""",
                suffix=".yml",
            )
        )
        assert len(config["context"]) > 5


def test_missing_env_var():
    """Confirm missing env vars included in context raise nice error."""
    with TmpFileManager() as manager:
        with pytest.raises(ValueError, match="Could not find variable"):
            etch.read_config(
                manager.tmpfile(
                    """context: FOO""",
                    suffix=".yml",
                )
            )
