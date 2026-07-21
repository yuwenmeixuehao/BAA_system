from typing import Any


class AgentExecutionError(RuntimeError):
    """A safe, classified failure that can be shown to the task owner."""

    def __init__(
        self,
        error_code: str,
        user_message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(user_message)
        self.error_code = error_code
        self.user_message = user_message
        self.details = details or {}
