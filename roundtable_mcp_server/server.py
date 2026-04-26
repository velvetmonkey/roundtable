#!/usr/bin/env python3
"""Roundtable AI MCP Server.

This MCP server exposes CLI subagents (Codex, Claude, Cursor, Gemini, Qwen) via the MCP protocol.
It supports stdio transport for integration with any MCP-compatible client.

Developed by Roundtable AI for seamless AI assistant integration.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import anyio

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

# Handle imports for both package and direct execution
def _import_module_item(module_name: str, item_name: str):
    """Import an item from a module, handling both package and direct execution."""
    try:
        # Try relative import first (package execution)
        import importlib
        package = __package__ or "roundtable_mcp_server"
        module = importlib.import_module(f".{module_name}", package=package)
        return getattr(module, item_name)
    except (ImportError, ValueError, TypeError):
        # Fall back to absolute import (direct execution)
        current_dir = Path(__file__).parent
        if str(current_dir) not in sys.path:
            sys.path.insert(0, str(current_dir))
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, item_name)

# Import required classes and functions


# Configure logging with debug traces
# Default to .juno_task/logs/ directory for consistency with juno_task CLI
log_dir = Path.cwd() / ".juno_task" / "logs"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "roundtable_mcp_server.log"
except (OSError, PermissionError):
    # Fallback to current directory if .juno_task/logs/ creation fails
    log_file = Path.cwd() / "roundtable_mcp_server.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='a'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

CLIAvailabilityChecker = _import_module_item("availability_checker", "CLIAvailabilityChecker")

# Import error handling and monitoring modules
try:
    from roundtable_mcp_server.exceptions import (
        RoundtableError,
        AgentNotAvailableError,
        AgentExecutionError,
        ConfigurationError
    )
    from roundtable_mcp_server.retry import retry_async
    from roundtable_mcp_server.error_handler import handle_agent_error
    from roundtable_mcp_server.metrics import MetricsCollector, track_execution
    ERROR_HANDLING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Error handling modules not available: {e}")
    ERROR_HANDLING_AVAILABLE = False
    # Define fallback exception classes
    class RoundtableError(Exception):
        pass
    class AgentNotAvailableError(RoundtableError):
        pass
    class AgentExecutionError(RoundtableError):
        pass
    class ConfigurationError(RoundtableError):
        pass

# Import CLI adapters directly for MCP streaming with progress
try:
    from claudable_helper.cli.adapters.codex_cli import CodexCLI
    from claudable_helper.cli.adapters.claude_code import ClaudeCodeCLI
    from claudable_helper.cli.adapters.cursor_agent import CursorAgentCLI
    from claudable_helper.cli.adapters.gemini_cli import GeminiCLI
    from claudable_helper.cli.adapters.qwen_cli import QwenCLI
    from claudable_helper.cli.adapters.kiro_cli import KiroCLI
    from claudable_helper.cli.adapters.copilot_cli import CopilotCLI
    from claudable_helper.cli.adapters.grok_cli import GrokCLI
    from claudable_helper.cli.adapters.kilocode_cli import KilocodeCLI
    from claudable_helper.cli.adapters.crush_cli import CrushCLI
    from claudable_helper.cli.adapters.opencode_cli import OpenCodeCLI
    from claudable_helper.cli.adapters.antigravity_cli import AntigravityCLI
    from claudable_helper.cli.adapters.factory_cli import FactoryCLI
    from claudable_helper.cli.adapters.rovo_cli import RovoCLI
    CLI_ADAPTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"CLI adapters not available for direct import: {e}")
    CLI_ADAPTERS_AVAILABLE = False



class SubagentConfig(BaseModel):
    """Configuration for a subagent."""
    name: str
    enabled: bool = True
    working_dir: Optional[str] = None
    model: Optional[str] = None


class ServerConfig(BaseModel):
    """Configuration for the MCP server."""
    subagents: List[str] = Field(
        default_factory=lambda: ["codex", "claude", "cursor", "gemini", "qwen", "kiro", "copilot", "grok", "kilocode", "crush", "opencode", "factory", "rovo"],
        description="List of subagents to enable"
    )
    working_dir: Optional[str] = Field(
        default=None,
        description="Default working directory for all subagents"
    )
    debug: bool = Field(
        default=True,
        description="Enable debug logging"
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose output for subagents, showing tool calls and everystep of the execution. "
    )

# Parse configuration from environment and availability cache
def parse_config_from_env() -> ServerConfig:
    """Parse server configuration from environment variables and availability cache.

    Environment variables:
    - CLI_MCP_SUBAGENTS: Comma-separated list of subagents to enable (overrides availability cache)
    - CLI_MCP_WORKING_DIR: Default working directory for subagents
    - CLI_MCP_DEBUG: Enable debug logging (true/false)
    - CLI_MCP_IGNORE_AVAILABILITY: Ignore availability cache and enable all subagents (true/false)

    Returns:
        ServerConfig instance
    """
    config = ServerConfig()

    # Check if we should ignore availability cache
    ignore_availability = os.getenv("CLI_MCP_IGNORE_AVAILABILITY", "true").lower() in ("true", "1", "yes", "on")

    # Parse enabled subagents
    subagents_env = os.getenv("CLI_MCP_SUBAGENTS")
    if subagents_env:
        # Environment variable override - use specified subagents
        subagents = [s.strip().lower() for s in subagents_env.split(",") if s.strip()]
        valid_subagents = {"codex", "claude", "cursor", "gemini", "qwen", "kiro", "copilot", "grok", "kilocode", "crush", "opencode", "factory", "rovo"}
        config.subagents = [s for s in subagents if s in valid_subagents]
        config.verbose = os.getenv("CLI_MCP_VERBOSE", "false").lower() in ("true", "1", "yes", "on")
        logger.info(f"Verbose: {config.verbose}")
        invalid = set(subagents) - valid_subagents
        if invalid:
            logger.warning(f"Invalid subagent names ignored: {', '.join(invalid)}")

        logger.info(f"Using subagents from environment variable: {config.subagents}")
    elif ignore_availability:
        # Ignore availability cache and enable all subagents
        config.subagents = ["codex", "claude", "cursor", "gemini", "qwen", "kiro", "copilot", "grok", "kilocode", "crush", "opencode", "factory", "rovo"]
        logger.info("Ignoring availability cache - enabling all subagents")
    else:
        # Use availability cache to determine enabled subagents
        checker = CLIAvailabilityChecker()
        available_clis = checker.get_available_clis()

        if available_clis:
            config.subagents = available_clis
            logger.info(f"Using available subagents from cache: {config.subagents}")
        else:
            # Fallback to default if no availability data
            logger.warning("No availability data found, falling back to default subagents")
            logger.warning("Run 'python -m roundtable_mcp_server.availability_checker --check' to check CLI availability")
            config.subagents = ["codex", "claude", "cursor", "gemini", "qwen", "kiro", "copilot", "grok", "kilocode", "crush", "opencode", "factory", "rovo"]

    # Parse working directory
    working_dir = os.getenv("CLI_MCP_WORKING_DIR")
    if working_dir:
        config.working_dir = working_dir

    # Parse debug flag
    debug_env = os.getenv("CLI_MCP_DEBUG", "true").lower()
    config.debug = debug_env in ("true", "1", "yes", "on")

    return config


# Global configuration variables (will be set in main())
config = None
enabled_subagents = set()
working_dir = Path.cwd()

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Initialize FastMCP server
server = FastMCP("roundtable-ai")

def initialize_config():
    """Initialize configuration - called from main()."""
    global config, enabled_subagents, working_dir

    config = parse_config_from_env()
    enabled_subagents = set(config.subagents)
    verbose = config.verbose
    working_dir = Path(config.working_dir) if config.working_dir else Path.cwd()

    logger.info(f"Initializing Roundtable AI MCP Server")
    logger.info(f"Enabled subagents: {', '.join(enabled_subagents)}")
    logger.info(f"Working directory: {working_dir}")
    logger.info(f"Verbose: {verbose}")
    
    # Initialize metrics collector if available
    if ERROR_HANDLING_AVAILABLE:
        metrics_enabled = os.getenv("CLI_MCP_METRICS", "false").lower() in ("true", "1", "yes", "on")
        if metrics_enabled:
            logger.info("Metrics collection enabled")
        else:
            logger.debug("Metrics collection disabled (set CLI_MCP_METRICS=true to enable)")


# Helper functions with error handling
async def _execute_codex_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: str,
    is_initial_prompt: bool
) -> str:
    """Execute Codex with error handling and retry logic."""
    codex_cli = CodexCLI()
    
    availability = await codex_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Codex CLI not available: {availability.get('error', 'Unknown error')}")
    
    messages = []
    agent_responses = []
    
    async for message in codex_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        messages.append(message)
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Codex task completed successfully"
    
    return f"**Codex Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Codex Response:**\n{chr(10).join(agent_responses)}"


async def _execute_claude_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool
) -> str:
    """Execute Claude with error handling."""
    claude_cli = ClaudeCodeCLI()
    
    availability = await claude_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Claude CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    
    async for message in claude_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Claude task completed successfully"
    
    return f"**Claude Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Claude Response:**\n{chr(10).join(agent_responses)}"


async def _execute_cursor_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool
) -> str:
    """Execute Cursor with error handling."""
    cursor_cli = CursorAgentCLI()
    
    availability = await cursor_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Cursor CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    
    async for message in cursor_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Cursor task completed successfully"
    
    return f"**Cursor Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Cursor Response:**\n{chr(10).join(agent_responses)}"


async def _execute_gemini_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool
) -> str:
    """Execute Gemini with error handling."""
    gemini_cli = GeminiCLI()
    
    availability = await gemini_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Gemini CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    
    async for message in gemini_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Gemini task completed successfully"
    
    return f"**Gemini Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Gemini Response:**\n{chr(10).join(agent_responses)}"


async def _execute_qwen_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool,
    ctx: Optional[Context] = None,
) -> str:
    """Execute Qwen with error handling."""
    qwen_cli = QwenCLI()
    
    availability = await qwen_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Qwen CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    message_count = 0
    
    async for message in qwen_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        message_count += 1

        if ctx is not None:
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))
            content = getattr(message, "content", "")
            await ctx.report_progress(
                progress=message_count,
                total=None,
                message=f"Qwen #{message_count}: {msg_type_str} => {content}",
            )

        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Qwen task completed successfully"
    
    return f"**Qwen Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Qwen Response:**\n{chr(10).join(agent_responses)}"


async def _execute_kiro_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool
) -> str:
    """Execute Kiro with error handling."""
    kiro_cli = KiroCLI()
    
    availability = await kiro_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Kiro CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    
    async for message in kiro_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ Kiro task completed successfully"
    
    return f"**Kiro Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Kiro Response:**\n{chr(10).join(agent_responses)}"


async def _execute_copilot_with_error_handling(
    instruction: str,
    project_path: str,
    session_id: Optional[str],
    model: Optional[str],
    is_initial_prompt: bool
) -> str:
    """Execute GitHub Copilot with error handling."""
    copilot_cli = CopilotCLI()
    
    availability = await copilot_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"GitHub Copilot CLI not available: {availability.get('error', 'Unknown error')}")
    
    agent_responses = []
    async for message in copilot_cli.execute_with_streaming(
        instruction=instruction,
        project_path=project_path,
        session_id=session_id,
        model=model,
        images=None,
        is_initial_prompt=is_initial_prompt
    ):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    
    if not agent_responses:
        return "✅ GitHub Copilot task completed successfully"
    
    return f"**GitHub Copilot Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**GitHub Copilot Response:**\n{chr(10).join(agent_responses)}"




async def _execute_grok_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    grok_cli = GrokCLI()
    availability = await grok_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Grok CLI not available")
    agent_responses = []
    async for message in grok_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Grok task completed"
    return f"**Grok:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Grok:**\n{chr(10).join(agent_responses)}"


async def _execute_kilocode_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    kilocode_cli = KilocodeCLI()
    availability = await kilocode_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Kilocode CLI not available")
    agent_responses = []
    async for message in kilocode_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Kilocode task completed"
    return f"**Kilocode:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Kilocode:**\n{chr(10).join(agent_responses)}"


async def _execute_crush_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    crush_cli = CrushCLI()
    availability = await crush_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Crush CLI not available")
    agent_responses = []
    async for message in crush_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Crush task completed"
    return f"**Crush:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Crush:**\n{chr(10).join(agent_responses)}"


async def _execute_opencode_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    opencode_cli = OpenCodeCLI()
    availability = await opencode_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"OpenCode CLI not available")
    agent_responses = []
    async for message in opencode_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ OpenCode task completed"
    return f"**OpenCode:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**OpenCode:**\n{chr(10).join(agent_responses)}"


async def _execute_antigravity_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    antigravity_cli = AntigravityCLI()
    availability = await antigravity_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Antigravity CLI not available")
    agent_responses = []
    async for message in antigravity_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Antigravity task completed"
    return f"**Antigravity:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Antigravity:**\n{chr(10).join(agent_responses)}"


async def _execute_factory_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    factory_cli = FactoryCLI()
    availability = await factory_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Factory/Droid CLI not available")
    agent_responses = []
    async for message in factory_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Factory/Droid task completed"
    return f"**Factory/Droid:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Factory/Droid:**\n{chr(10).join(agent_responses)}"


async def _execute_rovo_with_error_handling(instruction: str, project_path: str, session_id: Optional[str], model: Optional[str], is_initial_prompt: bool) -> str:
    rovo_cli = RovoCLI()
    availability = await rovo_cli.check_availability()
    if not availability.get("available", False):
        raise AgentNotAvailableError(f"Rovo Dev CLI not available")
    agent_responses = []
    async for message in rovo_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
        if hasattr(message, 'role') and message.role == "assistant":
            if message.content and message.content.strip():
                agent_responses.append(message.content.strip())
    if not agent_responses:
        return "✅ Rovo Dev task completed"
    return f"**Rovo Dev:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Rovo Dev:**\n{chr(10).join(agent_responses)}"


# Tool definitions
@server.tool()
async def check_codex_availability(ctx: Context = None) -> str:
    """
    Check if Codex CLI is available and configured properly.

    Returns:
        Status message about Codex availability
    """
    if "codex" not in enabled_subagents:
        return "❌ Codex subagent is not enabled in this server instance"

    logger.info("Checking Codex availability")

    try:
        check_codex = _import_module_item("cli_subagent", "check_codex_availability")
        result = await check_codex()
        logger.debug(f"Codex availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Codex availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def check_claude_availability(ctx: Context = None) -> str:
    """
    Check if Claude Code CLI is available and configured properly.

    Returns:
        Status message about Claude Code availability
    """
    if "claude" not in enabled_subagents:
        return "❌ Claude subagent is not enabled in this server instance"

    logger.info("Checking Claude Code availability")

    try:
        check_claude = _import_module_item("cli_subagent", "check_claude_availability")
        result = await check_claude()
        logger.debug(f"Claude availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Claude Code availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def check_cursor_availability(ctx: Context = None) -> str:
    """
    Check if Cursor Agent CLI is available and configured properly.

    Returns:
        Status message about Cursor Agent availability
    """
    if "cursor" not in enabled_subagents:
        return "❌ Cursor subagent is not enabled in this server instance"

    logger.info("Checking Cursor Agent availability")

    try:
        check_cursor = _import_module_item("cli_subagent", "check_cursor_availability")
        result = await check_cursor()
        logger.debug(f"Cursor availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Cursor Agent availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def check_gemini_availability(ctx: Context = None) -> str:
    """
    Check if Gemini CLI is available and configured properly.

    Returns:
        Status message about Gemini availability
    """
    if "gemini" not in enabled_subagents:
        return "❌ Gemini subagent is not enabled in this server instance"

    logger.info("Checking Gemini availability")

    try:
        check_gemini = _import_module_item("cli_subagent", "check_gemini_availability")
        result = await check_gemini()
        logger.debug(f"Gemini availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Gemini availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def check_qwen_availability(ctx: Context = None) -> str:
    """
    Check if Qwen CLI is available and configured properly.

    Returns:
        Status message about Qwen availability
    """
    if "qwen" not in enabled_subagents:
        return "❌ Qwen subagent is not enabled in this server instance"

    logger.info("Checking Qwen availability")

    try:
        check_qwen = _import_module_item("cli_subagent", "check_qwen_availability")
        result = await check_qwen()
        logger.debug(f"Qwen availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Qwen availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def check_kiro_availability(ctx: Context = None) -> str:
    """
    Check if Kiro CLI is available and configured properly.

    Returns:
        Status message about Kiro availability
    """
    if "kiro" not in enabled_subagents:
        return "❌ Kiro subagent is not enabled in this server instance"

    logger.info("Checking Kiro availability")

    try:
        check_kiro = _import_module_item("cli_subagent", "check_kiro_availability")
        result = await check_kiro()
        logger.debug(f"Kiro availability result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error checking Kiro availability: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"❌ {error_msg}"


@server.tool()
async def codex_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = 'gpt-5',
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Codex CLI agent.

    Codex has access to file operations, shell commands, web search,
    and can make code changes directly. It's ideal for implementing features,
    fixing bugs, refactoring code, and other development tasks.

    IMPORTANT: Always provide an absolute path for project_path to ensure proper execution.
    If you don't provide project_path, the current working directory will be used.

    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory (e.g., '/home/user/myproject'). If not provided, uses current working directory.
        session_id: Optional session ID for conversation continuity
        model: Optional model to use ( 'gpt-5' is the only supported model)
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Codex agent accomplished
    """

    if "codex" not in enabled_subagents:
        return "❌ Codex subagent is not enabled in this server instance"

    if not CLI_ADAPTERS_AVAILABLE:
        # Fallback to old method if CLI adapters not available
        try:
            codex_exec = _import_module_item("cli_subagent", "codex_subagent")
            result = await codex_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt
            )
            return result
        except Exception as e:
            error_msg = f"Error executing Codex subagent: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"

    # Robust path validation and fallback
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        # Ensure we have an absolute path
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    # Validate the directory exists
    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Codex: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] codex_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")
    
    # Use error handler if available
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_codex_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ Codex CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Codex execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "codex", instruction)

    try:
        # Initialize CodexCLI directly
        codex_cli = CodexCLI()

        # Check if Codex is available
        availability = await codex_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Codex CLI not available")
            logger.error(f"Codex unavailable: {error_msg}")
            return f"❌ Codex CLI not available: {error_msg}"

        # Collect all messages from streaming execution with progress reporting
        messages = []
        agent_responses = []
        tool_uses = []
        message_count = 0
        logger.info(f"Codex subagent execution started :verbose={config.verbose}")
        logger.debug(f"[MCP-TOOL] Codex CLI streaming started - will process messages and report progress")

        async for message in codex_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            message_count += 1
            messages.append(message)

            # Get message type as string
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))

            # Get content with fallback
            content = getattr(message, "content", "")
            content_preview = str(content)[:100] if content else ""

            # Progress reporting with debug logging
            progress_message = f"Codex #{message_count}: {msg_type_str} => {content}"
            logger.debug(f"[PROGRESS] {progress_message}")
            await ctx.report_progress(
                progress=message_count,
                total=None,
                message=progress_message
            )

            # Categorize messages for summary (same logic as cli_subagent.py)
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
            elif msg_type_str == "tool_use":
                tool_uses.append(message.content)
            elif msg_type_str == "tool_result":
                tool_uses.append(f"Tool result: {message.content}")
            elif msg_type_str == "error":
                logger.error(f"Codex error: {message.content}")
                return f"❌ Codex execution failed: {message.content}"
            else:
                # Capture any other message types that might contain useful content
                if message.content and str(message.content).strip():
                    agent_responses.append(str(message.content).strip())

        # Create comprehensive summary (same logic as cli_subagent.py)
        summary_parts = []

        if agent_responses:
            if len(agent_responses) == 1:
                summary_parts.append(f"**Codex Response:**\n{agent_responses[0]}")
            else:
                combined_response = "\n\n".join(agent_responses)
                summary_parts.append(f"**Codex Response:**\n{combined_response}")

        if tool_uses:
            summary_parts.append(f"🔧 **Tools Used ({len(tool_uses)}):**")
            for tool_use in tool_uses:
                summary_parts.append(f"• {tool_use}")

        if not summary_parts:
            summary_parts.append("✅ Codex task completed successfully (no detailed output captured)")

        summary = "\n\n".join(summary_parts)

        logger.info("Codex subagent execution completed")
        logger.debug(f"[MCP-TOOL] Codex execution completed - total messages: {message_count}, agent_responses: {len(agent_responses)}, tool_uses: {len(tool_uses)}")
        logger.debug(f"Result summary: {summary}")

        final_response = summary if config.verbose else agent_responses[-1]
        logger.info(f"[TOOL-RESPONSE] Codex final response: {final_response}")
        return final_response


    except Exception as e:
        error_msg = f"Error executing Codex subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def claude_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Claude Code CLI agent.

    Claude Code has access to file operations, shell commands, web search,
    and can make code changes directly. It's ideal for implementing features,
    fixing bugs, refactoring code, and other development tasks.

    IMPORTANT: Always provide an absolute path for project_path to ensure proper execution.
    If you don't provide project_path, the current working directory will be used.
    use sonnet-4 model by default unless the task is very complex and need more powerful model. opus-4.1 costs 10X more than sonnet-4. And sonnet-4 is smart enough to handle most tasks.


    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory (e.g., '/home/user/myproject'). If not provided, uses current working directory.
        session_id: Optional session ID for conversation continuity
        model: Optional model to use (e.g., 'sonnet-4', 'opus-4.1')
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Claude Code agent accomplished
    """
    if "claude" not in enabled_subagents:
        return "❌ Claude subagent is not enabled in this server instance"

    if not CLI_ADAPTERS_AVAILABLE:
        # Fallback to old method if CLI adapters not available
        try:
            claude_exec = _import_module_item("cli_subagent", "claude_subagent")
            result = await claude_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt
            )
            return result
        except Exception as e:
            error_msg = f"Error executing Claude subagent: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"

    # Robust path validation and fallback
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        # Ensure we have an absolute path
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    # Validate the directory exists
    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Claude: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] claude_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")

    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_claude_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ Claude CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Claude execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "claude", instruction)

    try:
        # Initialize ClaudeCodeCLI directly
        claude_cli = ClaudeCodeCLI()

        # Check if Claude Code is available
        availability = await claude_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Claude Code CLI not available")
            logger.error(f"Claude Code unavailable: {error_msg}")
            return f"❌ Claude Code CLI not available: {error_msg}"

        # Collect all messages from streaming execution with progress reporting
        messages = []
        agent_responses = []
        tool_uses = []
        message_count = 0
        logger.info(f"Claude subagent execution started :verbose={config.verbose}")
        logger.debug(f"[MCP-TOOL] Claude CLI streaming started - will process messages and report progress")

        async for message in claude_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            message_count += 1
            messages.append(message)

            # Get message type as string
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))

            # Get content with fallback
            content = getattr(message, "content", "")
            content_preview = str(content)[:100] if content else ""

            # Progress reporting with debug logging
            progress_message = f"Claude #{message_count}: {msg_type_str} => {content}"
            logger.debug(f"[PROGRESS] {progress_message}")
            await ctx.report_progress(
                progress=message_count,
                total=None,
                message=progress_message
            )

            # Categorize messages for summary (same logic as codex_subagent)
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
            elif msg_type_str == "tool_use":
                tool_uses.append(message.content)
            elif msg_type_str == "tool_result":
                tool_uses.append(f"Tool result: {message.content}")
            elif msg_type_str == "error":
                logger.error(f"Claude Code error: {message.content}")
                return f"❌ Claude Code execution failed: {message.content}"
            elif msg_type_str == "result":
                logger.debug(f"Claude Code result: {message.content}, not adding to agent_responses")
            else:
                # Capture any other message types that might contain useful content
                if message.content and str(message.content).strip():
                    agent_responses.append(str(message.content).strip())

        # Create comprehensive summary (same logic as codex_subagent)
        summary_parts = []

        if agent_responses:
            if len(agent_responses) == 1:
                summary_parts.append(f"**Claude Code Response:**\n{agent_responses[0]}")
            else:
                combined_response = "\n\n".join(agent_responses)
                summary_parts.append(f"**Claude Code Response:**\n{combined_response}")

        if tool_uses:
            summary_parts.append(f"🔧 **Tools Used ({len(tool_uses)}):**")
            for tool_use in tool_uses:
                summary_parts.append(f"• {tool_use}")

        if not summary_parts:
            summary_parts.append("✅ Claude Code task completed successfully (no detailed output captured)")

        summary = "\n\n".join(summary_parts)

        logger.info("Claude subagent execution completed")
        logger.debug(f"[MCP-TOOL] Claude execution completed - total messages: {message_count}, agent_responses: {len(agent_responses)}, tool_uses: {len(tool_uses)}")
        logger.debug(f"Result summary: {summary}")

        final_response = summary if config.verbose else (agent_responses[-1] if agent_responses else "✅ Claude Code task completed successfully")
        logger.info(f"[TOOL-RESPONSE] Claude final response: {final_response}")
        return final_response

    except Exception as e:
        error_msg = f"Error executing Claude subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def cursor_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Cursor Agent CLI.

    Cursor Agent has access to file operations, shell commands, web search,
    and can make code changes directly. It's ideal for implementing features,
    fixing bugs, refactoring code, and other development tasks.

    IMPORTANT: Always provide an absolute path for project_path to ensure proper execution.
    If you don't provide project_path, the current working directory will be used.

    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory (e.g., '/home/user/myproject'). If not provided, uses current working directory.
        session_id: Optional session ID for conversation continuity
        model: Optional model to use (e.g., 'gpt-5', 'sonnet-4', 'sonnet-4-thinking')
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Cursor Agent accomplished
    """
    if "cursor" not in enabled_subagents:
        return "❌ Cursor subagent is not enabled in this server instance"

    # Robust path validation and fallback
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        # Ensure we have an absolute path
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    # Validate the directory exists
    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Cursor: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] cursor_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")

    if ERROR_HANDLING_AVAILABLE and CLI_ADAPTERS_AVAILABLE:
        try:
            return await _execute_cursor_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ Cursor CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Cursor execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "cursor", instruction)

    # Prefer streaming via adapter (to emit MCP progress), with safe fallback
    try:
        # Try to import adapter class via relative import (works in-package)
        try:
            CursorCLIClass = _import_module_item(
                "claudable_helper.cli.adapters.cursor_agent", "CursorAgentCLI"
            )
            cursor_cli = CursorCLIClass()
            use_adapter = True
        except Exception as imp_err:
            logger.debug(f"Cursor adapter import failed, falling back: {imp_err}")
            use_adapter = False

        if not use_adapter:
            # Fallback to legacy tool wrapper (no streaming)
            cursor_exec = _import_module_item("cli_subagent", "cursor_subagent")
            result = await cursor_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt,
            )
            logger.info("Cursor subagent execution completed (fallback mode)")
            logger.debug(
                f"Result summary: {result[:200]}..." if len(result) > 200 else f"Result: {result}"
            )
            return result

        # Adapter path with streaming and progress reporting
        availability = await cursor_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Cursor Agent CLI not available")
            logger.error(f"Cursor Agent unavailable: {error_msg}")
            return f"❌ Cursor Agent CLI not available: {error_msg}"

        messages: List[Any] = []
        agent_responses: List[str] = []
        tool_uses: List[str] = []
        message_count = 0
        logger.info(f"Cursor subagent execution started :verbose={config.verbose}")
        logger.debug(f"[MCP-TOOL] Cursor CLI streaming started - will process messages and report progress")

        async for message in cursor_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt,
        ):
            message_count += 1
            messages.append(message)

            # Normalize type and content
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))
            content = getattr(message, "content", "")
            content_preview = str(content)[:100] if content else ""

            # Progress reporting with debug logging
            progress_message = f"Cursor #{message_count}: {msg_type_str} => {content}"
            logger.debug(f"[PROGRESS] {progress_message}")
            try:
                await ctx.report_progress(
                    progress=message_count,
                    total=None,
                    message=progress_message,
                )
            except Exception as e:
                logger.debug(f"Progress reporting failed (non-critical): {e}")

            # Accumulate for summary
            if hasattr(message, "role") and message.role == "assistant":
                if content and str(content).strip():
                    agent_responses.append(str(content).strip())
            elif msg_type_str == "tool_use":
                tool_uses.append(content)
            elif msg_type_str == "tool_result":
                tool_uses.append(f"Tool result: {content}")
            elif msg_type_str == "error":
                logger.error(f"Cursor Agent error: {content}")
                return f"❌ Cursor Agent execution failed: {content}"
            elif msg_type_str == "result":
                logger.debug(f"Cursor final result received: {content}")
                # Store the result content for the final response
                if content and str(content).strip():
                    agent_responses.append(str(content).strip())
                # Break the loop as cursor execution is complete
                logger.info("Cursor result received, ending stream")
                break
            else:
                if content and str(content).strip():
                    agent_responses.append(str(content).strip())

        # Build summary
        summary_parts: List[str] = []
        if agent_responses:
            if len(agent_responses) == 1:
                summary_parts.append(f"**Cursor Agent Response:**\n{agent_responses[0]}")
            else:
                combined = "\n\n".join(agent_responses)
                summary_parts.append(f"**Cursor Agent Response:**\n{combined}")
        if tool_uses:
            summary_parts.append(f"🔧 **Tools Used ({len(tool_uses)}):**")
            for t in tool_uses:
                summary_parts.append(f"• {t}")
        if not summary_parts:
            summary_parts.append(
                "✅ Cursor Agent task completed successfully (no detailed output captured)"
            )
        summary = "\n\n".join(summary_parts)

        logger.info("Cursor subagent execution completed")
        logger.debug(f"[MCP-TOOL] Cursor execution completed - total messages: {message_count}, agent_responses: {len(agent_responses)}, tool_uses: {len(tool_uses)}")
        logger.debug(f"Result summary: {summary}")

        final_response = summary if config.verbose else (agent_responses[-1] if agent_responses else summary)
        logger.info(f"[TOOL-RESPONSE] Cursor final response: {final_response}")
        return final_response

    except Exception as e:
        error_msg = f"Error executing Cursor subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def gemini_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Gemini CLI agent.

    Gemini has access to file operations, shell commands, web search,
    and can make code changes directly. It's ideal for implementing features,
    fixing bugs, refactoring code, and other development tasks.

    IMPORTANT: Always provide an absolute path for project_path to ensure proper execution.
    If you don't provide project_path, the current working directory will be used.

    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory (e.g., '/home/user/myproject'). If not provided, uses current working directory.
        session_id: Optional session ID for conversation continuity
        model: Optional model to use ( 'gemini-2.5-pro', 'gemini-2.5-flash' are the only supported models)
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Gemini agent accomplished
    """
    if "gemini" not in enabled_subagents:
        return "❌ Gemini subagent is not enabled in this server instance"

    if not CLI_ADAPTERS_AVAILABLE:
        # Fallback to old method if CLI adapters not available
        try:
            gemini_exec = _import_module_item("cli_subagent", "gemini_subagent")
            result = await gemini_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt
            )
            return result
        except Exception as e:
            error_msg = f"Error executing Gemini subagent: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"

    # Robust path validation and fallback
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        # Ensure we have an absolute path
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    # Validate the directory exists
    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Gemini: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] gemini_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")

    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_gemini_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ Gemini CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Gemini execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "gemini", instruction)

    try:
        # Initialize GeminiCLI directly
        gemini_cli = GeminiCLI()

        # Check if Gemini is available
        availability = await gemini_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Gemini CLI not available")
            logger.error(f"Gemini unavailable: {error_msg}")
            return f"❌ Gemini CLI not available: {error_msg}"

        # Collect all messages from streaming execution with progress reporting
        messages = []
        agent_responses = []
        tool_uses = []
        message_count = 0
        logger.info(f"Gemini subagent execution started :verbose={config.verbose}")
        logger.debug(f"[MCP-TOOL] Gemini CLI streaming started - will process messages and report progress")

        async for message in gemini_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            message_count += 1
            messages.append(message)

            # Get message type as string
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))

            # Get content with fallback
            content = getattr(message, "content", "")
            content_preview = str(content)[:100] if content else ""

            # Progress reporting with debug logging
            progress_message = f"Gemini #{message_count}: {msg_type_str} => {content}"
            logger.debug(f"[PROGRESS] {progress_message}")
            await ctx.report_progress(
                progress=message_count,
                total=None,
                message=progress_message
            )

            # Categorize messages for summary (same logic as codex_subagent)
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
            elif msg_type_str == "tool_use":
                tool_uses.append(message.content)
            elif msg_type_str == "tool_result":
                tool_uses.append(f"Tool result: {message.content}")
            elif msg_type_str == "error":
                logger.error(f"Gemini error: {message.content}")
                return f"❌ Gemini execution failed: {message.content}"
            elif msg_type_str == "result":
                logger.debug(f"Gemini result: {message.content}, not adding to agent_responses")
            else:
                # Capture any other message types that might contain useful content
                if message.content and str(message.content).strip():
                    agent_responses.append(str(message.content).strip())

        # Create comprehensive summary (same logic as codex_subagent)
        summary_parts = []

        if agent_responses:
            if len(agent_responses) == 1:
                summary_parts.append(f"**Gemini Response:**\n{agent_responses[0]}")
            else:
                combined_response = "\n\n".join(agent_responses)
                summary_parts.append(f"**Gemini Response:**\n{combined_response}")

        if tool_uses:
            summary_parts.append(f"🔧 **Tools Used ({len(tool_uses)}):**")
            for tool_use in tool_uses:
                summary_parts.append(f"• {tool_use}")

        if not summary_parts:
            summary_parts.append("✅ Gemini task completed successfully (no detailed output captured)")

        summary = "\n\n".join(summary_parts)

        logger.info("Gemini subagent execution completed")
        logger.debug(f"[MCP-TOOL] Gemini execution completed - total messages: {message_count}, agent_responses: {len(agent_responses)}, tool_uses: {len(tool_uses)}")
        logger.debug(f"Result summary: {summary}")

        final_response = summary if config.verbose else (agent_responses[-1] if agent_responses else "✅ Gemini task completed successfully")
        logger.info(f"[TOOL-RESPONSE] Gemini final response: {final_response}")
        return final_response

    except Exception as e:
        error_msg = f"Error executing Gemini subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def qwen_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Qwen CLI agent.

    Qwen has access to file operations, shell commands, web search,
    and can make code changes directly. It's ideal for implementing features,
    fixing bugs, refactoring code, and other development tasks.

    IMPORTANT: Always provide an absolute path for project_path to ensure proper execution.
    If you don't provide project_path, the current working directory will be used.

    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory (e.g., '/home/user/myproject'). If not provided, uses current working directory.
        session_id: Optional session ID for conversation continuity
        model: Optional model to use ('qwen-coder' is the default model)
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Qwen agent accomplished
    """
    if "qwen" not in enabled_subagents:
        return "❌ Qwen subagent is not enabled in this server instance"

    if not CLI_ADAPTERS_AVAILABLE:
        # Fallback to old method if CLI adapters not available
        try:
            qwen_exec = _import_module_item("cli_subagent", "qwen_subagent")
            result = await qwen_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt
            )
            return result
        except Exception as e:
            error_msg = f"Error executing Qwen subagent: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"

    # Robust path validation and fallback
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        # Ensure we have an absolute path
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    # Validate the directory exists
    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Qwen: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] qwen_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")

    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_qwen_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt, ctx
            )
        except AgentNotAvailableError as e:
            return f"❌ Qwen CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Qwen execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "qwen", instruction)

    try:
        # Initialize QwenCLI directly
        qwen_cli = QwenCLI()

        # Check if Qwen is available
        availability = await qwen_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Qwen CLI not available")
            logger.error(f"Qwen unavailable: {error_msg}")
            return f"❌ Qwen CLI not available: {error_msg}"

        # Collect all messages from streaming execution with progress reporting
        messages = []
        agent_responses = []
        tool_uses = []
        message_count = 0
        logger.info(f"Qwen subagent execution started :verbose={config.verbose}")
        logger.debug(f"[MCP-TOOL] Qwen CLI streaming started - will process messages and report progress")

        async for message in qwen_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            message_count += 1
            messages.append(message)

            # Get message type as string
            msg_type = getattr(message, "message_type", None)
            msg_type_str = getattr(msg_type, "value", str(msg_type))

            # Get content with fallback
            content = getattr(message, "content", "")
            content_preview = str(content)[:100] if content else ""

            # Progress reporting with debug logging
            progress_message = f"Qwen #{message_count}: {msg_type_str} => {content}"
            logger.debug(f"[PROGRESS] {progress_message}")
            await ctx.report_progress(
                progress=message_count,
                total=None,
                message=progress_message
            )

            # Categorize messages for summary
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
            elif msg_type_str == "tool_use":
                tool_uses.append(message.content)
            elif msg_type_str == "tool_result":
                tool_uses.append(f"Tool result: {message.content}")
            elif msg_type_str == "error":
                logger.error(f"Qwen error: {message.content}")
                return f"❌ Qwen execution failed: {message.content}"
            elif msg_type_str == "result":
                logger.debug(f"Qwen result: {message.content}, not adding to agent_responses")
            else:
                # Capture any other message types that might contain useful content
                if message.content and str(message.content).strip():
                    agent_responses.append(str(message.content).strip())

        # Create comprehensive summary
        summary_parts = []

        if agent_responses:
            if len(agent_responses) == 1:
                summary_parts.append(f"**Qwen Response:**\n{agent_responses[0]}")
            else:
                combined_response = "\n\n".join(agent_responses)
                summary_parts.append(f"**Qwen Response:**\n{combined_response}")

        if tool_uses:
            summary_parts.append(f"🔧 **Tools Used ({len(tool_uses)}):**")
            for tool_use in tool_uses:
                summary_parts.append(f"• {tool_use}")

        if not summary_parts:
            summary_parts.append("✅ Qwen task completed successfully (no detailed output captured)")

        summary = "\n\n".join(summary_parts)

        logger.info("Qwen subagent execution completed")
        logger.debug(f"[MCP-TOOL] Qwen execution completed - total messages: {message_count}, agent_responses: {len(agent_responses)}, tool_uses: {len(tool_uses)}")
        logger.debug(f"Result summary: {summary}")

        final_response = summary if config.verbose else (agent_responses[-1] if agent_responses else "✅ Qwen task completed successfully")
        logger.info(f"[TOOL-RESPONSE] Qwen final response: {final_response}")
        return final_response

    except Exception as e:
        error_msg = f"Error executing Qwen subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def kiro_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """
    Execute a coding task using Kiro CLI agent.

    Kiro has access to file operations, shell commands, web search,
    and can make code changes directly.

    Args:
        instruction: The coding task or instruction to execute
        project_path: ABSOLUTE path to the project directory
        session_id: Optional session ID for conversation continuity
        model: Optional model to use
        is_initial_prompt: Whether this is the first prompt in a new session

    Returns:
        Summary of what the Kiro agent accomplished
    """
    if "kiro" not in enabled_subagents:
        return "❌ Kiro subagent is not enabled in this server instance"

    if not CLI_ADAPTERS_AVAILABLE:
        try:
            kiro_exec = _import_module_item("cli_subagent", "kiro_subagent")
            result = await kiro_exec(
                instruction=instruction,
                project_path=project_path,
                session_id=session_id,
                model=model,
                images=None,
                is_initial_prompt=is_initial_prompt
            )
            return result
        except Exception as e:
            error_msg = f"Error executing Kiro subagent: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"

    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
        logger.debug(f"Using fallback directory: {project_path}")
    else:
        project_path = str(Path(project_path).absolute())
        logger.debug(f"Using provided project path: {project_path}")

    if not Path(project_path).exists():
        error_msg = f"Project directory does not exist: {project_path}"
        logger.error(error_msg)
        return f"❌ {error_msg}"

    logger.info(f"Kiro: {model} [INSTRUCTION]: {instruction}")
    logger.debug(f"[MCP-TOOL] kiro_subagent started - project_path: {project_path}, model: {model}, session_id: {session_id}")

    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_kiro_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ Kiro CLI not available: {str(e)}"
        except AgentExecutionError as e:
            return f"❌ Kiro execution failed: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "kiro", instruction)

    try:
        kiro_cli = KiroCLI()
        availability = await kiro_cli.check_availability()
        if not availability.get("available", False):
            error_msg = availability.get("error", "Kiro CLI not available")
            logger.error(f"Kiro unavailable: {error_msg}")
            return f"❌ Kiro CLI not available: {error_msg}"

        agent_responses = []
        async for message in kiro_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())

        if not agent_responses:
            return "✅ Kiro task completed successfully"

        return f"**Kiro Response:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Kiro Response:**\n{chr(10).join(agent_responses)}"

    except Exception as e:
        error_msg = f"Error executing Kiro subagent: {str(e)}"
        await ctx.error(error_msg)
        return f"❌ {error_msg}"


@server.tool()
async def check_copilot_availability(ctx: Context = None) -> str:
    """Check if GitHub Copilot CLI is available."""
    if "copilot" not in enabled_subagents:
        return "❌ GitHub Copilot subagent is not enabled"

    try:
        check_copilot = _import_module_item("cli_subagent", "check_copilot_availability")
        result = await check_copilot()
        return result
    except Exception as e:
        return f"❌ Error checking GitHub Copilot: {str(e)}"


@server.tool()
async def copilot_subagent(
    instruction: str,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    is_initial_prompt: bool = False,
    ctx: Context = None
) -> str:
    """Execute a coding task using GitHub Copilot CLI agent."""
    if "copilot" not in enabled_subagents:
        return "❌ GitHub Copilot subagent is not enabled"

    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())

    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"

    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_copilot_with_error_handling(
                instruction, project_path, session_id, model, is_initial_prompt
            )
        except AgentNotAvailableError as e:
            return f"❌ GitHub Copilot CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "copilot", instruction)

    try:
        copilot_cli = CopilotCLI()
        availability = await copilot_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ GitHub Copilot CLI not available"

        agent_responses = []
        async for message in copilot_cli.execute_with_streaming(
            instruction=instruction,
            project_path=project_path,
            session_id=session_id,
            model=model,
            images=None,
            is_initial_prompt=is_initial_prompt
        ):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())

        if not agent_responses:
            return "✅ GitHub Copilot task completed"

        return f"**GitHub Copilot:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**GitHub Copilot:**\n{chr(10).join(agent_responses)}"

    except Exception as e:
        return f"❌ Error: {str(e)}"




@server.tool()
async def check_grok_availability(ctx: Context = None) -> str:
    if "grok" not in enabled_subagents:
        return "❌ Grok subagent is not enabled"
    try:
        check_grok = _import_module_item("cli_subagent", "check_grok_availability")
        return await check_grok()
    except Exception as e:
        return f"❌ Error checking Grok: {str(e)}"

@server.tool()
async def grok_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "grok" not in enabled_subagents:
        return "❌ Grok subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_grok_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Grok CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "grok", instruction)
    try:
        grok_cli = GrokCLI()
        availability = await grok_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Grok CLI not available"
        agent_responses = []
        async for message in grok_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Grok task completed"
        return f"**Grok:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Grok:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_kilocode_availability(ctx: Context = None) -> str:
    if "kilocode" not in enabled_subagents:
        return "❌ Kilocode subagent is not enabled"
    try:
        check_kilocode = _import_module_item("cli_subagent", "check_kilocode_availability")
        return await check_kilocode()
    except Exception as e:
        return f"❌ Error checking Kilocode: {str(e)}"

@server.tool()
async def kilocode_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "kilocode" not in enabled_subagents:
        return "❌ Kilocode subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_kilocode_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Kilocode CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "kilocode", instruction)
    try:
        kilocode_cli = KilocodeCLI()
        availability = await kilocode_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Kilocode CLI not available"
        agent_responses = []
        async for message in kilocode_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Kilocode task completed"
        return f"**Kilocode:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Kilocode:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_crush_availability(ctx: Context = None) -> str:
    if "crush" not in enabled_subagents:
        return "❌ Crush subagent is not enabled"
    try:
        check_crush = _import_module_item("cli_subagent", "check_crush_availability")
        return await check_crush()
    except Exception as e:
        return f"❌ Error checking Crush: {str(e)}"

@server.tool()
async def crush_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "crush" not in enabled_subagents:
        return "❌ Crush subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_crush_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Crush CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "crush", instruction)
    try:
        crush_cli = CrushCLI()
        availability = await crush_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Crush CLI not available"
        agent_responses = []
        async for message in crush_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Crush task completed"
        return f"**Crush:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Crush:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_opencode_availability(ctx: Context = None) -> str:
    if "opencode" not in enabled_subagents:
        return "❌ OpenCode subagent is not enabled"
    try:
        check_opencode = _import_module_item("cli_subagent", "check_opencode_availability")
        return await check_opencode()
    except Exception as e:
        return f"❌ Error checking OpenCode: {str(e)}"

@server.tool()
async def opencode_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "opencode" not in enabled_subagents:
        return "❌ OpenCode subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_opencode_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ OpenCode CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "opencode", instruction)
    try:
        opencode_cli = OpenCodeCLI()
        availability = await opencode_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ OpenCode CLI not available"
        agent_responses = []
        async for message in opencode_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ OpenCode task completed"
        return f"**OpenCode:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**OpenCode:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_antigravity_availability(ctx: Context = None) -> str:
    if "antigravity" not in enabled_subagents:
        return "❌ Antigravity subagent is not enabled"
    try:
        check_antigravity = _import_module_item("cli_subagent", "check_antigravity_availability")
        return await check_antigravity()
    except Exception as e:
        return f"❌ Error checking Antigravity: {str(e)}"

@server.tool()
async def antigravity_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "antigravity" not in enabled_subagents:
        return "❌ Antigravity subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_antigravity_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Antigravity CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, instruction)
    try:
        antigravity_cli = AntigravityCLI()
        availability = await antigravity_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Antigravity CLI not available"
        agent_responses = []
        async for message in antigravity_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Antigravity task completed"
        return f"**Antigravity:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Antigravity:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_factory_availability(ctx: Context = None) -> str:
    if "factory" not in enabled_subagents:
        return "❌ Factory/Droid subagent is not enabled"
    try:
        check_factory = _import_module_item("cli_subagent", "check_factory_availability")
        return await check_factory()
    except Exception as e:
        return f"❌ Error checking Factory/Droid: {str(e)}"

@server.tool()
async def factory_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "factory" not in enabled_subagents:
        return "❌ Factory/Droid subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_factory_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Factory/Droid CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "factory", instruction)
    try:
        factory_cli = FactoryCLI()
        availability = await factory_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Factory/Droid CLI not available"
        agent_responses = []
        async for message in factory_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Factory/Droid task completed"
        return f"**Factory/Droid:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Factory/Droid:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def check_rovo_availability(ctx: Context = None) -> str:
    if "rovo" not in enabled_subagents:
        return "❌ Rovo Dev subagent is not enabled"
    try:
        check_rovo = _import_module_item("cli_subagent", "check_rovo_availability")
        return await check_rovo()
    except Exception as e:
        return f"❌ Error checking Rovo Dev: {str(e)}"

@server.tool()
async def rovo_subagent(instruction: str, project_path: Optional[str] = None, session_id: Optional[str] = None, model: Optional[str] = None, is_initial_prompt: bool = False, ctx: Context = None) -> str:
    if "rovo" not in enabled_subagents:
        return "❌ Rovo Dev subagent is not enabled"
    if not project_path or project_path.strip() == "":
        project_path = str(working_dir.absolute()) if working_dir else str(Path.cwd().absolute())
    else:
        project_path = str(Path(project_path).absolute())
    if not Path(project_path).exists():
        return f"❌ Project directory does not exist: {project_path}"
    if ERROR_HANDLING_AVAILABLE:
        try:
            return await _execute_rovo_with_error_handling(instruction, project_path, session_id, model, is_initial_prompt)
        except AgentNotAvailableError as e:
            return f"❌ Rovo Dev CLI not available: {str(e)}"
        except Exception as e:
            return handle_agent_error(e, "rovo", instruction)
    try:
        rovo_cli = RovoCLI()
        availability = await rovo_cli.check_availability()
        if not availability.get("available", False):
            return f"❌ Rovo Dev CLI not available"
        agent_responses = []
        async for message in rovo_cli.execute_with_streaming(instruction=instruction, project_path=project_path, session_id=session_id, model=model, images=None, is_initial_prompt=is_initial_prompt):
            if hasattr(message, 'role') and message.role == "assistant":
                if message.content and message.content.strip():
                    agent_responses.append(message.content.strip())
        if not agent_responses:
            return "✅ Rovo Dev task completed"
        return f"**Rovo Dev:**\n{agent_responses[0]}" if len(agent_responses) == 1 else f"**Rovo Dev:**\n{chr(10).join(agent_responses)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@server.tool()
async def test_tool(context: Context,signal: bool = True) -> Any:
    """
    Test the tool.
    """
    #await anyio.sleep(15)
    #print("15 seconds passed")
    #await anyio.sleep(18)

    if signal is False:
        await anyio.sleep(40)
        return " Tool tested successfully with signal False (No Progress Update)"
    total_items = 50
    for i in range(total_items):
        # Do work
        await anyio.sleep(1)
        progress_message = f"Processing step {i+1} of {total_items}"
        logger.debug(f"[PROGRESS] {progress_message}")
        await context.debug(progress_message)
        await context.report_progress(
                  progress=i + 1,
                  total=total_items,
                  message=progress_message
              )
    

    return "✅ Tool tested successfully"


async def run_availability_check():
    """Run CLI availability check and save results."""
    availability_main = _import_module_item("availability_checker", "main")
    await availability_main()


def get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        # Get the path to pyproject.toml relative to this file
        current_dir = Path(__file__).parent
        pyproject_path = current_dir.parent / "pyproject.toml"

        if not pyproject_path.exists():
            return "unknown"

        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)

        return pyproject_data.get("project", {}).get("version", "unknown")
    except Exception as e:
        logger.warning(f"Could not read version from pyproject.toml: {e}")
        return "unknown"


def main():
    """Main entry point for the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Roundtable AI MCP Server - CLI Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m roundtable_mcp_server                    # Start MCP server with auto-detected agents
  python -m roundtable_mcp_server --check            # Check CLI availability
  python -m roundtable_mcp_server --agents codex,gemini,qwen  # Start with specific agents

