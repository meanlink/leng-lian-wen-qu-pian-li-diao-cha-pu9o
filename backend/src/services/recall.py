"""温区调查召回服务。

流程：发起召回时在单事务内冻结当时涉及货批及已出库去向快照，然后沿拆合关系 BFS
隔离全部后代（合批货物整体隔离），为每条已出库明细生成一次性通知。任何一步中断后，
worker 或人工重试都会从已提交的快照继续：已冻结货批不重复隔离、已发通知不重复生成。
只有全部可达后代都有 recall_lots、全部出库明细都有通知时才置为 completed。
"""
import time
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from src.models import (GoodsLot, LotEvent, LotEventLine, Recall, RecallLot,
                        RecallNotification)
from src.constants.enums import LotStatus, RecallStatus, RecallStage, GenealogyEventType
from src.services.audit import record
from src.services import genealogy
def _lock_sorted(db, lot_ids):
    lots = []
    for lid in sorted(set(lot_ids)):
        lot = db.scalar(select(GoodsLot).where(GoodsLot.id == lid).with_for_update())
        if lot is None:
            raise HTTPException(404, f'货批 {lid} 不存在')
        lots.append(lot)
    return lots
def _existing_notification(db, recall_id, event_id, lot_id):
    return db.scalar(select(RecallNotification).where(
        RecallNotification.recall_id == recall_id,
        RecallNotification.event_id == event_id,
        RecallNotification.lot_id == lot_id))
def _notify_outbound(db, recall, lot_ids, now):
    """为受影响货批的全部已出库明细生成通知（幂等）。返回新增条数。"""
    lines = db.scalars(select(LotEventLine).where(
        LotEventLine.direction == 'in', LotEventLine.lot_id.in_(lot_ids))).all()
    event_ids = {line.event_id for line in lines}
    if not event_ids:
        return 0
    outbound_events = {ev.id: ev for ev in db.scalars(select(LotEvent).where(
        LotEvent.id.in_(event_ids),
        LotEvent.type == GenealogyEventType.outbound.value)).all()}
    created = 0
    for line in lines:
        ev = outbound_events.get(line.event_id)
        if not ev:
            continue
        if _existing_notification(db, recall.id, line.event_id, line.lot_id):
            continue
        lot = db.get(GoodsLot, line.lot_id)
        db.add(RecallNotification(
            recall_id=recall.id, lot_id=line.lot_id, lot_code=lot.code if lot else str(line.lot_id),
            event_id=line.event_id, order_code=ev.order_code,
            destination=line.destination or '', quantity=line.quantity, created_at=now))
        created += 1
    return created
def _quarantine(db, recall, lot, stage, now, audit_actor):
    existing = db.scalar(select(RecallLot).where(
        RecallLot.recall_id == recall.id, RecallLot.lot_id == lot.id))
    if existing:
        return False
    # 冻结时的可用数量即隔离数量；合批货物按整批可用量整体隔离
    db.add(RecallLot(recall_id=recall.id, lot_id=lot.id, stage=stage,
                     frozen_available=Decimal(lot.available_quantity), quarantined_at=now))
    if lot.status != LotStatus.quarantined.value:
        lot.status = LotStatus.quarantined.value
        lot.quarantined_at = now
    record(db, audit_actor, 'recall.quarantine',
           {'recall': recall.id, 'lot': lot.id, 'stage': stage})
    return True
