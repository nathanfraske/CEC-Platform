"""Durable model-owned decisions and event history, without an optimizer loop.

SQLite serializes writers and survives a stopped client. Decisions bind the
source and code epoch. A failed identical decision cannot silently run again;
the model must change the intent or explicitly explain its replanning.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Journal:
    def __init__(self, workspace):
        self.path = Path(workspace) / "campaign.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY, at REAL NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    identity TEXT PRIMARY KEY, job TEXT NOT NULL,
                    board TEXT NOT NULL, state TEXT NOT NULL,
                    payload TEXT NOT NULL, reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS parents (
                    board TEXT PRIMARY KEY, job TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, record TEXT NOT NULL
                );
            """
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=2.0, isolation_level=None)
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
    def _event(db, kind, payload):
        last = db.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = last[0] if last else "0" * 64
        body = canonical(payload)
        stamp = time.time()
        identity = hashlib.sha256(
            canonical([previous, stamp, kind, body]).encode()
        ).hexdigest()
        db.execute(
            "INSERT INTO events(at,kind,payload,previous_hash,event_hash) VALUES(?,?,?,?,?)",
            (stamp, kind, body, previous, identity),
        )

    def begin(self, job, board, source_sha256, code_identity, request):
        payload = dict(
            board=board,
            source_sha256=source_sha256,
            code_identity=code_identity,
            request=request,
        )
        identity = hashlib.sha256(canonical(payload).encode()).hexdigest()
        with self.connection() as db:
            old = db.execute(
                "SELECT job,state,reason FROM decisions WHERE identity=?", (identity,)
            ).fetchone()
            if old:
                if old[1] == "failed":
                    raise ValueError(
                        "identical_failed_decision_requires_changed_design:" + old[2]
                    )
                return dict(identity=identity, job=old[0], state=old[1], resumed=True)
            db.execute(
                "INSERT INTO decisions(identity,job,board,state,payload) VALUES(?,?,?,?,?)",
                (identity, job, board, "staged", canonical(payload)),
            )
            self._event(
                db, "decision_staged", dict(identity=identity, job=job, board=board)
            )
        return dict(identity=identity, job=job, state="staged", resumed=False)

    def transition(self, job, state, reason=""):
        if state not in ("staged", "checking", "failed", "selected"):
            raise ValueError("known_campaign_transition_required")
        with self.connection() as db:
            row = db.execute(
                "SELECT state FROM decisions WHERE job=?", (job,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown_campaign_decision")
            if row[0] in ("failed", "selected") and row[0] != state:
                raise ValueError("terminal_decision_requires_new_design")
            db.execute(
                "UPDATE decisions SET state=?,reason=? WHERE job=?",
                (state, reason, job),
            )
            if row[0] != state or reason:
                self._event(db, "decision_" + state, dict(job=job, reason=reason))

    def parent(self, board):
        with self.connection() as db:
            row = db.execute(
                "SELECT record FROM parents WHERE board=?", (board,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def set_parent(self, board, job, identity, record):
        with self.connection() as db:
            row = db.execute(
                "SELECT state FROM decisions WHERE job=? AND board=?", (job, board)
            ).fetchone()
            if row is None or row[0] != "selected":
                raise ValueError("selected_source_bound_decision_required")
            db.execute(
                "INSERT OR REPLACE INTO parents VALUES(?,?,?,?)",
                (board, job, identity, canonical(record)),
            )
            self._event(
                db,
                "review_parent_adopted",
                dict(board=board, job=job, candidate_sha256=identity),
            )

    def state(self, limit=24):
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("bounded_campaign_history_required")
        with self.connection() as db:
            decisions = [
                dict(job=j, board=b, state=s, reason=r)
                for j, b, s, r in db.execute(
                    "SELECT job,board,state,reason FROM decisions ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                )
            ]
            events = [
                dict(sequence=s, kind=k, payload=json.loads(p), event_hash=h)
                for s, k, p, h in db.execute(
                    "SELECT sequence,kind,payload,event_hash FROM events ORDER BY sequence DESC LIMIT ?",
                    (limit,),
                )
            ]
            count = db.execute("SELECT count(*) FROM decisions").fetchone()[0]
        failures = sum(row["state"] == "failed" for row in decisions[:3])
        return dict(
            ok=True,
            complete=True,
            decision_count=count,
            decisions=decisions,
            events=events,
            needs_replanning=len(decisions) >= 3 and failures == 3,
            autonomous_decision_loop=False,
            release_authority=False,
        )

    def verify(self):
        previous = "0" * 64
        with self.connection() as db:
            for at, kind, payload, parent, identity in db.execute(
                "SELECT at,kind,payload,previous_hash,event_hash FROM events ORDER BY sequence"
            ):
                expected = hashlib.sha256(
                    canonical([previous, at, kind, payload]).encode()
                ).hexdigest()
                if parent != previous or identity != expected:
                    raise ValueError("campaign_journal_integrity_changed")
                previous = identity
        return previous
