"""Etcher."""

from importlib.metadata import version

__version__ = version("etcher")

from ._config import read_config
from ._process import process
from .main import cli

__all__ = ["process", "read_config", "cli"]
