#!/usr/bin/env python3
import ast
import os
from pathlib import Path
import stat
import sys


def stop(label):
    raise SystemExit("FAIL: Python source check: " + label)


def checked_source(path):
    try:
        metadata = path.lstat()
    except OSError:
        stop("missing source")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        stop("unsafe source " + str(path))
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        stop("source encoding " + str(path))


def main():
    if len(sys.argv) < 2:
        stop("usage: check-python-sources.py SOURCE...")
    paths = [Path(__file__), *(Path(argument) for argument in sys.argv[1:])]
    for path in paths:
        source = checked_source(path)
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError:
            stop("syntax " + str(path))


if __name__ == "__main__":
    main()
