# ros-mcp-server: review and triage drafts

Drafts for the [robotmcp/ros-mcp-server](https://github.com/robotmcp/ros-mcp-server) maintainers. **None of this is posted upstream.** Each item is tested on ROS 2 Docker images from `tests/integration/docker` (Humble, Jazzy, Lyrical) on a Linux box.

This branch holds documents only; it shares no history with the code branches.

## PR reviews

| PR | What it does | Recommendation | Key evidence | Draft |
|---|---|---|---|---|
| [#399](https://github.com/robotmcp/ros-mcp-server/pull/399) | Concurrent action results (fixes #397) | Request one change, then merge first | Live repro on Jazzy: `develop` 14/24 wrong results, #399 0/24. Also fixes goal loss during other tool calls (likely #318). Fails `test_cancel_request_sent` on 3 distros | [week1-pr-399-377-398.md](week1-pr-399-377-398.md) |
| [#377](https://github.com/robotmcp/ros-mcp-server/pull/377) | Keep websocket open on receive timeout | Rebase after #399 | Conflicts with #399 in `websocket.py`; adds the built-in timeout case #399 misses | [week1-pr-399-377-398.md](week1-pr-399-377-398.md) |
| [#398](https://github.com/robotmcp/ros-mcp-server/pull/398) | macOS ping timeout (fixes #394) | Approve | All tests pass; Linux and Windows commands unchanged; not tested on a Mac | [week1-pr-399-377-398.md](week1-pr-399-377-398.md) |
| [#402](https://github.com/robotmcp/ros-mcp-server/pull/402) | Background topic subscriptions (closes #315) | Approve with changes, merge after #399 and #377 | Unit 39 passed, Jazzy/Humble 113 passed; live checks pass; memory cap for image topics and a list tool requested | [week2-pr-402.md](week2-pr-402.md) |

Suggested merge order (three PRs change `WebSocketManager.receive()`): **#399 → #377 → #402**; #398 any time.

## Backlog and design

| Document | Summary |
|---|---|
| [triage-proposal.md](triage-proposal.md) | 45 open PRs → 9 or fewer. The 33 bulk unit-test PRs break each other when merged together (13 failed, 31 errors: they replace `sys.modules` entries at import time), so the proposal is one consolidated test PR. |
| [telemetry-design-issue.md](telemetry-design-issue.md) | Anonymous usage telemetry: one event per server start (version, ROS distro, MCP client, transport, OS), never robot or topic names; `ROS_MCP_TELEMETRY=0` / `DO_NOT_TRACK=1`; three decisions for the maintainers. |

## Related PRs on this fork

| PR | What |
|---|---|
| [amankh#1](https://github.com/amankh/ros-mcp-server/pull/1) | ROS 2 Lyrical in the integration test matrix |
| [amankh#2](https://github.com/amankh/ros-mcp-server/pull/2) | PyPI download metrics (version, OS, installer, CI flag), replacing the empty release-download metric |
| [amankh#3](https://github.com/amankh/ros-mcp-server/pull/3) | Allow fastmcp 3.x (`<4`); tests use FastMCP's public API |

Last updated 2026-10-23.
