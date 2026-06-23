"""
State Manager
Tracks coordinator state in state.json.
Updated after every state change. Enables crash recovery.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TaskState:
    id: int
    name: str
    status: str  # pending, active, done
    specialist: Optional[str] = None
    output_file: Optional[str] = None


@dataclass
class ProjectState:
    project_name: str
    goal: str
    current_task_index: int = 0
    total_tasks: int = 0
    status: str = "initialized"  # initialized, planning, executing, complete
    loaded_model: Optional[str] = None  # coordinator, brain, specialist_name
    last_checkpoint: str = ""
    tasks: List[Dict] = None

    def __post_init__(self):
        if self.tasks is None:
            self.tasks = []
        if not self.last_checkpoint:
            self.last_checkpoint = datetime.now().isoformat()


class StateManager:
    """Manages state.json for crash recovery and tracking."""

    def __init__(self, state_file: str = "./state.json"):
        self.state_file = Path(state_file)
        self.state: Optional[ProjectState] = None

    def initialize(self, project_name: str, goal: str, task_names: List[str]) -> ProjectState:
        """Create initial state."""
        tasks = [
            {"id": i+1, "name": name, "status": "pending", 
             "specialist": None, "output_file": None}
            for i, name in enumerate(task_names)
        ]

        self.state = ProjectState(
            project_name=project_name,
            goal=goal,
            current_task_index=1,
            total_tasks=len(task_names),
            status="planning",
            loaded_model="coordinator",
            tasks=tasks
        )
        self._save()
        logger.info("[StateManager] Initialized with %d tasks", len(tasks))
        return self.state

    def mark_task_active(self, task_id: int, specialist: str) -> None:
        """Mark task as currently being worked on."""
        for task in self.state.tasks:
            if task["id"] == task_id:
                task["status"] = "active"
                task["specialist"] = specialist
                break
        self.state.current_task_index = task_id
        self.state.loaded_model = specialist
        self.state.last_checkpoint = datetime.now().isoformat()
        self._save()

    def mark_task_done(self, task_id: int, output_file: str) -> None:
        """Mark task as completed."""
        for task in self.state.tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["output_file"] = output_file
                break
        self.state.loaded_model = "coordinator"
        self.state.last_checkpoint = datetime.now().isoformat()
        self._save()

    def update_status(self, status: str) -> None:
        """Update overall project status."""
        self.state.status = status
        self.state.last_checkpoint = datetime.now().isoformat()
        self._save()

    def set_loaded_model(self, model_name: str) -> None:
        """Track which model is currently loaded."""
        self.state.loaded_model = model_name
        self.state.last_checkpoint = datetime.now().isoformat()
        self._save()

    def load_existing(self) -> bool:
        """Try to load existing state. Returns True if found."""
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.state = ProjectState(**data)
            logger.info("[StateManager] Loaded existing state. Task %d/%d",
                       self.state.current_task_index, self.state.total_tasks)
            return True
        except Exception as e:
            logger.error("[StateManager] Failed to load state: %s", e)
            return False

    def get_next_pending_task(self) -> Optional[Dict]:
        """Get next task that needs execution."""
        for task in self.state.tasks:
            if task["status"] == "pending":
                return task
        return None

    def get_task_output(self, task_id: int) -> Optional[str]:
        """Get output file path for a task."""
        for task in self.state.tasks:
            if task["id"] == task_id and task.get("output_file"):
                return task["output_file"]
        return None

    def all_tasks_done(self) -> bool:
        """Check if all tasks are completed."""
        return all(t["status"] == "done" for t in self.state.tasks)

    def _save(self) -> None:
        """Save state to JSON."""
        with open(self.state_file, "w") as f:
            json.dump(asdict(self.state), f, indent=2)

    def get_summary(self) -> str:
        """Human-readable summary."""
        if not self.state:
            return "No state."

        done = sum(1 for t in self.state.tasks if t["status"] == "done")
        total = len(self.state.tasks)

        lines = [
            f"Project: {self.state.project_name}",
            f"Status: {self.state.status}",
            f"Progress: {done}/{total} tasks",
            f"Current: Task {self.state.current_task_index}",
            f"Loaded: {self.state.loaded_model}",
            f"Checkpoint: {self.state.last_checkpoint}"
        ]
        return "\n".join(lines)
