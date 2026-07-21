from contextvars import ContextVar, Token

_trace_id_context: ContextVar[str] = ContextVar("trace_id", default="")


def set_trace_id(trace_id: str) -> Token[str]:
    return _trace_id_context.set(trace_id)


def reset_trace_id(token: Token[str]) -> None:
    _trace_id_context.reset(token)


def get_trace_id() -> str:
    return _trace_id_context.get()
