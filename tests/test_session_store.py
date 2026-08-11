"""Tests for session_store — runs fully local via SESSION_STORE_LOCAL_DIR override."""

import pytest

from agent.tools.session_store import get_session, save_pending_proposal, update_status


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_STORE_LOCAL_DIR", str(tmp_path / "sessions"))
    yield


def test_missing_session_returns_none():
    assert get_session("does-not-exist") is None


def test_save_then_get_round_trips():
    saved = save_pending_proposal("s1", {"program_id": "ctevt-special-scholarship"})
    assert saved["status"] == "pending_approval"

    fetched = get_session("s1")
    assert fetched["proposal"]["program_id"] == "ctevt-special-scholarship"
    assert fetched["status"] == "pending_approval"


def test_revising_a_pending_proposal_overwrites_it():
    save_pending_proposal("s1", {"program_id": "a"})
    save_pending_proposal("s1", {"program_id": "b"})  # agent changed its mind pre-approval
    assert get_session("s1")["proposal"]["program_id"] == "b"


def test_update_status_on_missing_session_raises():
    with pytest.raises(KeyError):
        update_status("nope", status="approved")


def test_cannot_overwrite_a_decided_session():
    # Safety property: decision history is immutable once resolved.
    save_pending_proposal("s1", {"program_id": "a"})
    update_status("s1", status="approved", decision_note="looks good")

    with pytest.raises(ValueError):
        save_pending_proposal("s1", {"program_id": "a-revised"})


def test_update_status_records_note():
    save_pending_proposal("s1", {"program_id": "a"})
    updated = update_status("s1", status="rejected", decision_note="wrong program")
    assert updated["status"] == "rejected"
    assert updated["decision_note"] == "wrong program"
