#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


engine_bin = Path("/opt/yasa/bin/yasa-engine.real")
if not engine_bin.exists():
    print(f"yasa-engine binary not found: {engine_bin}", file=sys.stderr)
    raise SystemExit(127)

os.execv(str(engine_bin), ["yasa-engine.real", *sys.argv[1:]])
