"""Global task store for async AI generation tasks.
Thread-safe dictionary storing task status for frontend polling.
Adapts PythonAnywhere free tier: single web worker, no SSE."""
import threading
import uuid
from datetime import datetime


class TaskStore:
    """Thread-safe async task storage."""

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()

    def create(self, task_type, requirement_id=None, user_id=None):
        """Create a new task, return task_id."""
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "requirement_id": requirement_id,
            "user_id": user_id,
            "status": "pending",
            "progress": 0,
            "message": "",
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }
        with self._lock:
            self._tasks[task_id] = task
        return task_id

    def update(self, task_id, status=None, progress=None, message=None, result=None, error=None):
        """Update task status."""
        with self._lock:
            if task_id not in self._tasks:
                return
            task = self._tasks[task_id]
            if status is not None:
                task["status"] = status
            if progress is not None:
                task["progress"] = progress
            if message is not None:
                task["message"] = message
            if result is not None:
                task["result"] = result
            if error is not None:
                task["error"] = error
            if status in ("completed", "failed"):
                task["completed_at"] = datetime.utcnow().isoformat()

    def get(self, task_id):
        """Get task status."""
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def cleanup_old(self, max_age_hours=2):
        """Remove tasks older than max_age_hours to prevent memory leak."""
        now = datetime.utcnow()
        to_remove = []
        with self._lock:
            for task_id, task in self._tasks.items():
                created = datetime.fromisoformat(task["created_at"])
                if (now - created).total_seconds() > max_age_hours * 3600:
                    to_remove.append(task_id)
            for tid in to_remove:
                del self._tasks[tid]


task_store = TaskStore()
