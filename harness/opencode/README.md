# OpenCode harness

Arm A: `opencode.json` MCP local/remote entry, `enabled:true`, drive via `opencode run --format json`. Gate via `permission: {"<server>_*": "ask|allow|deny"}`.

Arms C/D: `.opencode/plugins/substrate.ts` with `tool()` + `tool.execute.before/after` + source-only `tool.definition`. No per-inference swap — use per-message allow map only via Server/SDK, static config otherwise.
