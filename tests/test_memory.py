"""Player memory on a real SQLite file."""
import pytest

from bot.player_memory import PlayerMemory, get_divine_rank


@pytest.fixture()
def memory(tmp_path):
    return PlayerMemory(tmp_path / "players.db")


def test_rank_ladder():
    assert [get_divine_rank(v) for v in (90, 50, 20, 0, -40, -90)] == [
        "CHOSEN", "FAVORED", "NOTICED", "CURSED", "FORSAKEN", "HATED"]


def test_relationship_changes_report_rank_transitions(memory):
    memory.get_or_create_player("Alice")
    assert memory.update_relationship("Alice", 20) == ("CURSED", "NOTICED")
    assert memory.update_relationship("Alice", 500)[1] == "CHOSEN"
    assert memory.get_or_create_player("Alice")["relationship"] == 100, "clamped to 100"


def test_old_rank_ignores_stale_stored_names(memory):
    """Databases from an older version store German rank names in the column."""
    memory.get_or_create_player("Alice")
    with memory._get_connection() as conn:
        conn.execute("UPDATE players SET relationship=50, divine_rank='BEGÜNSTIGT' WHERE name='Alice'")
    assert memory.update_relationship("Alice", 1) == ("FAVORED", "FAVORED")


def test_sessions_and_absence(memory):
    memory.get_or_create_player("Bob")
    memory.record_join("Bob")
    memory.record_leave("Bob")
    with memory._get_connection() as conn:
        rows = conn.execute("SELECT joined_at, left_at FROM player_sessions").fetchall()
        conn.execute("UPDATE players SET last_seen='2020-01-01T00:00:00' WHERE name='Bob'")
    assert len(rows) == 1 and rows[0][1] is not None
    assert memory.days_since_last_seen("Bob") > 1000


def test_notes_and_effects(memory):
    memory.add_note("Carol", "built a temple")
    assert memory.get_notes("Carol")[0]["note"] == "built a temple"
    memory.add_curse_or_blessing("Carol", "curse", "frozen", expires_days=1)
    memory.add_curse_or_blessing("Carol", "curse", "long gone", expires_days=-1)
    assert memory.get_active_effects("Carol") == [{"type": "curse", "effect": "frozen"}]
