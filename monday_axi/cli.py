#!/usr/bin/env python3
"""monday-axi — agent-ergonomic CLI over the monday.com SA Weekly Activity Board.

Built on AXI principles: token-efficient TOON output, minimal default schemas,
pre-computed aggregates, definitive empty states, structured exit codes,
content-first (no args = live data), next-step disclosure.

Writes are deliberate: `put` validates every value against the board's own
picklists and refuses anything else (exit 4), and `delete` demands --yes.
The board is team-visible and owned by JV — treat a write as outward-facing.

Env overrides: MONDAY_BOARD, MONDAY_TOKEN, MONDAY_OP_REF, MONDAY_SA

Run `monday-axi doctor` to check whether 1Password and the monday.com API
are reachable before doing anything else.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

BOARD = os.environ.get("MONDAY_BOARD", "18424958790")
OP_REF = os.environ.get("MONDAY_OP_REF", "op://Lobster/monday.com/API Key")
SA = os.environ.get("MONDAY_SA", "Craig Smith")
ENDPOINT = "https://api.monday.com/v2"
API_VERSION = "2024-10"

E_OK, E_ERR, E_USAGE, E_NOTFOUND, E_REFUSED = 0, 1, 2, 3, 4

# Column ids are resolved live from the board, so a board edit cannot rot them.
WANT = {"people": "people", "date": "date", "status": "status",
        "activity": "dropdown", "note": "long_text"}


# ── transport ──────────────────────────────────────────────────────────────
def die(msg: str, code: int) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def token() -> str:
    t = os.environ.get("MONDAY_TOKEN")
    if t:
        return t.strip()
    try:
        out = subprocess.run(["op", "read", OP_REF], capture_output=True,
                             text=True, timeout=30)
    except FileNotFoundError:
        die("1Password CLI `op` not on PATH and MONDAY_TOKEN unset", E_ERR)
    if out.returncode != 0 or not out.stdout.strip():
        die(f"could not read {OP_REF} from 1Password\n  {out.stderr.strip()[:200]}", E_ERR)
    return out.stdout.strip()


def gql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": token(), "Content-Type": "application/json",
                 "API-Version": API_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        die(f"monday API HTTP {e.code}: {e.read()[:300].decode('utf8', 'replace')}", E_ERR)
    except urllib.error.URLError as e:
        die(f"monday API unreachable: {e.reason}", E_ERR)
    if "errors" in payload:
        msg = "; ".join(str(x.get("message", x)) for x in payload["errors"])
        die(f"monday API error: {msg}", E_ERR)
    return payload["data"]


# ── schema ─────────────────────────────────────────────────────────────────
def labels_of(settings: str) -> list[str]:
    try:
        js = json.loads(settings)
    except ValueError:
        return []
    lab = js.get("labels")
    if isinstance(lab, dict):
        return [lab[k] for k in sorted(lab, key=lambda x: int(x)) if lab[k]]
    if isinstance(lab, list):
        return [x.get("name", "") for x in lab if x.get("name")]
    return []


def schema() -> dict:
    d = gql("{ boards(ids:[%s]) { id name items_count groups { id title } "
            "columns { id title type settings_str } } }" % BOARD)
    boards = d.get("boards") or []
    if not boards:
        die(f"board {BOARD} not found, or the token cannot see it", E_NOTFOUND)
    b = boards[0]
    cols, opts = {}, {}
    for c in b["columns"]:
        for key, typ in WANT.items():
            if c["type"] == typ and key not in cols:
                cols[key] = c["id"]
        if c["type"] in ("status", "dropdown"):
            opts[c["id"]] = labels_of(c.get("settings_str") or "")
    b["cols"], b["opts"] = cols, opts
    return b


def legal(b: dict, key: str) -> list[str]:
    return b["opts"].get(b["cols"].get(key, ""), []) or []


# ── items ──────────────────────────────────────────────────────────────────
def fetch_items(board: dict) -> list[dict]:
    items, cursor = [], None
    while True:
        if cursor:
            page = gql('{ next_items_page(limit:100, cursor:"%s") { cursor items '
                       '{ id name group { title } column_values { id text } } } }'
                       % cursor)["next_items_page"]
        else:
            page = gql("{ boards(ids:[%s]) { items_page(limit:100) { cursor items "
                       "{ id name group { title } column_values { id text } } } } }"
                       % BOARD)["boards"][0]["items_page"]
        items += page["items"]
        cursor = page.get("cursor")
        if not cursor:
            break
    c = board["cols"]
    for it in items:
        cv = {x["id"]: (x["text"] or "") for x in it["column_values"]}
        it["sa"] = cv.get(c.get("people", ""), "")
        it["date"] = cv.get(c.get("date", ""), "")
        it["status"] = cv.get(c.get("status", ""), "")
        it["activity"] = cv.get(c.get("activity", ""), "")
    items.sort(key=lambda i: (i["date"] or "9999", i["name"]))
    return items


def only_mine(items: list[dict]) -> list[dict]:
    return [i for i in items if SA.lower() in (i["sa"] or "").lower()]


# ── output ─────────────────────────────────────────────────────────────────
def cell(v: object) -> str:
    s = str(v or "").replace("\n", " ").strip() or "-"
    return f'"{s}"' if ("," in s or '"' in s) else s


def toon(name: str, rows: list[list], fields: list[str]) -> None:
    print(f"{name}[{len(rows)}]{{{','.join(fields)}}}:")
    if not rows:
        print("  (none)")
        return
    for r in rows:
        print("  " + ",".join(cell(x) for x in r))


def show_items(items: list[dict], label: str) -> None:
    toon(label, [[i["id"], i["date"] or "-", i["status"] or "-",
                  i["activity"] or "-", i["name"]] for i in items],
         ["id", "date", "status", "activity", "name"])


# ── commands ───────────────────────────────────────────────────────────────
def cmd_board(a) -> int:
    b = schema()
    print(f"board:{b['id']} name:{b['name']} items:{b['items_count']}")
    toon("groups", [[g["id"], g["title"]] for g in b["groups"]], ["id", "title"])
    print()
    print("columns:")
    for key in ("people", "date", "status", "activity", "note"):
        cid = b["cols"].get(key)
        if not cid:
            print(f"  {key:<9} (not on this board)")
            continue
        opts = b["opts"].get(cid) or []
        print(f"  {key:<9} {cid}" + (f"  options: {' | '.join(opts)}" if opts else ""))
    print()
    print("next: monday-axi mine | monday-axi put <id> --status <s> --activity <a>")
    return E_OK


def cmd_mine(a) -> int:
    b = schema()
    rows = only_mine(fetch_items(b))
    if getattr(a, "stale", False):
        rows = [i for i in rows if i["status"] in ("Backlog", "") or not i["activity"]]
    show_items(rows, "mine")
    if rows:
        by: dict[str, int] = {}
        for i in rows:
            k = i["status"] or "(blank)"
            by[k] = by.get(k, 0) + 1
        print()
        print("by_status: " + " ".join(f"{k}={v}" for k, v in sorted(by.items())))
        print("next: monday-axi put <id> --status Done --activity PoV")
    return E_OK


def cmd_items(a) -> int:
    b = schema()
    items = fetch_items(b)
    if a.sa:
        items = [i for i in items if a.sa.lower() in (i["sa"] or "").lower()]
    show_items(items, "items")
    return E_OK


# Words the v1 calendar scrape drags in that carry no identity. Without
# stripping these, "(Placeholder) SpectroCloud Leadership and TMNA meeting"
# and "SpectroCloud Leadership and TMNA Meeting" look like different items.
NOISE = {"placeholder", "hold", "fw", "re", "copy", "internal", "prep", "precall",
         "the", "and", "a", "an", "of", "with", "for", "x", "vs", "sync", "call",
         "meeting", "session", "sessions", "spectro", "spectrocloud", "cloud"}


def tokens_of(name: str) -> frozenset[str]:
    words = "".join(ch if ch.isalnum() else " " for ch in name.lower()).split()
    kept = {w for w in words if w not in NOISE and len(w) > 1}
    return frozenset(kept or words)   # never return empty: fall back to raw words


def near_duplicate(x: frozenset[str], y: frozenset[str]) -> bool:
    if not x or not y:
        return False
    if x == y:                        # identical once noise is stripped
        return True
    if x <= y or y <= x:              # one title is the other plus noise
        return min(len(x), len(y)) >= 2
    inter = len(x & y)
    return inter / len(x | y) >= 0.75


def cmd_dupes(a) -> int:
    b = schema()
    items = fetch_items(b)
    if not a.all:
        items = only_mine(items)
    for i in items:
        i["_tok"] = tokens_of(i["name"])

    # A scrape duplicate is the SAME meeting on the SAME day. Without the date
    # guard, a monthly series ("Teradata Monthly", 8/20 and 9/8) reads as a
    # duplicate of itself. --loose drops the guard for the rarer misdated pair.
    def same_event(x: dict, y: dict) -> bool:
        if not a.loose and x["date"] != y["date"]:
            return False
        return near_duplicate(x["_tok"], y["_tok"])

    clusters: list[list[dict]] = []
    for i in items:
        for c in clusters:
            if any(same_event(i, j) for j in c):
                c.append(i)
                break
        else:
            clusters.append([i])
    dupes = [c for c in clusters if len(c) > 1]
    dupes.sort(key=len, reverse=True)

    rows = []
    for c in dupes:
        for i in sorted(c, key=lambda x: x["date"] or "9999"):
            rows.append([i["id"], i["date"] or "-", i["status"] or "-", i["name"]])
    toon("dupes", rows, ["id", "date", "status", "name"])
    if dupes:
        print()
        print(f"groups:{len(dupes)} items:{len(rows)}")
        print("next: monday-axi delete <id> --yes   # keep the one with the right date")
    return E_OK


def build_values(b: dict, status: str, activity: str, date: str, note: str = "") -> dict:
    vals: dict[str, object] = {}
    if note:
        cid = b["cols"].get("note")
        if not cid:
            die("this board has no long-text column to write a note into", E_REFUSED)
        vals[cid] = {"text": note}
    if status:
        if status not in legal(b, "status"):
            die(f"status {status!r} is not on this board. legal: "
                f"{' | '.join(legal(b, 'status'))}", E_REFUSED)
        vals[b["cols"]["status"]] = {"label": status}
    if activity:
        if activity not in legal(b, "activity"):
            die(f"activity {activity!r} is not on this board. legal: "
                f"{' | '.join(legal(b, 'activity'))}", E_REFUSED)
        vals[b["cols"]["activity"]] = {"labels": [activity]}
    if date:
        vals[b["cols"]["date"]] = {"date": date}
    return vals


def write_values(item: str, vals: dict) -> None:
    gql("mutation($b:ID!,$i:ID!,$v:JSON!){ change_multiple_column_values"
        "(board_id:$b,item_id:$i,column_values:$v){ id } }",
        {"b": BOARD, "i": item, "v": json.dumps(vals)})


def cmd_put(a) -> int:
    b = schema()
    vals = build_values(b, a.status or "", a.activity or "", a.date or "", a.note or "")
    if not vals:
        die("nothing to write — pass --status, --activity and/or --date", E_USAGE)
    if a.dry_run:
        print(f"dry-run item:{a.item}")
        print("  " + json.dumps(vals))
        print("next: rerun without --dry-run to write")
        return E_OK
    write_values(a.item, vals)
    d = gql("{ items(ids:[%s]) { id name column_values { id text } } }" % a.item)
    if not d.get("items"):
        die(f"item {a.item} not found after write", E_NOTFOUND)
    it = d["items"][0]
    cv = {x["id"]: (x["text"] or "") for x in it["column_values"]}
    print(f"wrote item:{it['id']} status:{cv.get(b['cols']['status']) or '-'} "
          f"activity:{cv.get(b['cols']['activity']) or '-'}  {it['name']}")
    return E_OK


def cmd_create(a) -> int:
    """Add a meeting the scrape missed, assigned to the SA, in one call."""
    b = schema()
    vals = build_values(b, a.status or "", a.activity or "", a.date or "", a.note or "")
    if a.me:
        who = gql("{ me { id } }")["me"]["id"]
        vals[b["cols"]["people"]] = {"personsAndTeams":
                                     [{"id": int(who), "kind": "person"}]}
    group = a.group or (b["groups"][0]["id"] if b["groups"] else "topics")
    if a.dry_run:
        print(f"dry-run create group:{group} name:{a.name!r}")
        print("  " + json.dumps(vals))
        return E_OK
    d = gql("mutation($b:ID!,$g:String!,$n:String!,$v:JSON!){ create_item"
            "(board_id:$b,group_id:$g,item_name:$n,column_values:$v){ id name } }",
            {"b": BOARD, "g": group, "n": a.name, "v": json.dumps(vals)})
    it = d["create_item"]
    print(f"created item:{it['id']}  {it['name']}")
    return E_OK


def cmd_delete(a) -> int:
    if not a.yes:
        die("refusing to delete without --yes", E_REFUSED)
    d = gql("{ items(ids:[%s]) { id name } }" % a.item)
    if not d.get("items"):
        die(f"item {a.item} not found", E_NOTFOUND)
    name = d["items"][0]["name"]
    gql("mutation($i:ID!){ delete_item(item_id:$i){ id } }", {"i": a.item})
    print(f"deleted item:{a.item}  {name}")
    return E_OK


def cmd_apply(a) -> int:
    """Batch write. Each line: item_id <TAB> status <TAB> activity.

    Blank lines and everything after a # are ignored. Every value is validated
    against the board before a single write goes out, so a typo on line 9 stops
    lines 1-8 from landing.
    """
    b = schema()
    plan, bad = [], []
    try:
        fh = open(a.file)
    except OSError as e:
        die(f"cannot read {a.file}: {e}", E_NOTFOUND)
    with fh:
        for n, raw in enumerate(fh, 1):
            line = raw.split("#")[0].strip()
            if not line:
                continue
            # Keep empty fields: "id<TAB><TAB>PoV" means leave status alone and
            # set only the activity. Filtering blanks would slide the activity
            # into the status slot and fail validation with a baffling message.
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 2:
                bad.append(f"line {n}: need id<TAB>status[<TAB>activity]")
                continue
            iid, status = parts[0], parts[1]
            activity = parts[2] if len(parts) > 2 else ""
            if not iid:
                bad.append(f"line {n}: missing item id")
                continue
            if not status and not activity:
                bad.append(f"line {n}: nothing to write for item {iid}")
                continue
            if status and status not in legal(b, "status"):
                bad.append(f"line {n}: status {status!r} not legal")
            if activity and activity not in legal(b, "activity"):
                bad.append(f"line {n}: activity {activity!r} not legal")
            plan.append((iid, status, activity))
    if bad:
        for x in bad:
            print(f"error: {x}", file=sys.stderr)
        print(f"legal status:   {' | '.join(legal(b, 'status'))}", file=sys.stderr)
        print(f"legal activity: {' | '.join(legal(b, 'activity'))}", file=sys.stderr)
        return E_REFUSED
    if not plan:
        print("apply[0]: (nothing to do)")
        return E_OK
    for iid, status, activity in plan:
        vals = build_values(b, status, activity, "")
        if a.dry_run:
            print(f"dry-run item:{iid} " + json.dumps(vals))
            continue
        write_values(iid, vals)
        print(f"wrote item:{iid} status:{status or '-'} activity:{activity or '-'}")
    print()
    print(f"{'planned' if a.dry_run else 'applied'}:{len(plan)}")
    return E_OK


def cmd_whoami(a) -> int:
    d = gql("{ me { id name email is_admin } }")["me"]
    print(f"id:{d['id']} name:{d['name']} email:{d['email']} admin:{d['is_admin']}")
    print(f"board:{BOARD} sa_filter:{SA!r}")
    return E_OK


# ── doctor ─────────────────────────────────────────────────────────────────
# One table, in code, of every external connector this tool depends on. Each
# probe returns (need, status, detail) and must never raise — a probe that
# blows up is caught by cmd_doctor and rendered as a "down" row instead of a
# traceback, because reporting a broken connector is the whole point of
# running doctor in the first place.
#
#   need   : "required" or "optional" (may depend on the current env, e.g.
#            1Password is optional once MONDAY_TOKEN is set)
#   status : "ok", "down", "absent", or "skip"
#   detail : human text. Every down/absent/skip row names the exact command
#            or env var that fixes it.

def _probe_onepassword() -> tuple[str, str, str]:
    if os.environ.get("MONDAY_TOKEN", "").strip():
        return "optional", "skip", "MONDAY_TOKEN is set — 1Password is not used"
    if not shutil.which("op"):
        return "required", "absent", (
            "op CLI not found on PATH — install the 1Password CLI, "
            "or set MONDAY_TOKEN to bypass it")
    try:
        out = subprocess.run(["op", "read", OP_REF], capture_output=True,
                             text=True, timeout=30)
    except Exception as e:  # noqa: BLE001 — a probe must never raise
        return "required", "down", f"`op read {OP_REF}` failed to run: {e}"
    if out.returncode != 0 or not out.stdout.strip():
        return "required", "down", (
            f"`op read {OP_REF}` failed — run `op signin`, or fix MONDAY_OP_REF "
            f"(currently {OP_REF!r}): {out.stderr.strip()[:150]}")
    return "required", "ok", f"op on PATH — {OP_REF} readable"


def _probe_monday_api() -> tuple[str, str, str]:
    tok = os.environ.get("MONDAY_TOKEN", "").strip()
    if not tok:
        if not shutil.which("op"):
            return "required", "down", (
                "no token available — set MONDAY_TOKEN, or install the "
                "1Password CLI (see the onepassword row)")
        try:
            out = subprocess.run(["op", "read", OP_REF], capture_output=True,
                                 text=True, timeout=30)
        except Exception as e:  # noqa: BLE001
            return "required", "down", f"no token available — `op read {OP_REF}` failed: {e}"
        if out.returncode != 0 or not out.stdout.strip():
            return "required", "down", (
                "no token available — fix 1Password (see the onepassword row), "
                "or set MONDAY_TOKEN directly")
        tok = out.stdout.strip()
    body = json.dumps({"query": "{ me { name } }"}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": tok, "Content-Type": "application/json",
                 "API-Version": API_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf8", "replace")
        if e.code == 401:
            return "required", "down", (
                "401 from api.monday.com — token rejected; mint a new one at "
                "monday avatar -> Developers -> My access tokens, then set "
                "MONDAY_TOKEN or update the MONDAY_OP_REF item")
        return "required", "down", f"{e.code} from api.monday.com — {detail}"
    except urllib.error.URLError as e:
        return "required", "down", f"api.monday.com unreachable — {e.reason}; check network/DNS"
    except Exception as e:  # noqa: BLE001 — a probe must never raise
        return "required", "down", f"unexpected error probing monday-api: {e}"
    if "errors" in payload:
        msg = "; ".join(str(x.get("message", x)) for x in payload.get("errors", []))
        return "required", "down", f"monday API error: {msg}"
    name = (payload.get("data") or {}).get("me", {}).get("name", "?")
    return "required", "ok", f"authenticated as {name}"


CONNECTORS: list[tuple[str, object]] = [
    ("onepassword", _probe_onepassword),
    ("monday-api", _probe_monday_api),
]


def cmd_doctor(a) -> int:
    rows = []
    exit_code = E_OK
    for name, probe in CONNECTORS:
        try:
            need, status, detail = probe()
        except Exception as e:  # noqa: BLE001 — probing is the whole job
            need, status, detail = "required", "down", f"probe crashed: {e}"
        rows.append({"name": name, "need": need, "status": status, "detail": detail})
        if need == "required" and status != "ok":
            exit_code = E_ERR

    config = [
        {"var": "MONDAY_BOARD", "value": BOARD,
         "source": "env" if os.environ.get("MONDAY_BOARD") else "default"},
        {"var": "MONDAY_SA", "value": SA,
         "source": "env" if os.environ.get("MONDAY_SA") else "default"},
        {"var": "MONDAY_TOKEN", "value": "set" if os.environ.get("MONDAY_TOKEN") else "(unset)",
         "source": "env" if os.environ.get("MONDAY_TOKEN") else "-"},
        {"var": "MONDAY_OP_REF", "value": OP_REF,
         "source": "env" if os.environ.get("MONDAY_OP_REF") else "default"},
    ]

    if getattr(a, "json", False):
        print(json.dumps({"connectors": rows, "config": config}, indent=2))
    else:
        toon("connectors", [[r["name"], r["need"], r["status"], r["detail"]] for r in rows],
             ["name", "need", "status", "detail"])
        print()
        toon("config", [[r["var"], r["value"], r["source"]] for r in config],
             ["var", "value", "source"])
        print()
        if exit_code == E_OK:
            print("all required connectors ok")
        else:
            print("next: fix the detail column above on every down/absent row, then rerun")
    return exit_code


def main() -> None:
    p = argparse.ArgumentParser(
        prog="monday-axi",
        description="agent-ergonomic CLI over the monday.com SA Weekly Activity Board")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("board", help="board schema: groups, columns, legal picklist values")

    m = sub.add_parser("mine", help="items where Craig is the SA (default)")
    m.add_argument("--stale", action="store_true",
                   help="only items still Backlog or missing an activity")

    i = sub.add_parser("items", help="every item on the board")
    i.add_argument("--sa", help="filter to one SA by name")

    d = sub.add_parser("dupes", help="same meeting scraped onto the board twice")
    d.add_argument("--all", action="store_true", help="every SA, not just Craig")
    d.add_argument("--loose", action="store_true",
                   help="also match across different dates (noisier)")

    w = sub.add_parser("put", help="write status / activity / date on one item")
    w.add_argument("item")
    w.add_argument("--status")
    w.add_argument("--activity")
    w.add_argument("--date", help="YYYY-MM-DD")
    w.add_argument("--note", help="replace the Summarize-updates text")
    w.add_argument("--dry-run", action="store_true")

    n = sub.add_parser("create", help="add a meeting the scrape missed")
    n.add_argument("name")
    n.add_argument("--date", help="YYYY-MM-DD")
    n.add_argument("--status")
    n.add_argument("--activity")
    n.add_argument("--note", help="Summarize-updates text")
    n.add_argument("--group", help="group id (default: the board's first group)")
    n.add_argument("--me", action="store_true", default=True,
                   help="assign the SA column to the token's own user (default)")
    n.add_argument("--no-me", dest="me", action="store_false")
    n.add_argument("--dry-run", action="store_true")

    x = sub.add_parser("delete", help="delete one item (needs --yes)")
    x.add_argument("item")
    x.add_argument("--yes", action="store_true")

    b = sub.add_parser("apply", help="batch write from a TSV: id<TAB>status<TAB>activity")
    b.add_argument("file")
    b.add_argument("--dry-run", action="store_true")

    sub.add_parser("whoami", help="who the token authenticates as")

    doc = sub.add_parser("doctor", help="check 1Password + monday.com API connectivity")
    doc.add_argument("--json", action="store_true", help="emit JSON instead of TOON")

    ns = p.parse_args()
    table = {"board": cmd_board, "mine": cmd_mine, "items": cmd_items,
             "dupes": cmd_dupes, "put": cmd_put, "create": cmd_create,
             "delete": cmd_delete, "apply": cmd_apply, "whoami": cmd_whoami,
             "doctor": cmd_doctor}
    # main() calls sys.exit itself, rather than just returning a code, because
    # the zipapp -m entry point (`module.fn()`) discards main()'s return value
    # — only sys.exit inside main() reaches the process exit code from every
    # entry point (direct script, `python -m monday_axi`, console_script, and
    # the .pyz).
    try:
        sys.exit(table[ns.cmd or "mine"](ns))   # content-first: no args = live data
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
