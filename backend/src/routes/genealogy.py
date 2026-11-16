from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import GoodsLot, LotEvent, LotEventLine, Recall, RecallLot, RecallNotification
from src.schemas.genealogy import (LotRegisterInput, SplitInput, MergeInput,
                                   OutboundInput, RecallInput)
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import genealogy, recall as recall_service
from src.services.audit import record
from src.utils.serialization import (lot_dict, event_dict, recall_dict, recall_lot_dict,
                                     notification_dict)
router = APIRouter(prefix='/genealogy')
def _event_lines(db, event_ids):
    rows = db.scalars(select(LotEventLine).where(LotEventLine.event_id.in_(event_ids))).all()
    grouped = {}
    for line in rows:
        grouped.setdefault(line.event_id, []).append(line)
    return grouped
# ---------- 货批 ----------
@router.get('/lots')
def list_lots(db=Depends(get_db), u=Depends(current_user)):
    lots = db.scalars(select(GoodsLot).order_by(GoodsLot.id.desc()).limit(300)).all()
    return [lot_dict(x) for x in lots]
@router.post('/lots', status_code=201)
def register_lot(data: LotRegisterInput, db=Depends(get_db), u=Depends(can_write)):
    lot = genealogy.register(db, data, u.email)
    record(db, u.email, 'lot.register', {'id': lot.id, 'code': lot.code})
    db.commit()
    return lot_dict(lot)
@router.get('/lots/{id}')
def lot_detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    lot = db.get(GoodsLot, id)
    if not lot:
        raise HTTPException(404, '货批不存在')
    graph = genealogy.genealogy_graph(db, id)
    events = [event_dict(item['event'], item['lines']) | {'relation': item['direction']}
              for item in graph]
    return {**lot_dict(lot), 'genealogy': events}
# ---------- 拆分 / 合批 / 出库 ----------
@router.post('/split', status_code=201)
def split(data: SplitInput, db=Depends(get_db), u=Depends(can_write)):
    ev = genealogy.split(db, data, u.email)
    record(db, u.email, 'lot.split', {'event': ev.id})
    db.commit()
    return {'event_id': ev.id}
@router.post('/merge', status_code=201)
def merge(data: MergeInput, db=Depends(get_db), u=Depends(can_write)):
    lot = genealogy.merge(db, data, u.email)
    record(db, u.email, 'lot.merge', {'lot': lot.id})
    db.commit()
    return lot_dict(lot)
@router.post('/outbound', status_code=201)
def outbound(data: OutboundInput, db=Depends(get_db), u=Depends(can_write)):
    ev = genealogy.outbound(db, data, u.email)
    record(db, u.email, 'lot.outbound', {'event': ev.id, 'order': data.order_code})
    db.commit()
    return {'event_id': ev.id, 'order_code': ev.order_code}
@router.get('/events')
def list_events(db=Depends(get_db), u=Depends(current_user)):
    events = db.scalars(select(LotEvent).order_by(LotEvent.id.desc()).limit(200)).all()
    grouped = _event_lines(db, [e.id for e in events])
    return [event_dict(e, grouped.get(e.id, [])) for e in events]
# ---------- 召回 ----------
@router.get('/recalls')
def list_recalls(db=Depends(get_db), u=Depends(current_user)):
    recalls = db.scalars(select(Recall).order_by(Recall.id.desc())).all()
    return [recall_dict(r) | {'summary': recall_service.affected_summary(db, r)} for r in recalls]
@router.post('/recalls', status_code=201)
def create_recall(data: RecallInput, db=Depends(get_db), u=Depends(admin_only)):
    r = recall_service.create_recall(db, data, u.email)
    db.commit()
    return recall_dict(r) | {'summary': recall_service.affected_summary(db, r)}
@router.get('/recalls/{id}')
def recall_detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    r = db.get(Recall, id)
    if not r:
        raise HTTPException(404, '召回不存在')
    items = db.scalars(select(RecallLot).where(RecallLot.recall_id == id)).all()
    notes = db.scalars(select(RecallNotification).where(RecallNotification.recall_id == id)).all()
    lots = {lot.id: lot_dict(lot) for lot in db.scalars(select(GoodsLot).where(
        GoodsLot.id.in_([x.lot_id for x in items]))).all()} if items else {}
    return {**recall_dict(r), 'summary': recall_service.affected_summary(db, r),
            'lots': [recall_lot_dict(x) | {'lot': lots.get(x.lot_id)} for x in items],
            'notifications': [notification_dict(n) for n in notes]}
@router.post('/recalls/{id}/retry')
def retry_recall(id: int, db=Depends(get_db), u=Depends(admin_only)):
    r = recall_service.resume_recall(db, id, u.email)
    db.commit()
    return recall_dict(r) | {'summary': recall_service.affected_summary(db, r)}
