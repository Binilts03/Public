# Claude API harness

Arm A: `mcp_servers:[{type:url}]` + `mcp_toolset defer_loading:true` + `tool_search_tool_regex|bm25`. Keep same `tools` array every turn.

Arms B/C: full catalog as deferred direct tools + custom retriever returning `tool_result:{content:[{type:tool_reference}]}`. E2E compare via `claude --bare -p --output-format json`, gate on `system/init.mcp_servers/errors`.
