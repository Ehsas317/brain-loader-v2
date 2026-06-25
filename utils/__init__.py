#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: utils/__init__.py                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   Utils package initializer for Relay.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — Utils Package

Utility modules for the Relay orchestrator.
"""

from utils.telegram_notify import TelegramNotifier

__all__ = ["TelegramNotifier"]
