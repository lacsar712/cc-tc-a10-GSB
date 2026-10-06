import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import func

from claimer import start as start_claimer
from models import (
    Base,
    ConvergenceLog,
    SessionLocal,
    TrafficSnapshot,
    TrafficSnapshotItem,
    engine,
    row_dict,
    snapshot_dict,
    snapshot_item_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    delta_mm=delta,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可提交收敛读数"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_snapshot_writer(fn):
    """拍快照是写操作：巡检身份只能查阅，不能点快照。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "巡检身份仅可查阅快照，不能拍快照"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()


# 待办 + 在办都算“还在路上”的测缝单，快照要一笔不漏地抄进来。
OPEN_STATUSES = ("pending", "processing")


@app.post("/api/snapshots")
@require_snapshot_writer
def create_snapshot():
    body = request.get_json(silent=True) or {}
    window_name = (body.get("window_name") or "").strip()
    if not window_name:
        return jsonify({"detail": "窗口名称不能为空"}), 400
    db = SessionLocal()
    try:
        open_rows = (
            db.query(ConvergenceLog)
            .filter(ConvergenceLog.status.in_(OPEN_STATUSES))
            .order_by(ConvergenceLog.id)
            .all()
        )
        snap = TrafficSnapshot(
            window_name=window_name,
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(snap)
        db.flush()  # 同一事务内先取快照头 id，尚未提交
        items = [
            TrafficSnapshotItem(
                snapshot_id=snap.id,
                log_id=r.id,
                chainage=r.chainage,
                delta_mm=r.delta_mm,
                status=r.status,
            )
            for r in open_rows
        ]
        db.add_all(items)
        # 快照头与全部明细只在此一次提交；任一步失败整体回滚，不留半截。
        db.commit()
        payload = snapshot_dict(snap, len(items))
        payload["items"] = [snapshot_item_dict(i) for i in items]
        return jsonify(payload), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/snapshots")
@require_login
def list_snapshots():
    db = SessionLocal()
    try:
        snaps = db.query(TrafficSnapshot).order_by(TrafficSnapshot.id.desc()).all()
        counts = dict(
            db.query(TrafficSnapshotItem.snapshot_id, func.count(TrafficSnapshotItem.id))
            .group_by(TrafficSnapshotItem.snapshot_id)
            .all()
        )
        return jsonify([snapshot_dict(s, counts.get(s.id, 0)) for s in snaps])
    finally:
        db.close()


@app.get("/api/snapshots/<int:snapshot_id>")
@require_login
def get_snapshot(snapshot_id):
    db = SessionLocal()
    try:
        snap = db.get(TrafficSnapshot, snapshot_id)
        if snap is None:
            return jsonify({"detail": "快照不存在"}), 404
        items = (
            db.query(TrafficSnapshotItem)
            .filter(TrafficSnapshotItem.snapshot_id == snapshot_id)
            .order_by(TrafficSnapshotItem.log_id)
            .all()
        )
        payload = snapshot_dict(snap, len(items))
        payload["items"] = [snapshot_item_dict(i) for i in items]
        return jsonify(payload)
    finally:
        db.close()
