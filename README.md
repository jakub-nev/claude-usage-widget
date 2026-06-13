# Claude Usage Widget

Always-on-top desktop widget showing how much of your Claude subscription
usage limit is consumed until the next reset (5-hour and weekly windows),
mirroring Claude Code's `/usage`.

## Run

Double-click `run.bat`, or:

    python widget.py

- **Drag** the widget to reposition (position is remembered).
- **Right-click** for the menu: switch between floating panel and thin bar,
  choose which window the bar shows, recalibrate the local fallback, or quit.
- **Esc** closes it.

A green dot = live numbers from Anthropic (exact, same as `/usage`).
Amber = local approximation from `~/.claude` logs (token unavailable).
Grey = stale (last fetch failed; showing last-known values).

## How it works

Primary source: the same authenticated endpoint `/usage` uses
(`/api/oauth/usage`), via your existing Claude Code OAuth token in
`~/.claude/.credentials.json` (refreshed automatically when expired).
If that's unavailable it falls back to summing tokens from your local session
logs against a calibrated budget (right-click → Recalibrate).

## Autostart on login (optional)

Press `Win+R`, type `shell:startup`, Enter. Create a shortcut to `run.bat`
in the folder that opens.

## Caveat

`/api/oauth/usage` is an internal Anthropic endpoint, not a public API. It
uses your own token for your own data, but a future Claude Code update could
change it; if that happens the widget falls back to the local approximation
until `sources/live.py` is updated.

## Tests

    python -m pytest -q
