"""进程内认领：同一 Flask 进程后台线程抢在途单据，不另起容器。

单据先从 pending（待办）置为 processing（在办）并提交，再出结论置 done（办结）。
中间的在办状态对外可见：通车快照在任一瞬间读到的待办+在办都是完整在途集合。
进程在两步之间崩溃后，processing 的单子会在下一轮按 id 顺序重新认领。
"""
import threading
import time
from datetime import datetime, timezone

from models import ConvergenceLog, SessionLocal
from rules import judge

_stop = threading.Event()

IN_FLIGHT_STATUSES = ("pending", "processing")


def _claim_one(db):
    return (
        db.query(ConvergenceLog)
        .filter(ConvergenceLog.status.in_(IN_FLIGHT_STATUSES))
        .order_by(ConvergenceLog.id)
        .with_for_update(skip_locked=True)
        .first()
    )


def claim_once() -> bool:
    db = SessionLocal()
    try:
        row = _claim_one(db)
        if row is None:
            db.commit()
            return False
        if row.status == "pending":
            row.status = "processing"
            db.commit()  # 在办状态先落库可见，再判结论
        # commit 后属性过期，访问时会在新事务里重新读回这行（此时为 processing）
        verdict, reason = judge(float(row.delta_mm))
        row.status = "done"
        row.verdict = verdict
        row.reason = reason
        row.processed_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def loop():
    while not _stop.is_set():
        try:
            if claim_once():
                time.sleep(0.4)
            else:
                time.sleep(1.0)
        except Exception as exc:
            print(f"claimer error: {exc}", flush=True)
            time.sleep(1.0)


def start():
    t = threading.Thread(target=loop, name="convergence-claimer", daemon=True)
    t.start()
