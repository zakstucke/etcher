import os
import pathlib
import typing as tp

import pathspec
from jinja2 import Environment

StrPath = tp.Union[str, os.PathLike[str]]


def _default_writer(path: pathlib.Path, contents: str) -> None:
    with open(path, "w") as file:
        file.write(contents)


def process(
    root: StrPath,
    context: "dict[str, tp.Any]",
    exclude: "tp.Optional[list[str]]" = None,
    jinja: "tp.Optional[dict[str, tp.Any]]" = None,
    ignore_files: "tp.Optional[list[StrPath]]" = None,
    template_matcher: str = "etch",
    child_flag: str = "!etch:child",
    writer: tp.Callable[[pathlib.Path, str], None] = _default_writer,
    printer: tp.Callable[[str], None] = lambda msg: None,
) -> "list[pathlib.Path]":
    """Reads the recursive contents of target and writes the compiled files.

    Args:
        root (pathlike object): The target directory to search or direct template or child.
        context (dict): The globals to pass to the Jinja environment.
        exclude (list[str], optional): Exclude files/directories matching these patterns. Read as git-style ignore patterns. Defaults to [].
        jinja (dict[str, Any], optional): Jinja custom config, used when creating the Jinja Environment. https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment. Defaults to {}.
        ignore_files (list[pathlike object], optional): Paths to git-style ignore files, e.g. '.gitignore' to use for exclude patterns. Defaults to None.
        template_matcher (str, optional): The match string to identify in-place templates or placeholders pointing to templates. Defaults to 'etch'. E.g. 'foo.etch.txt'.
        child_flag (str, optional): The match string to identify child templates. Defaults to '!etch:child'. E.g. 'foo.etch.txt' with contents '!etch:child ./templates/template.txt' will be replaced with the compiled contents of 'template.txt'.
        writer (callable, optional): The function to write the compiled files. Useful for testing. Defaults to _default_writer.
        printer (callable, optional): The function to print messages, i.e. will print when verbose. Defaults to lambda msg: None.

    Returns:
        list[pathlib.Path]: The paths of the files that were written.
    """
    environment = Environment(**jinja if jinja is not None else {})  # nosec

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

    matcher_with_dots = f".{template_matcher}."

    # Find and compile all the templates:
    outputs: "list[tuple[pathlib.Path, str]]" = []
    if os.path.isfile(root):
        # The match_tree_files fn doesn't work with files, so check in here and return if doesn't match:
        if len(list(spec.match_files([root], negate=True))) == 0:
            return []
        # The match_tree_files fn also returns relative paths to root, so mark this a root individual file to handle accordingly later:
        is_individual_file = True
        iterator = [str(root)]
    else:
        is_individual_file = False
        iterator = spec.match_tree_files(root, negate=True)

    for index, rel_filepath in enumerate(iterator):
        if index % 100 == 0:
            printer(f"Checked {index} non-ignored files. Currently checking {rel_filepath}...")

        if matcher_with_dots not in rel_filepath:
            continue

        filepath = os.path.join(root, rel_filepath) if not is_individual_file else root

        path = pathlib.Path(filepath)
        with open(path, "r") as file:
            contents = file.read()

        # If the contents contains the child flag, everything after it should be the path to a template:
        if child_flag in contents:
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
            printer(f"Found in-place template at {path}. Compiling...")
            template_contents = contents

        out_path = path.with_name(path.name.replace(matcher_with_dots, "."))
        outputs.append(
            (
                out_path,
                environment.from_string(template_contents, globals=context).render(),
            )
        )

    # Write the processed files now everything compiled successfully:
    for path, compiled in outputs:
        printer(f"Writing compiled template to {path}.")
        writer(path, compiled)

    return [path for path, _ in outputs]
