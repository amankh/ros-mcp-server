# Draft issue: anonymous usage telemetry (draft)

Title: **Design: anonymous, opt-out-able usage telemetry (one event per server start)**

---

## Problem

We can't tell how many people run ros-mcp, on which ROS distro, or with which AI client.

- GitHub traffic shows visitors and clones, not users.
- PyPI downloads overcount: mirrors, CI, bots and `uvx` cache refreshes all count. A PyPI tracker is in progress (fork PR [amankh/ros-mcp-server#2](https://github.com/amankh/ros-mcp-server/pull/2)). Of the last 30 days' 2,502 downloads, about 1,292 look like user installs.
- Downloads can't answer: How many servers actually run? Humble vs Jazzy vs ROS 1? Claude vs Cursor vs ChatGPT? stdio vs HTTP? These answers decide which distros to test and which clients to document.

## Proposal

Send **one anonymous event per server process**, when the first MCP client completes the `initialize` handshake. Sending at handshake time, not at process start, lets the event include the client name.

### Fields (complete list; changes only by PR)

| Field | Example | Source |
|---|---|---|
| `version` | `3.2.0` | package version |
| `ros` | `ros2-jazzy`, `ros1-noetic`, `unknown` | existing ROS version detection, if connected by then |
| `mcp_client` | `claude-ai 1.2`, `cursor 1.7` | `clientInfo.name` and `version` from the MCP handshake |
| `transport` | `stdio`, `http` | CLI argument |
| `os`, `arch` | `linux`, `x86_64` | `platform` |
| `python` | `3.12` | `sys.version_info` (major.minor) |
| `run_id` | random per process | `uuid4()`, never stored |

### Never sent

Robot IP, hostname or robot name; topic, service, node or action names; message content; prompts or tool arguments; error text with paths; any persistent user or machine ID.

### Controls

| Rule | How |
|---|---|
| Easy to turn off | `ROS_MCP_TELEMETRY=0` or `DO_NOT_TRACK=1`. Environment variables win over anything else. |
| Off in CI | Nothing is sent when `CI` is set. |
| Notice before the first event | One line on **stderr** (never stdout: with stdio transport, stdout carries the MCP protocol) or as an MCP log message. |
| Transparent | `ros-mcp --telemetry-status` prints whether telemetry is on and the exact payload it would send. |
| Never in the way | Background thread, timeout under 2 s, all errors ignored, never delays a tool call. |
| No IP storage | Pick a backend that drops the IP or keeps only the country; say so in the docs. |

### Implementation sketch

- `ros_mcp/utils/telemetry.py`: build the payload, check the switches, send in a daemon thread with `urllib` (no new dependency).
- Hook: FastMCP middleware or an `on_initialize` handler that fires once per process.
- `main.py`: `--telemetry-status` flag; README and `docs/` page listing the fields.
- Tests: switches (`ROS_MCP_TELEMETRY`, `DO_NOT_TRACK`, `CI`), payload contains only the listed fields, send failures never raise.

Estimate: 2–3 days including docs and tests.

## Decisions for the maintainers

1. **Default:**
   - opt-in (most trust, little data: stdio can't ask the user a question);
   - opt-out with notice (much more data; some labs and companies may object);
   - **middle option (suggested):** this one startup event by default; anything richer (for example, which tool groups were used) opt-in only.
2. **Backend:** [Scarf](https://docs.scarf.sh/custom-telemetry/) (built for open-source call-home; a URL with query parameters), PostHog (EU host or self-hosted), or a small endpoint we run that only counts.
3. **Who owns the dashboard** and how often numbers are shared (for example, a monthly post in Discussions).

## Prior art

Homebrew, Next.js, dbt, GitHub CLI, Unstructured, [Daft](https://docs.daft.ai/en/stable/telemetry/), [Apache Sedona](https://sedona.apache.org/latest-snapshot/asf/telemetry/). All use a fixed field list, `DO_NOT_TRACK`, and a documented opt-out. ROS itself has no in-product telemetry; the yearly [ROS Metrics Report](https://discourse.openrobotics.org/t/2025-ros-metrics-report/52575) uses package-server logs only.
