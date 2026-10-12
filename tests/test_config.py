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
