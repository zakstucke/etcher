import json
import os
import pathlib
import re
import typing as tp

import pathspec
from jinja2 import Environment

StrPath = tp.Union[str, os.PathLike[str]]


def _default_writer(path: pathlib.Path, contents: str) -> None:
    with open(path, "w") as file:
        file.write(contents)


class ProcessOutput(tp.TypedDict):
    """The output of the process function.

    Attributes:
        root_templates (list[pathlib.Path]): The paths of the root templates that were compiled.
        written (list[pathlib.Path]): The paths of the files that were written.
        identical (list[pathlib.Path]): The paths of the files that had existing equal compilation in the lockfile and were not overwritten.
    """

    root_templates: tp.List[pathlib.Path]
    written: tp.List[pathlib.Path]
    identical: tp.List[pathlib.Path]


_LOCK_FILENAME = ".etch.lock"
_DEFAULT_TEMPLATE_MATCHER = re.compile(r"\.etch")
_DEFAULT_CHILD_FLAG = "!etch:child"


def process(
    root: StrPath,
    context: "dict[str, tp.Any]",
    exclude: "tp.Optional[list[str]]" = None,
    jinja: "tp.Optional[dict[str, tp.Any]]" = None,
    ignore_files: "tp.Optional[list[StrPath]]" = None,
    template_matcher: "re.Pattern[str]" = _DEFAULT_TEMPLATE_MATCHER,
    child_flag: str = _DEFAULT_CHILD_FLAG,
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
        template_matcher (str, optional): The match filename regex to identify in-place templates or placeholders pointing to templates. Compiled files will omit the matcher. Defaults to `re.compile(r'\.etch')`. E.g. `foo.etch.txt` would compile to `foo.txt`.
        child_flag (str, optional): The match string to identify child templates. Defaults to `!etch:child`. E.g. `foo.etch.txt` with contents `!etch:child ./templates/template.txt` will be replaced with the compiled contents of `template.txt`ß.
        force (bool, optional): Whether to ignore the lockfile and overwrite all files, refreshing the lockfile. Defaults to `False`.
        writer (callable, optional): The function to write the compiled files. Useful for testing. Defaults to `_default_writer`.
        printer (callable, optional): The function to print messages, i.e. will print when verbose. Defaults to `lambda msg: None`.

    Returns:
        ProcessOutput: A dict containing the source templates, written files and identical files.
    """
    environment = Environment(**jinja if jinja is not None else {})  # nosec

    lockfile_modified = False

    # The lockfile contains a mapping from template paths to the last compiled versions.
    # This is used to avoid re-writing files that have identical contents to the last compilation.
    # This is the solution to not continuous re-writing when e.g. post processing formatters outside etch work on the file.
    cleaned_lock_path = _get_lockfile_path(root)
    lockfile: "dict[str, str]" = {}
    try:
        if not force and os.path.exists(cleaned_lock_path):
            with open(cleaned_lock_path, "r") as file:
                lockfile = json.load(file)
                if not isinstance(lockfile, dict) or not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in lockfile.items()
                ):
                    printer("Invalid lockfile. Resetting...")
                    lockfile = {}

        else:
            lockfile = {}
            lockfile_modified = True
    except json.JSONDecodeError:
        printer("Invalid lockfile. Resetting...")
        lockfile = {}
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

    # Need to apply changes at the end so later children from the same root do update (if inplace the lockfile would look correct for later children)
    lockfile_changes: "dict[str, str]" = {}

    root_templates: set[pathlib.Path] = set()
    identical: tp.List[pathlib.Path] = []
    outputs: "list[tuple[pathlib.Path, str]]" = []

    for index, rel_filepath in enumerate(spec.match_tree_files(root, negate=True)):
        if index % 100 == 0:
            printer(f"Checked {index} non-ignored files. Currently checking {rel_filepath}...")

        path = pathlib.Path(os.path.join(root, rel_filepath))

        # If doesn't contain the template matcher, or is the lockfile itself, skip:
        re_groups = template_matcher.search(path.name)
        if rel_filepath.endswith(cleaned_lock_path.name) or re_groups is None:
            continue

        with open(path, "r") as file:
            contents = file.read()

        # If the contents contains the child flag, everything after it should be the path to a template:
        # Making sure to only include if starts with the flag, after whitespace stripping,
        # this prevents the need for escaping the flag in e.g. documentation.
        if contents.strip().startswith(child_flag):
            root_template_path = pathlib.Path(contents.split(child_flag)[1].strip())

            printer(f"Found child at {path}. Root template: {root_template_path}. Compiling...")

            # Raise an error if the path doesn't exist:
            if not root_template_path.exists():
                raise FileNotFoundError(
                    f"Invalid child template. File matched with contents: '{contents}'. Could not find source template at {root_template_path}."
                )

            with open(root_template_path, "r") as file:
                template_contents = file.read().strip()
        else:
            root_template_path = path
            printer(f"Found in-place template at {path}. Compiling...")
            template_contents = contents

        root_templates.add(root_template_path)

        out_path = path.with_name(path.name.replace(re_groups.group(0), ""))
        compiled = environment.from_string(template_contents, globals=context).render()

        # Don't want to re-write files that are the same in the lockfile:
        relative_root_template_path_str = (
            str(root_template_path.relative_to(root))
            if root_template_path.is_absolute()
            else str(root_template_path)
        )
        if out_path.exists() and lockfile.get(relative_root_template_path_str, None) == compiled:
            identical.append(out_path)
            continue

        # Add changes
        lockfile_modified = True
        lockfile_changes[relative_root_template_path_str] = compiled

        outputs.append((out_path, compiled))

    # Remove files from the lockfile that don't seem to exist anymore:
    for path in list(lockfile.keys()):
        if not os.path.exists(os.path.join(root, path)):
            del lockfile[path]
            lockfile_modified = True

    # Apply lockfile changes:
    lockfile.update(lockfile_changes)

    # Write the processed files now everything compiled successfully:
    for path, compiled in outputs:
        printer(f"Writing compiled template to {path}.")
        writer(path, compiled)

    # When changed only to prevent modification when unnecessary, write the updated lockfile, attach onto root if relative:
    if lockfile_modified:
        with open(cleaned_lock_path, "w") as file:
            json.dump(lockfile, file, indent=4)

    return {
        "written": [path for path, _ in outputs],
        "identical": identical,
        "root_templates": list(root_templates),
    }


def _get_lockfile_path(root: StrPath) -> pathlib.Path:
    return pathlib.Path(root).joinpath(f"./{_LOCK_FILENAME}")
