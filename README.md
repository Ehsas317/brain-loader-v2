# 🧠 Brain Loader v2

**Sequential Orchestration Architecture for Apple Silicon**

A local multi-model AI system where a large brain model plans and adapts, a small coordinator model routes and manages, and specialist models execute tasks — all hot-swapped within a fixed RAM budget. Designed for large overnight tasks with 50+ tasks and 10–20 subtasks each.

---

## RAM Layout

```
┌─────────────────────────────────────────┐
│  Slot 1: Coordinator  (PERMANENT)       │
│  Qwen2.5-1.5B-Instruct-4bit             │
│  ~4GB (model + KV cache)                │
│  NEVER unloads                          │
├─────────────────────────────────────────┤
│  Slot 2: Hot-Swap  (Brain OR Specialist)│
│  Qwen3-32B-4bit  = ~18GB + 2GB KV       │
│  OR Qwen2.5-Coder-32B = ~18GB + 2GB KV  │
│  Only one at a time                     │
├─────────────────────────────────────────┤
│  System overhead: ~3GB                  │
├─────────────────────────────────────────┤
│  TOTAL: 24GB allocated (of 32GB)        │
└─────────────────────────────────────────┘
```

**Key insight:** Brain and specialists never coexist. The 20GB slot is reused.

---

## Architecture

### Coordinator (always resident, ~4GB)
- Small model (~1.5B params), stays loaded permanently
- Has no planning or reasoning responsibility
- **Responsibilities:**
  - Load / unload brain and specialist models
  - Inject `memory.md` as the first message on every brain reload
  - Pass current task's output file path to brain on reload
  - Write and maintain `state.json`
  - Write specialist outputs to `/outputs/task_N.md`
  - Perform atomic memory writes (`memory.tmp` → rename to `memory.md`)

### Brain (hot-swapped, ~20GB)
- Large model (Qwen3-32B Q4, ~18GB + 2GB KV cache)
- Loaded only when a decision needs to be made
- **On first load** (no memory.md):
  - Receives user goal
  - Produces full task list — task names only, no subtasks yet
  - Writes subtasks for Task 1 only
  - Writes `memory.md`
  - Unloads
- **On every subsequent load:**
  - Reads `memory.md` — its only memory
  - Reads completed task's output file
  - Removes completed task's subtask block from memory.md
  - Appends one summary line to completed task's entry
  - Adapts remaining task list if needed based on real output
  - Writes subtasks for next task only
  - Updates `memory.md`
  - Unloads
- **On final load:**
  - Reads `memory.md` + all `/outputs/task_N.md` files
  - Synthesizes final answer
  - Delivers to user

### Specialists (hot-swapped, ~20GB)
- Domain-specific models loaded into the 20GB slot when brain is out
- Examples: Coder, Researcher, Writer, Debugger, Math, Critic
- **Responsibilities:**
  - Receive subtask list from coordinator
  - Execute all subtasks sequentially
  - Write output to `/outputs/task_N.md`
  - Unload

---

## Execution Flow

```
1. User submits goal
        ↓
2. Coordinator loads Brain (first load — no memory.md)
   Brain produces: full task name list + subtasks for Task 1 only
   Brain writes memory.md
   Brain unloads
        ↓
3. Coordinator loads Specialist assigned for Task 1
   Specialist receives Task 1 subtask list
   Specialist executes all subtasks
   Specialist writes output to /outputs/task_1.md
   Specialist unloads
        ↓
4. Coordinator loads Brain
   Coordinator injects memory.md as first message
   Coordinator passes /outputs/task_1.md path
   Brain reads memory.md → fully caught up
   Brain reads task_1 output → assesses real result
   Brain removes Task 1 subtask block from memory.md
   Brain appends one summary line to Task 1 entry
   Brain adapts task list if needed
   Brain writes Task 2 subtasks
   Brain updates memory.md
   Brain unloads
        ↓
5. Repeat steps 3–4 for every task
        ↓
6. All tasks complete
   Coordinator loads Brain (final load)
   Brain reads memory.md + all output files
   Brain synthesizes final answer → delivers to user
```

---

## memory.md — Persistent Brain State

