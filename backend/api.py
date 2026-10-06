import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from claimer import IN_FLIGHT_STATUSES, start as start_claimer
from models import (
    Base,
    ConvergenceLog,
    SessionLocal,
    TrafficSnapshot,
    TrafficSnapshotItem,
    engine,
    row_dict,
    snapshot_dict,
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
if os.environ.get("DISABLE_CLAIMER") != "1":
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
            return jsonify({"detail": "巡检身份只读，不能点快照（仅测量员可写）"}), 403
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


@app.get("/api/snapshots")
@require_login
def list_snapshots():
    db = SessionLocal()
    try:
        rows = (
            db.query(TrafficSnapshot)
            .options(joinedload(TrafficSnapshot.items))
            .order_by(TrafficSnapshot.id.desc())
            .all()
        )
        return jsonify([snapshot_dict(r) for r in rows])
    finally:
        db.close()


@app.get("/api/snapshots/<int:snapshot_id>")
@require_login
def get_snapshot(snapshot_id):
    db = SessionLocal()
    try:
        row = (
            db.query(TrafficSnapshot)
            .options(joinedload(TrafficSnapshot.items))
            .filter(TrafficSnapshot.id == snapshot_id)
            .one_or_none()
        )
        if row is None:
            return jsonify({"detail": "快照不存在"}), 404
        return jsonify(snapshot_dict(row, with_items=True))
    finally:
        db.close()


@app.post("/api/snapshots")
@require_writer
def create_snapshot():
    body = request.get_json(silent=True) or {}
    window_name = (body.get("window_name") or "").strip()
    if not window_name:
        return jsonify({"detail": "通车窗口名称不能为空"}), 400
    db = SessionLocal()
    try:
        dup = (
            db.query(TrafficSnapshot.id)
            .filter(TrafficSnapshot.window_name == window_name)
            .first()
        )
        if dup is not None:
            return (
                jsonify({"detail": f"通车窗口「{window_name}」快照已存在，不能覆盖新旧两套必须分清"}),
                409,
            )
        # 一把行锁锁住此刻全部在途单据：认领线程在本事务提交前无法办结其中任何一笔，
        # 保证抄进快照的集合就是这一瞬间路上的完整集合。
        rows = (
            db.query(ConvergenceLog)
            .filter(ConvergenceLog.status.in_(IN_FLIGHT_STATUSES))
            .order_by(ConvergenceLog.id)
            .with_for_update()
            .all()
        )
        if not rows:
            return jsonify({"detail": "当前没有在途（待办/在办）测缝单，快照无明细可抄"}), 400
        snapshot = TrafficSnapshot(
            window_name=window_name,
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        for seq, r in enumerate(rows):
            snapshot.items.append(
                TrafficSnapshotItem(
                    seq=seq,
                    log_id=r.id,
                    chainage=r.chainage,
                    delta_mm=float(r.delta_mm),
                    status=r.status,
                )
            )
        db.add(snapshot)
        # 头与明细在同一事务一次提交：要么整份落库，要么什么都没有，禁止只写下半截。
        db.commit()
        db.refresh(snapshot)
        return jsonify(snapshot_dict(snapshot, with_items=True)), 201
    except IntegrityError:
        db.rollback()
        return jsonify({"detail": "同名通车窗口快照已存在，不能覆盖"}), 409
    finally:
        db.close()
