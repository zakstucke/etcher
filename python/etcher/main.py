"""Main entry point for the etcher CLI."""

import typer
import typing_extensions as tp

from ._config import read_config
from ._process import process


def main(
    root: tp.Annotated[
        str, typer.Option("--root", "-r", help="The target directory/file to compile")
    ] = ".",
    config_file: tp.Annotated[
        str, typer.Option("--config", "-c", help="The config file to use")
    ] = "./etch.config.yml",
    verbose: tp.Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
):
    """External layer on top of process() that supports the yaml config file."""

    def printer(msg: str) -> None:
        typer.echo(f"Etcher: {msg}")

    config = read_config(config_file, printer=printer if verbose else lambda msg: None)
    files_processed = process(
        root,
        context=config["context"],
        exclude=config["exclude"],
        jinja=config["jinja"],
        ignore_files=config["ignore_files"],
        template_matcher=config["template_matcher"],
        child_flag=config["child_flag"],
        printer=printer if verbose else lambda msg: None,
    )
    typer.echo(f"Etched {len(files_processed)} files.")


def cli():  # pragma: no cover
    """CLI entry point."""
    typer.run(main)
