"""Token storage and OAuth login helpers."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class TokenStore:
    """JSON file of tokens keyed by provider name, written atomically."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def get(self, name: str) -> dict | None:
        with self._lock:
            return self._read().get(name)

    def put(self, name: str, token: dict) -> None:
        with self._lock:
            data = self._read()
            data[name] = token
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tokens-")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
