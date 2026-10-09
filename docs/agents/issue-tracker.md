# Local issue workflow

Requirements and acceptance evidence live in `docs/issues/`. Use the
`manage-issues` skill's `scripts/issues.py` to create, transition and reindex issues.

Allowed transitions: proposed → ready → in-progress → done; in-progress → blocked;
blocked → ready or in-progress. Any nonterminal state can be cancelled.
Completion requires checked acceptance criteria, verification evidence and a
completion summary. Terminal transitions update `docs/changelog/`.

Run `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .` before
completion. Real-device verification is opt-in and uses only the isolated fixture
application; never commit device identifiers, personal screen contents or APK keys.
