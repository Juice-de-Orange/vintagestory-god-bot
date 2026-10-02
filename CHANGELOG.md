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

### Fixed

- The welcome-back line after a long absence never fired: the absence was
  measured after the join had already been recorded.
- The model call no longer blocks the event loop; log tailing and state polling
  stalled while the model was thinking.
- `docker build` failed on a fresh clone (`COPY data/`).
