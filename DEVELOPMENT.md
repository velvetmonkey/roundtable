# Development Guide

Complete guide for developing and extending Roundtable AI.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Development Setup](#development-setup)
- [Adding a New Agent](#adding-a-new-agent)
- [Testing](#testing)
- [Debugging](#debugging)
- [Release Process](#release-process)

## Architecture Overview

Roundtable AI uses a two-layer architecture:

```
┌─────────────────────────────────────┐
│   MCP Clients (IDEs, CLIs)          │
│   (Cursor, VS Code, Claude Desktop) │
└──────────────┬──────────────────────┘
               │ MCP Protocol
┌──────────────▼──────────────────────┐
│   roundtable_mcp_server/            │
│   - FastMCP Server                  │
│   - Tool Registration               │
│   - Configuration Management        │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   claudable_helper/                 │
│   - CLI Adapters                    │
│   - Message Streaming               │
│   - Model Mapping                   │
└─────────────────────────────────────┘
```

### Key Components

**1. MCP Server (`roundtable_mcp_server/`)**
- `server.py` - FastMCP server with tool definitions
- `availability_checker.py` - CLI availability detection
- `cli_subagent.py` - Legacy subagent wrappers

**2. CLI Framework (`claudable_helper/`)**
- `cli/adapters/` - Agent-specific implementations
- `cli/base.py` - Base classes and model mapping
- `models/` - Data models (Message, Session, etc.)
- `services/` - Shared services (GitHub, Vercel, etc.)

### Message Flow

```
User Request
    ↓
MCP Tool Invocation (e.g., codex_subagent)
    ↓
CLI Adapter Initialization (CodexCLI)
    ↓
Availability Check
    ↓
Streaming Execution (execute_with_streaming)
    ↓
Message Processing & Progress Reporting
    ↓
Response Aggregation
    ↓
Return to User
```

## Project Structure

```
roundtable/
├── roundtable_mcp_server/      # MCP server implementation
│   ├── server.py               # Main server with tools
│   ├── availability_checker.py # CLI detection
│   └── cli_subagent.py         # Legacy wrappers
│
├── claudable_helper/           # CLI framework
│   ├── cli/
│   │   ├── adapters/           # Agent implementations
│   │   │   ├── codex_cli.py
│   │   │   ├── claude_code.py
│   │   │   ├── cursor_agent.py
│   │   │   ├── gemini_cli.py
│   │   │   └── qwen_cli.py
│   │   ├── base.py             # Base classes
│   │   └── manager.py          # CLI management
│   ├── models/                 # Data models
│   └── services/               # Shared services
│
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── conftest.py             # Shared fixtures
│
├── .github/                    # CI/CD
│   └── workflows/              # GitHub Actions
│
└── scripts/                    # Development scripts
```

## Development Setup

### Prerequisites

- Python 3.10+
- pip or uv
- Git

### Installation

```bash
# Clone repository
git clone https://github.com/velvetmonkey/roundtable.git
cd roundtable

# Install in development mode
pip install -e ".[dev]"

# Or use setup script
./scripts/setup-dev.sh
```

### Environment Variables

```bash
# Enable specific agents
export CLI_MCP_SUBAGENTS="codex,gemini,qwen"

# Set working directory
export CLI_MCP_WORKING_DIR="/path/to/project"

# Enable debug logging
export CLI_MCP_DEBUG=true

# Enable verbose output
export CLI_MCP_VERBOSE=true

# Ignore availability cache
export CLI_MCP_IGNORE_AVAILABILITY=true
```

## Adding a New Agent

Complete step-by-step guide to add a new AI agent.

### Step 1: Create CLI Adapter

Create `claudable_helper/cli/adapters/newagent_cli.py`:

```python
from typing import AsyncGenerator, Dict, Any, Optional
from ..base import BaseCLI, CLIType
from ...models.messages import Message, MessageType

class NewAgentCLI(BaseCLI):
    """CLI adapter for NewAgent."""
    
    def __init__(self):
        super().__init__(CLIType.NEWAGENT)
    
    async def check_availability(self) -> Dict[str, Any]:
        """Check if NewAgent CLI is available."""
        # Check if CLI exists
        cli_path = shutil.which("newagent")
        if not cli_path:
            return {
                "available": False,
                "error": "NewAgent CLI not found"
            }
        
        return {
            "available": True,
            "path": cli_path,
            "version": "1.0.0"  # Get actual version
        }
    
    async def execute_with_streaming(
        self,
        instruction: str,
        project_path: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        images: Optional[List[str]] = None,
        is_initial_prompt: bool = False
    ) -> AsyncGenerator[Message, None]:
        """Execute instruction with streaming."""
        # Build command
        cmd = ["newagent", "execute", instruction]
        if project_path:
            cmd.extend(["--path", project_path])
        if model:
            cmd.extend(["--model", model])
        
        # Execute and stream
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Parse and yield messages
        async for line in process.stdout:
            message = self._parse_line(line)
            if message:
                yield message
```

### Step 2: Add Model Mapping

Edit `claudable_helper/cli/base.py`:

```python
MODEL_MAPPING = {
    # ... existing mappings ...
    "newagent": {
        "model-1": "actual-model-id-1",
        "model-2": "actual-model-id-2",
    }
}

class CLIType(str, Enum):
    # ... existing types ...
    NEWAGENT = "newagent"
```

### Step 3: Register in MCP Server

Edit `roundtable_mcp_server/server.py`:

**3.1 Import adapter:**
```python
from claudable_helper.cli.adapters.newagent_cli import NewAgentCLI
```

**3.2 Update valid_subagents:**
```python
valid_subagents = {"codex", "claude", "cursor", "gemini", "qwen", "newagent"}
```

**3.3 Add availability check tool:**
```python
@server.tool()
async def check_newagent_availability(ctx: Context = None) -> str:
    """Check if NewAgent CLI is available."""
    if "newagent" not in enabled_subagents:
        return "❌ NewAgent subagent is not enabled"
    
    logger.info("Checking NewAgent availability")
    
    try:
        check_newagent = _import_module_item("cli_subagent", "check_newagent_availability")
        result = await check_newagent()
        return result
    except Exception as e:
        return f"❌ Error: {str(e)}"
```

**3.4 Add execution tool:**
```python
@server.tool()
async def newagent_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """Execute task using NewAgent."""
    if "newagent" not in enabled_subagents:
        return "❌ NewAgent not enabled"
    
    # Path validation
    if not project_path:
        project_path = str(working_dir.absolute())
    
    # Initialize CLI
    cli = NewAgentCLI()
    
    # Check availability
    availability = await cli.check_availability()
    if not availability.get("available"):
        return f"❌ {availability.get('error')}"
    
    # Execute with streaming
    responses = []
    async for message in cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        is_initial_prompt=is_initial_prompt
    ):
        # Process message
        await ctx.report_progress(message=str(message.content))
        if message.role == "assistant":
            responses.append(message.content)
    
    return responses[-1] if responses else "✅ Completed"
```

### Step 4: Add Tests

Create `tests/unit/test_newagent.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.unit
@pytest.mark.asyncio
class TestNewAgentCLI:
    async def test_check_availability_success(self):
        from claudable_helper.cli.adapters.newagent_cli import NewAgentCLI
        
        cli = NewAgentCLI()
        result = await cli.check_availability()
        
        assert "available" in result
    
    async def test_execute_with_streaming(self, temp_project_dir):
        from claudable_helper.cli.adapters.newagent_cli import NewAgentCLI
        
        cli = NewAgentCLI()
        messages = []
        
        async for msg in cli.execute_with_streaming(
            instruction="test",
            project_path=str(temp_project_dir)
        ):
            messages.append(msg)
        
        assert len(messages) > 0
```

### Step 5: Update Documentation

**README.md:**
- Add NewAgent to agent list
- Update examples
- Add to environment variables

**CHANGELOG.md:**
```markdown
## [Unreleased]
### Added
- NewAgent support with model-1 and model-2
```

### Step 6: Test Integration

```bash
# Run tests
pytest tests/unit/test_newagent.py

# Test manually
export CLI_MCP_SUBAGENTS="newagent"
python -m roundtable_mcp_server --check
```

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov --cov-report=html

# Specific markers
pytest -m unit
pytest -m integration
pytest -m slow

# Specific file
pytest tests/unit/test_server_config.py

# Verbose
pytest -v
```

### Writing Tests

```python
import pytest

@pytest.mark.unit
def test_something(mock_config, temp_project_dir):
    """Test description."""
    # Arrange
    config = mock_config
    
    # Act
    result = function_under_test(config)
    
    # Assert
    assert result is not None
```

## Debugging

### Enable Debug Logging

```bash
export CLI_MCP_DEBUG=true
export CLI_MCP_VERBOSE=true
```

### Check Logs

```bash
# Server logs
tail -f .juno_task/logs/roundtable_mcp_server.log

# Or current directory
tail -f roundtable_mcp_server.log
```

### Debug in IDE

**VS Code launch.json:**
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Debug MCP Server",
            "type": "python",
            "request": "launch",
            "module": "roundtable_mcp_server.server",
            "args": ["--agents", "codex,qwen"],
            "console": "integratedTerminal"
        }
    ]
}
```

## Release Process

### Version Bump

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Commit changes

### Create Release

```bash
# Tag version
git tag -a v0.6.0 -m "Release v0.6.0"

# Push tag
git push origin v0.6.0
```

### Automated Release

GitHub Actions will automatically:
1. Run tests
2. Build package
3. Create GitHub Release
4. Publish to PyPI (if configured)

### Manual Release

```bash
# Build
python -m build

# Check
twine check dist/*

# Upload to PyPI
twine upload dist/*
```

## Troubleshooting

### Common Issues

**Import errors:**
```bash
pip install -e ".[dev]"
```

**Tests failing:**
```bash
# Clear cache
pytest --cache-clear

# Reinstall
pip install -e ".[dev]" --force-reinstall
```

**CLI not found:**
```bash
# Check availability
python -m roundtable_mcp_server.availability_checker --check
```

## Resources

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Protocol Spec](https://modelcontextprotocol.io)
- [pytest Documentation](https://docs.pytest.org)
