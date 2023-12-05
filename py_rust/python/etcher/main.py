"""Main entry point for the etcher CLI."""

import pprint
import time

import typer
import typing_extensions as tp

from ._config import read_config
from ._process import process


def main(
    root: tp.Annotated[
        str, typer.Option("--root", "-r", help="The target directory to search and compile.")
    ] = ".",
    config_file: tp.Annotated[
        str, typer.Option("--config", "-c", help="The config file to use.")
    ] = "./etch.config.yml",
    force: tp.Annotated[
        bool,
        typer.Option("--force", "-f", help="Force overwrite all files, ignore existing lockfile."),
    ] = False,
    verbose: tp.Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
):
    """External layer on top of process() that supports the yaml config file."""

    def printer(msg: str) -> None:
        typer.echo(f"Etcher: {msg}")

    total_time_start = time.time()

    config = read_config(config_file, printer=printer if verbose else lambda msg: None)
    result = process(
        root,
        context=config["context"],
        exclude=config["exclude"],
        jinja=config["jinja"],
        ignore_files=config["ignore_files"],
        force=force,
        printer=printer if verbose else lambda msg: None,
    )

    total_time = time.time() - total_time_start
    if verbose:

        def clean_time(length: float):
            return str(round(length * 1000)) + "ms"

        printer(
            "Timing: \n{}".format(
                pprint.pformat(
                    {
                        "scripting": {
                            k: clean_time(t) for k, t in config["scripting_time"].items()
                        },
                        **{k: clean_time(t) for k, t in result["timing_info"].items()},
                        "total": clean_time(total_time),
                    }
                )
            )
        )

    typer.echo(
        "Etched {} changed files. {} identical. Lockfile {}.".format(
            len(result["written"]),
            len(result["identical"]),
            "modified" if result["lockfile_modified"] else "untouched",
        )
    )
