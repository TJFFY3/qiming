"""【状态存储·互动课件】独立保存课件会话、任务、来源和版本，通过事务限制并发修改。"""

import copy
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from backend.app.courseware.llm.prompts import compose_prompt


def now():
    return datetime.now(timezone.utc).isoformat()


def identity():
    return uuid.uuid4().hex


class CoursewareConflict(ValueError):
    pass


class CoursewareStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id));"
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

    def read(self, db, kind, key):
        row = db.execute(
            "SELECT data FROM records WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        if row is None:
            raise KeyError("课件记录不存在")
        return json.loads(row[0])

    def save(self, db, kind, value):
        db.execute(
            "INSERT OR REPLACE INTO records VALUES (?,?,?)",
            (kind, value["id"], json.dumps(value, ensure_ascii=False)),
        )

    def all(self, db, kind):
        return [
            json.loads(row[0])
            for row in db.execute("SELECT data FROM records WHERE kind=?", (kind,))
        ]

    def create_session(self, settings):
        value = dict(
            id=identity(),
            settings=settings,
            created_at=now(),
            updated_at=now(),
            resources=[],
            sources=[],
            messages=[],
            versions=[],
        )
        with self.connection() as db:
            self.save(db, "session", value)
        return value

    def get_session(self, sid):
        with self.connection() as db:
            return self.read(db, "session", sid)

    def list_sessions(self):
        with self.connection() as db:
            sessions = self.all(db, "session")
        return [
            dict(
                id=s["id"],
                settings=s["settings"],
                updated_at=s["updated_at"],
                version_count=len(s["versions"]),
            )
            for s in sorted(sessions, key=lambda s: s["updated_at"], reverse=True)
        ]

    def get_job(self, jid):
        with self.connection() as db:
            return self.read(db, "job", jid)

    def jobs_for(self, sid):
        with self.connection() as db:
            return sorted(
                [j for j in self.all(db, "job") if j["session_id"] == sid],
                key=lambda j: j["created_at"],
            )

    def check_idle(self, db, sid):
        if any(
            j["session_id"] == sid and j["status"] in ("queued", "running")
            for j in self.all(db, "job")
        ):
            raise CoursewareConflict("课件任务执行中，请稍后操作")

    def mutate_idle(self, sid, change):
        with self.connection() as db:
            session = self.read(db, "session", sid)
            self.check_idle(db, sid)
            change(session)
            session["updated_at"] = now()
            self.save(db, "session", session)
        return session

    def update_settings(self, sid, settings):
        return self.mutate_idle(sid, lambda s: s.update(settings=settings))

    def add_resource(self, sid, resource):
        def change(s):
            if len(s["resources"]) >= 10:
                raise ValueError("每个课件会话最多10份资料")
            s["resources"].append(resource)

        return self.mutate_idle(sid, change)

    def delete_resource(self, sid, rid):
        def change(s):
            if not any(r["id"] == rid for r in s["resources"]):
                raise KeyError("资料不存在")
            s["resources"] = [r for r in s["resources"] if r["id"] != rid]

        return self.mutate_idle(sid, change)

    def reserve(self, sid, payload, kind):
        with self.connection() as db:
            session = self.read(db, "session", sid)
            self.check_idle(db, sid)
            if kind == "revision" and (
                not session["versions"]
                or session["versions"][-1]["id"] != payload["base_version_id"]
            ):
                raise CoursewareConflict("只能基于最新课件版本修改，请切换到最新版本")
            payload = {
                **payload,
                "prompt": compose_prompt(
                    payload.get("prompt", ""), session["settings"]
                ),
            }
            job = dict(
                id=identity(),
                session_id=sid,
                status="queued",
                kind=kind,
                created_at=now(),
                stages=[],
                error=None,
                version_id=None,
                request=payload,
                snapshot=copy.deepcopy(session),
            )
            self.save(db, "job", job)
            session["messages"].append(
                dict(role="user", content=payload["prompt"], job_id=job["id"])
            )
            session["updated_at"] = now()
            self.save(db, "session", session)
        return job

    def stage(self, jid, label):
        with self.connection() as db:
            job = self.read(db, "job", jid)
            if job["status"] not in ("queued", "running"):
                raise CoursewareConflict("任务已结束")
            for s in job["stages"]:
                s["status"] = "completed"
            job["stages"].append(dict(label=label, status="running"))
            job["status"] = "running"
            self.save(db, "job", job)

    def finish(self, jid, version):
        with self.connection() as db:
            job = self.read(db, "job", jid)
            if job["status"] != "running":
                raise CoursewareConflict("任务已结束")
            session = self.read(db, "session", job["session_id"])
            session["versions"].append(version)
            session["sources"] = version["sources"]
            session["messages"].append(
                dict(
                    role="assistant",
                    content="课件已生成，可逐页预览和下载 PPTX。",
                    version_id=version["id"],
                )
            )
            session["updated_at"] = now()
            job.update(status="completed", version_id=version["id"])
            for s in job["stages"]:
                s["status"] = "completed"
            self.save(db, "session", session)
            self.save(db, "job", job)

    def fail(self, jid, error):
        with self.connection() as db:
            job = self.read(db, "job", jid)
            job.update(status="failed", error=error)
            for s in job["stages"]:
                if s["status"] == "running":
                    s["status"] = "failed"
            self.save(db, "job", job)

    def recover_jobs(self):
        with self.connection() as db:
            for job in self.all(db, "job"):
                if job["status"] in ("queued", "running"):
                    job.update(
                        status="failed", error="服务重启，课件任务已中断，请重试"
                    )
                    for s in job["stages"]:
                        if s["status"] == "running":
                            s["status"] = "failed"
                    self.save(db, "job", job)

    def get_library(self):
        with self.connection() as db:
            try:
                return self.read(db, "library", "current")
            except KeyError:
                return dict(documents=[], chunk_count=0, synced_at=None)

    def save_library(self, documents):
        value = {
            "documents": documents,
            "chunk_count": sum(len(d["chunks"]) for d in documents),
            "id": "current",
            "synced_at": now(),
        }
        with self.connection() as db:
            self.save(db, "library", value)
        return value
