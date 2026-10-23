"""Unit tests for ros_mcp/utils/otel.py (fake span; no OpenTelemetry SDK needed)."""

import asyncio
import json

import pytest
from fastmcp import Client, Context, FastMCP

import ros_mcp.utils.otel as otel

pytestmark = pytest.mark.skipif(
    otel.trace is None or not hasattr(FastMCP("x"), "list_tools"),
    reason="needs fastmcp 3 with opentelemetry-api",
)


class FakeSpan:
    def __init__(self, recording=True):
        self.recording = recording
        self.attributes = {}
        self.status = None

    def is_recording(self):
        return self.recording

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        self.status = status


@pytest.fixture
def span(monkeypatch):
    s = FakeSpan()
    monkeypatch.setattr(otel, "_current_span", lambda: s)
    for name in (otel.RECORD_ARGS_ENV, otel.RECORD_RESULTS_ENV, otel.MAX_CHARS_ENV):
        monkeypatch.delenv(name, raising=False)
    return s


def _server():
    mcp = FastMCP("test")

    @mcp.tool
    def get_topic_type(topic: str = "") -> dict:
        if not topic:
            return {"error": "Topic name cannot be empty"}
        return {"topic": topic, "type": "turtlesim/msg/Pose"}

    @mcp.tool
    async def send_goal(action: str = "", ctx: Context = None) -> dict:  # type: ignore[assignment]
        return {"action": action, "status": "succeeded"}

    @mcp.tool
    def big(n: int = 10) -> dict:
        return {"data": "x" * n}

    return mcp


def _call(mcp, name, args):
    async def run():
        async with Client(mcp) as c:
            return await c.call_tool(name, args, raise_on_error=False)

    return asyncio.run(run())


class TestDefaults:
    def test_arguments_and_results_not_recorded_by_default(self, span):
        mcp = _server()
        assert otel.instrument_tools(mcp) == 3
        _call(mcp, "get_topic_type", {"topic": "/turtle1/pose"})
        assert "gen_ai.tool.call.arguments" not in span.attributes
        assert "gen_ai.tool.call.result" not in span.attributes
        assert span.status is None

    def test_tool_error_marked_without_message(self, span):
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "get_topic_type", {"topic": ""})
        assert span.attributes["error.type"] == "tool_error"
        assert span.status.status_code == otel.StatusCode.ERROR
        assert span.status.description is None

    def test_not_recording_span_is_left_alone(self, monkeypatch, span):
        span.recording = False
        monkeypatch.setenv(otel.RECORD_ARGS_ENV, "1")
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "get_topic_type", {"topic": ""})
        assert span.attributes == {} and span.status is None

    def test_instrumenting_twice_wraps_once(self, span):
        mcp = _server()
        assert otel.instrument_tools(mcp) == 3
        assert otel.instrument_tools(mcp) == 0

    def test_tool_results_unchanged(self, span):
        mcp = _server()
        before = _call(mcp, "get_topic_type", {"topic": "/a"}).content[0].text
        otel.instrument_tools(mcp)
        assert _call(mcp, "get_topic_type", {"topic": "/a"}).content[0].text == before


class TestFlags:
    def test_record_args(self, monkeypatch, span):
        monkeypatch.setenv(otel.RECORD_ARGS_ENV, "1")
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "get_topic_type", {"topic": "/turtle1/pose"})
        assert json.loads(span.attributes["gen_ai.tool.call.arguments"]) == {
            "topic": "/turtle1/pose"
        }

    def test_record_args_async_tool_skips_context(self, monkeypatch, span):
        monkeypatch.setenv(otel.RECORD_ARGS_ENV, "true")
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "send_goal", {"action": "/fibonacci"})
        assert json.loads(span.attributes["gen_ai.tool.call.arguments"]) == {"action": "/fibonacci"}

    def test_record_results_and_error_message(self, monkeypatch, span):
        monkeypatch.setenv(otel.RECORD_RESULTS_ENV, "1")
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "get_topic_type", {"topic": ""})
        assert json.loads(span.attributes["gen_ai.tool.call.result"]) == {
            "error": "Topic name cannot be empty"
        }
        assert span.status.description == "Topic name cannot be empty"

    def test_values_are_truncated(self, monkeypatch, span):
        monkeypatch.setenv(otel.RECORD_RESULTS_ENV, "1")
        monkeypatch.setenv(otel.MAX_CHARS_ENV, "100")
        mcp = _server()
        otel.instrument_tools(mcp)
        _call(mcp, "big", {"n": 1000})
        value = span.attributes["gen_ai.tool.call.result"]
        assert value.startswith('{"data": "xxx') and value.endswith("chars]")
        assert len(value) < 150
