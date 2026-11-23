"""List or run registered checks on supplied local evidence."""

import argparse
from dataclasses import asdict
import json

from .evidence import EvidenceBundle
from .registry import registered_checks, run_checks


def _metadata(check):
    return {"id": check.id, "stack": check.stack, "title": check.title,
            "basis": asdict(check.basis), "needs": [asdict(need) for need in check.needs]}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m checks")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List registered checks.")
    run = commands.add_parser("run", help="Read evidence from a local directory.")
    run.add_argument("evidence_dir")
    run.add_argument("--packet", help="Read the collector packet from this local JSON file.")
    args = parser.parse_args(argv)
    if args.command == "list":
        rows = [_metadata(check) for check in registered_checks()]
    else:
        try:
            bundle = EvidenceBundle.from_directory(args.evidence_dir, packet_path=args.packet)
        except (OSError, ValueError, RecursionError):
            parser.error("Supply a readable local evidence directory and a valid collector packet, if provided.")
        rows = [{**_metadata(item.check), **asdict(item.result)} for item in run_checks(bundle)]
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
