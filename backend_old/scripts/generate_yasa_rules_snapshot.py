#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.yasa_rules_snapshot import (
    YASA_RULES_SNAPSHOT_PATH,
    write_yasa_rules_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate YASA rules snapshot JSON")
    parser.add_argument(
        "--resource-dir",
        required=True,
        help="Path to YASA resource directory that contains checker/checker-config.json",
    )
    parser.add_argument(
        "--output",
        default=str(YASA_RULES_SNAPSHOT_PATH),
        help="Output snapshot path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = write_yasa_rules_snapshot(
        resource_dir=Path(args.resource_dir),
        output_path=Path(args.output),
    )
    print(
        f"wrote YASA snapshot: {args.output} "
        f"(rules={snapshot['count']}, checker_packs={len(snapshot['checker_pack_ids'])})"
    )


if __name__ == "__main__":
    main()
