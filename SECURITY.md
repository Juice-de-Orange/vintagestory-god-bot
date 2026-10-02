# Security Policy

This project is **unmaintained**. Reports are still read, but there is no
promise of a fix; a public advisory and a suggested patch are the likely outcome.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report privately
through GitHub's private vulnerability reporting on this repository:
**Security → Report a vulnerability**. You will receive an acknowledgement within
**14 days**.

## Scope

In scope: ways for a player to make the bot run something on the server that the
configured `GODBOT_ALLOWED_ACTIONS`, the rank gates or the rate limits should
prevent; RCON command or chat-markup injection; leaks of the RCON password or API
key into logs.

Not a vulnerability by itself: the model saying something rude, or using an
action you enabled in a way you did not like. That is configuration — see the
README section "Safety".