def create_recall(db, data, actor):
    roots = _lock_sorted(db, data.lot_ids)
    now = time.time()
    recall = Recall(reason=data.reason, job_id=data.job_id, dataset_id=data.dataset_id,
                    status=RecallStatus.propagating.value, created_by=actor,
                    created_at=now, confirmed_at=now,
                    root_lot_ids=[lot.id for lot in roots])
    db.add(recall); db.flush()
    record(db, actor, 'recall.create', {'id': recall.id, 'lots': recall.root_lot_ids})
    # 1) 确认瞬间冻结涉及货批与其当时已出库去向
    for lot in roots:
        _quarantine(db, recall, lot, RecallStage.root.value, now, actor)
    root_notify = _notify_outbound(db, recall, [lot.id for lot in roots], now)
    if root_notify:
        record(db, actor, 'recall.notify', {'recall': recall.id, 'count': root_notify})
    # 2) 沿拆合关系隔离全部后代（合批货物整体隔离）
    reached = genealogy.descendants(db, [lot.id for lot in roots])
    reached_lots = _lock_sorted(db, reached)
    for lot in reached_lots:
        _quarantine(db, recall, lot, RecallStage.descendant.value, now, actor)
    # 3) 后代的已出库去向同样通知
    extra = _notify_outbound(db, recall, list(reached), now)
    if extra:
        record(db, actor, 'recall.notify', {'recall': recall.id, 'count': extra})
    # 4) 完整核对：全部可达后代均已登记、全部出库明细均已通知
    _complete_if_verified(db, recall, reached, now, actor)
    return recall
def _complete_if_verified(db, recall, reached, now, actor):
    missing = [lid for lid in reached if not db.scalar(select(RecallLot.id).where(
        RecallLot.recall_id == recall.id, RecallLot.lot_id == lid))]
    if missing:
        return False
    outbound_lines = db.execute(select(LotEventLine.id, LotEventLine.event_id, LotEventLine.lot_id).where(
        LotEventLine.direction == 'in', LotEventLine.lot_id.in_(reached))).all()
    for _, event_id, lot_id in outbound_lines:
        ev = db.get(LotEvent, event_id)
        if ev and ev.type == GenealogyEventType.outbound.value and not _existing_notification(
                db, recall.id, event_id, lot_id):
            return False
    if recall.status != RecallStatus.completed.value:
        recall.status = RecallStatus.completed.value
        recall.finished_at = now
        record(db, actor, 'recall.completed', {'id': recall.id, 'lots': len(reached)})
    return True
def resume_recall(db, recall_id, actor='worker'):
    """中断恢复/幂等重试入口。返回召回对象；已完成则直接返回，不重复冻结或通知。"""
    recall = db.get(Recall, recall_id)
    if not recall:
        raise HTTPException(404, '召回不存在')
    if recall.status == RecallStatus.completed.value:
        return recall
    now = time.time()
    roots = list(recall.root_lot_ids or [])
    _lock_sorted(db, roots)  # 恢复时同样与拆合/出库串行
    reached = genealogy.descendants(db, roots)
    for lot in _lock_sorted(db, reached):
        _quarantine(db, recall, lot,
                    RecallStage.root.value if lot.id in roots else RecallStage.descendant.value,
                    now, actor)
    added = _notify_outbound(db, recall, list(reached), now)
    if added:
        record(db, actor, 'recall.notify', {'recall': recall.id, 'count': added})
    _complete_if_verified(db, recall, reached, now, actor)
    return recall
def affected_summary(db, recall):
    """页面追查用：受影响数量、流向与隔离进度。"""
    items = db.scalars(select(RecallLot).where(RecallLot.recall_id == recall.id)).all()
    notifications = db.scalars(select(RecallNotification).where(
        RecallNotification.recall_id == recall.id)).all()
    reached = genealogy.descendants(db, list(recall.root_lot_ids or []))
    quarantined_qty = sum((Decimal(x.frozen_available) for x in items), Decimal('0'))
    outbound_qty = sum((Decimal(n.quantity) for n in notifications), Decimal('0'))
    return {
        'total_descendants': len(reached),
        'quarantined_lots': len(items),
        'isolation_progress': round(len(items) / len(reached), 4) if reached else 1,
        'quarantined_quantity': float(quarantined_qty),
        'outbound_notifications': len(notifications),
        'outbound_quantity': float(outbound_qty),
        'destinations': sorted({n.destination for n in notifications if n.destination}),
    }
