#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import locale
import os
import sys

PY2 = sys.version_info[0] == 2

if PY2:
    STRING_TYPES = (basestring,)
    TEXT_TYPE = unicode
else:
    STRING_TYPES = (str,)
    TEXT_TYPE = str

JSONDecodeError = getattr(json, "JSONDecodeError", ValueError)
DEFAULT_TEXT_ENCODING = locale.getpreferredencoding(False) or sys.getfilesystemencoding() or "utf-8"


def ensure_text(value, encoding=None):
    if isinstance(value, TEXT_TYPE):
        return value

    if encoding is None:
        encoding = DEFAULT_TEXT_ENCODING

    if PY2 and isinstance(value, str):
        return value.decode(encoding, "replace")

    return TEXT_TYPE(value)


def normalize_data(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[ensure_text(key)] = normalize_data(item)
        return result

    if isinstance(value, list):
        return [normalize_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(normalize_data(item) for item in value)

    if PY2 and isinstance(value, str):
        return ensure_text(value, encoding="utf-8")

    return value


def normalize_namespace(args):
    if not PY2:
        return args

    for key, value in vars(args).items():
        setattr(args, key, _decode_cli_value(value))

    return args


def _decode_cli_value(value):
    if isinstance(value, list):
        return [_decode_cli_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_decode_cli_value(item) for item in value)

    if isinstance(value, str):
        return ensure_text(value)

    return value


def read_text(path, encoding="utf-8"):
    with io.open(path, "r", encoding=encoding) as handle:
        return handle.read()


def write_text(path, text, encoding="utf-8"):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent)

    with io.open(path, "w", encoding=encoding) as handle:
        handle.write(ensure_text(text, encoding=encoding))


def load_json_file(path):
    return json.loads(read_text(path, encoding="utf-8"))


def json_dumps(data):
    return json.dumps(normalize_data(data), ensure_ascii=False, indent=2)


def write_json_file(path, data):
    write_text(path, json_dumps(data) + u"\n", encoding="utf-8")


def print_text(value):
    text = ensure_text(value)
    if not text.endswith(u"\n"):
        text += u"\n"

    if PY2:
        sys.stdout.write(text.encode(sys.stdout.encoding or DEFAULT_TEXT_ENCODING, "replace"))
        return

    sys.stdout.write(text)


def print_json(data):
    print_text(json_dumps(data))
