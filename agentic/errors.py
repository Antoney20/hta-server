class AgenticError(Exception):
    code = "agentic_error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ConfigError(AgenticError):
    """Missing model, missing/empty key, no active provider — fixable in admin."""
    code = "config_error"


class ConnectionErr(AgenticError):
    """Could not reach the provider — network, timeout, auth rejected, rate limit."""
    code = "connection_error"


class ProcessingError(AgenticError):
    """Provider responded but output was unusable — empty, bad JSON, wrong shape."""
    code = "processing_error"