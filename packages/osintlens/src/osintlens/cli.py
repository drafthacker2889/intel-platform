"""Command-line interface: ``osintlens scan`` and ``osintlens version``."""

import argparse
import sys

from . import __version__
from .analyzer import Analyzer


def _read_input(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    with open(source, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="osintlens", description=__doc__)
    parser.add_argument("--version", action="version", version=f"osintlens {__version__}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Analyze a file (or - for stdin) and print JSON.")
    scan.add_argument("source", help="Path to a text file, or - to read stdin.")
    scan.add_argument("--ml-model", help="Path to a joblib risk model (needs the [ml] extra).")
    scan.add_argument("--no-entities", action="store_true", help="Skip spaCy NER.")
    scan.add_argument("--indent", type=int, default=2, help="JSON indent (default 2).")
    scan.add_argument("--graph", metavar="DOC_ID", help="Emit graph nodes/edges for DOC_ID.")

    args = parser.parse_args(argv)

    if args.command != "scan":
        parser.print_help()
        return 1

    text = _read_input(args.source)
    analyzer = Analyzer(ml_model_path=args.ml_model, enable_entities=not args.no_entities)
    result = analyzer.analyze(text)

    if args.graph:
        import json

        doc_id = args.graph
        print(json.dumps(result.graph(doc_id), ensure_ascii=False, indent=args.indent))
    else:
        print(result.to_json(indent=args.indent))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
