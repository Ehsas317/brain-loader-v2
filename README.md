# Relay (formerly Brain Loader v2)

Relay is the second iteration of the AI Build Engine. Unlike Forge, Relay is designed for continuous operation — the coordinator stays resident and relays the baton between hot-swapped models. The core metaphor is handoffs, not planning. Need DeepSeek for one task? Load it. Need Mistral for the next? Swap it in. All while maintaining full context.

## What's New in Relay

- **Resident Coordinator**: The orchestrator stays running, models come and go
- **Hot-Swappable Models**: Load and unload models on demand without losing context
- **Cloud-First Priority**: Local models are optional, not required
- **Persistent State**: Full JSON state management with resume capability
- **Context-Aware Handoffs**: Previous task outputs inform the next task automatically

## Hardware

MacBook Pro M1 Max 32GB (25GB allocated to Relay)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up config
cp config.yaml.example config.yaml
# Edit config.yaml with your tokens

# Run
python main.py "Build a React Native fitness app with AI meal planner"
```

## Architecture

Relay introduces a resident coordinator pattern. The orchestrator stays in memory throughout the build process while models are hot-swapped in and out as needed.

### Key Components

- **Orchestrator** (`core/orchestrator.py`) — Resident controller, manages the full build lifecycle
- **State Manager** (`core/state_manager.py`) — Persistent JSON state with resume support
- **Memory Manager** (`core/memory_manager.py`) — Context window management for long conversations
- **Model Manager** (`core/model_manager.py`) — Hot-swappable model loading/unloading
- **Telegram Notifier** (`utils/telegram_notify.py`) — Real-time progress updates

### Workflow

1. Relay receives a build request
2. The Brain (cloud or local) creates a plan
3. For each task, Relay loads the optimal model
4. Task is executed, output is reviewed
5. Model is unloaded, context is preserved
6. Next task loads the next optimal model
7. Repeat until complete

## Model Management

Relay supports multiple model backends:

| Backend | Models | Use Case |
|---------|--------|----------|
| Local MLX | Custom QLoRA models | Primary (Apple Silicon) |
| DeepSeek | deepseek-chat | Budget cloud fallback |
| Mistral | mistral-small | Fast cloud fallback |
| Anthropic | claude-sonnet-4-20250514 | Quality cloud fallback |
| Together | Llama-4-Maverick-17B | Open-source cloud fallback |

## State Management

Relay maintains persistent state in `memory/state.json`:

```json
{
  "app_idea": "Build a fitness app",
  "current_phase": "execution",
  "current_task_index": 3,
  "tasks": [...],
  "completed_tasks": ["T001", "T002"],
  "outputs": {...},
  "reviews": {...},
  "metadata": {...}
}
```

State is saved after every task, enabling robust resume functionality.

## Logs

All logs are written to `./logs/`. Check `logs/relay_*.log` for detailed execution traces.

## License

MIT