### Core Principle
Brain's KV cache is wiped on every unload. `memory.md` is the only cross-load memory. File size stays **constant** throughout the entire run — completed task subtasks are deleted, only one task's subtasks exist at any time.

### Structure
```markdown
# Brain State · Task 3 of 50

## LOCKED — Never modify
Goal: Build a React Native fitness app with AI meal planner
Hard constraints: Must use TypeScript, must work offline

## Task List
- [x] Task 1: Research EV market       — output good, proceeded as planned
- [x] Task 2: Competitor analysis      — output thin, added Task 8 critic pass
- [ ] Task 3: Write analysis draft     ← CURRENT
- [ ] Task 4: Generate charts
- [ ] Task 5: Critique draft
...
- [ ] Task 50: Final synthesis

## Current Task
Task: 3
Specialist: Writer
Subtasks:
  1. Write intro using /outputs/task_1.md data
  2. Write market size section
  3. Write key players section using /outputs/task_2.md

## ⚠ MANDATORY LAST ACTION BEFORE UNLOAD
Delete current subtask block. Append one summary line to completed task. Write next task subtasks. Update this file.
```

### What Changes on Each Brain Load
| Field | Action |
|---|---|
| Completed task entry | Append one summary line — outcome + any plan change |
| Completed task subtasks | **Delete entirely** |
| Next task subtasks | Write fresh |
| Task list | Modify if plan needs adapting |
| LOCKED section | Never touch |

---

## Key Properties

| Property | How it's achieved |
|---|---|
| **Constant memory file size** | Completed subtasks deleted on every brain load. Only current task's subtasks exist. |
| **One-line history** | Each completed task retains exactly one summary line. 50 tasks = 50 lines max. |
| **Adaptive planning** | Brain reads real output before every decision. Plan evolves based on what actually happened. |
| **Stateless model, stateful system** | Brain has no persistent RAM state. All state lives in `memory.md` on disk. |
| **Crash recovery** | Atomic writes + `state.json` checkpoints. Resume from last completed task. |
| **Specialist routing** | Tasks go to domain-specific models. |
| **Zero redundant RAM** | Brain and specialists never coexist. Peak = 4GB + 20GB = 24GB hard ceiling. |

---

## Installation

```bash
# 1. Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your Telegram token and chat ID

# 3. Download models
# Coordinator (permanent)
huggingface-cli download mlx-community/Qwen2.5-1.5B-Instruct-4bit

# Brain (hot-swap)
huggingface-cli download mlx-community/Qwen3-32B-4bit

# Specialists (hot-swap, choose what you need)
huggingface-cli download mlx-community/Qwen2.5-Coder-32B-Instruct-4bit
```

---

## Usage

```bash
# New project
python main.py "Build a React Native fitness app with AI meal planner"

# With constraints
python main.py "Build a SaaS dashboard" --constraints "Must use Next.js, must have dark mode"

# Resume crashed project
python main.py --resume

# List specialists
python main.py --list-specialists
```

---

## Output Structure

```
outputs/
├── task_001_coder.md       # Specialist outputs
├── task_002_researcher.md
├── task_003_writer.md
├── ...
└── FINAL_ANSWER.md         # Brain's synthesized result

memory.md                   # Brain's persistent state (constant size)
state.json                  # Coordinator tracking + crash recovery
```

---

## Telegram Notifications

- 🧠 Project start
- 📋 Master plan created (task count)
- ⚙️ Each task start (specialist name)
- ✅ Task complete (summary)
- 🚨 Memory corruption halt
- 🎉 Project complete with file locations

---

## Coordinator Rules (Hardcoded)

1. On every brain load: inject full `memory.md` as first message
2. Never load two large models simultaneously — confirm unload before next load
3. After specialist completes: write output to `/outputs/task_N.md` before loading brain
4. All memory writes are atomic: write to `memory.tmp` first, then rename to `memory.md`
5. If brain fails to update `memory.md` before unloading: **halt, do not proceed, alert**
6. Update `state.json` after every state change
7. On final load: pass all output file paths to brain, do not interrupt

---

Built for overnight runs on MacBook Pro M1 Max. 🌙
