import json
import os
import pprint
import subprocess  # nosec
import typing as tp

import yaml

from ._process import StrPath


class Config(tp.TypedDict):
    context: "dict[str, tp.Any]"
    exclude: "list[str]"
    jinja: "dict[str, tp.Any]"
    ignore_files: "list[StrPath]"


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


avail_config_keys = {
    "context",
    "exclude",
    "jinja",
    "ignore_files",
}

CTX_TYPES_T = tp.Literal["static", "cli", "env"]
CTX_TYPES: "set[CTX_TYPES_T]" = {"static", "cli", "env"}
COERCE_T = tp.Literal["str", "int", "float", "bool", "json"]
COERCE_TYPES: "set[COERCE_T]" = {"str", "int", "float", "bool", "json"}


def _process_config_file(contents: tp.Any, printer: tp.Callable[[str], None]) -> Config:
    merged = _dictify(contents)
    for key in merged.keys():
        if key not in avail_config_keys:
            raise ValueError(f"Unknown config key: '{key}'")

    context_vars = _dictify(merged.get("context", {}))

    context: dict[str, tp.Any] = {}
    for key, value in context_vars.items():
        ctx_type: CTX_TYPES_T
        inner_value: tp.Any
        coerce: tp.Optional[COERCE_T] = None
        if (isinstance(value, dict) and "type" in value) or (
            isinstance(value, list) and any(v.get("type", None) for v in value)
        ):
            value = _dictify(value) if not isinstance(value, dict) else value
            if value["type"] not in CTX_TYPES:
                raise ValueError(
                    f"Unknown context var type: '{value['type']}'. Must be one of {CTX_TYPES}. If this is a conflict with your value, don't use shorthand, use instead e.g. type: 'static', value: ..."
                )
            ctx_type = value["type"]
            if "value" not in value:
                raise ValueError(
                    f"Missing 'value' key for context var '{key}' when full 'type' syntax used."
                )
            inner_value = value["value"]
            coerce = value.get("as", None)
            if coerce is not None and coerce not in COERCE_TYPES:
                raise ValueError(
                    f"Unknown coercion type: '{coerce}'. 'as' key must be one of {COERCE_TYPES}."
                )
        else:
            ctx_type = "static"
            inner_value = value

        final_val: tp.Any
        if ctx_type == "static":
            final_val = inner_value
        elif ctx_type == "env":
            env_val = os.environ.get(inner_value, None)
            if env_val is None:
                if isinstance(value, dict) and "default" in value:
                    env_val = value["default"]
                else:
                    raise ValueError(
                        f"Could not find environment variable '{inner_value}' for requested context var '{key}'."
                    )
            final_val = env_val.strip()
        elif ctx_type == "cli":
            cmds = _listify(inner_value)
            for cmd in cmds[:-1]:
                subprocess.run(cmd, check=True, shell=True)  # nosec
            cmd_out = subprocess.check_output(cmds[-1], shell=True).decode()  # nosec
            final_val = cmd_out.strip()
        else:  # pragma: no cover
            raise ValueError(f"Internal err. Unexpected var type: '{ctx_type}'")

        if coerce is not None:
            final_val = _coerce(final_val, coerce)
        context[key] = final_val

    config: Config = {
        "context": context,
        "ignore_files": _listify(merged.get("ignore_files", [])),
        "exclude": _listify(merged.get("exclude", [])),
        "jinja": _dictify(merged.get("jinja", {})),
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


def _coerce(val: tp.Any, coerce: COERCE_T) -> tp.Any:
    err: Exception
    if coerce == "str":
        return str(val)
    elif coerce == "int":
        return round(float(str(val).strip()))
    elif coerce == "float":
        return float(str(val).strip())
    elif coerce == "bool":
        cleaned = str(val).strip().lower()
        is_true = cleaned in ("true", "1", "yes", "y")
        if is_true:
            return True
        elif cleaned in ("false", "0", "no", "n"):
            return False
        else:
            err = ValueError("Did not match true or false pattern.")
    elif coerce == "json":
        try:
            # Yaml parser will have already decoded, allow the dodgy behaviour of not passing in valid json:
            if not isinstance(val, str):
                return val
            return json.loads(val)
        except json.JSONDecodeError as e:
            err = e
    else:  # pragma: no cover
        raise ValueError(f"Internal err. Unexpected coercion type: '{coerce}'")

    raise ValueError(f"Could not convert value '{val}' to type '{coerce}'.") from err
