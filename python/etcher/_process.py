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
    context: tp.MutableMapping[str, tp.Any],
    exclude: "tp.Optional[list[str]]" = None,
    jinja: "tp.Optional[dict[str, tp.Any]]" = None,
    gitignore_path: tp.Optional[StrPath] = ".gitignore",
    template_matcher: str = "etch",
    child_flag: str = "!etch:child",
    writer: tp.Callable[[pathlib.Path, str], None] = _default_writer,
) -> "list[pathlib.Path]":
    """Reads the recursive contents of target and writes the compiled files.

    Args:
        root (pathlike object): The target directory to search or direct template or child.
        context (dict): The globals to pass to the Jinja environment.
        exclude (list[str], optional): Exclude files/directories matching these patterns. Read as git-style ignore patterns. Defaults to [].
        jinja (dict[str, Any], optional): Jinja custom config, used when creating the Jinja Environment. https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment. Defaults to {}.
        gitignore_path (pathlike object, optional): Path to the gitignore file. Useful if running from a sub-directory. Set to None to ignore the file. Defaults to '.gitignore'.
        template_matcher (str, optional): The match string to identify in-place templates or placeholders pointing to templates. Defaults to 'etch'. E.g. 'foo.etch.txt'.
        child_flag (str, optional): The match string to identify child templates. Defaults to '!etch:child'. E.g. 'foo.etch.txt' with contents '!etch:child ./templates/template.txt' will be replaced with the compiled contents of 'template.txt'.
        writer (callable, optional): The function to write the compiled files. Useful for testing. Defaults to _default_writer.

    Returns:
        list[pathlib.Path]: The paths of the files that were written.
    """
    environment = Environment(**jinja if jinja is not None else {})  # nosec

    if gitignore_path is not None:
        try:
            with open(gitignore_path, "r") as file:
                gitignore_text = file.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Could not find gitignore file at {gitignore_path}. In config, set 'gitignore_path' to a valid path or set 'gitignore_path=None'."
            ) from e
    else:
        gitignore_text = ""

    # Create a matcher from the gitignore and extra includes which will be negated in search:
    spec = pathspec.PathSpec.from_lines(
        pathspec.patterns.GitWildMatchPattern,  # type: ignore
        gitignore_text.splitlines() + (exclude if exclude is not None else []),
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

    for rel_filepath in iterator:
        if matcher_with_dots not in rel_filepath:
            continue

        filepath = os.path.join(root, rel_filepath) if not is_individual_file else root

        path = pathlib.Path(filepath)
        with open(path, "r") as file:
            contents = file.read()

        # If the contents contains the child flag, everything after it should be the path to a template:
        if child_flag in contents:
            root_template_path = pathlib.Path(contents.split(child_flag)[1].strip())

            # Raise an error if the path doesn't exist:
            if not root_template_path.exists():
                raise FileNotFoundError(
                    f"Invalid child template. File matched with contents: '{contents}'. Could not find source template at {root_template_path}."
                )

            with open(root_template_path, "r") as file:
                template_contents = file.read().strip()
        else:
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
        writer(path, compiled)

    return [path for path, _ in outputs]
