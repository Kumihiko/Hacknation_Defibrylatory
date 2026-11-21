"""Interfejs wiersza poleceń: `aed run`, `aed sources`."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_sources
from .pipeline import print_report, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aed", description="HeartSpot – agregator otwartych danych o defibrylatorach")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="pobierz źródła, połącz dane i wygeneruj eksporty")
    p_run.add_argument("--offline", action="store_true", help="użyj danych z data/raw zamiast pobierać")
    p_run.add_argument("--enable", default="", help="włącz dodatkowo źródła (id po przecinku), np. sopot,inpost")
    p_run.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("sources", help="wypisz skonfigurowane źródła")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(levelname)s %(message)s", stream=sys.stderr)

    if args.cmd == "sources":
        for s in load_sources(include_disabled=True):
            print(f"{'✔' if s.enabled else '·'} {s.id:24s} {s.license:10s} {s.connector:12s} {s.name}")
        return 0

    enable = [x.strip() for x in args.enable.split(",") if x.strip()]
    stats = run(offline=args.offline, enable=enable)
    print_report(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
