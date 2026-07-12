"""Command-line interface: ``synthreat generate``."""

import argparse
import sys

from . import __version__
from .generator import ThreatDataGenerator
from .vocab import LANGUAGES


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="synthreat", description=__doc__)
    parser.add_argument("--version", action="version", version=f"synthreat {__version__}")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate a dataset and write it to a file (or stdout).")
    gen.add_argument("-n", "--per-language", type=int, default=5000,
                     help="Samples per language (default 5000).")
    gen.add_argument("-o", "--output", help="Output path (.json or .jsonl). Omit to print to stdout.")
    gen.add_argument("--seed", type=int, help="RNG seed for reproducible output.")
    gen.add_argument("--languages", nargs="+", choices=LANGUAGES, help="Subset of languages.")
    gen.add_argument("--inject-iocs", type=float, default=0.0,
                     help="Fraction 0.0-1.0 of samples enriched with ground-truth IOCs.")
    gen.add_argument("--format", choices=["json", "jsonl"], help="Force output format.")
    gen.add_argument("--no-shuffle", action="store_true", help="Keep samples grouped by language/label.")

    args = parser.parse_args(argv)
    if args.command != "generate":
        parser.print_help()
        return 1

    generator = ThreatDataGenerator(
        seed=args.seed, languages=args.languages, inject_iocs=args.inject_iocs
    )
    dataset = generator.generate(samples_per_language=args.per_language, shuffle=not args.no_shuffle)

    if args.output:
        path = dataset.save(args.output, fmt=args.format)
        stats = dataset.stats()
        print(f"Wrote {stats['total']} samples to {path}", file=sys.stderr)
        print(f"  by language: {stats['by_language']}", file=sys.stderr)
        print(f"  by label:    {stats['by_label']}", file=sys.stderr)
        if stats["with_iocs"]:
            print(f"  with IOCs:   {stats['with_iocs']}", file=sys.stderr)
    else:
        print(dataset.to_jsonl() if args.format == "jsonl" else dataset.to_json())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
