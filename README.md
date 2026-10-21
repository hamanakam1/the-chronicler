# The Chronicler

**The memory core of the autonomous AI software factory.**

The Chronicler is the background daemon that cures *comprehension debt* — the gap where the execution agent (Taskrivet) burns retries figuring out a local network config, then forgets it tomorrow. It is the pipeline's amnesia-buster: an autonomous lore-keeper, meta-learning brain, and documentation engine that watches the append-only **EdgeRecord** ledger, extracts the golden fix from failure logs, hardens the target repository's rules, and commits the upgraded rules plus synthesized lore docs back to local Git — all headless, all local-first, all via local Ollama.

## The Mission

> If the bot burned through three retry loops figuring out a local network config, it will make the exact same mistake tomorrow. The Chronicler is the amnesia-buster.

## Core Autonomous Superpowers

1. **Asynchronous Ingest** — continuously polls the EdgeRecord ledger for friction points: failed execution logs, nasty stack traces, and the exact correction prompts that eventually fixed the bug.
2. **Pattern Extraction** — routes the raw friction through the local LLM (Ollama + Qwen) asking: *"What did the bots mess up, and what's the permanent fix?"*
3. **Dynamic Rule Hardening** — drafts new architectural rules / prompt context injections (e.g. updates to `RULES.json`, `SKILLS.md`) so the next pipeline run is inherently smarter.
4. **Lore Synthesis (Auto-Docs)** — translates raw semantic git diffs into human-readable markdown documentation, API maps, and system state records.

## Execution Environment

- **Local-first, containerized background daemon** (Docker), running stealthily in the background during idle compute cycles.
- **AI Integration:** no proprietary cloud LLMs. All log analysis and pattern extraction route through local Ollama/OpenClaw endpoints using models like Qwen.
- **State & Logging:** reads the "battle scars" from the append-only ledger (EdgeRecord), commits the "lessons learned" back to local Git.
- **Interface:** strictly CLI-driven and headless. No GUI. It watches, thinks, and writes in the shadows.

## Quick Start

```bash
# 1. Clone the memory core
git clone <target-repo> the-chronicler && cd the-chronicler

# 2. Point it at your local ledger + target repo (env overrides below)
export CHRONICLER_LEDGER_PATH=/Users/michaelhamanaka/.taskrivet/ledger.sqlite
export CHRONICLER_REPO_ROOT=/Users/michaelhamanaka/Projects/taskrivet

# 3. Sanity-check the black ops setup
chronicler doctor

# 4. Ingest one batch and commit what it learns
chronicler run --once

# 5. Watch the shadows
chronicler watch
```

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `CHRONICLER_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `CHRONICLER_OLLAMA_MODEL` | `qwen3.8:latest` | Local reasoning model |
| `CHRONICLER_LEDGER_PATH` | `~/.taskrivet/ledger.sqlite` | Append-only EdgeRecord ledger |
| `CHRONICLER_REPO_ROOT` | target checkout | Repo receiving hardened rules + docs |
| `CHRONICLER_RULES_FILE` | `RULES.json` | Hardened ruleset output target |
| `CHRONICLER_LORE_DIR` | `docs/lore` | Generated lore docs location |
| `CHRONICLER_STATE_PATH` | `~/.chronicler/state.json` | Daemon watermark / dedupe state |
| `CHRONICLER_POLL_INTERVAL_SECONDS` | `30` | Watcher cadence |
| `CHRONICLER_AUDIT_BATCH_LIMIT` | `25` | Max audits per cycle |
| `CHRONICLER_GIT_REMOTE` | `origin` | Git remote for zero-intervention push |
| `CHRONICLER_GIT_PUSH` | `true` | Enable automatic push |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ EdgeRecord      │────▶│ Meta-Learning    │────▶│ Local Git / FS   │
│ Watcher         │     │ Brain            │     │ Ninja            │
│ (polling)       │     │ (Ollama + Qwen)  │     │ (commit+push)    │
└─────────────────┘     └──────────────────┘     └──────────────────┘
        ▲                        │                          │
        └──────── Lore Docs ◀────┘                          │
                          ┌──────────────┘
                          ▼
                   Target Repo
                   (RULES.json, SKILLS.md, docs/lore/)
```

Module map:

| Module | Responsibility |
| --- | --- |
| `chronicler.schemas` | Pydantic data contracts: `ExecutionAuditLog`, `ExtractedHeuristic`, `DocUpdatePayload` |
| `chronicler.ledger` | EdgeRecord reader (`SQLiteEdgeRecordReader`) + async `EdgeRecordWatcher` poller |
| `chronicler.llm` | `OllamaClient` + prompt builders (`What did the bots mess up, and what's the permanent fix?`) |
| `chronicler.brain` | `ChroniclerBrain` orchestration loop + `HeuristicExtractor` + `ChroniclerState` |
| `chronicler.rules` | `RuleHardener` — drafts hardened rules / prompt injections |
| `chronicler.docs` | `DocSynthesizer` — turns heuristics into `DocUpdatePayload` |
| `chronicler.gitops` | `LocalGitCommitter` — safe writes + zero-intervention commit/push |
| `chronicler.cli` | Headless CLI: `run`, `watch`, `doctor` |

## Deliverables Implemented

1. **Pydantic / JSON Schemas (Data Contracts)**
   - `ExecutionAuditLog` — the raw friction data scooped from EdgeRecord (task, category, fingerprint, summary, resolution, timestamps).
   - `ExtractedHeuristic` — the "Aha!" moment: insight, generalized rule, confidence, status (`draft`/`promoted`).
   - `DocUpdatePayload` — structured map of generated markdown → target file paths.
2. **Architecture & Directory Tree** — modular layout above with strict separation between watcher / brain / rules / docs / git layers.
3. **Meta-Learning Brain (Core Orchestration)** — `ChroniclerBrain.run_cycle` scoops the latest failure batch, asks local Ollama, formats the fix into the target ruleset, commits rules + docs.
4. **Local Git & File-System Ninja Module** — `LocalGitCommitter` safely writes LLM payloads to disk and executes local `git commit` + push with zero human intervention.

## Safety & Hardening Notes

- Path-traversal guard in the committer (`UnsafePathError`) before any write.
- Heuristic IDs are deterministically derived from `(failure_category, fingerprint)` so dedupe across cycles is stable.
- Watermarking via `ChroniclerState` prevents re-processing the same ledger entries.
- Push is configurable (`CHRONICLER_GIT_PUSH`) and commit receipts are captured per cycle.
