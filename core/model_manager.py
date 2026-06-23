"""
MLX Model Manager v2 — Sequential Orchestration Architecture

RAM Layout:
  4GB  : Coordinator (Qwen2.5-1.5B) — PERMANENT, never unloads
  20GB : Hot-swap slot — Brain OR Specialist (never both)
  ─────
  24GB : Total allocated

Coordinator stays warm. Brain and specialists are aggressively offloaded.
"""

import gc
import time
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

import mlx.core as mx
from mlx_lm import load, generate

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    path: str
    max_tokens: int
    temperature: float
    description: str
    ram_estimate_gb: float
    role: str  # "coordinator", "brain", "specialist"


class MLXModelManager:
    """
    Manages the two-slot architecture:
    - Slot 1 (Permanent): Coordinator — stays loaded
    - Slot 2 (Hot-swap): Brain OR Specialist — one at a time
    """

    def __init__(self, gc_sleep: float = 2.0, aggressive_cleanup: bool = True):
        self.gc_sleep = gc_sleep
        self.aggressive_cleanup = aggressive_cleanup

        # Slot 1: Coordinator (permanent)
        self.coordinator_model = None
        self.coordinator_tokenizer = None
        self.coordinator_config: Optional[ModelConfig] = None

        # Slot 2: Hot-swap (brain or specialist)
        self.hot_model = None
        self.hot_tokenizer = None
        self.hot_config: Optional[ModelConfig] = None

        self._total_swaps = 0
        self._currently_loaded = None  # "coordinator", "brain", "specialist"

        logger.info("[MLXManager] v2 initialized. Two-slot architecture ready.")

    def load_coordinator(self, config: ModelConfig) -> None:
        """Load coordinator into permanent slot. Call once at startup."""
        if config.role != "coordinator":
            raise ValueError(f"Expected coordinator role, got {config.role}")

        logger.info("[MLXManager] Loading COORDINATOR (permanent): %s", config.path)

        self.coordinator_model, self.coordinator_tokenizer = load(config.path)
        self.coordinator_config = config
        self._currently_loaded = "coordinator"

        logger.info("[MLXManager] Coordinator loaded. ~%.1fGB occupied.", config.ram_estimate_gb)

    def load_brain(self, config: ModelConfig) -> None:
        """Load brain into hot-swap slot. Offloads any existing hot model first."""
        if config.role != "brain":
            raise ValueError(f"Expected brain role, got {config.role}")

        self._swap_hot_model(config)
        self._currently_loaded = "brain"
        logger.info("[MLXManager] BRAIN loaded: %s", config.path)

    def load_specialist(self, config: ModelConfig) -> None:
        """Load specialist into hot-swap slot. Offloads any existing hot model first."""
        if config.role != "specialist":
            raise ValueError(f"Expected specialist role, got {config.role}")

        self._swap_hot_model(config)
        self._currently_loaded = "specialist"
        logger.info("[MLXManager] SPECIALIST loaded: %s", config.path)

    def _swap_hot_model(self, config: ModelConfig) -> None:
        """Offload current hot model, load new one."""
        # Step 1: Confirm coordinator is still there
        if self.coordinator_model is None:
            raise RuntimeError("Coordinator not loaded! Load coordinator first.")

        # Step 2: Offload existing hot model
        if self.hot_model is not None:
            logger.info("[MLXManager] Offloading hot model: %s", 
                       self.hot_config.path if self.hot_config else "unknown")
            self._offload_hot()

        # Step 3: Load new hot model
        logger.info(
            "[MLXManager] Loading hot model: %s (est. %.1fGB)",
            config.path, config.ram_estimate_gb
        )

        try:
            self.hot_model, self.hot_tokenizer = load(config.path)
            self.hot_config = config
            self._total_swaps += 1

        except Exception as e:
            logger.critical("[MLXManager] Failed to load hot model: %s", e)
            self._emergency_cleanup()
            raise

    def _offload_hot(self) -> None:
        """Aggressively offload the hot model from unified memory."""
        if self.hot_model is None:
            return

        model_name = self.hot_config.path if self.hot_config else "unknown"

        # Delete references
        del self.hot_model
        del self.hot_tokenizer
        self.hot_model = None
        self.hot_tokenizer = None
        self.hot_config = None

        # Force GC (multiple passes)
        for _ in range(3):
            gc.collect()

        # MLX synchronize
        try:
            mx.synchronize()
        except Exception as e:
            logger.warning("[MLXManager] mx.synchronize() error: %s", e)

        # Aggressive cache clear
        if self.aggressive_cleanup:
            try:
                if hasattr(mx.metal, 'clear_cache'):
                    mx.metal.clear_cache()
                elif hasattr(mx, 'clear_cache'):
                    mx.clear_cache()
            except Exception as e:
                logger.debug("[MLXManager] Cache clear: %s", e)

        # Sleep for memory settlement
        logger.info("[MLXManager] Sleeping %.1fs for memory settlement...", self.gc_sleep)
        time.sleep(self.gc_sleep)

        logger.info("[MLXManager] Hot model offloaded: %s", model_name)

    def generate(self, prompt: str, role: str = "hot",
                 max_tokens: Optional[int] = None,
                 temperature: Optional[float] = None,
                 verbose: bool = False) -> str:
        """
        Generate text from specified role.

        Args:
            prompt: Input prompt
            role: "coordinator", "brain", or "specialist" (auto-detects hot slot)
            max_tokens: Override default
            temperature: Override default
        """
        if role == "coordinator":
            if self.coordinator_model is None:
                raise RuntimeError("Coordinator not loaded")
            model = self.coordinator_model
            tokenizer = self.coordinator_tokenizer
            config = self.coordinator_config
        else:
            # brain or specialist — both use hot slot
            if self.hot_model is None:
                raise RuntimeError(f"No hot model loaded for role: {role}")
            model = self.hot_model
            tokenizer = self.hot_tokenizer
            config = self.hot_config

        tokens = max_tokens or config.max_tokens
        temp = temperature if temperature is not None else config.temperature

        logger.info(
            "[MLXManager] Generate [%s]: max_tokens=%d, temp=%.2f",
            role, tokens, temp
        )

        result = generate(
            model=model,
            tokenizer=tokenizer,
            prompt=prompt,
            max_tokens=tokens,
            temp=temp,
            verbose=verbose
        )

        return result

    def get_status(self) -> Dict[str, Any]:
        return {
            "coordinator": self.coordinator_config.path if self.coordinator_config else None,
            "hot_model": self.hot_config.path if self.hot_config else None,
            "currently_loaded": self._currently_loaded,
            "total_swaps": self._total_swaps
        }

    def _emergency_cleanup(self) -> None:
        """Emergency: nuke everything except coordinator."""
        logger.critical("[MLXManager] EMERGENCY CLEANUP!")
        self.hot_model = None
        self.hot_tokenizer = None
        self.hot_config = None
        gc.collect()
        try:
            mx.synchronize()
            if hasattr(mx.metal, 'clear_cache'):
                mx.metal.clear_cache()
        except:
            pass
        time.sleep(5)

    def shutdown(self):
        """Graceful shutdown — offload everything."""
        logger.info("[MLXManager] Shutting down...")
        if self.hot_model is not None:
            self._offload_hot()
        if self.coordinator_model is not None:
            del self.coordinator_model
            del self.coordinator_tokenizer
            self.coordinator_model = None
            self.coordinator_tokenizer = None
            gc.collect()
            mx.synchronize()
        logger.info("[MLXManager] Shutdown complete.")
