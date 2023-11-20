"""Etcher."""

from importlib.metadata import version

__version__ = version("etcher")

from ._process import process

__all__ = ["process"]
