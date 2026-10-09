---
id: ISSUE-0002
title: "Installable Codex plugin with Android skills and MCP"
status: in-progress
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
- [ ] Validation, review and verification evidence are committed and pushed.

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

## Activity log

### 2026-10-09 — Created

Issue created from the supplied project input.

### 2026-10-09 — Status changed from proposed to ready.

### 2026-10-09 — Status changed from ready to in-progress.

## Completion summary

Not completed.
