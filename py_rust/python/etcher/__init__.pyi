import typing as tp

def register_function(func: tp.Callable) -> None:
    """Register a custom function to be available in the template context.

    Example:
        >>> @etch.register_function
        ... def adder(a: int, b: int = 3) -> int:
        ...     return a + b
        ...
        >>> "{{ foo(3, b=5) }}"
        8

    Args:
        func (tp.Callable): The function to register.
    """
    ...

def context() -> dict[str, tp.Any]:
    """Return the configured context globals for this run of etch, can be run during custom extensions.

    Example:
        >>> @etch.register_function
        ... def foo() -> str:
        ...     return etch.context()["foo"]
        ...
        >>> "{{ foo() }}" # Assuming the config has foo = {"value": "bar"}
        "bar"

    Returns:
        dict[str, tp.Any]: The configured context globals.
    """
    ...

def _toml_update(
    initial: str, update: tp.Any | None = None, remove: list[list[str]] | None = None
) -> str: ...
def _hash_contents(contents: str) -> str: ...

__version__: str

__all__ = ["__version__", "_hash_contents", "_toml_update"]
