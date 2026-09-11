# monday-axi

An agent-ergonomic CLI over a monday.com board. Built for the Spectro Cloud **SA Weekly
Activity Board**, where a Claude skill scrapes SA calendars into board items and each SA
then has to fix the event status and the activity dropdown by hand.

It exists because the board's real picklist values appear nowhere outside the API — not in
the notification emails, not in the board share links — so correcting items from the
outside was guesswork.

```
pip install nothing        # stdlib only, Python 3.10+
```

## Install

### Download the binary (recommended)

Pull the latest single-file build onto your `PATH` — just `curl`, `chmod`, `mv`. No `gh`,
no token, no dependencies:

```sh
curl -fsSL https://github.com/craig-ai-tooling/monday-axi/releases/latest/download/monday-axi.pyz -o monday-axi
chmod +x monday-axi
mv monday-axi ~/.local/bin/monday-axi        # or anywhere on your PATH
```

Or run the bundled installer (same three steps, honours `$BIN` for the target path):

```sh
curl -fsSL https://raw.githubusercontent.com/craig-ai-tooling/monday-axi/main/scripts/install.sh | bash
```

`monday-axi.pyz` is a zipapp — it needs a Python 3.10+ interpreter on the target (every lab
box has one), not a compiled binary.

### From a checkout

```bash
git clone git@github.com:craig-ai-tooling/monday-axi.git ~/code/monday-axi
python -m pip install -e ".[dev]"     # or: make build && make install
```

## Configure

A monday.com API token, read from 1Password by default:

```bash
op://Lobster/monday.com/API Key          # default, override with MONDAY_OP_REF
export MONDAY_TOKEN=...                  # or supply it directly
```

Mint one from your monday avatar → **Developers** → **My access tokens**. The token acts
as *you*: everything it writes is attributed to your user.

| variable | default | required |
|---|---|---|
| `MONDAY_BOARD` | `18424958790` | no |
| `MONDAY_SA` | `Craig Smith` | no |
| `MONDAY_TOKEN` | — | no — bypasses 1Password when set |
| `MONDAY_OP_REF` | `op://Lobster/monday.com/API Key` | only if `MONDAY_TOKEN` is unset |

`monday-axi doctor` tells you what is still missing.

## Commands

```
monday-axi board                    groups, columns, and the legal picklist values
monday-axi mine [--stale]           your items + a status histogram
monday-axi items [--sa NAME]        the whole board
monday-axi dupes [--all] [--loose]  the same meeting scraped on twice
monday-axi create "<name>" --date --status --activity --note
monday-axi put <id> --status --activity --date --note [--dry-run]
monday-axi delete <id> --yes
monday-axi apply <tsv> [--dry-run]  batch write, whole file validated first
monday-axi whoami
monday-axi doctor [--json]          check 1Password + monday.com API connectivity
```

No arguments is `mine`, so the bare command prints live data.

### The batch file

`apply` reads `item_id <TAB> status <TAB> activity`. Blank status leaves the column alone;
`#` comments and blank lines are ignored. The **entire file is validated before the first
write goes out**, so a typo on line 9 cannot leave lines 1–8 half-applied.

```
12970524528	Done	PoV		# status and activity
12969237488		Check-in	# activity only, leave status alone
```

### doctor

Checks every connector this tool depends on — 1Password and the monday.com API — and
prints a TOON table (or `--json`) naming the exact fix for anything that's down:

```
$ monday-axi doctor
connectors[2]{name,need,status,detail}:
  onepassword,required,ok,"op on PATH — op://Lobster/monday.com/API Key readable"
  monday-api,required,ok,"authenticated as Craig Smith"
config[4]{var,value,source}:
  MONDAY_BOARD,18424958790,default
  MONDAY_SA,Craig Smith,default
  MONDAY_TOKEN,(unset),-
  MONDAY_OP_REF,op://Lobster/monday.com/API Key,default
```

Exits `0` only when every required connector is `ok`; exits `1` if any required connector
is `down` or `absent`. 1Password drops to `optional`/`skip` once `MONDAY_TOKEN` is set.
`doctor` never crashes on a broken environment — that's the whole point of running it.

## What the SA Weekly Activity Board offers

```
status:   Working on it | Done | Stuck | Review | Backlog
activity: Workshop | Check-in | Product | Discovery | Enablement | Demo | PoV | RA | Partner
```

There is **no PoC** option. A POC engagement goes in as `PoV`.

## Notes on behaviour

**Writes are deliberate.** Every status and activity value is checked against the board's
own picklist before anything is sent; a miss exits `4` and prints the legal set. `delete`
demands `--yes`. `--dry-run` prints the exact column payload without sending it.

**Column ids are resolved live** from the board rather than hardcoded, so renaming a
column upstream cannot silently rot the tool.

**`dupes` requires a matching date as well as a near-identical name.** The scrape
duplicates a meeting onto the *same day*; a monthly series legitimately repeats the same
title on *different* days — without the date guard, Teradata's 8/20 and 9/8 occurrences
read as duplicates of each other. `--loose` drops the guard.

**The write subcommand is `put`, not `set`.** Some shell guard hooks match a bare `set`
loosely and block the whole command line.

## The failure mode worth knowing about

The calendar scrape **under-counts**, and that is the half of accuracy that costs an SE
credit rather than embarrassment. Over 9/3–9/11/26 it produced 14 items against 20 distinct
customer-facing meetings — a ~30% undercount. It reliably misses:

- a second distinct session with the same customer on the same day
- any meeting titled after people rather than the account
  (`Craig / Austin - Ad-hoc working session`, `Lunch Sync`)

It also over-counts in the other direction, scraping in internal prep calls that happen to
have a partner domain on the invite, and meetings you declined.

Reconcile `monday-axi mine` against your calendar weekly and `create` the gap. When
diffing, match a **recurring series by name on any date** and a **one-off on its own
date** — otherwise the diff reports phantom misses for every occurrence of a series the
board models as a single item.

## Exit codes

| | |
|---|---|
| `0` | ok |
| `1` | error (network, auth, API) |
| `2` | usage |
| `3` | not found |
| `4` | refused (illegal picklist value, missing `--yes`) |
