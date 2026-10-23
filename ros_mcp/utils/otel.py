"""Optional OpenTelemetry attributes on ros-mcp tool-call spans.

FastMCP 3 creates one ``tools/call <name>`` span per tool call, with the tool name,
session ID and duration, but no arguments or results. ``instrument_tools()`` wraps
each registered tool function so it can add, on that same span:

- ``error.type = tool_error`` and an ERROR status when a tool returns
  ``{"error": ...}`` (ros-mcp tools report failures this way instead of raising).
  Always on; no error text is recorded unless results are recorded.
- ``gen_ai.tool.call.arguments``: the call arguments as JSON, only when
  ``ROS_MCP_OTEL_RECORD_ARGS=1``.
- ``gen_ai.tool.call.result``: the result as JSON or text, only when
  ``ROS_MCP_OTEL_RECORD_RESULTS=1``.

Arguments and results can hold topic names, robot names and message content, so both
are off by default. ``ROS_MCP_OTEL_MAX_ATTR_CHARS`` (default 4096) caps each value.

Nothing is recorded unless the process has an OpenTelemetry SDK and exporter
configured (for example, when started with ``opentelemetry-instrument``).
"""

import asyncio
import functools
import inspect
import json
import os
from typing import Any, Callable

from fastmcp import Context, FastMCP

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ImportError:  # opentelemetry-api comes with fastmcp 3; absent on fastmcp 2
    trace = None

RECORD_ARGS_ENV = "ROS_MCP_OTEL_RECORD_ARGS"
RECORD_RESULTS_ENV = "ROS_MCP_OTEL_RECORD_RESULTS"
MAX_CHARS_ENV = "ROS_MCP_OTEL_MAX_ATTR_CHARS"
DEFAULT_MAX_CHARS = 4096


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _max_chars() -> int:
    try:
        return max(64, int(os.getenv(MAX_CHARS_ENV, DEFAULT_MAX_CHARS)))
    except ValueError:
        return DEFAULT_MAX_CHARS


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit} chars]"


def _arguments_json(kwargs: dict) -> str:
    # Injected FastMCP objects (Context) are not call arguments.
    args = {k: v for k, v in kwargs.items() if not isinstance(v, Context)}
    return json.dumps(args, default=str, ensure_ascii=False)


def _result_text(result: Any) -> str:
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return json.dumps(result, default=str, ensure_ascii=False)
    # ToolResult and MCP content lists: keep text, replace binary content with a marker.
    content = getattr(result, "content", result)
    if isinstance(content, list):
        parts = [getattr(c, "text", None) or f"[{getattr(c, 'type', 'content')}]" for c in content]
        return " ".join(parts)
    return str(result)


def _current_span():
    return trace.get_current_span()


def _annotate(span, result: Any, record_results: bool, limit: int) -> None:
    if isinstance(result, dict) and "error" in result:
        span.set_attribute("error.type", "tool_error")
        message = _truncate(str(result["error"]), limit) if record_results else None
        span.set_status(Status(StatusCode.ERROR, message))
    if record_results:
        span.set_attribute("gen_ai.tool.call.result", _truncate(_result_text(result), limit))


def _wrap(fn: Callable, record_args: bool, record_results: bool, limit: int) -> Callable:
    def before():
        span = _current_span()
        return span if span.is_recording() else None

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            span = before()
            if span is not None and record_args:
                span.set_attribute(
                    "gen_ai.tool.call.arguments", _truncate(_arguments_json(kwargs), limit)
                )
            result = await fn(*args, **kwargs)
            if span is not None:
                _annotate(span, result, record_results, limit)
            return result

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        span = before()
        if span is not None and record_args:
            span.set_attribute(
                "gen_ai.tool.call.arguments", _truncate(_arguments_json(kwargs), limit)
            )
        result = fn(*args, **kwargs)
        if span is not None:
            _annotate(span, result, record_results, limit)
        return result

    return wrapper


def instrument_tools(mcp: FastMCP) -> int:
    """Wrap every registered tool of ``mcp``; return how many were wrapped.

    Call it after all tools are registered and before the server's event loop starts.
    Does nothing without OpenTelemetry or on FastMCP 2 (which creates no spans).
    """
    if trace is None or not hasattr(mcp, "list_tools"):
        return 0
    tools = asyncio.run(mcp.list_tools())
    record_args = _flag(RECORD_ARGS_ENV)
    record_results = _flag(RECORD_RESULTS_ENV)
    limit = _max_chars()
    count = 0
    for tool in tools:
        fn = getattr(tool, "fn", None)
        if fn is None or getattr(fn, "_ros_mcp_otel", False):
            continue
        wrapped = _wrap(fn, record_args, record_results, limit)
        wrapped._ros_mcp_otel = True
        tool.fn = wrapped
        count += 1
    return count
