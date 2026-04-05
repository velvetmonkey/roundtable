"""Error handling utilities for MCP server."""
import logging
from typing import Optional
from pathlib import Path

from .exceptions import (
    PathValidationError,
    AgentNotAvailableError,
    ConfigurationError
)

logger = logging.getLogger(__name__)


def validate_project_path(
    path: Optional[str],
    fallback_path: Path,
    agent_name: str = "agent"
) -> str:
    """Validate and normalize project path.
    
    Args:
        path: User-provided path (may be None or empty)
        fallback_path: Fallback path if user path is invalid
        agent_name: Name of agent for error context
    
    Returns:
        Absolute path as string
    
    Raises:
        PathValidationError: If path is invalid
    """
    # Use fallback if no path provided
    if not path or not path.strip():
        result_path = fallback_path.absolute()
        logger.debug(f"Using fallback directory for {agent_name}: {result_path}")
        return str(result_path)
    
    # Convert to Path and make absolute
    try:
        result_path = Path(path).absolute()
    except Exception as e:
        raise PathValidationError(
            path,
            f"Invalid path format: {e}",
            {"agent": agent_name}
        )
    
    # Check if exists
    if not result_path.exists():
        raise PathValidationError(
            str(result_path),
            "Directory does not exist",
            {"agent": agent_name}
        )
    
    # Check if directory
    if not result_path.is_dir():
        raise PathValidationError(
            str(result_path),
            "Path is not a directory",
            {"agent": agent_name}
        )
    
    logger.debug(f"Validated project path for {agent_name}: {result_path}")
    return str(result_path)


def format_error_response(
    error: Exception,
    agent_name: str = None,
    include_context: bool = True
) -> str:
    """Format error for user-friendly response.
    
    Args:
        error: The exception to format
        agent_name: Optional agent name for context
        include_context: Whether to include error context
    
    Returns:
        Formatted error message
    """
    from .exceptions import RoundtableError
    
    # Handle custom exceptions
    if isinstance(error, RoundtableError):
        message = f"❌ {error.message}"
        
        if include_context and error.context:
            context_str = ", ".join(f"{k}={v}" for k, v in error.context.items())
            message += f" ({context_str})"
        
        return message
    
    # Handle generic exceptions
    error_type = type(error).__name__
    message = f"❌ {error_type}: {str(error)}"
    
    if agent_name:
        message = f"❌ {agent_name} - {error_type}: {str(error)}"
    
    return message


def handle_agent_error(
    error: Exception,
    agent_name: str,
    instruction: str = ""
) -> str:
    """Handle agent execution error and return formatted message."""
    log_error_with_context(
        error, f"{agent_name}_execution", {"instruction": instruction[:200]}
    )
    return format_error_response(error, agent_name=agent_name)


def log_error_with_context(
    error: Exception,
    operation: str,
    context: dict = None
):
    """Log error with structured context.
    
    Args:
        error: The exception to log
        operation: Operation that failed
        context: Additional context
    """
    from .exceptions import RoundtableError
    
    context = context or {}
    
    if isinstance(error, RoundtableError):
        context.update(error.context)
        logger.error(
            f"Operation '{operation}' failed: [{error.error_code}] {error.message}",
            extra={"context": context},
            exc_info=True
        )
    else:
        logger.error(
            f"Operation '{operation}' failed: {type(error).__name__}: {error}",
            extra={"context": context},
            exc_info=True
        )
