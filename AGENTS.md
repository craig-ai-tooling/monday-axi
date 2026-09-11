# AGENTS.md

Primary context file for **every** AI agent working in this repo (Claude Code, Copilot,
Cursor, Codex, or a human). Read this first.

---

## Why

Agent-ergonomic CLI over a monday.com board: the Spectro Cloud SA Weekly Activity Board.
A Claude skill scrapes SA calendars into board items; this tool fixes the event status and
activity dropdown from the outside, because the board's real picklist values appear nowhere
except the API. Sibling to launchpad-axi and palette-axi.

---

## What — project map

| Path | What lives here |
|---|---|
| `monday_axi/` | Application code — `cli.py` holds every verb, `__init__.py` holds `__version__` |
| `tests/` | Offline unit tests (network layer monkeypatched) |
| `scripts/install.sh` | curl-the-release-asset installer |
| `.github/workflows/` | CI (compile/lint/test/smoke) + release (tag -> zipapp) |

---

## How — the only commands that matter

Keep this table honest. A stale command here costs more than a missing one.

| Task | Command |
|---|---|
| Install (dev) | `python -m pip install -e ".[dev]"` |
| Build zipapp | `make build` → `dist/monday-axi.pyz` |
| Test | `make test` (`python -m unittest discover -s tests`) |
| Lint | `make lint` (`ruff check .`) |
| Check connectors | `./dist/monday-axi.pyz doctor` (or `monday-axi doctor` once installed) |

**Definition of done** — a change is not done until build, test, and lint all pass, and
`doctor` still runs (it may legitimately report a connector `down` on a runner with no
credentials — it must never crash).

---

## Conventions

One example each. Match the surrounding code over the example if they conflict.

**Naming** — modules and functions `snake_case`; each CLI subcommand has a handler named
`cmd_<verb>`, dispatched from a single `table` dict in `main()`.
```
def cmd_put(a) -> int:   # one handler per subcommand
```

**Errors** — never swallow. `die(msg, code)` prints to stderr and exits with one of the
structured exit codes (`E_OK/E_ERR/E_USAGE/E_NOTFOUND/E_REFUSED`, see README). The one
exception is `doctor`: probes must never call `die()` or raise — a broken connector is
data to report, not a reason to crash.

**Output** — TOON, via the shared `toon()`/`cell()` helpers: `name[N]{field,...}:` header,
one row per line, `(none)` for empty. Every new verb that lists rows uses it rather than
inventing another table format.

**Tests** — offline; the network layer (`gql`/`token`/`schema`) is monkeypatched. A PR that
changes batch, dupes, or doctor logic adds or updates a `tests/` case.

**Comments** — explain *why*, never *what*. If the code needs a "what" comment, rewrite
the code.

---

## Hard rules

- **Never commit secrets.** No API tokens, no `.env` files, no 1Password item contents.
- **Never push to `main`.** Branch, PR, review — checks passing is the merge gate.
- **`__version__` in `monday_axi/__init__.py` is the single place a release bumps.**
- **Writes stay deliberate.** `put`/`create`/`apply` validate every value against the
  board's live picklist before sending anything; `delete` demands `--yes`.
- **`doctor` must never crash.** It is the tool a broken environment reaches for first;
  catch every probe's exceptions and render them as a `down`/`absent` row instead.
- **Prefer editing over creating.** A new file needs a reason.
