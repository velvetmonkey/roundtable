# Roundtable AI MCP Server

[![PyPI version](https://badge.fury.io/py/roundtable-ai.svg)](https://badge.fury.io/py/roundtable-ai)
[![Tests](https://github.com/velvetmonkey/roundtable/actions/workflows/test.yml/badge.svg)](https://github.com/velvetmonkey/roundtable/actions/workflows/test.yml)
[![CodeQL](https://github.com/velvetmonkey/roundtable/actions/workflows/codeql.yml/badge.svg)](https://github.com/velvetmonkey/roundtable/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/velvetmonkey/roundtable/branch/main/graph/badge.svg)](https://codecov.io/gh/velvetmonkey/roundtable)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[![Install Roundtable AI MCP Server in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](cursor://anysphere.cursor-deeplink/mcp/install?name=roundtable-ai&config=eyJ0eXBlIjoic3RkaW8iLCJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJyb3VuZHRhYmxlLWFpQGxhdGVzdCJdLCJlbnYiOnsiQ0xJX01DUF9TVUJBR0VOVFMiOiJjb2RleCxjbGF1ZGUsY3Vyc29yLGdlbWluaSJ9fQo=)

Stop copy-pasting between AI models. Roundtable AI is a local MCP server that lets your primary AI assistant delegate tasks to specialized models like Gemini, Claude, Codex, and Cursor. Solve complex engineering problems in parallel, directly from your IDE.

**Key Features:**
- **Context Continuity**: Shared project context across all sub-agents
- **Parallel Execution**: All agents work simultaneously
- **Model Specialization**: Right AI for each task (Gemini's 1M context, Claude's reasoning, Codex's implementation, Qwen's code generation)
- **Zero Markup**: Uses your existing CLI tools and API subscriptions
- **26+ IDE Support**: Works with Claude Code, Cursor, VS Code, JetBrains, and more

## Table of Contents

- [Quick Start](#quick-start)
- [What is Roundtable AI](#what-is-roundtable-ai)
- [Technical Architecture](#technical-architecture)
- [Why Multi-Agent vs Single AI](#why-multi-agent-vs-single-ai)
- [Real-World Examples](#real-world-examples)
- [Installation](#installation)
- [IDE Integration](#ide-integration)
- [Advanced Configuration](#advanced-configuration)
- [Contributing](#contributing)
- [License](#license)

## Quick Start

```bash
# Install Roundtable AI (standard)
pip install roundtable-ai

# Or from GitHub (until PyPI merge)
pip install git+https://github.com/velvetmonkey/roundtable.git@v0.5.1

# Check available AI tools
roundtable-ai --check

# Start with all available tools
roundtable-ai

# Use specific assistants only
roundtable-ai --agents codex,claude,qwen
```

**One-liner for Claude Code:**
```bash
claude mcp add roundtable-ai -- roundtable-ai --agents gemini,claude,codex,cursor,qwen
```

**Try this multi-agent prompt in your IDE:**
```markdown
The user dashboard is randomly slow for enterprise customers.

Use Gemini SubAgent to analyze frontend performance issues in the React components, especially expensive re-renders and inefficient data fetching.

Use Codex SubAgent to examine the backend API endpoint for N+1 queries and database bottlenecks.

Use Claude SubAgent to review the infrastructure logs and identify memory/CPU pressure during peak hours.
```

## What is Roundtable AI

Roundtable AI is a local Model Context Protocol (MCP) server that coordinates specialized AI sub-agents to solve complex engineering problems. Instead of manually switching between different AI tools, you delegate tasks from a single prompt in your IDE, and Roundtable manages the coordination, context sharing, and response synthesis.

### Key Benefits

- **Context Continuity**: The primary agent provides shared, rich context to all sub-agents
- **Parallel Execution**: All agents work simultaneously, drastically reducing wait time
- **Model Specialization**: Use the right AI for each task - Gemini's 1M context for analysis, Claude's reasoning for logic, Codex for implementation
- **No Extra Cost**: Uses your existing CLI tools and API subscriptions with zero markup
- **Single Interface**: One prompt, multiple specialized responses, automatically synthesized

## Technical Architecture

```text
    +----------------------------------+
    | Your IDE (VS Code, Cursor, etc.) |
    | (Primary AI Assistant)           |
    +----------------+-----------------+
                     |
    (1. User prompt with subagent delegation)
                     |
    +----------------v-----------------+
    |      Roundtable MCP Server       |
    |         (localhost)              |
    +----------------+-----------------+
                     |
    (2. Dispatches tasks to sub-agent CLIs in parallel)
                     |
+--------------------v--------------------+
|                                         |
|  +-----------+   +-----------+   +-----------+  |
|  |  Gemini   |   |  Claude   |   |   Codex   |  |
|  | (Analysis)|   |  (Logic)  |   | (Implement)| |
|  +-----------+   +-----------+   +-----------+  |
|                                         |
+--------------------^--------------------+
                     |
    (3. Sub-agents execute using local tools,
        e.g., read_file, run_shell_command)
                     |
    +----------------+-----------------+
    |      Roundtable MCP Server       |
    | (Aggregates & Synthesizes)       |
    +----------------+-----------------+
                     |
(4. Returns a single, synthesized response)
                     |
    +----------------v-----------------+
    | Your IDE (Primary AI Assistant)  |
    +----------------------------------+
```

### How It Works

1. **Context Continuity**: The initial prompt and relevant file/project context are packaged by the primary agent. The MCP server passes this "context bundle" to each sub-agent, ensuring all participants have the same ground truth without manual copy-pasting.

2. **Model Specialization**: Use the right model for the job. Leverage Gemini's 1M context for codebase analysis, Claude's reasoning for logic and implementation, and Codex's proficiency for code generation and reviews, all in one workflow.

3. **No Extra Cost**: Roundtable invokes the CLI tools you already have installed and configured. It uses your existing API keys and subscriptions. We add no markup. The cost is exactly what you would pay running the tools manually.

## Why Multi-Agent vs Single AI

Because manual context-switching is slow, error-prone, and prevents deep analysis.

### The Multi-Tab Workflow ❌

- Manually copy-paste code and context between different AI chats
- Each agent starts fresh, unaware of other conversations or files
- You wait for one agent to finish before starting the next
- You are responsible for merging disparate, often conflicting, advice
- High risk of pasting outdated code or incorrect context

### The Roundtable Workflow ✅

- Delegate tasks from a single prompt in your IDE
- The primary agent provides shared, rich context to all sub-agents
- All agents work in parallel, drastically reducing wait time
- The final output automatically synthesizes the best insights from each model
- The entire workflow is a single, deterministic, and repeatable command

## Real-World Examples

Each example includes real code, logs, and explicit delegation to specialized sub-agents. Copy the whole block and paste it into your IDE assistant.

1) Multi-Stack Debugging — Virtual War Room for Production Issues

```markdown
I'm debugging a critical production issue. The user sees a "Failed to load data" message.

Here is the browser console output:
```json
{
  "timestamp": "2024-09-24T10:05:21.123Z",
  "level": "error",
  "message": "API request failed for /api/v1/user/profile",
  "error": {
    "status": 500,
    "statusText": "Internal Server Error"
  }
}
```

Here is the backend server log:
```
ERROR: Exception in ASGI application
File "/app/services/user_service.py", line 42, in get_user_profile
  user_data = await db.fetch_one(query)
ValueError: Database connection is not available
```

Use Gemini SubAgent to analyze the logs from both stacks, correlate the events, and form a hypothesis about the root cause.
Use Codex SubAgent to analyze the Python backend traceback and suggest a specific code fix for the database connection error.
Use Claude SubAgent to review the frontend error handling and recommend more resilient patterns.
Use Cursor SubAgent to search the codebase for other files that might have similar database connection issues.

At the end, aggregate all findings into a single incident report with root cause analysis and prioritized fixes.
```

2) Performance Optimization — API Latency & Database Query Tuning

```markdown
Our checkout API p95 latency increased from 220ms to 780ms. Need optimization strategy.

PostgreSQL slow query log:
```sql
-- Duration: 2455.112 ms
SELECT c.name, COUNT(o.id) AS total_orders, SUM(p.amount) AS revenue
FROM companies c, orders o, payments p
WHERE c.id = o.company_id
  AND o.id = p.order_id
  AND c.region = 'North America'
GROUP BY c.name
ORDER BY revenue DESC;
```

EXPLAIN ANALYZE shows:
```
Seq Scan on orders (cost=0.00..52000.00 rows=100000)
  Filter: (status = 'completed')
  Rows Removed by Filter: 134,201
```

Node.js hotspot from profiling:
```javascript
// 40% CPU time
orders.map(o => ({ ...o, json: JSON.stringify(o) }));

// N+1 query problem
for (const id of orderIds) {
  await fetchInventory(id);
}
```

Use Claude SubAgent to analyze the EXPLAIN plan and identify why the query is slow.
Use Codex SubAgent to rewrite the SQL with proper JOINs and suggest indexes.
Use Gemini SubAgent to fix the N+1 query problem with batch fetching.
Use Cursor SubAgent to find all instances of JSON.stringify in hot code paths.

Aggregate findings into a performance optimization plan with measurable improvements.
```

## Installation

### Using pip (Standard)

```bash
pip install roundtable-ai
```

**Alternative (until PyPI merge):**
```bash
pip install git+https://github.com/velvetmonkey/roundtable.git@v0.5.1
```

### Using UV/UVX (Recommended for faster installs)

```bash
uvx roundtable-ai@latest
```

**Alternative (until PyPI merge):**
```bash
uvx --from git+https://github.com/velvetmonkey/roundtable.git@v0.5.1 roundtable-ai
```

## IDE Integration

Roundtable AI supports 26+ MCP-compatible clients. Here are the top 7:

### 1. Claude Code

**Using pip:**
```bash
claude mcp add roundtable-ai -- roundtable-ai --agents gemini,claude,codex,cursor
```

**Using UVX:**
```bash
claude mcp add roundtable-ai -- uvx roundtable-ai@latest --agents gemini,claude,codex,cursor
```

### 2. Cursor

**One-Click Install:**

[![Install Roundtable AI MCP Server in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](cursor://anysphere.cursor-deeplink/mcp/install?name=roundtable-ai&config=eyJ0eXBlIjoic3RkaW8iLCJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJyb3VuZHRhYmxlLWFpQGxhdGVzdCJdLCJlbnYiOnsiQ0xJX01DUF9TVUJBR0VOVFMiOiJjb2RleCxjbGF1ZGUsY3Vyc29yLGdlbWluaSJ9fQo=)

Or use this direct link:
```
cursor://anysphere.cursor-deeplink/mcp/install?name=roundtable-ai&config=eyJ0eXBlIjoic3RkaW8iLCJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJyb3VuZHRhYmxlLWFpQGxhdGVzdCJdLCJlbnYiOnsiQ0xJX01DUF9TVUJBR0VOVFMiOiJjb2RleCxjbGF1ZGUsY3Vyc29yLGdlbWluaSJ9fQo=
```

**Manual Installation:**

**File:** `.cursor/mcp.json`

**Using pip:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Using UVX:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "roundtable-ai@latest"
      ],
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

### 3. Claude Desktop

**File:** `~/.config/claude_desktop_config.json`

**Using pip:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Using UVX:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "uvx",
      "args": ["roundtable-ai@latest"],
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

### 4. VS Code

**Add to `settings.json`:**

**Using pip:**
```json
{
  "mcp.servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Using UVX:**
```json
{
  "mcp.servers": {
    "roundtable-ai": {
      "command": "uvx",
      "args": ["roundtable-ai@latest"],
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

### 5. OpenAI Codex

**File:** `~/.codex/config.toml`

**Using pip:**
```toml
# IMPORTANT: the top-level key is 'mcp_servers' rather than 'mcpServers'.
[mcp_servers.roundtable-ai]
command = "roundtable-ai"
args = []
env = { "CLI_MCP_SUBAGENTS" = "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo" }
```

**Using UVX:**
```toml
# IMPORTANT: the top-level key is 'mcp_servers' rather than 'mcpServers'.
[mcp_servers.roundtable-ai]
command = "uvx"
args = ["roundtable-ai@latest"]
env = { "CLI_MCP_SUBAGENTS" = "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo" }
```

### 6. Windsurf

**File:** `~/.codeium/windsurf/mcp_config.json`

**Using pip:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Using UVX:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "uvx",
      "args": ["roundtable-ai@latest"],
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

### 7. Gemini CLI

**File:** `~/.gemini/settings.json`

**Using pip:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Using UVX:**
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "uvx",
      "args": ["roundtable-ai@latest"],
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

### Additional IDE Support

Roundtable AI integrates with **26+ different IDEs and AI coding tools**:

#### JetBrains IDEs (IntelliJ, PyCharm, WebStorm, etc.)

**Settings Path**: `Settings > Tools > AI Assistant > Model Context Protocol (MCP)`

```json
{
  "name": "roundtable-ai",
  "command": "roundtable-ai",
  "transport": "stdio",
  "env": {
    "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
  }
}
```

#### GitHub Copilot

**Standard Configuration** (recommended):
```json
{
  "github.copilot.mcp.servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Alternative Configuration** (if ENV variables don't work):
```json
{
  "github.copilot.mcp.servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "args": [
        "--agents=codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      ]
    }
  }
}
```

> **Note**: GitHub Copilot CLI has a known bug with environment variables. If the standard configuration doesn't work, use the alternative format with `args` instead of `env`.

---

### 🖥️ Desktop IDEs

<details>
<summary><b>JetBrains AI Assistant</b> - IntelliJ, PyCharm, WebStorm, etc.</summary>

1. **Settings Path**: `Settings > Tools > AI Assistant > Model Context Protocol (MCP)`
2. **Add New Server**: Click "+" to add new MCP server
3. **Configuration**:
   ```json
   {
     "name": "roundtable-ai",
     "command": "roundtable-ai",
     "transport": "stdio",
     "env": {
       "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo",
     }
   }
   ```
4. **Apply & Restart**: Apply settings and restart the IDE

</details>

<details>
<summary><b>Visual Studio 2022</b> - Microsoft's Flagship IDE</summary>

Create `mcp_config.json` in your project root:
```json
{
  "servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "transport": "stdio",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Alternative**: Use Extensions > Manage Extensions > Search for "Roundtable AI"

</details>

<details>
<summary><b>Zed</b> - High-Performance Code Editor</summary>

Add to `settings.json` (Cmd/Ctrl + ,):
```json
{
  "context_servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

**Extension Alternative**: Search for "Roundtable AI" in Zed Extensions

</details>

---

### 💻 CLI Tools

<details>
<summary><b>Gemini CLI</b> - Google's Gemini Command-Line Interface</summary>

Edit `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Rovo Dev CLI</b> - Atlassian's Development CLI</summary>

Configure via `rovo config` command:
```bash
# Add MCP server
rovo mcp add roundtable-ai roundtable-ai

# Verify
rovo mcp list
```

**Manual configuration** in `~/.rovo/config.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Amazon Q Developer CLI</b> - Amazon's AI Development Assistant</summary>

Edit configuration in `~/.aws/q-developer/config.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Crush</b> - Terminal-Based AI Assistant</summary>

Create or edit `crush.json` in your project:
```json
{
  "mcp": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "transport": "stdio",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Warp</b> - AI-Powered Terminal</summary>

Configure via Warp settings:
1. **Open Settings**: Cmd/Ctrl + ,
2. **Navigate to**: Features > AI > MCP Servers
3. **Add Server**:
   ```json
   {
     "name": "roundtable-ai",
     "command": "roundtable-ai",
     "env": {
       "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
     }
   }
   ```

</details>

---

### 🤖 AI Assistants

<details>
<summary><b>Claude Desktop</b> - Anthropic's Desktop Application</summary>

Edit `~/.config/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Cline</b> - AI Assistant Extension</summary>

**One-Click Install**:
1. Open Cline MCP Server Marketplace
2. Search for "Roundtable AI"
3. Click "Install"

**Manual Configuration** in `cline_mcp_settings.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>BoltAI</b> - AI Assistant Application</summary>

1. **Open BoltAI Settings**
2. **Navigate to**: Plugins > MCP Servers
3. **Add New Server**:
   - Name: `roundtable-ai`
   - Command: `roundtable-ai`
   - Environment Variables:
     ```
     CLI_MCP_SUBAGENTS=codex,claude,cursor,gemini
     ```

</details>

<details>
<summary><b>Perplexity Desktop</b> - AI Search and Research Assistant</summary>

Configure in Perplexity settings:
```json
{
  "mcpConfig": {
    "servers": {
      "roundtable-ai": {
        "command": "roundtable-ai",
        "env": {
          "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
        }
      }
    }
  }
}
```

</details>

<details>
<summary><b>Qodo Gen</b> - AI Code Generation and Analysis Tool</summary>

Add to Qodo Gen configuration:
```json
{
  "mcp_servers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

---

### 🛠️ Specialized Tools

<details>
<summary><b>Opencode</b> - Open-Source AI Code Editor</summary>

Add to `opencode_config.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>OpenAI Codex</b> - OpenAI's Code Generation Model Interface</summary>

Edit `config.toml`:
```toml
[mcp_servers.roundtable-ai]
command = "roundtable-ai"
env = { CLI_MCP_SUBAGENTS = "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo" }
```

</details>

<details>
<summary><b>Kiro</b> - AI Development Assistant</summary>

Configure in `~/.kiro/config.json`:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Trae</b> - AI Development Environment</summary>

Add to Trae workspace configuration:
```json
{
  "mcp": {
    "servers": {
      "roundtable-ai": {
        "command": "roundtable-ai",
        "env": {
          "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
        }
      }
    }
  }
}
```

</details>

<details>
<summary><b>LM Studio</b> - Local Language Model Interface</summary>

**One-Click Install**:
1. Navigate to **Program > Install > Edit mcp.json**
2. Search for "Roundtable AI" in marketplace
3. Click "Install"

**Manual Configuration**:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Zencoder</b> - AI-Powered Coding Assistant</summary>

Configure via Zencoder settings panel:
```json
{
  "mcp_configuration": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Augment Code</b> - AI-Powered Code Completion</summary>

Add to Augment Code workspace settings:
```json
{
  "mcpServers": {
    "roundtable-ai": {
      "command": "roundtable-ai",
      "transport": "stdio",
      "env": {
        "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Roo Code</b> - AI Development Environment</summary>

Configure in Roo Code project settings:
```json
{
  "ai_assistants": {
    "mcp_servers": {
      "roundtable-ai": {
        "command": "roundtable-ai",
        "env": {
          "CLI_MCP_SUBAGENTS": "codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"
        }
      }
    }
  }
}
```

</details>

---

### 🔧 Configuration Tips

#### Environment Variables Reference
```bash
# Specify which AI assistants to enable
CLI_MCP_SUBAGENTS="codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo"


# Enable debug logging
CLI_MCP_DEBUG=true

# Override availability checking
CLI_MCP_IGNORE_AVAILABILITY=true
```

#### Command Alternatives
All IDEs support these equivalent commands:
- `roundtable-ai` (primary command)
- `roundtable-mcp-server` (descriptive alias)
- `python -m roundtable_mcp_server` (Python module)
- `npx @roundtable/mcp-server` (NPM package - coming soon)

#### Verification
After installation, verify the integration works:

```bash
# Check server availability
roundtable-ai --check

# Test connection (varies by IDE)
# Most IDEs will show "Roundtable AI" in their AI assistant panel
```

#### Troubleshooting
1. **Server not found**: Ensure `roundtable-ai` is in your PATH
2. **Permission denied**: Run `chmod +x $(which roundtable-ai)`
3. **Config not loaded**: Check file paths and JSON syntax
4. **No AI tools detected**: Run `roundtable-ai --check` first

## Available MCP Tools

Once integrated, you get access to:

### Availability Checks
- `check_codex_availability` - Verify Codex CLI status
- `check_claude_availability` - Verify Claude Code CLI status
- `check_cursor_availability` - Verify Cursor CLI status
- `check_gemini_availability` - Verify Gemini CLI status

### Unified Task Execution
- `execute_codex_task` - Run coding tasks through Codex
- `execute_claude_task` - Run coding tasks through Claude Code
- `execute_cursor_task` - Run coding tasks through Cursor
- `execute_gemini_task` - Run coding tasks through Gemini

## Advanced Configuration

### Environment Variables
```bash
# Specify which assistants to enable
export CLI_MCP_SUBAGENTS="codex,gemini"


# Enable all tools regardless of availability
export CLI_MCP_IGNORE_AVAILABILITY=true

# Enable debug logging
export CLI_MCP_DEBUG=true

# Enable verbose output
export CLI_MCP_VERBOSE=true

# Enable metrics collection (OPTIONAL)
export CLI_MCP_METRICS=true
```

### Command Line Options

```bash
roundtable-ai --help

Options:
  --agents TEXT     Comma-separated list of agents (gemini,claude,codex,cursor)
  --check          Check availability of all AI tools
  --debug          Enable debug logging
  --version        Show version information
  --help           Show this message and exit
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone repository
git clone https://github.com/yourusername/roundtable.git
cd roundtable

# Install development dependencies
pip install -e ".[dev]"

# Or use the setup script
./scripts/setup-dev.sh
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov --cov-report=html

# Run specific test types
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only

# Run specific test file
pytest tests/unit/test_server_config.py
```

### Code Quality

```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy roundtable_mcp_server
```

## Related repositories

Part of the **Flywheel suite** — local-first knowledge infrastructure over a plain-markdown Obsidian vault:

- [vault-core](https://github.com/velvetmonkey/vault-core) — Shared infrastructure for the Flywheel ecosystem.
- [flywheel-memory](https://github.com/velvetmonkey/flywheel-memory) — Persistent knowledge-graph memory MCP server: semantic search, read, and write over your vault.
- [flywheel-crank](https://github.com/velvetmonkey/flywheel-crank) — Desktop window into your vault's Flywheel MCP server.
- [flywheel-gravity](https://github.com/velvetmonkey/flywheel-gravity) — A compressed, reality-filtered context field over a vault.
- [flywheel-ideas](https://github.com/velvetmonkey/flywheel-ideas) — Local-first decision ledger: falsifiable bets, accepted outcomes, reusable lessons.
- [mega-monkey](https://github.com/velvetmonkey/mega-monkey) — Telegram-native AI research cockpit over an Obsidian vault.
- **roundtable** (this repo) — Local MCP server for delegating tasks to multiple AI models.

Research and experiments:

- [flywheel-concept](https://github.com/velvetmonkey/flywheel-concept) — A falsifiable study of cross-model concept geometry.
- [flywheel-geometry](https://github.com/velvetmonkey/flywheel-geometry) — A pre-registered study of cross-domain knowledge retrieval.
- [flywheel-universe](https://github.com/velvetmonkey/flywheel-universe) — Lean 4 / Mathlib-verified core of the descent argument.
- [flywheel-velvetgram](https://github.com/velvetmonkey/flywheel-velvetgram) — Local widescreen Telegram reader for long-form reading.

Verified-cognition demo: [mcp-seal](https://github.com/velvetmonkey/mcp-seal) (verified MCP approval gate) and [canary](https://github.com/velvetmonkey/canary) (the seal demo host).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Built for developers who value their time.** Stop context-switching between AI tools and start solving problems faster with coordinated multi-agent workflows.

For more examples, advanced usage patterns, and troubleshooting guides, visit our [GitHub repository](https://github.com/askbudi/roundtable).