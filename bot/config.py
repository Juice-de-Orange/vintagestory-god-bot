"""Configuration for the god bot. Everything comes from the environment (see .env.example)."""
import os
from pathlib import Path



class ConfigError(ValueError):
    """A setting the bot cannot start with. main() prints it in one line and exits."""


# Exit status for a ConfigError (EX_CONFIG from sysexits.h).
EXIT_CONFIG = 78

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

# RCON (needs the VintageRCon server mod)
RCON_HOST     = os.getenv("RCON_HOST", "localhost")
RCON_PORT     = int(os.getenv("RCON_PORT", "42425"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "")

# LLM behind an OpenAI-compatible API (llama.cpp, Ollama, LM Studio, vLLM, ...)
LOCAL_API_BASE_URL = os.getenv("LOCAL_API_BASE_URL", "http://localhost:8080/api/v1")
# May be empty for servers that need no key: no Authorization header is sent then.
LOCAL_API_KEY      = os.getenv("LOCAL_API_KEY", "")
LOCAL_MODEL        = os.getenv("LOCAL_MODEL", "gemma4:e4b")

# Server log files the bot tails for chat, joins and leaves
CHAT_LOG_PATH = os.getenv("CHAT_LOG_PATH", "/logs/server-chat.log")
MAIN_LOG_PATH = os.getenv("MAIN_LOG_PATH", "/logs/server-main.log")

# Language of everything the deity says: "de" (the original voice) or "en"
LANGUAGE = os.getenv("GODBOT_LANGUAGE", "de").lower()

# The deity's name, and the words that count as addressing it
DEITY_NAME   = os.getenv("GODBOT_DEITY_NAME", "Arathos")
GOD_KEYWORDS = [k.strip().lower() for k in
                os.getenv("GOD_KEYWORDS", "gott,god,herr,deity,arathos").split(",") if k.strip()]

# Response probabilities
PROB_RESPOND_ADDRESSED = float(os.getenv("PROB_RESPOND_ADDRESSED", "0.95"))
PROB_RESPOND_PASSIVE   = float(os.getenv("PROB_RESPOND_PASSIVE",   "0.10"))

# Spontaneous messages
MIN_SPONTANEOUS_DAYS = float(os.getenv("MIN_SPONTANEOUS_DAYS", "1"))
MAX_SPONTANEOUS_DAYS = float(os.getenv("MAX_SPONTANEOUS_DAYS", "7"))

# Divine rank thresholds (relationship -100..100): the good ranks start at or above their
# value, the bad ones at or below. In between (new players start at 0) the rank is UNNOTICED.
RANK_HATED    = int(os.getenv("RANK_HATED",    "-80"))
RANK_FORSAKEN = int(os.getenv("RANK_FORSAKEN", "-60"))
RANK_CURSED   = int(os.getenv("RANK_CURSED",   "-25"))
RANK_NEUTRAL  = int(os.getenv("RANK_NEUTRAL",   "15"))
RANK_FAVORED  = int(os.getenv("RANK_FAVORED",   "40"))
RANK_CHOSEN   = int(os.getenv("RANK_CHOSEN",    "70"))

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
ACTIONS_PER_PLAYER = int(os.getenv("GODBOT_ACTIONS_PER_PLAYER", "3"))
ACTIONS_TOTAL      = int(os.getenv("GODBOT_ACTIONS_TOTAL", "20"))
ACTION_WINDOW_MIN  = float(os.getenv("GODBOT_ACTION_WINDOW_MIN", "10"))

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
