import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


class WorkspaceStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def task_root(self, task_id: str) -> Path:
        return self.resolve_key(PurePosixPath("tasks", task_id).as_posix())

    def resolve_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or ".." in key.parts:
            raise ValueError("invalid storage key")
        path = self.root.joinpath(*key.parts).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("storage key escapes workspace")
        return path

    def write_json(self, storage_key: str, payload: Any) -> tuple[int, str]:
        path = self.resolve_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        path.write_bytes(content)
        return len(content), hashlib.sha256(content).hexdigest()

    def write_text(self, storage_key: str, content: str) -> tuple[int, str]:
        path = self.resolve_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        path.write_bytes(encoded)
        return len(encoded), hashlib.sha256(encoded).hexdigest()

    def sha256(self, storage_key: str) -> str:
        digest = hashlib.sha256()
        with self.resolve_key(storage_key).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
