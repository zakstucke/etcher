"""Test all the builtins that aren't enabled by default in minijinja, added from minijinja-contrib or included in etch directly."""

import datetime as dt
import re
import time
import typing as tp

import pytest

from ..helpers.tmp_file_manager import TmpFileManager
from ..helpers.types import StaticCtx
from ..helpers.utils import check_single


class BuiltinTestcase(tp.TypedDict):
    input: str
    # Either the output to expect, or a function that returns True if valid when passed the rendered result:
    expected: tp.Union[str, tp.Callable[[str], bool]]
    static_ctx: tp.NotRequired[dict[str, StaticCtx]]
    # Defaults to "txt"
    file_type: tp.NotRequired[str]


class BuiltinBase(tp.TypedDict):
    description: str
    tests: list[BuiltinTestcase]


class FunctionBuiltin(BuiltinBase):
    pass


class FilterBuiltin(BuiltinBase):
    pass


class AllBuiltins(tp.TypedDict):
    functions: dict[str, FunctionBuiltin]
    filters: dict[str, FilterBuiltin]


# Defining with descriptions all inplace, to allow easy documentation building.
ENGINE_BUILTINS: AllBuiltins = {
    "filters": {
        # https://docs.rs/minijinja/latest/minijinja/filters/fn.items.html
        "items": {
            "description": "Returns a list of pairs (items) from a mapping.\nThis can be used to iterate over keys and values of a mapping at once. This will use the original order of the map.",
            "tests": [
                {
                    "static_ctx": {"users": {"value": {"foo": "bar", "ree": "roo"}}},
                    "input": "{% for key, value in users|items %}{{ key }}:{{ value }}\n{% endfor %}",
                    "expected": "foo:bar\nree:roo\n",
                },
                # Make sure workarounds for other chars e.g. @ work using json coercion:
                # Note this is being done on a json file to confirm works in there, historic issue of minijinja escaping values in json files specifically:
                {
                    "static_ctx": {
                        "aliases": {
                            "value": '{ "@root": "./example_project_js", "@scripts": "./scripts" }',
                            "coerce": "json",
                        }
                    },
                    "input": "{% for key, value in aliases|items %}{{ key }}:{{ value }}\n{% endfor %}",
                    "expected": "@root:./example_project_js\n@scripts:./scripts\n",
                    "file_type": "json",
                },
            ],
        },
        # Only included as extra minijinja feature:
        # https://docs.rs/minijinja/latest/minijinja/filters/fn.tojson.html
        "tojson": {
            "description": "Dumps a value to JSON.\nThe resulting value is safe to use in HTML as well as it will not contain any special HTML characters. The optional parameter to the filter can be set to true to enable pretty printing. Not that the \" character is left unchanged as it's the JSON string delimiter. If you want to pass JSON serialized this way into an HTTP attribute use single quoted HTML attributes:",
            "tests": [
                {
                    "static_ctx": {"users": {"value": ["foo@bar.com", "ree@roo.com"]}},
                    "input": "{{ users|tojson }}",
                    "expected": '["foo@bar.com","ree@roo.com"]',
                },
            ],
        },
        # Only included as extra minijinja feature:
        # https://docs.rs/minijinja/latest/minijinja/filters/fn.tojson.html
        "urlencode": {
            "description": "URL encodes a value.\nIf given a map it encodes the parameters into a query set, otherwise it encodes the stringified value. If the value is none or undefined, an empty string is returned.",
            "tests": [
                {
                    "input": '/search?{{ {"q": "my search", "lang": "fr"}|urlencode }}',
                    "expected": "/search?q=my%20search&lang=fr",
                },
            ],
        },
        # https://docs.rs/minijinja-contrib/latest/minijinja_contrib/filters/fn.pluralize.html
        "pluralize": {
            "description": 'Returns a plural suffix if the value is not 1, "1", or an object of length 1.\nBy default, the plural suffix is "s" and the singular suffix is empty (""). You can specify a singular suffix as the first argument (or None, for the default). You can specify a plural suffix as the second argument (or None, for the default).',
            "tests": [
                {
                    "static_ctx": {"users": {"value": ["foo@bar.com", "ree@roo.com"]}},
                    "input": "{{ users|length }} user{{ users|pluralize }}.",
                    "expected": "2 users.",
                },
                {
                    "static_ctx": {"users": {"value": ["foo@bar.com"]}},
                    "input": "{{ users|length }} user{{ users|pluralize }}.",
                    "expected": "1 user.",
                },
                {
                    "static_ctx": {"entities": {"value": ["foo@bar.com", "ree@roo.com"]}},
                    "input": '{{ entities|length }} entit{{ entities|pluralize("y", "ies") }}.',
                    "expected": "2 entities.",
                },
                {
                    "static_ctx": {"platypuses": {"value": ["foo@bar.com", "ree@roo.com"]}},
                    "input": '{{ platypuses|length }} platypus{{ platypuses|pluralize(None, "es") }}.',
                    "expected": "2 platypuses.",
                },
            ],
        },
        # https://docs.rs/minijinja-contrib/latest/minijinja_contrib/filters/fn.dateformat.html
        "dateformat": {
            "description": 'Formats a timestamp as date.\nThe value needs to be a unix timestamp, or a parsable string (ISO 8601) or another format supported by `chrono` or `time`. If the string does not include time information, then timezone adjustments are not performed.\nThe filter accepts a keyword argument `format` to influence the format. The default format is "medium". The default is taken from the global variable in the template context: `DATE_FORMAT`.',
            "tests": [
                {
                    "input": "{{ now()|dateformat }}",
                    # Rust doesn't include the 0 before days like python does, making python act the same:
                    "expected": "{month_name} {dt.day} {dt.year}".format(
                        month_name=dt.datetime.utcnow().strftime("%b"),
                        dt=dt.datetime.utcnow(),
                    ),
                },
                {
                    "input": "{{ \"2018-04-01T15:20:15-07:00\"|dateformat(format='short') }}",
                    "expected": "2018-04-01",
                },
            ],
        },
        # https://docs.rs/minijinja-contrib/latest/minijinja_contrib/filters/fn.timeformat.html
        "timeformat": {
            "description": 'Formats a timestamp as time.\nThe value needs to be a unix timestamp, or a parsable string (ISO 8601) or another format supported by `chrono` or `time`. If the string does not include time information, then timezone adjustments are not performed.\nThe filter accepts a keyword argument `format` to influence the format. The default format is "medium". The default is taken from the global variable in the template context: `TIME_FORMAT`.',
            "tests": [
                {
                    "input": "{{ now()|timeformat }}",
                    "expected": dt.datetime.utcnow().strftime("%H:%M"),
                },
                {
                    "input": "{{ \"2018-04-01T15:20:15-07:00\"|timeformat(format='long') }}",
                    "expected": "15:20:15",
                },
            ],
        },
        # https://docs.rs/minijinja-contrib/latest/minijinja_contrib/filters/fn.datetimeformat.html
        "datetimeformat": {
            "description": 'Formats a timestamp as datetime.\nThe value needs to be a unix timestamp, or a parsable string (ISO 8601) or another format supported by `chrono` or `time`. If the string does not include time information, then timezone adjustments are not performed.\nThe filter accepts a keyword argument `format` to influence the format. The default format is "medium". The default is taken from the global variable in the template context: `DATETIME_FORMAT`.',
            "tests": [
                {
                    "input": "{{ now()|datetimeformat }}",
                    # Rust doesn't include the 0 before days like python does, making python act the same:
                    "expected": "{month_name} {dt.day} {dt.year} {dt.hour}:{dt.minute}".format(
                        month_name=dt.datetime.utcnow().strftime("%b"),
                        dt=dt.datetime.utcnow(),
                    ),
                },
                {
                    "input": "{{ \"2018-04-01T15:20:15-07:00\"|datetimeformat(format='short') }}",
                    "expected": "2018-04-01 15:20",
                },
            ],
        },
    },
    "functions": {
        # https://docs.rs/minijinja-contrib/latest/minijinja_contrib/globals/fn.now.html
        "now": {
            "description": "Returns the current time in UTC as unix timestamp. To format this timestamp, use the `datetimeformat` filter.",
            "tests": [
                {
                    "input": "{{ now() }}",
                    # Make sure 10 digits (seconds) is returned before the dot e.g. 1702207289.952969:
                    "expected": lambda output: re.match(r"\d{10}.", output) is not None,
                }
            ],
        }
    },
}


