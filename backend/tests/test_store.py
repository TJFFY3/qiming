import pytest
from backend.app.store import Store, Conflict


def test_session_survives_reopen(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    session = store.create_session({"chapter": "氧化还原反应"})
    assert (
        Store(tmp_path / "db.sqlite").get_session(session["id"])["settings"]["chapter"]
        == "氧化还原反应"
    )


def test_recover_marks_running_interrupted(tmp_path):
    store = Store(tmp_path / "db")
    session = store.create_session({})
    job = store.create_job(session["id"], {"prompt": "生成"})
    assert store.recover_jobs() == 1
    assert store.get_job(job["id"])["status"] == "failed"
    assert "中断" in store.get_job(job["id"])["error"]


def test_one_active_job_per_session(tmp_path):
    store = Store(tmp_path / "db")
    session = store.create_session({})
    store.create_job(session["id"], {})
    with pytest.raises(Conflict):
        store.create_job(session["id"], {})
