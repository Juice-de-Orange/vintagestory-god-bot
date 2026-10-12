"""Start-up checks of the configuration: run the real entry point in a subprocess, since the
settings are read at import time."""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def start(tmp_path, **settings):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GODBOT_")}
    env.update(DATA_DIR=str(tmp_path), LOCAL_API_KEY="", **settings)
    return subprocess.run([sys.executable, "-m", "bot.main"], env=env, capture_output=True,
                          text=True, timeout=60, cwd=REPO)


@pytest.mark.parametrize("name, value", [
    ("RCON_PORT", "abc"),
    ("RCON_PORT", "70000"),
    ("GODBOT_ACTIONS_TOTAL", "ten"),
    ("PROB_RESPOND_PASSIVE", "often"),
    ("RANK_CHOSEN", "7.5"),
])
def test_a_bad_number_is_one_line_naming_the_variable(tmp_path, name, value):
    run = start(tmp_path, **{name: value})
    assert run.returncode == 78
    assert "Traceback" not in run.stdout + run.stderr
    config_lines = [line for line in run.stdout.splitlines() if line.startswith("[CONFIG]")]
    assert len(config_lines) == 1 and config_lines[0].startswith(f"[CONFIG] {name}=")


def test_every_bad_number_is_reported_at_once(tmp_path):
    run = start(tmp_path, RCON_PORT="abc", GODBOT_ACTION_WINDOW_MIN="soon")
    assert run.returncode == 78
    assert [line.split("=")[0] for line in run.stdout.splitlines()
            if line.startswith("[CONFIG]")] == ["[CONFIG] RCON_PORT", "[CONFIG] GODBOT_ACTION_WINDOW_MIN"]


def test_a_misspelt_setting_warns_with_the_closest_name(tmp_path):
    # RCON_PORT=abc only makes the bot stop right after the checks.
    run = start(tmp_path, GODBOT_LANGAUGE="en", GODBOT_ACTION_PER_PLAYER="2",
                GODBOT_SOMETHING="x", RCON_PORT="abc")
    warnings = [line for line in run.stdout.splitlines() if line.startswith("[CONFIG WARNING]")]
    assert warnings == [
        "[CONFIG WARNING] unknown setting GODBOT_ACTION_PER_PLAYER is ignored"
        " -- did you mean GODBOT_ACTIONS_PER_PLAYER?",
        "[CONFIG WARNING] unknown setting GODBOT_LANGAUGE is ignored -- did you mean GODBOT_LANGUAGE?",
        "[CONFIG WARNING] unknown setting GODBOT_SOMETHING is ignored",
    ]
    assert "=x" not in run.stdout, "the value of an unknown variable is never printed"


def test_lower_case_names_are_caught_too():
    from bot.config import unknown_settings
    assert unknown_settings({"godbot_language": "en", "PATH": "/bin"}) == [
        "unknown setting godbot_language is ignored -- did you mean GODBOT_LANGUAGE?"]


def test_the_example_env_file_raises_no_warning():
    from bot.config import unknown_settings
    with open(os.path.join(REPO, ".env.example")) as f:
        names = {line.split("=", 1)[0] for line in f if "=" in line and not line.startswith("#")}
    assert any(n.startswith("GODBOT_") for n in names)
    assert unknown_settings(dict.fromkeys(names, "")) == []


def test_a_new_install_speaks_english(tmp_path):
    """No GODBOT_LANGUAGE set: English. German stays one setting away (GODBOT_LANGUAGE=de)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GODBOT_")}
    probe = ("from bot.config import LANGUAGE; from bot.texts import texts; "
             "print(LANGUAGE, texts(LANGUAGE)['none'], texts('xx')['none'], texts('de')['none'])")
    run = subprocess.run([sys.executable, "-c", probe], env=dict(env, DATA_DIR=str(tmp_path)),
                         capture_output=True, text=True, timeout=60, cwd=REPO)
    from bot.texts import TEXTS
    assert run.stdout.split() == ["en", TEXTS["en"]["none"], TEXTS["en"]["none"],
                                  TEXTS["de"]["none"]]