def wait_for_new_minute():
    """If less than a second before the next minute, wait for the next minute to start.

    Prevents inaccuracy in tests that rely on the current minute. Not easy to mock as going between python and rust.
    """
    now = dt.datetime.utcnow()
    if now.second > 58:
        time.sleep(60 - now.second)


@pytest.mark.parametrize(
    "name,info,test_info",
    [
        (name, info, test)
        for name, info in ENGINE_BUILTINS["functions"].items()
        for test in info["tests"]
    ],
)
def test_extra_builtin_functions(name: str, info: FilterBuiltin, test_info: BuiltinTestcase):
    """Confirm all builtin expected filters work."""
    with TmpFileManager() as manager:
        wait_for_new_minute()
        check_single(
            manager,
            manager.create_cfg({"context": {"static": test_info.get("static_ctx", {})}}),
            test_info["input"],
            test_info["expected"]
            if isinstance(test_info["expected"], str)
            else test_info["expected"],
            file_type=test_info.get("file_type", "txt"),
        )


@pytest.mark.parametrize(
    "name,info,test_info",
    [
        (name, info, test)
        for name, info in ENGINE_BUILTINS["filters"].items()
        for test in info["tests"]
    ],
)
def test_extra_builtin_filters(name: str, info: FilterBuiltin, test_info: BuiltinTestcase):
    """Confirm all builtin expected filters work."""
    with TmpFileManager() as manager:
        wait_for_new_minute()
        check_single(
            manager,
            manager.create_cfg({"context": {"static": test_info.get("static_ctx", {})}}),
            test_info["input"],
            test_info["expected"]
            if isinstance(test_info["expected"], str)
            else test_info["expected"],
            file_type=test_info.get("file_type", "txt"),
        )
