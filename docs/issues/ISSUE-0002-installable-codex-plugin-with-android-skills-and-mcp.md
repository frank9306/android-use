---
id: ISSUE-0002
title: "Installable Codex plugin with Android skills and MCP"
status: blocked
priority: P1
created: 2026-10-09
updated: 2026-10-09
closed:
sources: ["https://developers.openai.com/plugins/build/plugins"]
related_adrs: []
depends_on: []
---

# ISSUE-0002: Installable Codex plugin with Android skills and MCP

## Problem

Android Use currently requires manual MCP registration and has no installable plugin bundle.

## Desired outcome

Provide a repository marketplace and Codex plugin bundling setup/control skills and the existing USB MCP server; verify native plugin installation and MCP startup from its installed copy.

## Acceptance criteria

- [x] A Codex plugin manifest declares packaged Android setup/control skills and MCP.
- [x] A repository marketplace supports native Codex plugin installation.
- [x] The declared MCP launcher works from its installed copy with no checkout-specific paths.
- [ ] Native Codex discovers both skills and all 11 MCP tools; the installed launcher passes the isolated real-device workflow.
- [x] Installation instructions include a shareable one-sentence prompt and direct install commands.
- [x] Validation, review and verification evidence are committed and pushed.

## Out of scope

Public-directory submission, cloud device hosting, runtime API changes and embedded streaming.

## Decisions

Bundle the existing Python runtime at the plugin root, use a supported Codex
compatibility manifest and repository marketplace, and keep local USB execution.
Setup runs through a packaged onboarding skill without lifecycle hooks.

## Implementation notes

Added a root Codex manifest, repository marketplace, bundled MCP launch configuration
and setup/control skills. The native validation helper installs into a disposable
Codex home and inspects actual app-server skill/MCP discovery. Native plugin loading
requires the MCP working directory to resolve to the installed root; this is checked.
The real-device suite can select the installed plugin launcher without changing
runtime control APIs. Existing CLI and independent MCP use remain supported.

## Verification

Both skills validate. Independent-directory MCP startup and native Codex install,
skill discovery and all 11 tools pass. Full installed-plugin run: 30 passed,
2 failed because the connected phone is locked/asleep; unlock requested.
See docs/verification.md. Runtime implementation remains unchanged.
After review fixes, 30 offline tests pass and both Ruff checks pass. Review of
`89b274c..57dd7ed` found and fixed explicit device selection and bounded request
waiting in validation helpers. The phone subsequently disconnected; real-device
reverification needs a connected, unlocked phone.
Remote Git marketplace installation, both skills and all 11 MCP tools pass.
Windows, Linux and macOS CI pass for `50fb2f3`; see the linked run in
docs/verification.md. Fix review of `57dd7ed..50fb2f3` found no new issues.

## Activity log

### 2026-10-09 — Created

Issue created from the supplied project input.

### 2026-10-09 — Status changed from proposed to ready.

### 2026-10-09 — Status changed from ready to in-progress.

### 2026-10-09 — Status changed from in-progress to blocked.

## Completion summary

Plugin packaging and remote native installation are delivered. The remaining installed-plugin real-device workflow is blocked because the phone disconnected after a locked-screen run. Reconnect and unlock the phone to rerun the 32-test suite, confirm restored settings and uninstall the task fixture.
