import os
import pprint
import subprocess  # nosec
import tempfile
import typing as tp

import yaml

from ._process import StrPath


class Config(tp.TypedDict):
    context: "dict[str, tp.Any]"
    exclude: "list[str]"
    jinja: "dict[str, tp.Any]"
    ignore_files: "list[StrPath]"
    template_matcher: str
    child_flag: str


def read_config(
    config_path: StrPath, printer: tp.Callable[[str], None] = lambda msg: None
) -> Config:
    """Reads the config file and returns the config dict.

    Args:
        config_path (str): The path to the config file.
        printer (callable, optional): The function to print messages, i.e. will print when verbose.

    Raises:
        FileNotFoundError: If the config file is not found.
        ValueError: If the config file is not valid or a required env variable is not available.

    Returns:
        Config: The config dict that can be used to populate process() params.
    """
    config_path = str(config_path)

    # Handle mistyping the yml/yaml extension automatically:
    maybe_paths = []
    if config_path.endswith(".yml"):
        maybe_paths.append(config_path)
        maybe_paths.append("{}.yaml".format(_remove_suffix(config_path, ".yml")))
    elif config_path.endswith(".yaml"):
        maybe_paths.append(config_path)
        maybe_paths.append("{}.yml".format(_remove_suffix(config_path, ".yaml")))
    else:
        raise ValueError(
            f"Config file must be a YAML file, with 'yml'/'yaml' ext, not {config_path}."
        )

    for path in maybe_paths:
        if os.path.isfile(path):
            with open(path, "r") as file:
                contents = yaml.safe_load(file)
                return _process_config_file(contents, printer)

    raise FileNotFoundError(f"Could not find config file at {config_path} specified.")


def _remove_suffix(src: str, suffix: str) -> str:
    assert src.endswith(suffix), f"Expected {src} to end with {suffix}"
    return src[: -len(suffix)]


def _process_config_file(contents: tp.Any, printer: tp.Callable[[str], None]) -> Config:
    merged = _dictify(contents)

    setup_commands: "list[str]" = _listify(merged.get("setup", []))

    env_dict: "tp.Union[os._Environ, dict[str, str]]"
    if setup_commands:
        merged_command = " && ".join(setup_commands)

        # Run the merged command, but save the environment to a temporary file:
        tmpfile = tempfile.NamedTemporaryFile()
        try:
            subprocess.run(merged_command + f" && env > {tmpfile.name}", check=True, shell=True)  # nosec
            with open(tmpfile.name, "r") as file:
                env_dict = {}
                for line in file.read().splitlines():
                    key, value = line.split("=", 1)
                    env_dict[key] = value
        finally:
            tmpfile.close()
    else:
        env_dict = os.environ

    context: dict[str, tp.Any] = {}
    context_vars = _listify(merged.get("context", []))

    printer(f"Context vars: {context_vars}")

    for var in context_vars:
        if isinstance(var, dict):
            for key, value in var.items():
                context[key] = value
        else:
            var = str(var)
            if var.strip() == "*":
                context.update(env_dict)
            else:
                try:
                    context[var] = env_dict[var]
                except KeyError as e:
                    raise ValueError(
                        f"Could not find variable '{var}' in environment. Available variables: {env_dict.keys()}"
                    ) from e

    config: Config = {
        "context": context,
        "ignore_files": _listify(merged.get("ignore_files", [])),
        "exclude": _listify(merged.get("exclude", [])),
        "jinja": _dictify(merged.get("jinja", {})),
        "child_flag": merged.get("child_flag", "!etch:child"),
        "template_matcher": merged.get("template_matcher", "etch"),
    }

    printer(f"Config: \n{pprint.pformat(config)}")

    return config


def _listify(obj: tp.Any) -> tp.Any:
    assert isinstance(obj, (str, list)), f"Expected str or list, not {type(obj)}. Output: '{obj}'"

    if isinstance(obj, list):
        return obj
    else:
        return obj.splitlines()


def _dictify(contents: tp.Any) -> "dict[str, tp.Any]":
    assert (
        isinstance(contents, (dict, list)) or contents is None
    ), f"Expected dict, list, or None, not {type(contents)}. Output: '{contents}'"

    if not contents:
        contents = []
    elif isinstance(contents, dict):
        contents = [contents]

    merged = {}
    for item in contents:
        merged.update(item)

    return merged
