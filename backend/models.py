import os
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrafficSnapshot(Base):
    """通车窗打开时的快照头：一个填窗口名称一份，头与明细同生共死。"""

    __tablename__ = "traffic_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["TrafficSnapshotItem"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="TrafficSnapshotItem.seq",
    )


class TrafficSnapshotItem(Base):
    """快照明细：当时在途单据（待办 pending / 在办 processing）的编号、断面、毫米副本。

    只抄值、不挂外键到 convergence_logs：在线单据日后办结或改状态不得回写快照。
    """

    __tablename__ = "traffic_snapshot_items"
    __table_args__ = (UniqueConstraint("snapshot_id", "log_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("traffic_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    log_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)

    snapshot: Mapped[TrafficSnapshot] = relationship(back_populates="items")


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def snapshot_item_dict(row: TrafficSnapshotItem) -> dict:
    return {
        "log_id": row.log_id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
    }


def snapshot_dict(row: TrafficSnapshot, *, with_items: bool = False) -> dict:
    data = {
        "id": row.id,
        "window_name": row.window_name,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "item_count": len(row.items),
    }
    if with_items:
        data["items"] = [snapshot_item_dict(i) for i in row.items]
    return data
