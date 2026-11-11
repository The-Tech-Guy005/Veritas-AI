"""
Persistent Task Store
Provides thread-safe and restart-persistent storage for Master Agent orchestration tasks.
Saves task state, progress updates, execution traces, and results to disk.
"""

import os
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from threading import Lock

from app.config import settings

_TASK_DIR = Path(settings.data_dir) / "tasks"
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()


def _ensure_dir():
    _TASK_DIR.mkdir(parents=True, exist_ok=True)


def _get_task_path(task_id: str) -> Path:
    _ensure_dir()
    # Strip any directory traversal characters
    safe_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))
    return _TASK_DIR / f"{safe_id}.json"


def save_task(task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves a task record to memory and persists to disk as JSON.
    """
    with _LOCK:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "created_at" not in data:
            data["created_at"] = now
        data["updated_at"] = now
        data["task_id"] = task_id

        # Update in-memory cache
        _MEMORY_CACHE[task_id] = data

        # Persist to disk
        file_path = _get_task_path(task_id)
        try:
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            temp_path.replace(file_path)
        except Exception as exc:
            # Still maintain in-memory if disk write encounters an issue
            pass

        return data


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves task data from in-memory cache, or falls back to disk
    so task state survives server restarts.
    """
    with _LOCK:
        if task_id in _MEMORY_CACHE:
            return _MEMORY_CACHE[task_id]

        file_path = _get_task_path(task_id)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _MEMORY_CACHE[task_id] = data
                    return data
            except Exception:
                return None
        return None


def update_task_progress(
    task_id: str,
    progress: int,
    stage: str,
    message: str,
    status: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Updates progress percentage, stage, and log messages for an active or completed task.
    """
    task = get_task(task_id) or {"task_id": task_id, "trace": []}
    task["progress"] = max(0, min(100, progress))
    task["stage"] = stage
    task["message"] = message
    if status:
        task["status"] = status
    elif "status" not in task:
        task["status"] = "in_progress"

    if extra_data:
        task.update(extra_data)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if "trace" not in task:
        task["trace"] = []
    task["trace"].append({
        "stage": stage,
        "progress": progress,
        "detail": message,
        "timestamp": now,
        "data": extra_data or {}
    })

    return save_task(task_id, task)


def list_all_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns summary list of all tasks persisted across restarts.
    """
    _ensure_dir()
    tasks: List[Dict[str, Any]] = []

    # Read from disk to guarantee all historical tasks are included
    try:
        files = sorted(_TASK_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
        for f in files[:limit]:
            task_id = f.stem
            t = get_task(task_id)
            if t:
                tasks.append({
                    "task_id": t.get("task_id", task_id),
                    "query": t.get("query", ""),
                    "status": t.get("status", "unknown"),
                    "progress": t.get("progress", 0),
                    "stage": t.get("stage", "completed" if t.get("status") == "completed" else "unknown"),
                    "message": t.get("message", ""),
                    "created_at": t.get("created_at", ""),
                    "updated_at": t.get("updated_at", ""),
                    "report_id": t.get("report_id"),
                })
    except Exception:
        pass

    return tasks


def delete_task(task_id: str) -> bool:
    """
    Deletes task from disk and cache.
    """
    with _LOCK:
        _MEMORY_CACHE.pop(task_id, None)
        file_path = _get_task_path(task_id)
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception:
                return False
        return False
