# Week 2 review draft: #402 (draft)

Tested 2026-10-23 on the home box. Containers: the repo's `tests/integration/docker` images (ROS 2 Jazzy, Humble). Run ID: `pr402_review_20261023`.

Upstream head tested: #402 `396e234`; base `develop` `2dfbef1`. fastmcp 2.13.0.

---

## #402: Add background ROS topic subscriptions

**Recommendation: approve with changes. Merge after #399 and #377, and drop the `websocket.py` hunk if #377 lands first.**

### What I tested

| Check | Result |
|---|---|
| ruff check + format | clean |
| Unit tests | 39 passed (19 existing + 20 new) |
| Integration, Jazzy | 113 passed, 1 skipped (same as `develop`) |
| Integration, Humble | 113 passed, 1 skipped (same as `develop`) |
| Live: start on `/turtle1/pose` (`max_buffer=50`) through an MCP client | starts at once, 1 listener thread |
| Live: other tools during the subscription | `publish_once` to `/turtle1/cmd_vel` and `get_topics` work |
| Live: after 2 s | 252 received, 50 buffered, 202 dropped (counters correct) |
| Live: stop | status `stopped`, 0 listener threads left |
| Live: 21 subscriptions | 20 start, 21st refused with a clear error; all 20 stop cleanly, 0 threads left |
| Live: `subscribe_once` on a silent topic (affected by the `websocket.py` change) | times out after 3.0 s with the same error as `develop`; the next tool call works |
| Merge with #377 | clean |
| Merge with #399 | **conflict** in `ros_mcp/utils/websocket.py` |

Live checks used a FastMCP in-memory client against the Jazzy turtlesim image.

### Review comment

> Thanks for this; it closes #315 and the lifecycle work is careful. I tested it on ROS 2 Jazzy and Humble (Docker images from `tests/integration/docker`):
>
> - ruff clean, unit 39 passed, integration 113 passed / 1 skipped on both distros (same as `develop`).
> - Live through an MCP client on Jazzy turtlesim: a subscription on `/turtle1/pose` collected 252 messages in 2 s with `max_buffer=50` (50 buffered, 202 dropped, counters correct). `publish_once` and `get_topics` kept working while it ran. Stop left no listener threads. The 21st subscription was refused with a clear error, and stopping all 20 left no threads.
>
> Requests before merge:
>
> 1. **The `websocket.py` hunk overlaps #377 and conflicts with #399.** Returning `None` on a receive timeout changes behavior for every caller, not only background listeners. #377 makes the same change more completely (it also handles `socket.timeout`). Suggest merging #399, then #377, then rebasing this PR and dropping its own hunk.
> 2. **Memory with large messages.** The buffer limit counts messages, not bytes. `sensor_msgs/Image` or `PointCloud2` subscriptions can hold about 1 MB per message, so 20 subscriptions × `max_buffer=1000` could grow to about 20 GB. Suggest refusing image and point-cloud types here (point to `subscribe_once` with image support), or adding a byte cap per subscription.
> 3. **No way to list subscriptions.** If the agent loses a `subscription_id` (for example after the context is compacted), the subscription keeps running until the limit of 20 is reached. A `list_background_subscriptions` tool (id, topic, status, counts) would let it recover and clean up.
>
> Smaller points:
>
> 4. `get_subscription_messages` returns the **oldest** buffered messages first. For a robot agent the newest is usually what matters; a `newest_first` option, or a line in the tool description, would help.
> 5. Stopped subscriptions keep their buffers until pruned at 100 records, which can hold up to 100 × 1,000 messages. Freeing the buffer once it has been read with `clear=true` after stop would bound this.
> 6. An integration test against the turtlesim image (start, collect, stop) would protect this beyond the mocked unit tests. Happy to send one as a follow-up PR.
