import json
import os
import pathlib
import subprocess
import typing as tp


class RenderResult(tp.TypedDict):
    debug: dict
    stdout: str


def render(
    root: tp.Union[str, pathlib.Path],
    config_file: tp.Optional[tp.Union[str, os.PathLike[str]]] = None,
    force: bool = False,
    verbose: bool = False,
) -> RenderResult:
    args = ["etch", "--debug", root]

    if config_file is not None:
        args += ["--config", str(config_file)]

    if force:
        args.insert(1, "--force")
    if verbose:
        args.insert(1, "--verbose")

    p1 = subprocess.run(args, capture_output=True, text=True)
    total_output = f"{p1.stdout}\n{p1.stderr}".strip()
    if p1.returncode != 0:
        raise ValueError(total_output)
    else:
        print(total_output)

    with open(os.path.join(root, "etcher_debug.json"), "r") as file:
        result = tp.cast(dict, json.load(file))

    return {
        "debug": result,
        "stdout": p1.stdout,
    }


def init(root: tp.Union[str, pathlib.Path]):
    args = ["etch", "init"]
    p1 = subprocess.run(args, capture_output=True, text=True, cwd=root)
    total_output = f"{p1.stdout}\n{p1.stderr}".strip()
    if p1.returncode != 0:
        raise ValueError(total_output)
    else:
        print(total_output)


def run(args: list[str]) -> str:
    """Run an arbitrary command, returning stdout and err combined. Raises ValueError on non-zero exit code."""
    p1 = subprocess.run(args, capture_output=True, text=True)
    total_output = f"{p1.stdout}\n{p1.stderr}".strip()
    if p1.returncode != 0:
        raise ValueError(total_output)
    else:
        print(total_output)
    return total_output
