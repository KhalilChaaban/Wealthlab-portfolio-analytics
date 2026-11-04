"""Command-line entry point: python -m wealthlab --source demo --root ."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import ClientConfig, ResearchConfig
from .data import DataError, DataQualityError
from .pipeline import run_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a multi-asset portfolio and client-goals report.")
    parser.add_argument("--source", choices=["demo", "yahoo"], default=None)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, help="JSON containing research and client sections")
    parser.add_argument("--start", help="Inclusive date, YYYY-MM-DD")
    parser.add_argument("--end", help="Exclusive date, YYYY-MM-DD")
    parser.add_argument("--risk-free-source", choices=["constant", "fred"])
    parser.add_argument("--refresh", action="store_true", help="Explicitly replace matching cached snapshots")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    try:
        payload = json.loads(args.config.read_text()) if args.config else {}
        research = payload.get("research", {})
        client_fields = payload.get("client", {})
        if "one_off_spending" in client_fields:
            client_fields["one_off_spending"] = {int(k): v for k, v in client_fields["one_off_spending"].items()}
        for name, value in {"source": args.source, "start": args.start, "end": args.end,
                            "risk_free_source": args.risk_free_source}.items():
            if value is not None:
                research[name] = value
        result = run_project(ResearchConfig(**research), ClientConfig(**client_fields), args.root, args.refresh)
        print(result.metrics.round(4).to_string())
        print(f"\nReport: {result.report_path}\nRun bundle: {result.output_dir}")
    except (DataError, DataQualityError, ValueError, TypeError, KeyError, OSError) as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
