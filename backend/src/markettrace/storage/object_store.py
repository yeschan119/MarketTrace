"""Local content-addressed object store (S3 abstraction stub).

Raw bytes are saved under ``<object_store_dir>/<key[:2]>/<key>`` where ``key`` is
the sha256 hex digest of the content. This preserves original disclosures and
gives free deduplication. No network access.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["ObjectStore"]


class ObjectStore:
    """Store raw bytes on the local filesystem keyed by sha256."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @staticmethod
    def hash_content(content: bytes | str) -> str:
        """Return the sha256 hex digest of ``content`` (utf-8 if a str)."""

        data = content.encode("utf-8") if isinstance(content, str) else content
        return hashlib.sha256(data).hexdigest()

    def _path_for(self, key: str) -> Path:
        return self.root / key[:2] / key

    def put(self, content: bytes | str) -> str:
        """Write ``content`` and return its sha256 key.

        Idempotent: re-putting identical content overwrites the same file.
        """

        data = content.encode("utf-8") if isinstance(content, str) else content
        key = self.hash_content(data)
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        """Return the stored bytes for ``key``."""

        return self._path_for(key).read_bytes()
