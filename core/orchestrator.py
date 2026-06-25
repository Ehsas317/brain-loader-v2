"""
Brain Orchestrator v2 — Sequential Orchestration Architecture

Two-slot RAM layout:
  Slot 1 (Permanent): Coordinator — always loaded
  Slot 2 (Hot-swap): Brain OR Specialist — one at a time

Execution Flow:
  1. Coordinator loads (permanent)
  2. Coordinator loads Brain → Brain creates task list + Task 1 subtasks → Brain unloads
  3. Coordinator loads Specialist → Specialist executes → Writes output → Specialist unloads
  4. Coordinator loads Brain → Brain reads memory.md + output → Adapts → Writes Task 2 subtasks → Brain unloads
  5. Repeat 3-4 until all tasks done
  6. Coordinator loads Brain (final) → Brain synthesizes answer → Done
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from core.model_manager import MLXModelManager, ModelConfig
from core.memory_manager import MemoryManager
from core.state_manager import StateManager

logger = logging.getLogger(__name__)


class BrainOrchestrator:
    """Main orchestration engine implementing the two-slot architecture."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Initialize components
        self.model_mgr = MLXModelManager(
            gc_sleep=self.config["memory"]["gc_sleep_seconds"],
            aggressive_cleanup=self.config["memory"]["aggressive_cleanup"]
        )

        self.memory_mgr = MemoryManager(
            memory_file=self.config["project"]["memory_file"]
        )

        self.state_mgr = StateManager(
            state_file=self.config["project"]["state_file"]
        )

        # Ensure outputs directory exists
        self.outputs_dir = Path(self.config["project"]["outputs_dir"])
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        # Model configs
        self.coordinator_config = self._create_config("coordinator", self.config["coordinator"])
        self.brain_config = self._create_config("brain", self.config["brain"])
        self.specialist_configs = {
            key: self._create_config("specialist", val, key)
            for key, val in self.config["specialists"].items()
        }

        # Telegram
        self._telegram = None

        # FIX BUG-V2-003: Load coordinator immediately in __init__
        # so it's always available before any brain/specialist operations
        logger.info("[Orchestrator] Loading coordinator into permanent slot...")
        self.model_mgr.load_coordinator(self.coordinator_config)

        logger.info("[Orchestrator] v2 initialized. Coordinator: %s", 
                   self.coordinator_config.path)

    def run(self, goal: str, constraints: str = "", resume: bool = False) -> None:
        """Main entry point."""
        self._notify(f"🧠 Brain Loader v2 Started\nGoal: _{goal}_")

        if resume and self.state_mgr.load_existing():
            logger.info("[Orchestrator] Resuming from checkpoint...")
            self._notify("📂 Resuming from checkpoint...")
            self._resume_execution()
        else:
            self._start_new_project(goal, constraints)

    def _start_new_project(self, goal: str, constraints: str) -> None:
        """Start fresh project."""
        logger.info("[Orchestrator] Starting new project: %s", goal)

        # STEP 1: Coordinator is already loaded (permanent) from __init__
        # FIX BUG-V2-003: Coordinator loaded in __init__, not here
        self.state_mgr.set_loaded_model("coordinator")

        # STEP 2: First Brain load — create full task list + Task 1 subtasks
        self._notify("📝 Brain creating master plan...")
        task_names, first_specialist, first_subtasks = self._brain_first_load(goal, constraints)

        if not task_names:
            raise RuntimeError("Brain failed to produce task list!")

        logger.info("[Orchestrator] Brain created %d tasks", len(task_names))
        self._notify(f"📋 Master plan: *{len(task_names)}* tasks")

        # Initialize state and memory
        self.state_mgr.initialize(
            self.config["project"]["name"],
            goal,
            task_names
        )
        self.state_mgr.update_status("planning")

        self.memory_mgr.initialize(
            goal=goal,
            constraints=constraints,
            task_names=task_names,
            first_task_specialist=first_specialist,
            first_subtasks=first_subtasks
        )

        # Brain unloads automatically after first load
        self.state_mgr.set_loaded_model("coordinator")

        # STEP 3: Execute tasks sequentially
        self.state_mgr.update_status("executing")
        self._execute_task_loop()

    def _execute_task_loop(self) -> None:
        """Main loop: execute tasks one by one."""
        while True:
            next_task = self.state_mgr.get_next_pending_task()

            if not next_task:
                # All tasks done — final review
                self._do_final_load()
                break

            self._execute_single_task(next_task)

    def _execute_single_task(self, task: Dict) -> None:
        """
        Execute one task:
        1. Get task info from memory
        2. Load specialist → execute → write output → unload
        3. Load brain → read output → adapt → write next subtasks → unload
        """
        task_id = task["id"]
        task_name = task["name"]

        # Get current task info from memory
        mem_info = self.memory_mgr.get_current_task_info()
        specialist_key = mem_info.get("specialist", "coder")
        subtasks = mem_info.get("subtasks", [])

        logger.info("=" * 60)
        logger.info("[Orchestrator] Task %d: %s | Specialist: %s", 
                   task_id, task_name, specialist_key)
        logger.info("=" * 60)

        self.state_mgr.mark_task_active(task_id, specialist_key)
        self._notify(
            f"⚙️ *Task {task_id}/{self.state_mgr.state.total_tasks}*\n"
            f"{task_name}\n"
            f"Specialist: `{specialist_key}`"
        )

        # PHASE A: Specialist executes
        specialist_config = self.specialist_configs.get(specialist_key, 
                                                        self.specialist_configs["coder"])

        # Load specialist into hot-swap slot
        logger.info("[Orchestrator] Loading specialist: %s", specialist_key)
        self.model_mgr.load_specialist(specialist_config)
        self.state_mgr.set_loaded_model(specialist_key)

        # Build specialist prompt
        specialist_prompt = self._build_specialist_prompt(
            task_id, task_name, subtasks, goal=self.state_mgr.state.goal
        )

        # Generate
        try:
            output = self.model_mgr.generate(
                prompt=specialist_prompt,
                role="specialist",
                max_tokens=specialist_config.max_tokens,
                temperature=specialist_config.temperature
            )
        except Exception as e:
            logger.error("[Orchestrator] Specialist failed: %s", e)
            output = f"ERROR: Specialist generation failed.\n\n{str(e)}"

        # Write output
        output_file = self.outputs_dir / f"task_{task_id:03d}_{specialist_key}.md"
        with open(output_file, "w") as f:
            f.write(f"# Task {task_id}: {task_name}\n\n")
            f.write(f"**Specialist:** {specialist_key}\n")
            f.write(f"**Subtasks:**\n")
            for i, st in enumerate(subtasks, 1):
                f.write(f"{i}. {st}\n")
            f.write(f"\n---\n\n{output}\n")

        logger.info("[Orchestrator] Output written: %s", output_file)
        self.state_mgr.mark_task_done(task_id, str(output_file))

        # Unload specialist
        self.model_mgr.load_coordinator(self.coordinator_config)  # This offloads hot model
        self.state_mgr.set_loaded_model("coordinator")

        # PHASE B: Brain reviews and plans next
        self._notify(f"🧠 Brain reviewing Task {task_id}...")

        # Load brain
        logger.info("[Orchestrator] Loading brain for review...")
        self.model_mgr.load_brain(self.brain_config)
        self.state_mgr.set_loaded_model("brain")

        # Read memory and output
        memory_content = self.memory_mgr.read()
        output_content = output_file.read_text()

        # Build brain prompt
        brain_prompt = self._build_brain_review_prompt(
            task_id, task_name, memory_content, output_content,
            self.state_mgr.state.total_tasks
        )

        # Generate
        try:
            brain_output = self.model_mgr.generate(
                prompt=brain_prompt,
                role="brain",
                max_tokens=self.config["brain"]["max_tokens_subsequent"],
                temperature=self.config["brain"]["temperature"]
            )
        except Exception as e:
            logger.error("[Orchestrator] Brain review failed: %s", e)
            brain_output = f"Summary: Task completed.\nNext: Continue with next task."

        # Parse brain output
        summary, next_specialist, next_subtasks, adapted_names = self._parse_brain_output(
            brain_output, task_id, self.state_mgr.state.total_tasks
        )

        # Update memory
        has_next = task_id < self.state_mgr.state.total_tasks
        self.memory_mgr.update_after_task(
            task_num=task_id,
            summary=summary,
            next_task_specialist=next_specialist if has_next else None,
            next_subtasks=next_subtasks if has_next else None,
            adapted_task_names=adapted_names
        )

        # Verify memory was updated (Coordinator Rule #5)
        if not self.memory_mgr.verify_integrity():
            logger.critical("[Orchestrator] memory.md integrity check FAILED!")
            self._notify("🚨 CRITICAL: Memory corruption detected! Halting.")
            raise RuntimeError("Memory integrity check failed after brain unload")

        # Unload brain (coordinator handles the swap)
        self.model_mgr.load_coordinator(self.coordinator_config)
        self.state_mgr.set_loaded_model("coordinator")

        self._notify(f"✅ Task {task_id} complete. {summary[:100]}")

    def _do_final_load(self) -> None:
        """Final brain load: synthesize answer from all outputs."""
        logger.info("[Orchestrator] All tasks complete. Final synthesis...")
        self.state_mgr.update_status("complete")
        self._notify("🔍 *Final Review* — Brain synthesizing complete answer...")

        # Load brain
        self.model_mgr.load_brain(self.brain_config)
        self.state_mgr.set_loaded_model("brain")

        # Gather all outputs
        memory_content = self.memory_mgr.read()
        all_outputs = []

        for task in self.state_mgr.state.tasks:
            if task.get("output_file"):
                output_path = Path(task["output_file"])
                if output_path.exists():
                    all_outputs.append({
                        "task_id": task["id"],
                        "name": task["name"],
                        "content": output_path.read_text()[:3000]  # Truncate
                    })

        # Build final prompt
        final_prompt = f"""You are the Brain doing FINAL SYNTHESIS.

## Your Memory (entire project history)
{memory_content}

## All Task Outputs (summarized)
"""
        for out in all_outputs:
            final_prompt += f"\n### Task {out['task_id']}: {out['name']}\n{out['content']}\n"

        final_prompt += """
## Your Job
Synthesize all outputs into a coherent final answer/deliverable.
Deliver the complete result to the user. Be thorough.
"""

        final_answer = self.model_mgr.generate(
            prompt=final_prompt,
            role="brain",
            max_tokens=self.config["brain"]["max_tokens_final"],
            temperature=0.5
        )

        # Save final answer
        final_file = self.outputs_dir / "FINAL_ANSWER.md"
        with open(final_file, "w") as f:
            f.write(f"# Final Answer\n\n{final_answer}\n")

        # Unload everything
        self.model_mgr.shutdown()

        # Notify
        self._notify(
            f"🎉 *PROJECT COMPLETE!*\n\n"
            f"Goal: _{self.state_mgr.state.goal}_\n"
            f"Tasks: {self.state_mgr.state.total_tasks}\n\n"
            f"📂 Review at:\n"
            f"`{self.outputs_dir.absolute()}`\n\n"
            f"Key files:\n"
            f"• `memory.md` — Full project history\n"
            f"• `state.json` — Execution tracking\n"
            f"• `task_###_*.md` — All outputs\n"
            f"• `FINAL_ANSWER.md` — Synthesized result"
        )

        logger.info("[Orchestrator] Project complete!")

    def _brain_first_load(self, goal: str, constraints: str) -> Tuple[List[str], str, List[str]]:
        """
        First brain load: create full task list and Task 1 subtasks.
        Returns: (task_names, first_specialist, first_subtasks)
        """
        # FIX BUG-V2-003: Coordinator is already loaded from __init__
        self.model_mgr.load_brain(self.brain_config)
        self.state_mgr.set_loaded_model("brain")

        prompt = f"""You are the Brain. This is your FIRST load.

## User Goal
{goal}

## Hard Constraints
{constraints if constraints else "None specified"}

## Your Job
1. Create a complete task list (task NAMES only, no subtasks yet)
2. Assign a specialist to Task 1
3. Write detailed subtasks for Task 1 ONLY

Available specialists:
- coder: Code generation, debugging, implementation
- researcher: Research, analysis, data gathering  
- writer: Documentation, copy, synthesis
- critic: Review, critique, quality assurance
- math: Mathematical reasoning, algorithms

## Output Format
```
TASK_LIST:
1. Task name here
2. Task name here
3. Task name here
... (continue for all tasks)

TASK_1_SPECIALIST: <specialist_name>

TASK_1_SUBTASKS:
1. First subtask
2. Second subtask
3. Third subtask
```

Create 30-80 tasks. Be specific. Task 1 subtasks should be granular and actionable.
"""

        output = self.model_mgr.generate(
            prompt=prompt,
            role="brain",
            max_tokens=self.config["brain"]["max_tokens_first_load"],
            temperature=self.config["brain"]["temperature"]
        )

        # Parse output
        task_names = []
        first_specialist = "coder"
        first_subtasks = []

        # Extract task list
        task_list_match = re.search(r'TASK_LIST:\n(.+?)(?=TASK_1_SPECIALIST|$)', 
                                    output, re.DOTALL)
        if task_list_match:
            task_lines = task_list_match.group(1).strip().split("\n")
            for line in task_lines:
                match = re.match(r'^\d+\.\s*(.+)$', line.strip())
                if match:
                    task_names.append(match.group(1).strip())

        # Extract specialist
        spec_match = re.search(r'TASK_1_SPECIALIST:\s*(\w+)', output)
        if spec_match:
            first_specialist = spec_match.group(1).strip().lower()

        # Extract subtasks
        subtask_match = re.search(r'TASK_1_SUBTASKS:\n(.+?)(?=\n\n|$)', 
                                  output, re.DOTALL)
        if subtask_match:
            sub_lines = subtask_match.group(1).strip().split("\n")
            for line in sub_lines:
                match = re.match(r'^\d+\.\s*(.+)$', line.strip())
                if match:
                    first_subtasks.append(match.group(1).strip())

        # Unload brain
        self.model_mgr.load_coordinator(self.coordinator_config)

        if not task_names:
            task_names = ["Analyze requirements", "Design architecture", "Implement core", 
                         "Add features", "Test and deploy"]
        if not first_subtasks:
            first_subtasks = ["Understand the goal", "Plan approach", "Produce output"]

        return task_names, first_specialist, first_subtasks

    def _build_specialist_prompt(self, task_id: int, task_name: str, 
                                  subtasks: List[str], goal: str) -> str:
        """Build prompt for specialist."""
        subtasks_text = "\n".join(f"{i+1}. {st}" for i, st in enumerate(subtasks))

        return f"""You are a specialist AI executing a specific task.

## Project Goal
{goal}

## Your Task
Task {task_id}: {task_name}

## Your Subtasks (complete ALL)
{subtasks_text}

## Rules
- Execute all subtasks thoroughly
- Write complete, production-quality output
- Use markdown formatting
- Explain your reasoning
- List any assumptions you made

## Output
Write your complete response below.
"""

    def _build_brain_review_prompt(self, task_id: int, task_name: str,
                                    memory: str, output: str, total_tasks: int) -> str:
        """Build prompt for brain review between tasks."""
        is_last = task_id >= total_tasks

        next_instruction = "" if is_last else """
## Your Job
1. Read the memory above — this is your ONLY memory (KV cache was wiped)
2. Read the task output below
3. Write ONE summary line for Task {task_id} (outcome + any plan change)
4. Delete Task {task_id} subtasks from memory (already done by coordinator)
5. Write subtasks for Task {task_id+1}
6. If the output reveals issues, ADAPT the remaining task list

## Output Format
```
SUMMARY: One-line summary of Task {task_id} outcome

NEXT_SPECIALIST: <specialist_name>

NEXT_SUBTASKS:
1. First subtask for next task
2. Second subtask
3. Third subtask

ADAPTATIONS: (if any, otherwise "None")
- Modified Task X to include Y
- Added Task Z for missing piece
```
""".format(task_id=task_id, task_id_plus=task_id+1)

        final_instruction = """
## Your Job
This is the FINAL task. Synthesize all work into a coherent summary.
Output a brief synthesis of the entire project.
""" if is_last else ""

        return f"""You are the Brain. Your KV cache was wiped — memory.md is your ONLY state.

## Your Memory (read carefully — this is everything you know)
{memory}

## Task {task_id} Output (just completed)
{output[:6000]}

{next_instruction}
{final_instruction}
"""

    def _parse_brain_output(self, output: str, current_task_id: int, 
                            total_tasks: int) -> Tuple[str, str, List[str], Optional[List[str]]]:
        """Parse brain's review output."""
        summary = "Task completed."
        next_specialist = "coder"
        next_subtasks = []
        adapted_names = None

        # Extract summary
        summary_match = re.search(r'SUMMARY:\s*(.+?)(?=\n|$)', output, re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).strip()

        # Extract next specialist
        spec_match = re.search(r'NEXT_SPECIALIST:\s*(\w+)', output, re.IGNORECASE)
        if spec_match:
            next_specialist = spec_match.group(1).strip().lower()

        # Extract next subtasks
        subtask_match = re.search(r'NEXT_SUBTASKS:\n(.+?)(?=ADAPTATIONS|\n\n|$)', 
                                  output, re.DOTALL | re.IGNORECASE)
        if subtask_match:
            sub_lines = subtask_match.group(1).strip().split("\n")
            for line in sub_lines:
                match = re.match(r'^\d+\.\s*(.+)$', line.strip())
                if match:
                    next_subtasks.append(match.group(1).strip())

        if not next_subtasks:
            next_subtasks = ["Continue with next phase", "Build on previous output"]

        return summary, next_specialist, next_subtasks, adapted_names

    def _resume_execution(self) -> None:
        """Resume from saved state."""
        # Coordinator already loaded from __init__
        # Verify memory integrity
        if not self.memory_mgr.verify_integrity():
            raise RuntimeError("Cannot resume — memory.md is corrupted or missing")

        # Continue from where we left off
        self._execute_task_loop()

    def _create_config(self, role: str, cfg: dict, key: str = None) -> ModelConfig:
        """Create ModelConfig from config dict."""
        return ModelConfig(
            path=cfg["model_path"],
            max_tokens=cfg.get("max_tokens", 4096),
            temperature=cfg.get("temperature", 0.7),
            description=cfg.get("description", ""),
            ram_estimate_gb=cfg.get("ram_estimate_gb", 10.0),
            role=role
        )

    def _notify(self, message: str) -> None:
        """Send Telegram notification."""
        if self._telegram is None:
            try:
                from utils.telegram_notify import TelegramNotifier
                self._telegram = TelegramNotifier(
                    self.config["telegram"]["token"],
                    self.config["telegram"]["chat_id"]
                )
            except Exception as e:
                logger.debug("Telegram not available: %s", e)
                return

        try:
            self._telegram.send(message)
        except Exception as e:
            logger.debug("Telegram send failed: %s", e)
