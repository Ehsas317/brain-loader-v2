#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: core/memory_manager.py                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   Memory Manager — manages context windows for long conversations.
#   Keeps the most relevant context when approaching token limits.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — Memory Manager

Manages context windows for long conversations with relevance-based pruning.
"""

import logging
from typing import List, Dict, Optional
from collections import deque

logger = logging.getLogger("relay.memory")


class MemoryManager:
    """
    Relay Memory Manager

    Manages conversation context windows by tracking token usage and
    pruning less relevant messages when approaching limits.

    Usage:
        memory = MemoryManager(max_tokens=8192)
        memory.add_message("user", "Build a fitness app")
        memory.add_message("assistant", "Here's the plan...")
        context = memory.get_context()  # Returns pruned context
    """

    def __init__(self, max_tokens: int = 8192, reserve_tokens: int = 512):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.messages: List[Dict[str, str]] = []
        self.token_counts: List[int] = []
        self.current_tokens = 0

    def add_message(self, role: str, content: str, estimated_tokens: int = None):
        """Add a message to the conversation history."""
        if estimated_tokens is None:
            # Rough estimate: 1 token ≈ 4 chars for English
            estimated_tokens = len(content) // 4

        self.messages.append({"role": role, "content": content})
        self.token_counts.append(estimated_tokens)
        self.current_tokens += estimated_tokens

        # Prune if over limit
        if self.current_tokens > (self.max_tokens - self.reserve_tokens):
            self._prune_context()

    def _prune_context(self):
        """Remove oldest non-system messages to fit within token limit."""
        logger.info("[Memory] Pruning context: %d tokens", self.current_tokens)

        while (self.current_tokens > (self.max_tokens - self.reserve_tokens)
               and len(self.messages) > 2):
            # Remove oldest non-system message
            for i, msg in enumerate(self.messages):
                if msg["role"] != "system":
                    removed_tokens = self.token_counts.pop(i)
                    self.messages.pop(i)
                    self.current_tokens -= removed_tokens
                    break

        logger.info("[Memory] Pruned to %d tokens", self.current_tokens)

    def get_context(self) -> List[Dict[str, str]]:
        """Get the current conversation context."""
        return self.messages.copy()

    def get_token_count(self) -> int:
        """Get current token estimate."""
        return self.current_tokens

    def clear(self):
        """Clear all messages."""
        self.messages = []
        self.token_counts = []
        self.current_tokens = 0

    def __len__(self):
        return len(self.messages)
