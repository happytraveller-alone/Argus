from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value
