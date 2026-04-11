#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


engine_root = Path("/opt/yasa/engine")
engine = Path("/opt/yasa/bin/yasa-engine")
if not engine.exists():
    print(f"YASA engine wrapper not found: {engine}", file=sys.stderr)
    raise SystemExit(127)

os.chdir(engine_root)
os.execv(str(engine), ["yasa-engine", *sys.argv[1:]])
