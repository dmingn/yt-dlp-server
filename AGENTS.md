# Tests

Structure every test with `# Arrange` / `# Act` / `# Assert`.

Prefer `pytest.mark.parametrize` over copy-pasted cases.
Use `pytest.param(..., id="...")`.

For subprocesses / I/O, use a small fake (`_FakeProc`) or `monkeypatch.setattr` on the call site.
Do not use `unittest.mock`; tests should assert observable state, not mock call counts.

Async: wait on `asyncio.Event` (or another explicit signal) after `spawn`.
Do not `asyncio.sleep` to “let the task start”.
