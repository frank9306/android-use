---
id: ISSUE-0001
title: "Android automation MCP and real-device acceptance"
status: blocked
priority: P1
created: 2026-10-09
updated: 2026-10-09
closed:
sources: ["https://github.com/openatx/uiautomator2"]
related_adrs: []
depends_on: []
---

# ISSUE-0001: Android automation MCP and real-device acceptance

## Problem

AI has no repository-owned Android observation and control tools.

## Desired outcome

Deliver a USB Android MCP server and CLI, validate against a connected device, commit and push.

## Acceptance criteria

- [x] A reproducible Python package exposes the Android tools over MCP stdio and CLI.
- [x] Devices/ready/observe/find/tap/swipe/type_text/press/launch_app/wait/batch work.
- [x] Observations contain compact hierarchy, screenshot metadata and coordinate mapping.
- [x] Ambiguous selectors, stale/rotated coordinates and failed batches stop explicitly.
- [x] Chinese input is read back and the original input method is restored.
- [ ] Unit and MCP protocol tests pass; an isolated real-device workflow passes.
- [x] Documentation, configuration examples and verification evidence are committed and pushed.

## Out of scope

Root access, CAPTCHA solving, credential entry, app data extraction and embedded video streaming.

## Decisions

Python 3.12 + uv, official MCP Python SDK 1.x, uiautomator2 3.x, USB ADB.
Use standard argparse for a JSON CLI. scrcpy remains an optional external preview.
One process owns one device; a process lock prevents concurrent controllers.

## Implementation notes

Starting from an empty repository. ADB detected one authorized NX737J device.
Use a repository-owned Android fixture with no permissions for device acceptance.
Implemented typed tools, a JSON CLI/session, bounded observation caching,
semantic screen signatures, device leases, input restoration and cancellation.
Pinned the SDK adapter to prevent replay and preserve failed-click acknowledgements.
Owned UI service shutdown precedes releasing the lease to prevent process handoff races.

## Verification

See [verification.md](../verification.md). 29 offline tests passed; real MCP and
IME workflows passed before the final SDK acknowledgement fix. The latest
device run was interrupted by a physical USB disconnection; final acceptance
and screen-setting restoration await reconnection. Ruff and package builds pass.
Windows, Linux and macOS GitHub CI passed for pushed commit `bc457f3`.

## Blocker and resumption

ADB reports no device after USB disappeared during the final acceptance run.
Reconnect the phone and confirm its original automatic rotation setting, restore
`user_rotation=0` and the confirmed setting, then run all 31 tests with
`--device-serial auto`. After passing, uninstall only the task-created fixture,
record final evidence and close this Issue. Implementation and Git delivery are complete.

## Activity log

### 2026-10-09 — Created

Issue created from the supplied project input.

### 2026-10-09 — Status changed from proposed to ready.

### 2026-10-09 — Status changed from ready to in-progress.

### 2026-10-09 — Root commit reviewed; directional-coordinate validation fixed

Reviewed root commit `0f40792a462018d84352b448aaf77a7391d494aa`.
One P2 finding: directional swipes ignored screenshot coordinate space.
A failing regression test demonstrated the defect; native-space validation fixes it.
No P0/P1 findings. Final device acceptance remains pending reconnection.

### 2026-10-09 — Status changed from in-progress to blocked.

## Completion summary

Final USB device acceptance cannot finish because the phone disappeared from ADB; reconnection and the original automatic rotation setting are required for restoration and retesting.
