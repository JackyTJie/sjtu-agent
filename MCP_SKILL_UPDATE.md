# MCP and Skill Support Update

Disclosure: the optional Shuiyuan MCP setup in this update installs
[`dajiaohuang/shuiyuan-mcp`](https://github.com/dajiaohuang/shuiyuan-mcp), which
is maintained by the PR author of this integration. The installer pins the
checkout to a known commit by default instead of silently pulling future changes.

披露说明：本更新中的可选 Shuiyuan MCP 安装流程会安装
[`dajiaohuang/shuiyuan-mcp`](https://github.com/dajiaohuang/shuiyuan-mcp)，该仓库由本集成 PR 作者维护。安装器默认 pin 到一个已知 commit，而不是静默拉取未来变更。

## English

This update adds an extension layer for `sjtu-agent` so the agent can load
external MCP servers and prompt-only skills in addition to its built-in tools.

### What Changed

- Added a dynamic tool registry that combines built-in tools and enabled MCP
  tools.
- Added MCP client support for `stdio`, `sse`, and `streamable_http` transports.
- Added prompt-only skill loading through `SKILL.md` files.
- Updated terminal chat, Web UI, Telegram bot, Feishu bot, and WeChat bot to use
  the same dynamic tool and prompt loading path.
- Added a bundled `shuiyuan-mcp` skill.
- Added a setup flow for
  [`dajiaohuang/shuiyuan-mcp`](https://github.com/dajiaohuang/shuiyuan-mcp).
- Added a bundled `ykst-mcp` skill and setup flow for
  [`dajiaohuang/ykst-treehole-mcp`](https://github.com/dajiaohuang/ykst-treehole-mcp).
- Added `add-mcp-server` / `add_mcp_server` for custom MCP server registration.
- Added `add-skill` / `add_skill` for custom prompt-only skills.
- Added `create_skill`, `list_skills`, and `manage_skill` so the chat agent can
  create skills from requirements, ask clarifying questions, and manage enabled
  skills.

### New Command

```bash
python -m sjtu_agent.cli setup-shuiyuan-mcp
python -m sjtu_agent.cli setup-ykst-mcp
```

### Trigger Paths

There are two supported ways to trigger the setup:

- CLI: run `python -m sjtu_agent.cli setup-shuiyuan-mcp`.
- Chat agent: ask the agent to "install Shuiyuan MCP", "enable Shuiyuan MCP",
  or "load dajiaohuang/shuiyuan-mcp"; the model can then call the built-in
  `setup_shuiyuan_mcp` tool. The first chat-triggered call only warns that this
  installs an external GitHub repository and asks for confirmation. The model
  should call the tool again with `acknowledge_external_repo=true` only after the
  user explicitly confirms.
- CLI: run `python -m sjtu_agent.cli setup-ykst-mcp`.
- Chat agent: ask the agent to "install YKST MCP", "enable Treehole MCP", or
  "load dajiaohuang/ykst-treehole-mcp"; the model can then call
  `setup_ykst_mcp`. The first chat-triggered call only warns that this installs
  an external GitHub repository and may run a local browser-login helper. The
  model should call the tool again with `acknowledge_external_repo=true` only
  after the user explicitly confirms.

Custom MCP servers can also be added in two ways:

- CLI: `python -m sjtu_agent.cli add-mcp-server my-tools --transport stdio --command python --arg /path/to/server.py`
- Chat agent: ask the agent to add or register a custom MCP server. The first
  tool call returns an external-command/URL warning; only after user confirmation
  should the model call `add_mcp_server` with `acknowledge_external_mcp=true`.

Custom prompt-only skills can be added in two ways:

- CLI: `python -m sjtu_agent.cli add-skill my-skill --content-file /path/to/SKILL.md`
- CLI: `python -m sjtu_agent.cli list-skills`
- CLI: `python -m sjtu_agent.cli manage-skill disable my-skill`
- Chat agent: ask the agent to add a skill and provide the `SKILL.md` content or
  a local source file path; the model can call `add_skill`.
- Chat agent: ask the agent to create a skill from a described need. The model
  calls `create_skill`; if the tool returns `requires_more_info`, it asks the
  returned questions before creating the skill. Skill listing and enable/disable
  or deletion requests route through `list_skills` and `manage_skill`.

The command clones or updates `dajiaohuang/shuiyuan-mcp`, installs Node
dependencies, checks out the pinned commit, builds the MCP server, registers it
in `config.json`, and enables the bundled `shuiyuan-mcp` skill.

The YKST command clones or updates `dajiaohuang/ykst-treehole-mcp`, installs Node
dependencies, checks out the pinned commit, registers it in `config.json`, and
enables the bundled `ykst-mcp` skill. Treehole write operations exposed by that
MCP require `confirm: true` after the action is reviewed.

Useful options:

```bash
python -m sjtu_agent.cli setup-shuiyuan-mcp --read-only
python -m sjtu_agent.cli setup-shuiyuan-mcp --login
python -m sjtu_agent.cli setup-shuiyuan-mcp --install-dir /path/to/shuiyuan-mcp
python -m sjtu_agent.cli setup-shuiyuan-mcp --ref <commit-or-tag>
```

### Config Format

External MCP servers are configured in `config.json`:

```json
{
  "mcp_servers": {
    "shuiyuan": {
      "enabled": true,
      "transport": "stdio",
      "command": "node",
      "args": ["/path/to/shuiyuan-mcp/dist/shuiyuan-mcp.js"],
      "cwd": "/path/to/shuiyuan-mcp",
      "call_timeout": 180
    }
  }
}
```

Enabled skills are configured with:

```json
{
  "skills": {
    "enabled": ["shuiyuan-mcp"],
    "dirs": []
  }
}
```

MCP tools are exposed to the LLM using this naming pattern:

```text
mcp__<server_id>__<tool_name>
```

For example:

```text
mcp__shuiyuan__discourse_search
```

### Notes

- `shuiyuan-mcp` requires Node.js 24 or newer.
- The default pinned ref is `5c79b6e767f5aa55a3f342f5550ec74520fd52e5`.
- If Shuiyuan MCP reports a missing profile or cookies, run the `login_command`
  printed by `setup-shuiyuan-mcp`.
- The existing built-in tools remain available and backward compatible.

## 中文

这次更新为 `sjtu-agent` 增加了扩展层，使 agent 除了内置工具以外，还能加载外部 MCP Server 和 prompt-only skill。

### 主要变化

- 新增动态工具注册表，可以合并内置工具和已启用的 MCP 工具。
- 新增 MCP client 支持，支持 `stdio`、`sse`、`streamable_http` 三种传输方式。
- 新增基于 `SKILL.md` 的 prompt-only skill 加载机制。
- 终端对话、Web UI、Telegram Bot、飞书 Bot、微信 Bot 统一接入动态工具和动态 system prompt。
- 内置一个 `shuiyuan-mcp` skill。
- 新增
  [`dajiaohuang/shuiyuan-mcp`](https://github.com/dajiaohuang/shuiyuan-mcp)
  的安装和启用流程。

### 新命令

```bash
python -m sjtu_agent.cli setup-shuiyuan-mcp
```

### 触发方式

目前支持两种触发方式：

- CLI：运行 `python -m sjtu_agent.cli setup-shuiyuan-mcp`。
- 对话 agent：对 agent 说「安装水源 MCP」「启用 Shuiyuan MCP」或
  「加载 dajiaohuang/shuiyuan-mcp」，模型会调用内置的
  `setup_shuiyuan_mcp` 工具。第一次由对话触发时只会提示这是外部 GitHub
  仓库安装并要求确认；只有用户明确确认后，模型才应再次调用工具并传入
  `acknowledge_external_repo=true` 开始安装。

这个命令会拉取或更新 `dajiaohuang/shuiyuan-mcp`，安装 Node 依赖，checkout 到默认 pin 的 commit，构建 MCP server，写入 `config.json`，并启用内置的 `shuiyuan-mcp` skill。

常用选项：

```bash
python -m sjtu_agent.cli setup-shuiyuan-mcp --read-only
python -m sjtu_agent.cli setup-shuiyuan-mcp --login
python -m sjtu_agent.cli setup-shuiyuan-mcp --install-dir /path/to/shuiyuan-mcp
python -m sjtu_agent.cli setup-shuiyuan-mcp --ref <commit-or-tag>
```

### 配置格式

外部 MCP Server 写在 `config.json` 的 `mcp_servers` 字段：

```json
{
  "mcp_servers": {
    "shuiyuan": {
      "enabled": true,
      "transport": "stdio",
      "command": "node",
      "args": ["/path/to/shuiyuan-mcp/dist/shuiyuan-mcp.js"],
      "cwd": "/path/to/shuiyuan-mcp",
      "call_timeout": 180
    }
  }
}
```

启用 skill 的配置：

```json
{
  "skills": {
    "enabled": ["shuiyuan-mcp"],
    "dirs": []
  }
}
```

MCP 工具会以如下命名方式暴露给大模型：

```text
mcp__<server_id>__<tool_name>
```

例如：

```text
mcp__shuiyuan__discourse_search
```

### 注意事项

- `shuiyuan-mcp` 需要 Node.js 24 或更高版本。
- 默认 pin 的 ref 是 `5c79b6e767f5aa55a3f342f5550ec74520fd52e5`。
- 如果 Shuiyuan MCP 提示缺少 profile 或 cookie，请运行 `setup-shuiyuan-mcp` 输出里的 `login_command`。
- 原有内置工具仍然保留，并保持向后兼容。
## Custom MCP and Skill Trigger Paths / 自定义 MCP 和 Skill 触发方式

Custom MCP servers:

- CLI: `python -m sjtu_agent.cli add-mcp-server my-tools --transport stdio --command python --arg /path/to/server.py`
- Chat agent: ask the agent to add or register a custom MCP server. The first
  call only warns that an external command or URL will be trusted; after user
  confirmation, call `add_mcp_server` with `acknowledge_external_mcp=true`.

自定义 MCP server：

- CLI：`python -m sjtu_agent.cli add-mcp-server my-tools --transport stdio --command python --arg /path/to/server.py`
- 对话 agent：让 agent 添加或注册自定义 MCP server。第一次调用只提示会信任外部命令或 URL；用户确认后，再调用 `add_mcp_server` 并传入 `acknowledge_external_mcp=true`。

Custom prompt-only skills:

- CLI: `python -m sjtu_agent.cli add-skill my-skill --content-file /path/to/SKILL.md`
- CLI: `python -m sjtu_agent.cli list-skills`
- CLI: `python -m sjtu_agent.cli manage-skill disable my-skill`
- Chat agent: ask the agent to add a skill and provide the full `SKILL.md`
  content or a local source file path; the model can call `add_skill`.
- Chat agent: ask the agent to create a skill from a described need. The model
  calls `create_skill`; if more detail is needed, it asks the returned
  questions. Skill listing and enable/disable/delete requests route to
  `list_skills` and `manage_skill`.

自定义 prompt-only skill：

- CLI：`python -m sjtu_agent.cli add-skill my-skill --content-file /path/to/SKILL.md`
- 对话 agent：让 agent 添加 skill，并提供完整 `SKILL.md` 内容或本地文件路径；模型可调用 `add_skill`。
