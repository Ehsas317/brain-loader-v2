#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RELAY  — FILE: core/model_manager.py                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Relay (formerly Brain Loader v2)
# REPO:       https://github.com/Ehsas317/relay
# WHAT:       The coordinator stays resident and relays the baton between
#             hot-swapped models. The core metaphor is handoffs, not planning.
#
# THIS FILE:
#   Model Manager — handles hot-swappable model loading/unloading for
#   both local MLX models and cloud API backends.
#
# HOW TO USE RELAY:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project description"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Relay — Model Manager

Hot-swappable model loading for local MLX and cloud API backends.
"""

import gc
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Any

import mlx.core as mx
from mlx_lm import load, generate as mlx_generate

logger = logging.getLogger("relay.model_manager")


class ModelManager:
    """
    Relay Model Manager

    Manages hot-swappable model loading for both local MLX models
    and cloud API backends. Only one model is loaded at a time.

    Usage:
        manager = ModelManager(config)
        manager.load("relay-coder")
        output = manager.generate("Write a React component...")
        manager.unload()  # Free memory for next model
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.current_model_key: Optional[str] = None
        self.model = None
        self.tokenizer = None
        self.load_times: Dict[str, float] = {}

    def load(self, model_key: str) -> bool:
        """Load a model by key. Returns True on success."""
        if model_key not in self.config:
            logger.error("[ModelManager] Unknown model: %s", model_key)
            return False

        if self.current_model_key == model_key:
            logger.info("[ModelManager] Model %s already loaded", model_key)
            return True

        # Unload current
        if self.model is not None:
            self.unload()

        cfg = self.config[model_key]
        logger.info("[ModelManager] Loading %s: %s", model_key, cfg.get("description", ""))

        start = time.time()
        try:
            self.model, self.tokenizer = load(cfg["path"])
            self.current_model_key = model_key
            load_time = time.time() - start
            self.load_times[model_key] = load_time
            logger.info("[ModelManager] Loaded in %.1fs", load_time)
            return True
        except Exception as e:
            logger.error("[ModelManager] Failed to load %s: %s", model_key, e)
            return False

    def unload(self):
        """Unload current model and free memory."""
        if self.model is not None:
            logger.info("[ModelManager] Unloading %s", self.current_model_key)
            del self.model
            del self.tokenizer
            self.model = None
            self.tokenizer = None
            self.current_model_key = None
            gc.collect()
            mx.clear_cache()

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        """Generate text using currently loaded model."""
        if self.model is None:
            raise RuntimeError("No model loaded. Call load() first.")

        return mlx_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=kwargs.get("temperature", 0.0),
            verbose=kwargs.get("verbose", False),
        )

    def __del__(self):
        if self.model is not None:
            self.unload()
