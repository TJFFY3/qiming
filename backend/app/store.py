"""SQLite JSON records; all read-modify-write operations use immediate transactions."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, db_path: Path):
        self.path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS library (id TEXT PRIMARY KEY, data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, data TEXT NOT NULL);"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _read(db, table, key):
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("记录不存在")
        return json.loads(row[0])

    @staticmethod
    def _write(db, table, value):
        db.execute(
            f"UPDATE {table} SET data=? WHERE id=?",
            (json.dumps(value, ensure_ascii=False), value["id"]),
        )

    def create_session(self, payload: dict) -> dict:
        value = dict(
            id=uuid.uuid4().hex,
            settings=payload,
            created_at=now(),
            updated_at=now(),
            messages=[],
            resources=[],
            sources=[],
            versions=[],
        )
        with self.connection() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?)",
                (value["id"], json.dumps(value, ensure_ascii=False)),
            )
        return value

    def get_session(self, session_id: str) -> dict:
        with self.connection() as db:
            return self._read(db, "sessions", session_id)

    def list_sessions(self) -> list[dict]:
        with self.connection() as db:
            records = [
                json.loads(row[0]) for row in db.execute("SELECT data FROM sessions")
            ]
        return [
            dict(
                id=s["id"],
                settings=s["settings"],
                updated_at=s["updated_at"],
                version_count=len(s["versions"]),
            )
            for s in sorted(records, key=lambda s: s["updated_at"], reverse=True)
        ]

    def update_session(self, session_id, change):
        with self.connection() as db:
            value = self._read(db, "sessions", session_id)
            change(value)
            value["updated_at"] = now()
            self._write(db, "sessions", value)
        return value

    def delete_resource(self, session_id, resource_id):
        # Share the job-creation transaction lock so generation cannot race deletion.
        with self.connection() as db:
            session = self._read(db, "sessions", session_id)
            jobs = db.execute("SELECT data FROM jobs WHERE session_id=?", (session_id,))
            if any(
                json.loads(row[0])["status"] in ("queued", "running") for row in jobs
            ):
                raise Conflict("任务执行中，请完成后删除资料")
            if not any(r["id"] == resource_id for r in session["resources"]):
                raise KeyError("本课上传资料不存在")
            session["resources"] = [
                r for r in session["resources"] if r["id"] != resource_id
            ]
            session["sources"] = [
                r for r in session["sources"] if r["id"] != resource_id
            ]
            # Keep saved versions and their original upload files for historical traceability.
            session["updated_at"] = now()
            self._write(db, "sessions", session)
        return session

    def create_job(self, session_id: str, payload: dict) -> dict:
        with self.connection() as db:
            session = self._read(db, "sessions", session_id)
            active = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM jobs WHERE session_id=?", (session_id,)
                )
            ]
            if any(j["status"] in ("queued", "running") for j in active):
                raise Conflict("本会话已有任务进行中")
            if payload.get("kind") == "revision" and (
                not session["versions"]
                or session["versions"][-1]["id"] != payload.get("base_version_id")
            ):
                raise Conflict("当前版本已更新，请选择最新版本后重试")
            value = dict(
                id=uuid.uuid4().hex,
                session_id=session_id,
                request=payload,
                status="queued",
                stages=[],
                error=None,
                version_id=None,
                created_at=now(),
                updated_at=now(),
            )
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?)",
                (value["id"], session_id, json.dumps(value, ensure_ascii=False)),
            )
            session["messages"].append(
                dict(
                    role="user",
                    content=payload.get("prompt", ""),
                    job_id=value["id"],
                    created_at=now(),
                )
            )
            self._write(db, "sessions", session)
        return value

    def get_job(self, job_id):
        with self.connection() as db:
            return self._read(db, "jobs", job_id)

    def update_job(self, job_id, **values):
        with self.connection() as db:
            value = self._read(db, "jobs", job_id)
            value.update(values, updated_at=now())
            self._write(db, "jobs", value)
        return value

    def jobs_for(self, session_id):
        with self.connection() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM jobs WHERE session_id=?", (session_id,)
                )
            ]

    def publish(self, job_id, version):
        with self.connection() as db:
            job = self._read(db, "jobs", job_id)
            session = self._read(db, "sessions", job["session_id"])
            if (
                job["request"].get("kind") == "revision"
                and session["versions"][-1]["id"] != job["request"]["base_version_id"]
            ):
                raise Conflict("基线已更新，拒绝发布")
            session["versions"].append(version)
            session["messages"].append(
                dict(
                    role="assistant",
                    content="导学案已生成"
                    if not version["parent_id"]
                    else "已保存新版本",
                    version_id=version["id"],
                    created_at=now(),
                )
            )
            session["updated_at"] = now()
            self._write(db, "sessions", session)
            for step in job["stages"]:
                step.update(status="completed", ended_at=step.get("ended_at", now()))
            job.update(status="completed", version_id=version["id"], updated_at=now())
            self._write(db, "jobs", job)

    def recover_jobs(self):
        count = 0
        with self.connection() as db:
            for row in db.execute("SELECT data FROM jobs").fetchall():
                value = json.loads(row[0])
                if value["status"] in ("queued", "running"):
                    value.update(
                        status="failed",
                        error="服务重启，任务已中断，请重新提交",
                        updated_at=now(),
                    )
                    self._write(db, "jobs", value)
                    count += 1
        return count

    def get_library(self, identity):
        with self.connection() as db:
            row = db.execute(
                "SELECT data FROM library WHERE id=?", (identity,)
            ).fetchone()
        return (
            json.loads(row[0])
            if row
            else {"documents": [], "chunk_count": 0, "synced_at": None}
        )

    def save_library(self, identity, documents):
        value = {
            "documents": documents,
            "chunk_count": sum(len(d["chunks"]) for d in documents),
            "synced_at": now(),
        }
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO library VALUES (?,?)",
                (identity, json.dumps(value, ensure_ascii=False)),
            )
        return value
