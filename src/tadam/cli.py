"""The `tadam` command line."""
from __future__ import annotations

import argparse
from typing import Sequence

from tadam import __version__, doctor


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tadam", description="TadamShow Studio")
    ap.add_argument("--version", action="version", version=f"tadam {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("doctor", help="check that everything the studio needs is installed")
    a = ap.parse_args(argv)
    if a.command == "doctor":
        return doctor.main()
    ap.print_help()
    return 0
