import threading
from typing import Dict, List, Optional, Any


class FileStorage:
    """Thread-safe in-memory and metadata storage for uploaded geospatial files."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store: Dict[str, Dict[str, Any]] = {}

    def save(self, file_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._store[file_id] = data

    def update(self, file_id: str, updates: Dict[str, Any]) -> None:
        with self._lock:
            if file_id in self._store:
                self._store[file_id].update(updates)

    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(file_id)

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._store.values())

    def delete(self, file_id: str) -> bool:
        with self._lock:
            if file_id in self._store:
                del self._store[file_id]
                return True
            return False


storage = FileStorage()
