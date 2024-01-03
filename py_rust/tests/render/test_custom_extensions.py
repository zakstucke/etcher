import re
import typing as tp

import pytest

from ..helpers.tmp_file_manager import TmpFileManager
from ..helpers.types import StaticCtx
from ..helpers.utils import check_single

DEFAULT_MODULE = """import etcher as etch
@etch.register_function
def no_args():
    return "I AM A FUNC"

@etch.register_function
def one_arg(arg):
    return "I AM A FUNC {}".format(arg)

@etch.register_function
def add(a, b):
    return a + b

@etch.register_function
def optionals(a, b=None, c=None):
    return "{} {} {}".format(a, b, c)

@etch.register_function
def uses_ctx(var):
    context = etch.context()
    my_var = context["my_var"]
    return "{}{}".format(var, my_var)
"""


@pytest.mark.parametrize(
    "template_src,static_ctx,expected",
    [
        (
            "{{ no_args() }}",
            {},
            "I AM A FUNC",
        ),
        (
            "{{ one_arg('HELLO') }}",
            {},
            "I AM A FUNC HELLO",
        ),
        # Arg from ctx:
        (
            "{{ one_arg(var) }}",
            {"var": {"value": "HELLO"}},
            "I AM A FUNC HELLO",
        ),
        # Non str types:
        (
            "{{ add(1, 2) }}",
            {},
            "3",
        ),
        (
            '{{ add(["foo"], ["bar"]) }}',
            {},
            '["foo", "bar"]',
        ),
        # Optionals:
        (
            "{{ optionals(1) }}",
            {},
            "1 None None",
        ),
        (
            "{{ optionals(1, 2) }}",
            {},
            "1 2 None",
        ),
        (
            "{{ optionals(1, 2, 3) }}",
            {},
            "1 2 3",
        ),
        (
            "{{ optionals(1, c=2) }}",
            {},
            "1 None 2",
        ),
        # Uses global context:
        (
            "{{ uses_ctx('Hello, ') }}",
            {"my_var": {"value": "World!"}},
            "Hello, World!",
        ),
    ],
)
def test_custom_func_various(template_src: str, static_ctx: dict[str, StaticCtx], expected: str):
    """User defined custom functions."""
    with TmpFileManager() as manager:
        func_file = manager.tmpfile(
            DEFAULT_MODULE,
            suffix=".py",
        )

        check_single(
            manager,
            manager.create_cfg(
                {
                    "context": {"static": static_ctx},
                    "engine": {"custom_extensions": [str(func_file)]},
                }
            ),
            template_src,
            expected,
        )


def test_custom_pkg():
    """Confirm a pkg can be used as a custom extension."""
    with TmpFileManager() as manager:
        pkg = manager.tmpdir()
        manager.tmpfile(
            """from . import module_1""",
            full_name="__init__.py",
            parent=pkg,
        )
        manager.tmpfile(
            """import etcher as etch
from . import module_2

@etch.register_function
def func_1():
    return "I AM A FUNC"
""",
            full_name="module_1.py",
            parent=pkg,
        )
        manager.tmpfile(
            """import etcher as etch

@etch.register_function
def func_2():
    return "I AM FUNC_2"
""",
            full_name="module_2.py",
            parent=pkg,
        )

        check_single(
            manager,
            manager.create_cfg(
                {
                    "engine": {"custom_extensions": [str(pkg)]},
                }
            ),
            "{{ func_1() }} {{ func_2() }}",
            "I AM A FUNC I AM FUNC_2",
        )


def test_custom_ext_duplicate_parent():
    """Confirm when 2 files from the same dir are added this doesn't cause any problems with the sys path editing."""
    with TmpFileManager() as manager:
        ext_1 = manager.tmpfile(DEFAULT_MODULE, suffix=".py")
        ext_2 = manager.tmpfile(
            """import etcher as etch
@etch.register_function
def func_2():
    return "I AM FUNC_2"
""",
            suffix=".py",
        )

        check_single(
            manager,
            manager.create_cfg(
                {
                    "engine": {"custom_extensions": [str(ext_1), str(ext_2)]},
                }
            ),
            "{{ no_args() }} {{ func_2() }}",
            "I AM A FUNC I AM FUNC_2",
        )


