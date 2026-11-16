"""货物谱系领域模型：货批、谱系事件与召回。

数量口径：registered_quantity 为登记入谱的初始数量；available_quantity 为当前仍可被
拆分、合批与出库共用占用的数量。每次整单操作在同一事务内校验并扣减，超额整单拒绝。
"""
from sqlalchemy import String, Double, ForeignKey, Boolean, Integer, Numeric, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
# MySQL 8 下 Numeric 精度由数据库保证；SQLite 本地测试按 NUMERIC 亲和性存储
Q = Numeric(14, 3)
class GoodsLot(Base):
    __tablename__ = 'goods_lots'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    registered_quantity: Mapped[object] = mapped_column(Q)
    available_quantity: Mapped[object] = mapped_column(Q)
    unit: Mapped[str] = mapped_column(String(16), default='件')
    status: Mapped[str] = mapped_column(String(20), default='active')
    created_at: Mapped[float] = mapped_column(Double)
    quarantined_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class LotEvent(Base):
    __tablename__ = 'lot_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    order_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    note: Mapped[str] = mapped_column(String(300), default='')
    actor: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[float] = mapped_column(Double)
class LotEventLine(Base):
    __tablename__ = 'lot_event_lines'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('lot_events.id'), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # in 消耗来源 / out 产出去向
    lot_id: Mapped[int] = mapped_column(ForeignKey('goods_lots.id'), index=True)
    quantity: Mapped[object] = mapped_column(Q)
    destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (Index('ix_event_lines_event_dir', 'event_id', 'direction'),)
class Recall(Base):
    __tablename__ = 'recalls'
    id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str] = mapped_column(String(300))
    job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='propagating', index=True)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[float] = mapped_column(Double)
    confirmed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # 发起确认时冻结的快照：涉及货批 id 与当时已出库去向
    root_lot_ids: Mapped[list] = mapped_column(JSON, default=list)
class RecallLot(Base):
    __tablename__ = 'recall_lots'
    id: Mapped[int] = mapped_column(primary_key=True)
    recall_id: Mapped[int] = mapped_column(ForeignKey('recalls.id'), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey('goods_lots.id'), index=True)
    stage: Mapped[str] = mapped_column(String(12))
    frozen_available: Mapped[object] = mapped_column(Q)
    quarantined_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    __table_args__ = (Index('ix_recall_lot_unique', 'recall_id', 'lot_id', unique=True),)
class RecallNotification(Base):
    __tablename__ = 'recall_notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    recall_id: Mapped[int] = mapped_column(ForeignKey('recalls.id'), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey('goods_lots.id'))
    lot_code: Mapped[str] = mapped_column(String(60))
    event_id: Mapped[int] = mapped_column(ForeignKey('lot_events.id'))
    order_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    destination: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[object] = mapped_column(Q)
    created_at: Mapped[float] = mapped_column(Double)
    # 同一召回下同一条出库明细只通知一次，重试不重复
    __table_args__ = (Index('ix_recall_notify_unique', 'recall_id', 'event_id', 'lot_id', unique=True),)
