#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: core/state_manager.py                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   State Manager — handles persistent JSON state with resume support.
#   Saves state after every task for robust recovery.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — State Manager

Persistent JSON state management with full resume support.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("relay.state")


@dataclass
class AppState:
    """Application state for Relay."""
    app_idea: str = ""
    current_phase: str = "planning"
    current_task_index: int = 0
    tasks: list = field(default_factory=list)
    completed_tasks: list = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
    reviews: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateManager:
    """
    Relay State Manager

    Manages persistent application state in JSON format.
    State is saved after every task, enabling robust resume functionality.

    Usage:
        state_mgr = StateManager()
        state_mgr.state.app_idea = "Build a fitness app"
        state_mgr.save()
        # Later...
        state_mgr.load()
    """

    def __init__(self, state_file: str = "memory/state.json"):
        self.state_file = Path(state_file)
        self.state = AppState()
        self._load_state()

    def _load_state(self):
        """Load state from disk or create default."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                raw = f.read()
                if not raw.strip():
                    self.logger.warning("State file empty — using defaults")
                    self.state = AppState()
                    self._save_state()
                    return
                self.state = AppState(**data)
                logger.info("[StateManager] Loaded state: %d tasks", len(self.state.tasks))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("[StateManager] Corrupt state file, starting fresh: %s", e)
                self.state = AppState()
        else:
            logger.info("[StateManager] No state file found, starting fresh")
            self.state = AppState()

    def save(self):
        """Save current state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(asdict(self.state), f, indent=2)
        logger.debug("[StateManager] State saved")

    def is_resumable(self) -> bool:
        """Check if there's a project to resume."""
        return bool(self.state.app_idea and self.state.current_phase != "done")

    def reset(self):
        """Reset state for a new project."""
        self.state = AppState()
        self.save()
        logger.info("[StateManager] State reset")