def test_custom_ext_naming_conflict():
    """Check naming conflicts work as expected.

    - Custom funcs live alongside built in filters, different syntax.
    - Custom funcs override built in funcs, same syntax.
    - Custom func with same name as config var raises err, syntax similar.
    - Duplicate custom funcs raise error.
    """
    # capitalize is a built in filter, custom function should be able to live alongside it as different syntax:
    with TmpFileManager() as manager:
        check_single(manager, manager.create_cfg({}), "{{ 'hello'|capitalize }}", "Hello")

    with TmpFileManager() as manager:
        ext = manager.tmpfile(
            """import etcher as etch
@etch.register_function
def capitalize(var):
    return "I AM A FUNC"
""",
            suffix=".py",
        )
        check_single(
            manager,
            manager.create_cfg({"engine": {"custom_extensions": [str(ext)]}}),
            "{{ capitalize('hello') }}, {{ 'hello'|capitalize }}",
            "I AM A FUNC, Hello",
        )

    # debug() is an in-built function, should be overridden by custom:
    with TmpFileManager() as manager:
        check_single(
            manager,
            manager.create_cfg({"context": {"static": {"foo": {"value": "I AM A STATIC VAR"}}}}),
            "{{ debug(foo) }}",
            '"I AM A STATIC VAR"',
        )

    with TmpFileManager() as manager:
        ext = manager.tmpfile(
            """import etcher as etch
@etch.register_function
def debug(foo):
    return "I AM A FUNC"
""",
            suffix=".py",
        )
        check_single(
            manager,
            manager.create_cfg(
                {
                    "context": {"static": {"foo": {"value": "I AM A STATIC VAR"}}},
                    "engine": {"custom_extensions": [str(ext)]},
                }
            ),
            "{{ debug(foo) }}",
            "I AM A FUNC",
        )

    # Custom func with same name as config var should raise:
    with TmpFileManager() as manager:
        ext = manager.tmpfile(
            """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
            full_name="foo_mod.py",
            suffix=".py",
        )
        with pytest.raises(
            ValueError,
            match="Failed to register custom function: 'foo_mod.foo' as it clashes with a context key.",
        ):
            check_single(
                manager,
                manager.create_cfg(
                    {
                        "context": {"static": {"foo": {"value": "I AM A STATIC VAR"}}},
                        "engine": {"custom_extensions": [str(ext)]},
                    }
                ),
                "{{ foo() }} {{ foo }}",
                "I AM A FUNC I AM A STATIC VAR",
            )

    # Duplicate custom funcs should raise:
    with TmpFileManager() as manager:
        pkg = manager.tmpdir(name="pkg")
        manager.tmpfile(
            """from . import module_1
from . import module_2
""",
            full_name="__init__.py",
            parent=pkg,
        )
        manager.tmpfile(
            """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
            full_name="module_1.py",
            parent=pkg,
        )
        manager.tmpfile(
            """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
            full_name="module_2.py",
            parent=pkg,
        )
        with pytest.raises(
            ValueError,
            match="Failed to register custom function: 'pkg.module_2.foo' as 'foo' is already registered.",
        ):
            check_single(
                manager,
                manager.create_cfg({"engine": {"custom_extensions": [str(pkg)]}}),
                "{{ foo() }}",
                "I AM A FUNC",
            )


def _directory_is_not_a_pkg(manager: TmpFileManager):
    pkg = manager.tmpdir(name="pkg")
    manager.tmpfile(
        """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
        full_name="module_1.py",
        parent=pkg,
    )
    return pkg


@pytest.mark.parametrize(
    "mod_or_lambda,template_src,expected_err",
    [
        # Directory not a pkg:
        (
            _directory_is_not_a_pkg,
            "",
            "pkg' is a directory but does not contain an __init__.py file, not a valid package.",
        ),
        # File not a python file:
        (
            lambda manager: manager.tmpfile(
                """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
                suffix=".sdfsdfsdf",
                parent=manager.tmpdir(),
            ),
            "",
            ".sdfsdfsdf' is not a .py file.",
        ),
        # Syntax error in py file:
        (
            """import etcher as etch
@etch.register_function
foo():
    return "I AM A FUNC"
""",
            "",
            "foo.py'. Error: 'SyntaxError: invalid syntax (foo.py, line 3)'",
        ),
        # Args wrong for custom func:
        (
            """import etcher as etch
@etch.register_function
def foo():
    return "I AM A FUNC"
""",
            "{{ foo('HELLO', bar=3) }}",
            "Failed to call custom filter 'foo'. Err: 'TypeError: foo() got an unexpected keyword argument 'bar'",
        ),
        # Error in custom func:
        (
            """import etcher as etch
@etch.register_function
def foo():
    raise ValueError("I AM AN ERROR")
    return "I AM A FUNC"
""",
            "{{ foo() }}",
            "Failed to call custom filter 'foo'. Err: 'ValueError: I AM AN ERROR'",
        ),
        # Unable to convert return to rust:
        (
            """import etcher as etch
@etch.register_function
def foo():
    class Foo:
        pass
    return Foo()
""",
            "{{ foo() }}",
            "Failed to call custom filter 'foo'. Err: 'Failed to convert python result to a rust-like value: 'unsupported type foo.<locals>.Foo'",
        ),
    ],
)
def test_custom_ext_nice_user_invalid_errs(
    mod_or_lambda: tp.Union[tp.Callable[[TmpFileManager], str], str],
    template_src: str,
    expected_err: str,
):
    """Check nice error messages when somethings wrong with the custom extensions."""
    with TmpFileManager() as manager:
        if isinstance(mod_or_lambda, str):
            ext = manager.tmpfile(mod_or_lambda, full_name="foo.py")
        else:
            ext = mod_or_lambda(manager)

        with pytest.raises(
            ValueError,
            match=re.escape(expected_err),
        ):
            check_single(
                manager,
                manager.create_cfg({"engine": {"custom_extensions": [str(ext)]}}),
                template_src,
                "",
            )


# DONE duplicate pkg names/sys paths
# DONE conflict with ctx/in built filter/in built function
# DONE check module and importing between files works
# DONE check error during func
# DONE check arg error is clear when args weren't accepted by the py func
# DONE check nice error on non python file
# DONE py type interface for register_function and context
# DONE schema descriptions
# DONE init
# DONE version
# DONE setup that are run sequentially (e.g. npm i)
# DONE get everything out into bitbazaar that's possible
# TODO fix schema - not sure why its not working
# TODO on config parsing, make sure the schema directive is at the correct version, update the config file if not
# TODO update static
# TODO allow replacing the matcher
# TODO ruff and pyright checking in tests, connected to requires_python correctly
# TODO think about interop with jinja,cookiecutter,copier,etc
# TODO rust cli variant
# TODO fixed branch locking
# TODO decide and document optimal formatting, probably using scolvins and making sure it can working with custom extensions.
# Fix the windows binary build, if saying usable by all then this will be needed.
