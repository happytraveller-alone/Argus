#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


os.execvp("php", ["php", "/opt/phpstan/phpstan", *sys.argv[1:]])
