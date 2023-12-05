# ruff: noqa

from importlib.metadata import version

__version__ = version("etcher")

# Import the rust modules and top level fns:
# https://www.maturin.rs/project_layout
from ._rs import *  # type: ignore

# Setup docs and __all__, note this might need modifying if we start adding pure python in here too:
__doc__ = _rs.__doc__  # type: ignore
if hasattr(_rs, "__all__"):  # type: ignore
    __all__ = _rs.__all__  # type: ignore

from ._config import read_config
from ._process import process

__all__ = ["process", "read_config"]
