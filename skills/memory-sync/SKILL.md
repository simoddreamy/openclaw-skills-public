# memory-sync

## Description
Synchronize agent sessions into memory.db, with incremental extraction, safe history-only cleansing prompts, and session discovery via `openclaw sessions --all-agents`.

## Instructions
- Use `memory_sync.sh` as the canonical sync script.
- Session discovery must prefer `openclaw sessions --all-agents` and fall back to `sessions.json`.
- Avoid duplicate inserts by respecting `last_line_processed` and content-level dedupe.
- AI cleanse prompts must treat messages as historical records only.
