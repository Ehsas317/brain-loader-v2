#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: core/__init__.py                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   Core package initializer for Relay. Exports main orchestration classes.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — Core Package

Exposes the main orchestration classes:
- RelayOrchestrator: Resident coordinator with hot-swap support
- StateManager: Persistent JSON state management
- MemoryManager: Context window management
"""

from core.orchestrator import RelayOrchestrator
from core.state_manager import StateManager
from core.memory_manager import MemoryManager

__all__ = [
    "RelayOrchestrator",
    "StateManager",
    "MemoryManager",
]
