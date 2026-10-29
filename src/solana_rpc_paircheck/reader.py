"""Bounded, read-only loading of local JSON documents."""

import json
import math
import os
from pathlib import Path
import stat

from .core import CheckResult, check_pair

MAX_FILE_BYTES = 1024 * 1024
MAX_DEPTH = 64


class _InputProblem(Exception):
    """A controlled reason code; never contains input data or paths."""


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-standard JSON number")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Unrepresentable JSON number")
    return number


def _check_depth(text: str) -> None:
    """Count containers outside quoted strings before invoking the decoder."""
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{[":
            depth += 1
            if depth > MAX_DEPTH:
                raise _InputProblem("nesting_too_deep")
        elif char in "}]":
            depth -= 1


def _read_json(source: str | Path) -> object:
    raw = os.fspath(source)
    normalized = raw.replace("\\", "/")
    colon = normalized.find(":")
    if normalized.startswith("//") or (colon > 1 and normalized[colon + 1:].startswith("/")):
        raise _InputProblem("non_local_path")

    path = Path(raw)
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise _InputProblem("non_regular_file")
    if info.st_size > MAX_FILE_BYTES:
        raise _InputProblem("file_too_large")

    # Recheck the opened descriptor before any read. Nonblocking prevents a
    # replaced FIFO from hanging on platforms that support O_NONBLOCK.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise _InputProblem("non_regular_file")
        content = stream.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise _InputProblem("file_too_large")

    text = content.decode("utf-8")
    _check_depth(text)
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant, parse_float=_finite_float)


def check_files(request_path: str | Path, response_path: str | Path) -> CheckResult:
    """Read two files without rewriting them or echoing their contents."""
    try:
        request, response = _read_json(request_path), _read_json(response_path)
    except _InputProblem as exc:
        return CheckResult("not_checkable", str(exc))
    except (OSError, ValueError, RecursionError):
        return CheckResult("not_checkable", "unreadable_json")
    return check_pair(request, response)
