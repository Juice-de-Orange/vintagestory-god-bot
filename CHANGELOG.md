# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
