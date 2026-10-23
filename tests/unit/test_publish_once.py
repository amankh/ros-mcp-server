"""Unit tests for publish_once's settle window (no rosbridge needed)."""

import asyncio
import json
import time

import pytest
from fastmcp import FastMCP

import ros_mcp.tools.topics as topics_module
from ros_mcp.tools.topics import register_topic_tools

TWIST = {"linear": {"x": 1.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}


class FakeWebSocketManager:
    """Records sent ops; poll() returns queued replies, then waits out the timeout."""

    def __init__(self, replies=()):
        self.sent = []
        self.replies = list(replies)
        self.receive_calls = 0

    def send(self, message):
        self.sent.append(message)
        return None

    def poll(self, timeout):
        if self.replies:
            return self.replies.pop(0)
        time.sleep(timeout)
        return None

    def receive(self, timeout=None):
        # receive() closes the connection on timeout; publish_once must not use it.
        self.receive_calls += 1
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _publish_once(ws):
    mcp = FastMCP("test")
    register_topic_tools(mcp, ws)
    if hasattr(mcp, "get_tools"):  # FastMCP 2.x
        tools = asyncio.run(mcp.get_tools())
    else:  # FastMCP 3.x
        tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    return tools["publish_once"].fn


def _call(ws):
    return _publish_once(ws)(
        topic="/turtle1/cmd_vel", msg_type="geometry_msgs/msg/Twist", msg=TWIST
    )


class TestPublishOnceSettle:
    def test_success_sends_advertise_publish_unadvertise(self):
        ws = FakeWebSocketManager()
        result = _call(ws)
        assert result["success"] is True
        assert [m["op"] for m in ws.sent] == ["advertise", "publish", "unadvertise"]

    def test_success_does_not_use_closing_receive(self):
        ws = FakeWebSocketManager()
        _call(ws)
        assert ws.receive_calls == 0

    def test_takes_about_the_settle_window(self):
        ws = FakeWebSocketManager()
        t0 = time.monotonic()
        _call(ws)
        elapsed = time.monotonic() - t0
        assert topics_module.PUBLISH_SETTLE_SECONDS <= elapsed < 0.5

    def test_rosbridge_error_is_reported_and_topic_unadvertised(self):
        error = json.dumps({"op": "status", "level": "error", "msg": "bad field 'lin'"})
        ws = FakeWebSocketManager(replies=[error])
        result = _call(ws)
        assert result == {"error": "Publish failed: bad field 'lin'"}
        assert ws.sent[-1] == {"op": "unadvertise", "topic": "/turtle1/cmd_vel"}

    @pytest.mark.parametrize(
        "reply",
        ["not json", json.dumps({"op": "status", "level": "info", "msg": "ok"})],
    )
    def test_non_error_replies_are_ignored(self, reply):
        ws = FakeWebSocketManager(replies=[reply])
        result = _call(ws)
        assert result["success"] is True
        assert ws.sent[-1]["op"] == "unadvertise"
