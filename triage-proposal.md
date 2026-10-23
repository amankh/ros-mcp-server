# Triage proposal: 45 open PRs → 9 (draft)

Prepared 2026-10-23 for the ros-mcp-server maintainers. Proposals only; the maintainers decide. Evidence: runs `pr_reviews_20261022`, `pr402_review_20261023`, `triage_bulk_tests_20261023`.

## Summary

| Group | PRs | Proposal | Open after |
|---|---|---|---|
| A. Real fixes and features, tested | #399, #377, #398, #402, #343 | Review and merge in order (below) | 5 → 0 as they merge |
| B. Duplicates and superseded | #352, #307 | Close with a link to the PR that replaces them | 0 |
| C. Bulk unit-test PRs (Bartok9, July 10–29) | 33 test PRs: #350, #351, #353–#376, #379–#384, #386 | Close with thanks; replace with one consolidated test PR | 1 (the new PR) |
| D. Other Bartok9 PRs | #385 (fix, targets `main`), #378 (docs) | Retarget #385 to `develop` and review; merge #378 after a read | 2 |
| E. Drafts and scope questions | #396, #400 (drafts), #401 (docs example) | Ask authors for status; ask #401 whether it belongs in the repo | 3 |
| **Total** | **45** | | **≤ 9** (fewer as group A merges) |

## A. Merge order for the tested PRs

Three PRs change `WebSocketManager.receive()` timeout handling, so order matters.

| Order | PR | State of review | Notes |
|---|---|---|---|
| 1 | #399 concurrent action results (fixes #397) | Tested; request one change | Live repro on Jazzy: `develop` 14/24 wrong results, #399 0/24. Also fixes goal loss during other tool calls (likely #318). Fails `test_cancel_request_sent` on Humble, Jazzy, Lyrical. |
| 2 | #377 keep websocket open on receive timeout | Tested | Conflicts with #399 in `websocket.py`; rebase after #399. |
| 3 | #402 background subscriptions (closes #315) | Tested; approve with changes | Merges clean with #377, conflicts with #399. Drop its own `websocket.py` hunk once #377 lands. Memory cap for image topics and a list tool requested. |
| any | #398 macOS ping timeout (fixes #394) | Tested; approve | Independent. Not tested on a real Mac. |
| any | #343 guard topics block against non-dict values | Maintainer's own PR | Keep; close #352 as its duplicate. |

## B. Close as duplicate or superseded

| PR | Reason |
|---|---|
| #352 | Same fix as #343 (guard topics block against non-dict rosbridge values); #343 targets `develop` |
| #307 (draft) | Image save path already fixed on `develop` by #345 (`ROS_MCP_IMAGE_DIR`) |

## C. The 33 bulk unit-test PRs

All 33 add one new test file each (+4,888 lines in total). 28 target `develop`, 5 target `main` (#350, #351, #381, #382, #386).

I merged all 33 onto `develop` locally (no conflicts) and ran `tests/unit` (`triage_bulk_tests_20261023`):

| Check | Result |
|---|---|
| All 33 together | 205 passed, **13 failed, 31 errors** |
| Broken even alone | #362 and #356 (`numpy` stubbed without `ndarray`), #386 (stubs `ros_mcp.utils`, then `config_utils` import fails) |
| Without those 3 | 205 passed, **5 failed, 17 errors**, same on 3 runs |
| Root cause | 25 of the 33 files replace entries in `sys.modules` (numpy, cv2, websocket, ros_mcp modules) at import time. Each file passes alone; together they break each other. |

Merging them one by one would make `tests/unit` fail. Proposal:

1. Close all 33 with a thank-you and this explanation.
2. One consolidated PR keeps the useful cases and moves the stubs into `conftest.py` fixtures (`monkeypatch.setitem(sys.modules, ...)`), so nothing leaks between files. I can prepare it; the author is welcome to do it instead.

## D. Other PRs from the same author

| PR | Proposal |
|---|---|
| #385 fix(topics): validate `publish_once` msg type before dict copy | Real fix, but targets `main`. Ask to retarget to `develop`, then review. |
| #378 docs(install): troubleshoot false action-goal timeouts | 15 lines; merge after a read. May need an update once #399 fixes the underlying timeout. |
| #377 | Covered in group A. |

## E. Drafts and scope

| PR | Proposal |
|---|---|
| #396 (draft) send_action_goal reports success on rosbridge failures (#395) | Ask the author whether it is ready; the bug is confirmed on Lyrical. |
| #400 (draft) raw image row stride | Ask the author whether it is ready. |
| #401 read-only robot code lookup example (+1,488 lines) | Ask whether a large example belongs in this repo or in `robotmcp/demos-ros-mcp-server`. |

## Issues to close when v3.2.0 ships

Fixed on `develop`, not yet released: #301 (by #345), #317 (by #344), #277 (by #341), #302 (by #303), #308 (by #309). Close each with a link to the fixing PR once the release is out.

## Now, independent of the PRs

- Acknowledge security report #283 (no reply since 2026-03-27) and say a design for allow-lists and a read-only mode is coming.

## Ask

- GitHub **Triage** role for me, so I can label, close duplicates and ask authors for status without write access.
