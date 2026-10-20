"""Private practice persistence; intentionally independent of the study-guide Store."""

import copy
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class PracticeConflict(ValueError):
    pass


class PracticeStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,data TEXT NOT NULL); CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY,data TEXT NOT NULL);"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, db, table, key):
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("限时练习记录不存在")
        return json.loads(row[0])

    def write(self, db, table, value):
        db.execute(
            f"UPDATE {table} SET data=? WHERE id=?",
            (json.dumps(value, ensure_ascii=False, allow_nan=False), value["id"]),
        )

    def create_session(self, payload):
        s = dict(
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
                "INSERT INTO sessions VALUES(?,?)",
                (s["id"], json.dumps(s, ensure_ascii=False)),
            )
        return s

    def get_session(self, sid):
        with self.connection() as db:
            return self.read(db, "sessions", sid)

    def jobs_for(self, sid):
        with self.connection() as db:
            return self._jobs(db, sid)

    def _jobs(self, db, sid):
        return [
            json.loads(r[0])
            for r in db.execute(
                "SELECT data FROM jobs WHERE session_id=? ORDER BY rowid", (sid,)
            )
        ]

    def list_sessions(self):
        with self.connection() as db:
            records = [
                json.loads(r[0]) for r in db.execute("SELECT data FROM sessions")
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

    def update_session(self, sid, change, idle=False):
        with self.connection() as db:
            s = self.read(db, "sessions", sid)
            if idle and any(
                j["status"] in ("queued", "running") for j in self._jobs(db, sid)
            ):
                raise PracticeConflict("限时练习任务执行中，请完成后再操作")
            change(s)
            s["updated_at"] = now()
            self.write(db, "sessions", s)
        return s

    def change_idle(self, sid, change):
        return self.update_session(sid, change, True)

    def create_job(self, sid, payload):
        with self.connection() as db:
            s = self.read(db, "sessions", sid)
            if any(j["status"] in ("queued", "running") for j in self._jobs(db, sid)):
                raise PracticeConflict("本会话已有任务进行中")
            if payload["kind"] == "revision" and (
                not s["versions"]
                or s["versions"][-1]["id"] != payload.get("base_version_id")
            ):
                raise PracticeConflict("当前版本已更新，请选择最新版本后重试")
            request = copy.deepcopy(payload)
            request["teacher_settings"] = s["settings"]
            request["resources"] = s["resources"]
            j = dict(
                id=uuid.uuid4().hex,
                session_id=sid,
                request=request,
                status="queued",
                stages=[],
                error=None,
                can_draft=False,
                version_id=None,
                created_at=now(),
                updated_at=now(),
            )
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?)",
                (j["id"], sid, json.dumps(j, ensure_ascii=False)),
            )
            s["messages"].append(
                dict(role="user", content=payload["prompt"], job_id=j["id"])
            )
            s["updated_at"] = now()
            self.write(db, "sessions", s)
        return j

    def get_job(self, jid):
        with self.connection() as db:
            return self.read(db, "jobs", jid)

    def update_job(self, jid, **values):
        with self.connection() as db:
            j = self.read(db, "jobs", jid)
            j.update(values, updated_at=now())
            self.write(db, "jobs", j)
        return j

    def publish(self, jid, version):
        with self.connection() as db:
            j = self.read(db, "jobs", jid)
            if j["status"] not in ("queued", "running"):
                raise PracticeConflict("任务已终止，拒绝发布")
            s = self.read(db, "sessions", j["session_id"])
            if (
                j["request"]["kind"] == "revision"
                and s["versions"][-1]["id"] != j["request"]["base_version_id"]
            ):
                raise PracticeConflict("基线已更新")
            s["versions"].append(version)
            s["updated_at"] = now()
            s["messages"].append(
                dict(
                    role="assistant",
                    content="限时练习与独立答案已生成",
                    version_id=version["id"],
                )
            )
            self.write(db, "sessions", s)
            for stage in j["stages"]:
                stage.update(status="completed")
            j.update(status="completed", version_id=version["id"], updated_at=now())
            self.write(db, "jobs", j)

    def recover_jobs(self):
        count = 0
        with self.connection() as db:
            for row in db.execute("SELECT data FROM jobs").fetchall():
                j = json.loads(row[0])
                if j["status"] in ("queued", "running"):
                    j.update(
                        status="failed",
                        error="服务重启，限时练习任务已中断，请重新提交",
                        updated_at=now(),
                    )
                    self.write(db, "jobs", j)
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
            else dict(documents=[], chunk_count=0, synced_at=None)
        )

    def save_library(self, identity, documents):
        value = dict(
            documents=documents,
            chunk_count=sum(len(d["chunks"]) for d in documents),
            synced_at=now(),
        )
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO library VALUES(?,?)",
                (identity, json.dumps(value, ensure_ascii=False)),
            )
        return value
