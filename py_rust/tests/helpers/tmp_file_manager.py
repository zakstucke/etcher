import os
import pathlib
import shutil
import tempfile
import typing as tp

import etcher as etch

from .types import InputConfig


class TmpFileManager:
    """A context manager for managing temporary files and directories.

    Usage:
    with TmpFileManager() as manager:
        file_path = manager.tmpfile(content="Hello, temporary file!")
        dir_path = manager.tmp_dir()
    """

    root_dir: str
    files_created: int = 0
    dirs_created: int = 0

    def __init__(self):
        self.root_dir = tempfile.mkdtemp()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore
        self.cleanup()

    def tmpfile(
        self,
        content: str,
        suffix: tp.Optional[str] = None,
        parent: tp.Optional[tp.Union[str, pathlib.Path]] = None,
        full_name: tp.Optional[str] = None,
    ) -> pathlib.Path:
        """Create a temporary file.

        Parameters:
        - content: The content to write to the temporary file.
        - suffix: Optional suffix to append to the temporary file. Otherwise will be created with tempfile.
        - parent: Optional directory to create the temporary file in. Otherwise will be placed in root.
        - full_name: Optional full name of the temporary file, overrides suffix. Otherwise will be created with tempfile.

        Returns:
        - The path to the created temporary file.
        """
        if parent is None:
            parent = self.root_dir

        tmp_file = tempfile.NamedTemporaryFile(delete=False, dir=parent, suffix=suffix)
        with open(tmp_file.name, "w") as file:
            file.write(content)

        final_path = pathlib.Path(tmp_file.name)
        if full_name is not None:
            os.rename(tmp_file.name, os.path.join(parent, full_name))
            final_path = pathlib.Path(os.path.join(parent, full_name))

        self.files_created += 1

        return final_path

    def create_cfg(self, config: InputConfig) -> pathlib.Path:
        return self.tmpfile(
            etch._toml_update("", update=config),
            suffix=".toml",
        )

    def tmpdir(
        self, parent: tp.Optional[str] = None, name: tp.Optional[str] = None
    ) -> pathlib.Path:
        """Create a temporary directory.

        Parameters:
        - parent: Optional directory to create the temporary directory in. Otherwise will be placed in root.

        Returns:
        - The path to the created temporary directory.
        """
        if parent is None:
            parent = self.root_dir

        tmp_dir = tempfile.mkdtemp(dir=parent)

        if name is not None:
            os.rename(tmp_dir, os.path.join(parent, name))
            tmp_dir = os.path.join(parent, name)

        self.dirs_created += 1
        return pathlib.Path(tmp_dir)

    def writer(self, path: pathlib.Path, content: str):
        """A replacement for the default write function in process(). To allow for temporary creations during tests."""
        # Make sure the path is inside of the root directory:
        if not str(path).startswith(self.root_dir):
            raise ValueError(
                f"TmpFileManager: Path {path} is not inside of the root directory {self.root_dir}."
            )

        with open(path, "w") as file:
            file.write(content)

        self.files_created += 1

    def cleanup(self):
        """Clean up created temporary files and directories."""
        shutil.rmtree(self.root_dir)
