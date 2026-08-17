import threading
from typing import Optional

_cache: dict[str, dict[int, dict[int, bytes]]] = {}
_lock = threading.Lock()


def put(task_id: str, page: int, index: int, data: bytes) -> None:
    with _lock:
        _cache.setdefault(task_id, {}).setdefault(page, {})[index] = data


def get(task_id: str, page: int, index: int) -> Optional[bytes]:
    with _lock:
        return _cache.get(task_id, {}).get(page, {}).get(index)
