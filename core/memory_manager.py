"""
Memory Manager
Handles memory.md — the Brain's ONLY persistent state across loads.

Core principle: Brain never writes directly. Coordinator handles atomic writes.
Completed task subtasks are DELETED. Only current task subtasks exist.
File size stays CONSTANT regardless of task count.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Manages memory.md with atomic writes and strict structure.

    Structure:
      # Brain State · Task N of M
      ## LOCKED — Never modify
      Goal: <user goal>
      Hard constraints: <non-negotiables>
      ## Task List
      - [x] Task 1: Name — one-line summary
      - [x] Task 2: Name — one-line summary
      - [ ] Task 3: Name ← CURRENT
      - [ ] Task 4: Name
      ## Current Task
      Task: N
      Specialist: <name>
      Subtasks:
        1. <subtask>
        2. <subtask>
      ## ⚠ MANDATORY LAST ACTION BEFORE UNLOAD
      Delete current subtask block. Append one summary line to completed task. Write next task subtasks. Update this file.
    """

    def __init__(self, memory_file: str = "./memory.md"):
        self.memory_file = Path(memory_file)
        self.tmp_file = self.memory_file.with_suffix(".md.tmp")

    def initialize(self, goal: str, constraints: str, task_names: List[str],
                   first_task_specialist: str, first_subtasks: List[str]) -> None:
        """
        First load: Create memory.md from scratch.
        Brain produces full task name list + Task 1 subtasks only.
        """
        content = f"""# Brain State · Task 1 of {len(task_names)}

## LOCKED — Never modify
Goal: {goal}
Hard constraints: {constraints}

## Task List
"""
        for i, name in enumerate(task_names, 1):
            status = " " if i > 1 else "x"
            current = " ← CURRENT" if i == 1 else ""
            content += f"- [{status}] Task {i}: {name}{current}\n"

        content += f"""
## Current Task
Task: 1
Specialist: {first_task_specialist}
Subtasks:
"""
        for i, st in enumerate(first_subtasks, 1):
            content += f"  {i}. {st}\n"

        content += """
## ⚠ MANDATORY LAST ACTION BEFORE UNLOAD
Delete current subtask block. Append one summary line to completed task. Write next task subtasks. Update this file.
"""
        self._atomic_write(content)
        logger.info("[MemoryManager] Initialized memory.md with %d tasks", len(task_names))

    def read(self) -> str:
        """Read current memory.md content."""
        if not self.memory_file.exists():
            return ""
        with open(self.memory_file, "r") as f:
            return f.read()

    def update_after_task(self, task_num: int, summary: str,
                          next_task_specialist: Optional[str] = None,
                          next_subtasks: Optional[List[str]] = None,
                          adapted_task_names: Optional[List[str]] = None) -> None:
        """
        Brain's mandatory action before every unload:
        1. Remove completed task subtasks
        2. Append one summary line to completed task
        3. Write next task subtasks (or mark complete)
        4. Update task list
        """
        current = self.read()

        # Update task list — mark completed, update summaries
        lines = current.split("\n")
        new_lines = []
        in_task_list = False

        for line in lines:
            # Detect task list section
            if line.strip() == "## Task List":
                in_task_list = True
                new_lines.append(line)
                continue

            if in_task_list and line.startswith("## "):
                in_task_list = False

            if in_task_list:
                # Update completed task
                done_match = re.match(r'^(\s*- \[)(.)\] Task ' + str(task_num) + r': (.+?)(?: — .+)?(\s*← CURRENT)?$', line)
                if done_match:
                    # Mark done, append summary, remove CURRENT marker
                    new_line = f"{done_match.group(1)}x] Task {task_num}: {done_match.group(3)} — {summary}"
                    new_lines.append(new_line)
                    continue

                # Update next task — add CURRENT marker
                if next_subtasks:
                    next_match = re.match(r'^(\s*- \[)(.)(\] Task ' + str(task_num + 1) + r': .+?)$', line)
                    if next_match:
                        new_line = f"{next_match.group(1)} {next_match.group(3)} ← CURRENT"
                        new_lines.append(new_line)
                        continue

            new_lines.append(line)

        # Rebuild content
        content = "\n".join(new_lines)

        # Replace Current Task section
        if next_subtasks and next_task_specialist:
            # Remove old Current Task block and insert new one
            pattern = r'(## Current Task\n).+?(?=\n## ⚠|$)'
            replacement = f"""Task: {task_num + 1}
Specialist: {next_task_specialist}
Subtasks:
"""
            for i, st in enumerate(next_subtasks, 1):
                replacement += f"  {i}. {st}\n"

            content = re.sub(pattern, r"\1" + replacement, content, flags=re.DOTALL)

            # Update header
            total_tasks = len(re.findall(r'^\s*- \[', content, re.MULTILINE))
            content = re.sub(
                r'# Brain State · Task \d+ of \d+',
                f'# Brain State · Task {task_num + 1} of {total_tasks}',
                content
            )
        else:
            # Final task — remove Current Task section entirely
            content = re.sub(r'## Current Task\n.+?(?=\n## ⚠|$)', '', content, flags=re.DOTALL)
            content = re.sub(
                r'# Brain State · Task \d+ of \d+',
                f'# Brain State · COMPLETE',
                content
            )

        self._atomic_write(content)
        logger.info("[MemoryManager] Updated after Task %d. Summary: %s", task_num, summary[:60])

    def get_current_task_info(self) -> Dict:
        """Parse current task number, specialist, and subtasks from memory."""
        content = self.read()
        info = {"task_num": None, "specialist": None, "subtasks": [], "total_tasks": 0}

        # Extract task number from header
        header_match = re.search(r'Task (\d+) of (\d+)', content)
        if header_match:
            info["task_num"] = int(header_match.group(1))
            info["total_tasks"] = int(header_match.group(2))

        # Extract specialist
        spec_match = re.search(r'Specialist:\s*(.+?)(?:\n|$)', content)
        if spec_match:
            info["specialist"] = spec_match.group(1).strip()

        # Extract subtasks
        subtask_match = re.search(r'Subtasks:\n((?:\s+\d+\..*\n?)+)', content)
        if subtask_match:
            subtasks_text = subtask_match.group(1)
            info["subtasks"] = re.findall(r'\d+\.\s*(.+?)(?=\n\d+\.|\n##|$)', 
                                          subtasks_text, re.DOTALL)
            info["subtasks"] = [s.strip() for s in info["subtasks"] if s.strip()]

        return info

    def get_task_list(self) -> List[Dict]:
        """Parse all tasks from memory."""
        content = self.read()
        tasks = []

        task_lines = re.findall(r'^\s*- \[(.?)\] Task (\d+): (.+?)(?: — |$)', 
                                content, re.MULTILINE)
        for status, num, name in task_lines:
            tasks.append({
                "num": int(num),
                "name": name.strip(),
                "done": status == "x"
            })

        return tasks

    def _atomic_write(self, content: str) -> None:
        """Atomic write: write to tmp, then rename."""
        try:
            with open(self.tmp_file, "w") as f:
                f.write(content)
            os.replace(self.tmp_file, self.memory_file)
        except Exception as e:
            logger.error("[MemoryManager] Atomic write failed: %s", e)
            raise

    def verify_integrity(self) -> bool:
        """Verify memory.md exists and has required sections."""
        if not self.memory_file.exists():
            return False

        content = self.read()
        required = ["## LOCKED", "## Task List", "## ⚠ MANDATORY"]
        return all(section in content for section in required)
