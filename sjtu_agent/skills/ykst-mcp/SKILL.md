Use this skill when the user asks to read, search, summarize, reply to, like, favorite, manage identities for, or otherwise work with YKST/Treehole through an enabled YKST MCP server.

Prefer YKST MCP tools whose names start with `mcp__ykst__treehole_` for Treehole operations. Use read/search tools before answering questions about a specific thread or post, and do not invent thread contents from ids or titles alone.

Writing to Treehole is a high-impact action. Draft the exact content or action first unless the user has clearly asked you to publish, reply, switch identity, like/rate, favorite, subscribe, check in, or change settings. When calling write tools, pass `confirm: true` only after the intended target and arguments are clear. Report the resulting thread id, post id, identity id, or updated state from the tool result.

If a YKST MCP tool reports that the session is missing, call `mcp__ykst__treehole_auth_status` if available and then ask the user to run the YKST MCP login flow. In this repo that usually means `sjtu-agent setup-ykst-mcp --login`, or the `login_command` returned by `setup_ykst_mcp`.
