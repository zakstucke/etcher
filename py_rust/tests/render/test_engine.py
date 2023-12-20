import os
import re
import typing as tp
from pathlib import Path

import pytest

from ..helpers.tmp_file_manager import TmpFileManager
from ..helpers.types import Engine, InputConfig
from ..helpers.utils import check_single


@pytest.mark.parametrize(
    "other_tmpl_creator, other_tmpl_path_creator",
    [
        # Absolute:
        (
            lambda manager: manager.tmpfile(content="Hello, {{ var }}!", suffix=".txt"),
            lambda other_tmpl: str(other_tmpl),
        ),
        # Relative:
        (
            lambda manager: manager.tmpfile(content="Hello, {{ var }}!", suffix=".txt"),
            lambda other_tmpl: os.path.join(".", other_tmpl.name),
        ),
    ],
)
def test_include_other_template(
    other_tmpl_creator: tp.Callable[[TmpFileManager], Path],
    other_tmpl_path_creator: tp.Callable[[Path], str],
):
    """Other arbitrary files can be included in a template.

    - They do not need the etch suffix/matcher
    - If relative, they are resolved based from the root dir, not the config file.
    - Absolute paths also work.
    """
    with TmpFileManager() as manager:
        with TmpFileManager() as other_manager:
            other_tmpl = other_tmpl_creator(manager)
            other_tmpl_path = other_tmpl_path_creator(other_tmpl)
            check_single(
                manager,
                # Putting config in a different dir to make sure they're not resolving relative to the config file:
                other_manager.create_cfg({"context": {"static": {"var": {"value": "World"}}}}),
                f"{{% include '{other_tmpl_path}' %}}",
                "Hello, World!",
            )


@pytest.mark.parametrize(
    "template_src,config,expected",
    [
        # Macro no params:
        (
            "{% macro foo() %}I AM A MACRO{% endmacro %}{{ foo() }}",
            {},
            "I AM A MACRO",
        ),
        # Macro with params:
        (
            "{% macro hello(name) %}Hello {{name}}!{% endmacro %}{{ hello(name_var) }}",
            {"context": {"static": {"name_var": {"value": "Bob"}}}},
            "Hello Bob!",
        ),
        # Slices:
        (
            "{{ var[1:3] }} {% for i in var[1:3] %}{{i}}{% endfor %}",
            {"context": {"static": {"var": {"value": range(4)}}}},
            "[1, 2] 12",
        ),
    ],
)
def test_engine_misc_syntax(template_src: str, config: InputConfig, expected: str):
    """Confirm random native rendering functionality works."""
    with TmpFileManager() as manager:
        check_single(manager, manager.create_cfg(config), template_src, expected)


DEFAULT_TEMPLATE_SRC = "Hello, {{ var }}!{# this is an ignored comment #}\nmybool is {% if mybool %}True{% else %}False{% endif %}\n"


@pytest.mark.parametrize(
    "template_src,engine_config,expected",
    [
        # Default configuration: newlines kept, default syntax matchers (allow undefined is False but will be tested in separate test as hard to add in here):
        (
            DEFAULT_TEMPLATE_SRC,
            {},
            "Hello, World!\nmybool is True\n",
        ),
        # Should be the same when full engine defaults are specified:
        (
            DEFAULT_TEMPLATE_SRC,
            {
                "variable_start": "{{",
                "variable_end": "}}",
                "block_start": "{%",
                "block_end": "%}",
                "comment_start": "{#",
                "comment_end": "#}",
                "keep_trailing_newline": True,
                "allow_undefined": False,
            },
            "Hello, World!\nmybool is True\n",
        ),
        # Newline should be stripped when keep_trailing_newline is False:
        (
            DEFAULT_TEMPLATE_SRC,
            {"keep_trailing_newline": False},
            "Hello, World!\nmybool is True",
        ),
        # Custom syntax matchers should work:
        (
            "Hello, [< var >]![# this is an ignored comment #]\nmybool is [? if mybool ?]True[? else ?]False[? endif ?]\n",
            {
                "variable_start": "[<",
                "variable_end": ">]",
                "block_start": "[?",
                "block_end": "?]",
                "comment_start": "[#",
                "comment_end": "#]",
            },
            "Hello, World!\nmybool is True\n",
        ),
        # With custom matchers the default template should come out identical as no longer matches:
        (
            DEFAULT_TEMPLATE_SRC,
            {
                "variable_start": "[<",
                "variable_end": ">]",
                "block_start": "[?",
                "block_end": "?]",
                "comment_start": "[#",
                "comment_end": "#]",
            },
            DEFAULT_TEMPLATE_SRC,
        ),
    ],
)
def test_engine_config(template_src: str, engine_config: Engine, expected: str):
    """Confirm engine defaults are as expected & all overrides work."""
    with TmpFileManager() as manager:
        check_single(
            manager,
            manager.create_cfg(
                {
                    "context": {"static": {"var": {"value": "World"}, "mybool": {"value": True}}},
                    "engine": engine_config,
                }
            ),
            template_src,
            expected,
        )


@pytest.mark.parametrize(
    "template_src,config,expected,expected_is_err_match",
    [
        # Working example when no undefineds:
        (
            "Hello, {{ var }}! My name is {{ name }}!",
            {
                "context": {
                    "static": {"var": {"value": "World"}, "name": {"value": "Bob"}},
                }
            },
            "Hello, World! My name is Bob!",
            False,
        ),
        # Should raise when name in undefined as by default banned:
        (
            "Hello, {{ var }}! My name is {{ name }}!",
            {"context": {"static": {"var": {"value": "World"}}}},
            "Failed to render template: 'undefined value",
            True,
        ),
        # Should also raise when specifically set:
        (
            "Hello, {{ var }}! My name is {{ name }}!",
            {
                "context": {"static": {"var": {"value": "World"}}},
                "engine": {
                    "allow_undefined": False,
                },
            },
            "Failed to render template: 'undefined value",
            True,
        ),
        # Should be fine when allowed:
        (
            "Hello, {{ var }}! My name is {{ name }}!",
            {
                "context": {"static": {"var": {"value": "World"}}},
                "engine": {
                    "allow_undefined": True,
                },
            },
            "Hello, World! My name is !",
            False,
        ),
    ],
)
def test_allow_undefined(
    template_src: str, config: InputConfig, expected: str, expected_is_err_match: bool
):
    """Check errors on unknown context when no allow_defined or allow_defined is False, but when true should work fine."""
    with TmpFileManager() as manager:
        if not expected_is_err_match:
            check_single(manager, manager.create_cfg(config), template_src, expected)
        else:
            with pytest.raises(ValueError, match=re.escape(expected)):
                check_single(manager, manager.create_cfg(config), template_src, expected)
