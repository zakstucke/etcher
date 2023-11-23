import json
import os
import pathlib
import re
import typing as tp
from importlib.metadata import version

import pathspec
from jinja2 import Environment, FileSystemLoader

StrPath = tp.Union[str, os.PathLike[str]]


def _default_writer(path: pathlib.Path, contents: str) -> None:
    with open(path, "w") as file:
        file.write(contents)


class ProcessOutput(tp.TypedDict):
    """The output of the process function.

    Attributes:
        written (list[pathlib.Path]): The paths of the files that were written.
        identical (list[pathlib.Path]): The paths of the files that had existing equal compilation in the lockfile and were not overwritten.
    """

    written: tp.List[pathlib.Path]
    identical: tp.List[pathlib.Path]
    lockfile_modified: bool


_LOCK_FILENAME = ".etch.lock"
_MIDDLE_MATCHER = re.compile(r"\.etch\.")
_END_MATCHER = re.compile(r"\.etch$")


class Lockfile(tp.TypedDict):
    version: str
    files: "dict[str, int]"


def _empty_lockfile() -> Lockfile:
    return {
        "version": version("etcher"),
        "files": {},
    }


def process(
    root: StrPath,
    context: "dict[str, tp.Any]",
    exclude: "tp.Optional[list[str]]" = None,
    jinja: "tp.Optional[dict[str, tp.Any]]" = None,
    ignore_files: "tp.Optional[list[StrPath]]" = None,
    force: bool = False,
    writer: tp.Callable[[pathlib.Path, str], None] = _default_writer,
    printer: tp.Callable[[str], None] = lambda msg: None,
) -> ProcessOutput:
    r"""Reads the recursive contents of target and writes the compiled files.

    Args:
        root (pathlike object): The target directory to search.
        context (dict): The globals to pass to the Jinja environment.
        exclude (list[str], optional): Exclude files/directories matching these patterns. Read as git-style ignore patterns. Defaults to `[]`.
        jinja (dict[str, Any], optional): Jinja custom config, used when creating the Jinja Environment. https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment. Defaults to `{}`.
        ignore_files (list[pathlike object], optional): Paths to git-style ignore files, e.g. '.gitignore' to use for exclude patterns. Defaults to `None`.
        force (bool, optional): Whether to ignore the lockfile and overwrite all files, refreshing the lockfile. Defaults to `False`.
        writer (callable, optional): The function to write the compiled files. Useful for testing. Defaults to `_default_writer`.
        printer (callable, optional): The function to print messages, i.e. will print when verbose. Defaults to `lambda msg: None`.

    Returns:
        ProcessOutput: A dict containing the source templates, written files and identical files.
    """
    if jinja is None:
        jinja = {}

    # Unless manually specified something else externally, use the file system loader relative to the root: (making sure not to mutate the input)
    if "loader" not in jinja:
        jinja = {**jinja, "loader": FileSystemLoader(root)}

    environment = Environment(**jinja if jinja is not None else {})  # nosec

    # The lockfile contains a mapping from template paths to the last compiled versions in hashed form.
    # This is used to avoid re-writing files that have identical contents to the last compilation.
    # This is the solution to not continuous re-writing when e.g. post processing formatters outside etch work on the file.
    cleaned_lock_path = _get_lockfile_path(root)
    maybe_lockfile = None
    lockfile_valid = False
    if not force and os.path.exists(cleaned_lock_path):
        with open(cleaned_lock_path, "r") as file:
            try:
                maybe_lockfile = json.load(file)
            except json.JSONDecodeError:
                pass

            if (
                isinstance(maybe_lockfile, dict)
                and set(maybe_lockfile.keys()) == {"version", "files"}
                and all(
                    isinstance(key, str) and isinstance(value, int)
                    for key, value in maybe_lockfile["files"].items()
                )
                and version("etcher") == maybe_lockfile["version"]
            ):
                lockfile_valid = True

    if maybe_lockfile is not None and lockfile_valid:
        lockfile = tp.cast(Lockfile, maybe_lockfile)
        lockfile_modified = False
    else:
        printer("Invalid or missing lockfile. Starting afresh...")
        lockfile = _empty_lockfile()
        lockfile_modified = True

    ignore_file_texts = []
    if ignore_files is not None:
        for filepath in ignore_files:
            try:
                with open(filepath, "r") as file:
                    ignore_file_texts.append(file.read())
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    f"Could not find git-style ignore file at {filepath} specified."
                ) from e

    # Create a matcher from the gitignore and extra includes which will be negated in search:
    spec = pathspec.PathSpec.from_lines(
        pathspec.patterns.GitWildMatchPattern,  # type: ignore
        [
            line
            for group in (
                [ignore_text.splitlines() for ignore_text in ignore_file_texts]
                + (exclude if exclude is not None else [])
            )
            for line in group
        ],
    )

    # Find and compile all the templates:
    if os.path.isfile(root):
        raise ValueError(
            f"Root path {root} is a file. Please specify a directory to search instead."
        )

    identical: "set[pathlib.Path]" = set()
    outputs: "list[tuple[pathlib.Path, str]]" = []

    for index, rel_filepath in enumerate(spec.match_tree_files(root, negate=True)):
        if index % 100 == 0:
            printer(f"Checked {index} non-ignored files. Currently checking {rel_filepath}...")

        path = pathlib.Path(os.path.join(root, rel_filepath))

        # Don't match the lockfile:
        if rel_filepath.endswith(cleaned_lock_path.name):
            continue

        # If doesn't contain the any of the matchers, skip:
        out_path = _get_out_path(path)
        if out_path is None:
            continue

        printer(f"Found in-place template at {path}. Compiling...")

        with open(path, "r") as file:
            template_contents = file.read()

        compiled = environment.from_string(template_contents, globals=context).render()
        hashed = _insecure_hash(compiled)

        # Don't want to re-write files that are the same in the lockfile:
        if out_path.exists() and lockfile["files"].get(rel_filepath, None) == hashed:
            identical.add(out_path)
            continue

        # Add changes
        lockfile_modified = True
        lockfile["files"][rel_filepath] = hashed

        outputs.append((out_path, compiled))

    # Remove files from the lockfile that don't seem to exist anymore:
    for path in list(lockfile["files"].keys()):
        if not os.path.exists(os.path.join(root, path)):
            del lockfile["files"][path]
            lockfile_modified = True

    # Write the processed files now everything compiled successfully:
    for path, compiled in outputs:
        printer(f"Writing compiled template to {path}.")
        writer(path, compiled)

    # When changed only to prevent modification when unnecessary, write the updated lockfile, attach onto root if relative:
    if lockfile_modified:
        with open(cleaned_lock_path, "w") as file:
            json.dump(lockfile, file, indent=4)
            # To prevent end of line fixer from changing lock:
            file.write("\n")

    return {
        "written": [path for path, _ in outputs],
        "identical": list(identical),
        "lockfile_modified": lockfile_modified,
    }


def _get_out_path(path: pathlib.Path) -> tp.Optional[pathlib.Path]:
    middle_match = _MIDDLE_MATCHER.search(path.name)
    if middle_match is not None:
        return path.with_name(path.name.replace(middle_match.group(0), "."))

    end_match = _END_MATCHER.search(path.name)
    if end_match is not None:
        return path.with_name(path.name.replace(end_match.group(0), ""))

    return None


def _get_lockfile_path(root: StrPath) -> pathlib.Path:
    return pathlib.Path(root).joinpath(f"./{_LOCK_FILENAME}")


def _insecure_hash(data: str) -> int:
    """Simple insecure FNV-1a hash implementation to prevent needing to store the full contents in a lockfile to save on memory and diffs."""
    hash_value = 0x811C9DC5
    for byte in data.encode():
        hash_value ^= byte
        hash_value *= 0x01000193
    return hash_value & 0xFFFFFFFF
