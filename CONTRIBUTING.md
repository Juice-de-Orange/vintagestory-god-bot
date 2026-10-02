# Contributing

This project is **unmaintained**, but contributions are welcome — especially a
report or fix from someone running it on a current Vintage Story version.

## Setup

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
pip install pre-commit && pre-commit install   # gitleaks on every commit
```

## Rules of the house

- **Every action goes through `bot/actions.py`.** A new action needs a validator
  there (fixed vocabulary, clamped numbers, cleaned text), an entry in both
  languages in `bot/texts.py`, and a test. It is opt-in unless it cannot hurt a
  player.
- Player-facing text lives in `bot/texts.py`, in German and English.
- Never put real RCON passwords, API keys, IPs or player names into code, tests or
  screenshots.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) and
  are signed off (`git commit -s`, [DCO](https://developercertificate.org/)).

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
