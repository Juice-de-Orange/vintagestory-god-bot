"""Configuration for the god bot. Everything comes from the environment (see .env.example)."""
import difflib
import os
from pathlib import Path



class ConfigError(ValueError):
    """A setting the bot cannot start with. main() prints it in one line and exits."""


# Exit status for a ConfigError (EX_CONFIG from sysexits.h).
EXIT_CONFIG = 78

# Settings that could not be read. Collected instead of raised: this module is read at import
# time, and main() reports each one in a single line before it starts anything.
ERRORS: list[str] = []


def _number(name: str, default: str, kind=int, low=None, high=None):
    raw = os.getenv(name, default)
    try:
        value = kind(raw.strip())
        if value != value:  # NaN
            raise ValueError
    except ValueError:
        ERRORS.append(f"{name}={raw[:40]!r} is not a {'whole number' if kind is int else 'number'}")
        return kind(default)
    if (low is not None and value < low) or (high is not None and value > high):
        ERRORS.append(f"{name}={value} is out of range ({low}..{high})")
        return kind(default)
    return value


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

# RCON (needs the VintageRCon server mod)
RCON_HOST     = os.getenv("RCON_HOST", "localhost")
RCON_PORT     = _number("RCON_PORT", "42425", int, 1, 65535)
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "")

# LLM behind an OpenAI-compatible API (llama.cpp, Ollama, LM Studio, vLLM, ...)
LOCAL_API_BASE_URL = os.getenv("LOCAL_API_BASE_URL", "http://localhost:8080/api/v1")
# May be empty for servers that need no key: no Authorization header is sent then.
LOCAL_API_KEY      = os.getenv("LOCAL_API_KEY", "")
LOCAL_MODEL        = os.getenv("LOCAL_MODEL", "gemma4:e4b")

# Server log files the bot tails for chat, joins and leaves
CHAT_LOG_PATH = os.getenv("CHAT_LOG_PATH", "/logs/server-chat.log")
MAIN_LOG_PATH = os.getenv("MAIN_LOG_PATH", "/logs/server-main.log")

# Language of everything the deity says: "en" (the default) or "de" (the original voice)
LANGUAGE = os.getenv("GODBOT_LANGUAGE", "en").lower()

# The deity's name, and the words that count as addressing it
DEITY_NAME   = os.getenv("GODBOT_DEITY_NAME", "Arathos")
GOD_KEYWORDS = [k.strip().lower() for k in
                os.getenv("GOD_KEYWORDS", "gott,god,herr,deity,arathos").split(",") if k.strip()]

# Response probabilities
PROB_RESPOND_ADDRESSED = _number("PROB_RESPOND_ADDRESSED", "0.95", float)
PROB_RESPOND_PASSIVE   = _number("PROB_RESPOND_PASSIVE",   "0.10", float)

# Spontaneous messages
MIN_SPONTANEOUS_DAYS = _number("MIN_SPONTANEOUS_DAYS", "1", float)
MAX_SPONTANEOUS_DAYS = _number("MAX_SPONTANEOUS_DAYS", "7", float)

# Divine rank thresholds (relationship -100..100): the good ranks start at or above their
# value, the bad ones at or below. In between (new players start at 0) the rank is UNNOTICED.
RANK_HATED    = _number("RANK_HATED",    "-80")
RANK_FORSAKEN = _number("RANK_FORSAKEN", "-60")
RANK_CURSED   = _number("RANK_CURSED",   "-25")
RANK_NEUTRAL  = _number("RANK_NEUTRAL",   "15")
RANK_FAVORED  = _number("RANK_FAVORED",   "40")
RANK_CHOSEN   = _number("RANK_CHOSEN",    "70")

# ── What the language model may do on the server ─────────────────────────────
# The model decides from player chat, so a player can try to talk it into
# anything. Only the actions listed here ever reach RCON; everything else is
# refused and written to the audit log. The default set cannot hurt a player.
# Opt-in extras: smite, kill, clearinv, teleport, freeze, kick, gamemode,
# spawn_hostile, tempstorm, month.
SAFE_ACTIONS = "give,giveblock,heal,intoxicate,spawn,weather,time,whisper"
ALLOWED_ACTIONS = {a.strip() for a in
                   os.getenv("GODBOT_ALLOWED_ACTIONS", SAFE_ACTIONS).split(",") if a.strip()}

# At most this many actions per player, and in total, per window.
ACTIONS_PER_PLAYER = _number("GODBOT_ACTIONS_PER_PLAYER", "3")
ACTIONS_TOTAL      = _number("GODBOT_ACTIONS_TOTAL", "20")
ACTION_WINDOW_MIN  = _number("GODBOT_ACTION_WINDOW_MIN", "10", float)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Every GODBOT_ setting read above. Any other GODBOT_ variable is a typo or a leftover; it would
# be ignored without a word, so main() warns about it (see unknown_settings).
SETTINGS = (
    "GODBOT_LANGUAGE", "GODBOT_DEITY_NAME", "GODBOT_ALLOWED_ACTIONS",
    "GODBOT_ACTIONS_PER_PLAYER", "GODBOT_ACTIONS_TOTAL", "GODBOT_ACTION_WINDOW_MIN",
)


def unknown_settings(environ=os.environ) -> list[str]:
    """One warning per GODBOT_ variable the bot does not read, with the closest known name.
    Only names: the value of an unknown variable might be a secret."""
    warnings = []
    for name in sorted(environ):
        if not name.upper().startswith("GODBOT_") or name in SETTINGS:
            continue
        # Compare without the shared prefix, or every name would look close to every other.
        close = difflib.get_close_matches(name.upper()[7:], [s[7:] for s in SETTINGS], n=1)
        hint = f" -- did you mean GODBOT_{close[0]}?" if close else ""
        warnings.append(f"unknown setting {name} is ignored{hint}")
    return warnings
