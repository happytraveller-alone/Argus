#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


existing_pythonpath = os.environ.get("PYTHONPATH", "")
prefix = "/opt/yasa/engine/deps/uast4py-src"
os.environ["PYTHONPATH"] = f"{prefix}:{existing_pythonpath}" if existing_pythonpath else prefix
python_bin = "/opt/yasa/uast4py-venv/bin/python"
os.execv(python_bin, [python_bin, "-m", "uast.builder", *sys.argv[1:]])
