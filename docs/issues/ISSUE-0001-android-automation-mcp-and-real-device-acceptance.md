---
id: ISSUE-0001
title: "Android automation MCP and real-device acceptance"
status: done
priority: P1
created: 2026-10-09
updated: 2026-10-09
closed: 2026-10-09
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
- [x] Unit and MCP protocol tests pass; an isolated real-device workflow passes.
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

uv run --frozen pytest --device-serial auto -q: 31 passed in 27.51s; 30 real MCP calls across all 11 tools; Chinese IME defaults/enabled state restored; rotation values read back as 0/0; fixture uninstall Success; Ruff, build and three-platform GitHub CI passed. See docs/verification.md.

## Resolved blocker

USB disappeared during an earlier acceptance run. On 2026-10-09 the user
reconnected the phone and confirmed automatic rotation was originally off.
Restored `user_rotation=0` and `accelerometer_rotation=0`, then passed all 31 tests.
Local ignored fixture build/diagnostic artifacts remain because automatic approval
rejected cleanup; no APK, signing key or device identifier was committed.

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

### 2026-10-09 — Status changed from blocked to in-progress.

### 2026-10-09 — Status changed from in-progress to done.

## Completion summary

Delivered the 11-tool Android MCP server, JSON CLI/session and reproducible package; all 31 tests passed on the connected Android 15 device, settings restored and temporary fixture uninstalled; implementation committed and pushed.
