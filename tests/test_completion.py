"""Advanced completion ranking tests."""

from __future__ import annotations

from ssh_it.completion import CompletionEngine
from ssh_it.library import CommandLibrary


def test_completion_respects_vendor_and_prefix() -> None:
    """Vendor match and command prefix lift expected command to top."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    results = engine.suggest("show interfaces sta", vendor="Cisco IOS / IOS XE")
    assert results
    assert results[0].command_id == "cisco.interface.status"


def test_history_is_memory_only_newest_first_and_unique() -> None:
    """Session history deduplicates and outranks library on matching input."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    engine.remember("custom diagnostic one")
    engine.remember("custom diagnostic two")
    engine.remember("custom diagnostic one")
    assert engine.history == ("custom diagnostic one", "custom diagnostic two")
    result = engine.suggest("custom diagnostic")
    assert result[0].source == "history"


def test_blank_completion_returns_bounded_candidates() -> None:
    """Completion respects requested result limit."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    assert len(engine.suggest("", limit=5)) == 5


def test_intellisense_predicts_next_keywords_and_flags() -> None:
    """Token grammar offers next word/flag instead of only whole command strings."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    cisco = engine.suggest("show interfaces ", vendor="Cisco IOS / IOS XE")
    assert any(item.source == "keyword" and item.text == "status" for item in cisco)
    ssh = engine.suggest("ssh ", vendor="SSH / OpenSSH", limit=30)
    assert any(
        item.source == "flag" and item.text in {"-G", "-J", "-N", "-i", "-p"} for item in ssh
    )


def test_parameter_values_rank_connection_history_and_defaults() -> None:
    """Value dropdown merges current endpoint, captured history, and typed defaults."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    engine.remember("ping -c 7 router.history.example")
    hosts = engine.suggest_parameter("host", profile_host="router.current.example")
    counts = engine.suggest_parameter("count")
    assert hosts[0].text == "router.current.example"
    assert any(item.text == "router.history.example" for item in hosts)
    assert any(item.text == "7" and "history" in item.title.casefold() for item in counts)
    assert any(item.text == "10" for item in counts)


def test_favorite_command_boosts_prediction() -> None:
    """Favorites affect ranking without excluding other matching library commands."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    results = engine.suggest(
        "show ",
        vendor="Cisco IOS / IOS XE",
        favorite_ids={"cisco.route.table"},
        limit=30,
    )
    favorite_scores = [item.score for item in results if item.command_id == "cisco.route.table"]
    assert favorite_scores
    assert max(favorite_scores) >= 700


def test_embedded_placeholders_match_validate_and_enter_context_history() -> None:
    """User-at-host and forwarding tokens expose each typed value independently."""
    engine = CompletionEngine(CommandLibrary.load_bundled())
    matched = engine.match_template("ssh -p 2222 operator@router.example.test")
    assert matched is not None
    assert matched[0].id == "ssh.connect.basic"
    assert matched[1] == {
        "port": "2222",
        "user": "operator",
        "host": "router.example.test",
    }
    engine.remember("ssh -p 2222 operator@router.example.test")
    assert any(item.text == "operator" for item in engine.suggest_parameter("user"))
    assert any(item.text == "router.example.test" for item in engine.suggest_parameter("host"))
