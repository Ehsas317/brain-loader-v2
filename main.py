#!/usr/bin/env python3
"""
Brain Loader v2 — Main Entry Point

Sequential Orchestration Architecture:
  4GB permanent coordinator + 20GB hot-swap slot
  Brain and specialists never coexist in RAM

Usage:
    python main.py "Build a React Native fitness app with AI meal planner"
    python main.py --resume
    python main.py --goal "My app idea" --constraints "Must use TypeScript"
"""

import os
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import BrainOrchestrator


def setup_logging():
    """Configure logging."""
    logs_dir = Path("./logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"brain_loader_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    return log_file


def main():
    parser = argparse.ArgumentParser(
        description="Brain Loader v2 — MLX Multi-Agent Orchestrator"
    )
    parser.add_argument(
        "goal",
        nargs="?",
        help="Your project goal / app idea"
    )
    parser.add_argument(
        "--constraints",
        default="",
        help="Hard constraints (e.g., 'Must use React, Must be mobile-first')"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file path"
    )
    parser.add_argument(
        "--list-specialists",
        action="store_true",
        help="List available specialists"
    )

    args = parser.parse_args()

    log_file = setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("BRAIN LOADER v2 — Sequential Orchestration Architecture")
    logger.info("RAM: 4GB permanent coordinator + 20GB hot-swap slot = 24GB")
    logger.info("=" * 70)

    if not Path(args.config).exists():
        logger.error("Config not found: %s", args.config)
        sys.exit(1)

    orchestrator = BrainOrchestrator(config_path=args.config)

    if args.list_specialists:
        print("\nAvailable Specialists:")
        print("-" * 50)
        for key, cfg in orchestrator.specialist_configs.items():
            print(f"  {key:15s} — {cfg.description}")
            print(f"    Model: {cfg.path}")
            print(f"    RAM: ~{cfg.ram_estimate_gb}GB")
            print()
        print(f"\nBrain: {orchestrator.brain_config.path}")
        print(f"Coordinator: {orchestrator.coordinator_config.path}")
        sys.exit(0)

    if args.resume:
        logger.info("Resuming...")
        orchestrator.run(goal="", resume=True)
    elif args.goal:
        logger.info("Starting: %s", args.goal)
        orchestrator.run(goal=args.goal, constraints=args.constraints)
    else:
        print("\n🧠 Brain Loader v2")
        print("=" * 50)
        print("What do you want to build?")
        print("Example: 'A React Native fitness app with AI meal planner'")
        print()

        goal = input("> ").strip()
        if not goal:
            print("No goal provided. Exiting.")
            sys.exit(0)

        print("\nAny hard constraints? (press Enter for none)")
        constraints = input("> ").strip()

        orchestrator.run(goal=goal, constraints=constraints)

    logger.info("Done. Log: %s", log_file)
    print(f"\n✅ Complete! Log: {log_file}")


if __name__ == "__main__":
    main()