Environment Variables:
  CLI_MCP_SUBAGENTS          Comma-separated list of subagents (codex,claude,cursor,gemini,qwen)
  CLI_MCP_WORKING_DIR        Default working directory
  CLI_MCP_DEBUG             Enable debug logging (true/false)
  CLI_MCP_IGNORE_AVAILABILITY  Ignore availability cache (true/false)

Priority Order:
  1. Command line --agents flag (highest priority)
  2. Environment variable CLI_MCP_SUBAGENTS
  3. Availability cache from ~/.roundtable/availability_check.json
  4. Default to all agents (lowest priority)
        """
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check CLI availability and save results to ~/.roundtable/availability_check.json"
    )
    parser.add_argument(
        "--agents",
        type=str,
        help="Comma-separated list of agents to enable (codex,claude,cursor,gemini,qwen,kiro,copilot,grok,kilocode,crush,opencode,antigravity,factory,rovo)"
    )
    parser.add_argument(
        "--working-dir",
        type=str,
        help="Default working directory for subagents"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    # Parse known args to support both --flag and --flag=value formats
    args, unknown = parser.parse_known_args()
    
    # Process unknown args for --key=value format (GitHub Copilot CLI compatibility)
    for arg in unknown:
        if arg.startswith("--agents="):
            args.agents = arg.split("=", 1)[1]
        elif arg.startswith("--working-dir="):
            args.working_dir = arg.split("=", 1)[1]
        elif arg.startswith("--debug="):
            args.debug = arg.split("=", 1)[1].lower() in ("true", "1", "yes")
        elif arg.startswith("--verbose="):
            args.verbose = arg.split("=", 1)[1].lower() in ("true", "1", "yes")

    if args.check:
        # Run availability check
        print("🔍 Checking CLI availability...")
        try:
            asyncio.run(run_availability_check())
        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            sys.exit(1)
        return

    # Set environment variables from command line args (highest priority)
    if args.agents:
        os.environ["CLI_MCP_SUBAGENTS"] = args.agents
    if args.working_dir:
        os.environ["CLI_MCP_WORKING_DIR"] = args.working_dir
    if args.debug:
        os.environ["CLI_MCP_DEBUG"] = "true"
    if args.verbose:
        os.environ["CLI_MCP_VERBOSE"] = "true"
        print(f"📋 Using agents from command line: {args.agents}")

    # Initialize configuration after processing command line arguments
    initialize_config()

    # Normal server startup
    version = get_version()
    logger.info("=" * 60)
    logger.info(f"Roundtable AI MCP Server v{version} starting at {datetime.now()}")
    logger.info("=" * 60)

    try:
        # Note: FastMCP handles tool filtering via the @server.tool() decorators
        # The enabled_subagents check is done in each tool function
        logger.info(f"Enabled subagents: {', '.join(enabled_subagents)}")

        # Run the server
        server.run()

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
