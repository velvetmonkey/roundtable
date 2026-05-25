"""Custom exceptions for Roundtable MCP Server."""


class RoundtableError(Exception):
    """Base exception for all Roundtable errors."""
    
    def __init__(self, message: str, error_code: str = "UNKNOWN", context: dict = None):
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        super().__init__(self.message)
    
    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class ConfigurationError(RoundtableError):
    """Configuration-related errors."""
    
    def __init__(self, message: str, context: dict = None):
        super().__init__(message, "CONFIG_ERROR", context)


class AgentNotAvailableError(RoundtableError):
    """Agent CLI not available or not configured."""
    
    def __init__(self, agent_name: str, reason: str = None, context: dict = None):
        message = f"Agent '{agent_name}' is not available"
        if reason:
            message += f": {reason}"
        super().__init__(message, "AGENT_NOT_AVAILABLE", context or {"agent": agent_name})


class AgentExecutionError(RoundtableError):
    """Error during agent execution."""

    def __init__(self, agent_name_or_message: str, message: str = None, context: dict = None):
        if message is None:
            # Single-arg form: AgentExecutionError("some message")
            full_message = agent_name_or_message
            agent_name = "unknown"
        else:
            agent_name = agent_name_or_message
            full_message = f"Agent '{agent_name}' execution failed: {message}"
        super().__init__(full_message, "AGENT_EXECUTION_ERROR", context or {"agent": agent_name})


class StreamingError(RoundtableError):
    """Error during message streaming."""
    
    def __init__(self, message: str, context: dict = None):
        super().__init__(message, "STREAMING_ERROR", context)


class PathValidationError(RoundtableError):
    """Invalid or inaccessible path."""
    
    def __init__(self, path: str, reason: str = None, context: dict = None):
        message = f"Invalid path: {path}"
        if reason:
            message += f" - {reason}"
        super().__init__(message, "PATH_ERROR", context or {"path": path})


class TimeoutError(RoundtableError):
    """Operation timeout."""
    
    def __init__(self, operation: str, timeout: int, context: dict = None):
        message = f"Operation '{operation}' timed out after {timeout}s"
        super().__init__(message, "TIMEOUT_ERROR", context or {"operation": operation, "timeout": timeout})


class RetryableError(RoundtableError):
    """Error that can be retried."""
    
    def __init__(self, message: str, error_code: str = "RETRYABLE", context: dict = None):
        super().__init__(message, error_code, context)
