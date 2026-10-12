# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- A `GODBOT_…` variable the bot does not know (a typo such as `GODBOT_LANGAUGE`)
  gives a `[CONFIG WARNING]` line at start with the closest known name, instead of
  being ignored without a word. Only the name is printed, never the value.
- README sections "Backup" (a consistent copy of `players.db` with SQLite's online
  backup, safe while the bot runs, plus the audit log), "Restore", "Updating" (from
  v0.1.0, data kept) and "Known limitations".

### Changed

- The deity speaks **English by default** (`GODBOT_LANGUAGE` defaults to `en`, and
  so does `.env.example`); an unknown language falls back to English. German is
  still there: an existing install whose `.env` has no `GODBOT_LANGUAGE` line and
  should keep the German voice sets `GODBOT_LANGUAGE=de` before updating (the
  v0.1.0 `.env.example` already set it explicitly).

### Fixed

- The relationship change the model attaches to its reply was booked even when the
  reply or its actions never reached the server (RCON down): players gained or lost
  standing for something they never saw. It is now only booked when everything the
  deity said and did was delivered; a refused action does not hold it back.
- A number setting that is not a number (`RCON_PORT=abc`, `GODBOT_ACTIONS_TOTAL=ten`, …)
  or a port outside 1–65535 ended in a traceback (or, for the port, in endless failed
  connects). Now one `[CONFIG]` line per bad variable, naming it, and exit status 78.

## [0.1.0] - 2026-10-06

### Added

- First public release of the bot as last used in April 2026: chat observer and
  responder, relationship ranks, player memory, RCON actions, time-of-day and
  season events.
- `ActionPolicy`: allowlist (safe default), speaker-only targets, fixed
  item/block/creature lists, clamped values, rank gates, rate limits, audit log.
- English voice (`GODBOT_LANGUAGE=en`) next to the original German one.
- Unit tests, CI, Docker image that builds from a fresh clone.

### Changed

- New rank UNNOTICED for players between the thresholds (-24 … 14 by default),
  where every new player starts; the prompt used to call them CURSED while the
  database said NOTICED. The bad ranks now start *at or below* their threshold,
  as the German prompt always described: CURSED ≤ -25, FORSAKEN ≤ -60, HATED ≤ -80
  (new `RANK_HATED`). Before, -25 … 14 was CURSED, -60 … -26 FORSAKEN, below HATED.
- The audit log has a `delivered` field. An allowed action that did not reach the
  server is no longer booked (no gift row, no effect, no relationship change); it
  still uses its rate-limit slot.
- `LOCAL_API_KEY` may be empty (servers without a key).

### Fixed

- RCON login: a server that answers with two packets (empty response, then the
  auth response — the Source convention) shifted every later reply by one command
  and hid a wrong password. The client now reads up to the auth response and
  matches every reply to its request id.
- Log rotation lost lines when the new file had already grown past the old read
  offset; rotation is now detected by inode.
- An unknown action in `GODBOT_ALLOWED_ACTIONS` ended in a traceback; now one
  `[CONFIG]` line and exit status 78.
- The welcome-back line after a long absence never fired: the absence was
  measured after the join had already been recorded.
- The model call no longer blocks the event loop; log tailing and state polling
  stalled while the model was thinking.
- `docker build` failed on a fresh clone (`COPY data/`).
