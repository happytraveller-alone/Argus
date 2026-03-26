#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

os.execv("/usr/local/bin/opengrep.real", ["opengrep.real", *sys.argv[1:]])
