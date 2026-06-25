#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: core/orchestrator.py                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   Relay Orchestrator — the resident coordinator that manages the full
#   build lifecycle. Stays in memory throughout, hot-swapping models as
#   needed for each task while maintaining full context.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — Orchestrator

Resident coordinator with hot-swappable model support.
"""

import os
import sys
import yaml
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.model_manager import ModelManager
from core.state_manager import StateManager, AppState
from core.memory_manager import MemoryManager
from utils.telegram_notify import TelegramNotifier

logger = logging.getLogger("relay.orchestrator")


class RelayOrchestrator:
    """
    Relay Orchestrator

    The resident coordinator that manages the entire build process.
    Unlike Forge which loads everything upfront, Relay hot-swaps models
    per task, keeping only the coordinator resident in memory.

    Usage:
        orchestrator = RelayOrchestrator(config_path="config.yaml")
        orchestrator.run("Build a fitness app")
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.state_manager = StateManager()
        self.memory = MemoryManager()
        self.model_manager = ModelManager(self.config.get("models", {}))

        # Worker model assignments
        self.worker_map = {
            "frontend": "relay-coder",
            "backend": "relay-coderx",
            "planning": "relay-brain",
            "review": "relay-brain",
        }

        # Telegram
        telegram_cfg = self.config.get("telegram", {})
        if telegram_cfg.get("enabled"):
            self.notifier = TelegramNotifier(
                bot_token=telegram_cfg.get("bot_token", ""),
                chat_id=telegram_cfg.get("chat_id", ""),
            )
        else:
            self.notifier = None

        Path("./memory").mkdir(exist_ok=True)
        Path("./logs").mkdir(exist_ok=True)

        logger.info("[Orchestrator] Relay initialized")

    def _load_config(self) -> Dict:
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def run(self, app_idea: str, resume: bool = False):
        """Main entry point."""
        if resume and self.state_manager.is_resumable():
            logger.info("[Orchestrator] Resuming project...")
            self._notify("🏃 Relay resuming project...")
        else:
            self.state_manager.state.app_idea = app_idea
            self.state_manager.state.current_phase = "planning"
            self.state_manager.save()
            logger.info("[Orchestrator] Starting: %s", app_idea)
            self._notify(f"🏃 Relay starting: {app_idea}")

        # Phase 1: Planning
        if self.state_manager.state.current_phase == "planning":
            plan = self._create_plan(self.state_manager.state.app_idea)
            self.state_manager.state.tasks = self._decompose_plan(plan)
            self.state_manager.state.current_phase = "execution"
            self.state_manager.save()
            self._notify(f"📋 Plan: {len(self.state_manager.state.tasks)} tasks")

        # Phase 2: Execution
        if self.state_manager.state.current_phase == "execution":
            tasks = self.state_manager.state.tasks
            for i, task in enumerate(tasks):
                if i < self.state_manager.state.current_task_index:
                    continue  # Skip completed

                self._execute_task(task)
                self.state_manager.state.current_task_index = i + 1
                self.state_manager.state.completed_tasks.append(task.get("id", f"T{i}"))
                self.state_manager.save()

            self.state_manager.state.current_phase = "review"
            self.state_manager.save()

        # Phase 3: Final Review
        if self.state_manager.state.current_phase == "review":
            self._final_review()
            self.state_manager.state.current_phase = "done"
            self.state_manager.save()

        logger.info("[Orchestrator] Relay build complete!")
        self._notify("✅ Relay build complete!")

    def _create_plan(self, app_idea: str) -> str:
        """Create a plan using the Brain model."""
        logger.info("[Orchestrator] Planning with Brain...")

        prompt = f"""You are Relay's Brain. Create a detailed plan for:
"{app_idea}"

Break into tasks with IDs, types (frontend/backend/devops/docs/testing), descriptions, and dependencies."""

        # Try local brain first, fallback to cloud
        if not self.model_manager.load("relay-brain"):
            logger.info("[Orchestrator] Using cloud fallback for planning")
            return self._cloud_generate(prompt, max_tokens=4096)

        plan = self.model_manager.generate(prompt, max_tokens=4096)
        self.model_manager.unload()
        return plan

    def _decompose_plan(self, plan: str) -> List[Dict]:
        """Decompose plan into structured tasks."""
        import re
        tasks = []
        for match in re.finditer(r'Task\s+(\w+):\s*\((\w+)\)\s*(.+?)(?=Task|$)', plan, re.DOTALL):
            task_id, task_type, desc = match.groups()
            tasks.append({
                "id": task_id.strip(),
                "type": task_type.strip(),
                "description": desc.strip(),
                "status": "pending",
            })
        return tasks if tasks else []

    def _execute_task(self, task: Dict):
        """Execute a single task with hot-swapped model."""
        task_id = task.get("id", "unknown")
        task_type = task.get("type", "general")

        logger.info("[Orchestrator] Task %s (%s)", task_id, task_type)
        self._notify(f"🔨 {task_id}: {task.get('description', '')[:50]}...")

        model_key = self.worker_map.get(task_type, "relay-coder")

        # Build prompt with context
        context = self._get_context()
        prompt = f"{context}\n\nTask: {task.get('description', '')}\n\nOutput:"

        # Load model, generate, unload
        if self.model_manager.load(model_key):
            output = self.model_manager.generate(prompt, max_tokens=4096)
            self.model_manager.unload()
        else:
            output = self._cloud_generate(prompt, max_tokens=4096)

        # Review
        review = self._review_output(task, output)

        # Save output
        self.state_manager.state.outputs[task_id] = {
            "content": output,
            "review": review,
        }

        # Update memory
        self.memory.add_message("assistant", f"Task {task_id}: {output[:500]}")

    def _get_context(self) -> str:
        """Build context from memory and previous outputs."""
        context_parts = ["Project: " + self.state_manager.state.app_idea]

        # Add recent outputs
        for task_id, output_data in list(self.state_manager.state.outputs.items())[-3:]:
            content = output_data.get("content", "")[:300]
            context_parts.append(f"Previous task ({task_id}): {content}")

        return "\n\n".join(context_parts)

    def _review_output(self, task: Dict, output: str) -> str:
        """Review output with Brain."""
        prompt = f"""Review this output for quality:
Task: {task.get('description', '')}
Output: {output[:2000]}
Respond: APPROVED or NEEDS_REVISION + feedback"""

        if self.model_manager.load("relay-brain"):
            review = self.model_manager.generate(prompt, max_tokens=2048)
            self.model_manager.unload()
        else:
            review = self._cloud_generate(prompt, max_tokens=2048)

        return review

    def _final_review(self):
        """Perform final review."""
        logger.info("[Orchestrator] Final review...")

        outputs_text = "\n\n".join(
            f"{tid}:\n{data.get('content', '')[:500]}"
            for tid, data in self.state_manager.state.outputs.items()
        )

        prompt = f"Final review:\n{outputs_text}\n\nOverall assessment:"

        if self.model_manager.load("relay-brain"):
            review = self.model_manager.generate(prompt, max_tokens=4096)
            self.model_manager.unload()
        else:
            review = self._cloud_generate(prompt, max_tokens=4096)

        self.state_manager.state.reviews["final"] = review
        self._notify("🔍 Final review complete")

    def _cloud_generate(self, prompt: str, max_tokens: int = 4096) -> str:
        """Fallback to cloud API for generation."""
        import httpx

        cloud_cfg = self.config.get("cloud", {})
        # Try providers in order
        for provider in ["deepseek", "mistral", "anthropic"]:
            if provider not in cloud_cfg:
                continue
            cfg = cloud_cfg[provider]
            try:
                headers = {"Authorization": f"Bearer {cfg['api_key']}"}
                payload = {
                    "model": cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                }
                resp = httpx.post(
                    f"{cfg['endpoint']}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("Cloud fallback %s failed: %s", provider, e)
                continue

        return "Error: All generation methods failed"

    def _notify(self, message: str):
        if self.notifier:
            try:
                self.notifier.send(message)
            except Exception as e:
                logger.warning("Notification failed: %s", e)
