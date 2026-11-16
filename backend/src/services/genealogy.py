"""货物谱系领域服务。

并发约定：所有会改动 available_quantity 的操作（split/merge/outbound）以及召回传播，
都先按货批 id 升序加行锁（SELECT ... FOR UPDATE），避免交叉等待导致的死锁；隔离货批
一律拒绝再被占用，确认召回后不会再放走受影响货物。
整单语义：任一来源可用数量不足或已被隔离，全部改动回滚，错误整单返回，不产生部分占用。
"""
import time
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from src.models import GoodsLot, LotEvent, LotEventLine
from src.constants.enums import LotStatus, GenealogyEventType
def _q(value):
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if value <= 0 or not value.is_finite():
        raise HTTPException(422, '数量须为大于 0 的有限数字')
    return value.quantize(Decimal('0.001'))
def _lock_lots(db, lot_ids):
    ids = sorted(set(lot_ids))
    lots = []
    for lid in ids:
        lot = db.scalar(select(GoodsLot).where(GoodsLot.id == lid).with_for_update())
        if lot is None:
            raise HTTPException(404, f'货批 {lid} 不存在')
        lots.append(lot)
    return lots
def _assert_usable(lot, need):
    if lot.status == LotStatus.quarantined.value:
        raise HTTPException(409, f'货批 {lot.code} 已被召回隔离，禁止拆分、合批或出库')
    if Decimal(lot.available_quantity) < need:
        raise HTTPException(409, f'货批 {lot.code} 可用数量不足，整单拒绝')
def _next_code(db, prefix):
    count = db.scalar(select(func.count()).select_from(GoodsLot)) or 0
    code = f'{prefix}{int(time.time())}-{count + 1:04d}'
    if db.scalar(select(GoodsLot.id).where(GoodsLot.code == code)):
        code = f'{prefix}{int(time.time()*1000)}-{count + 1:04d}'
    return code
def _add_line(db, event_id, direction, lot_id, quantity, destination=None):
    db.add(LotEventLine(event_id=event_id, direction=direction, lot_id=lot_id,
                        quantity=quantity, destination=destination))
def register(db, data, actor):
    quantity = _q(data.quantity)
    if data.dataset_id is not None:
        from src.models import Dataset
        if not db.get(Dataset, data.dataset_id):
            raise HTTPException(404, '绑定的测温批次不存在')
    code = data.code or _next_code(db, 'LOT-')
    if data.code and db.scalar(select(GoodsLot.id).where(GoodsLot.code == code)):
        raise HTTPException(422, f'货批号 {code} 已存在')
    lot = GoodsLot(code=code, name=data.name, dataset_id=data.dataset_id,
                   registered_quantity=quantity, available_quantity=quantity,
                   unit=data.unit, status=LotStatus.active.value, created_at=time.time())
    db.add(lot); db.flush()
    ev = LotEvent(type=GenealogyEventType.register.value, actor=actor,
                  note=f'登记测温批次对应货批：{data.name}', created_at=time.time())
    db.add(ev); db.flush()
    _add_line(db, ev.id, 'out', lot.id, quantity)
    return lot
def split(db, data, actor):
    outputs = [(x.lot_id, _q(x.quantity)) for x in data.outputs]
    if len(set(lid for lid, _ in outputs)) != len(outputs):
        raise HTTPException(422, '拆分行中的目标货批重复')
    if any(lid == data.source_lot_id for lid, _ in outputs):
        raise HTTPException(422, '不能拆分回源货批自身')
    source = _lock_lots(db, [data.source_lot_id])[0]
    total = sum((q for _, q in outputs), Decimal('0'))
    _assert_usable(source, total)
    targets = _lock_lots(db, [lid for lid, _ in outputs])
    now = time.time()
    ev = LotEvent(type=GenealogyEventType.split.value, actor=actor, note=data.note, created_at=now)
    db.add(ev); db.flush()
    _add_line(db, ev.id, 'in', source.id, total)
    source.available_quantity = Decimal(source.available_quantity) - total
    for lot, (_, q) in zip(targets, outputs):
        if lot.status == LotStatus.quarantined.value:
            raise HTTPException(409, f'目标货批 {lot.code} 已隔离，整单拒绝')
        lot.available_quantity = Decimal(lot.available_quantity) + q
        _add_line(db, ev.id, 'out', lot.id, q)
    return ev
def merge(db, data, actor):
    sources_in = [(x.lot_id, _q(x.quantity)) for x in data.sources]
    if len(set(lid for lid, _ in sources_in)) != len(sources_in):
        raise HTTPException(422, '合批来源货批重复')
    sources = _lock_lots(db, [lid for lid, _ in sources_in])
    by_id = {lot.id: lot for lot in sources}
    total = Decimal('0')
    for lid, q in sources_in:
        lot = by_id[lid]
        _assert_usable(lot, q)
        total += q
    code = data.output_code or _next_code(db, 'MRG-')
    if data.output_code and db.scalar(select(GoodsLot.id).where(GoodsLot.code == code)):
        raise HTTPException(422, f'合批货批号 {code} 已存在')
    out_lot = GoodsLot(code=code, name=data.output_name,
                       registered_quantity=Decimal('0'), available_quantity=total,
                       unit=data.unit, status=LotStatus.active.value, created_at=time.time())
    db.add(out_lot); db.flush()
    ev = LotEvent(type=GenealogyEventType.merge.value, actor=actor, note=data.note, created_at=time.time())
    db.add(ev); db.flush()
    for lid, q in sources_in:
        lot = by_id[lid]
        lot.available_quantity = Decimal(lot.available_quantity) - q
        _add_line(db, ev.id, 'in', lot.id, q)
    _add_line(db, ev.id, 'out', out_lot.id, total)
    return out_lot
def outbound(db, data, actor):
    if db.scalar(select(LotEvent.id).where(LotEvent.order_code == data.order_code,
                                           LotEvent.type == GenealogyEventType.outbound.value)):
        raise HTTPException(422, f'出库单号 {data.order_code} 已存在，避免重复提交')
    lines = []
    for x in data.lines:
        lines.append((x.lot_id, _q(x.quantity), x.destination))
    if len({(lid, dest) for lid, _, dest in lines}) != len(lines):
        raise HTTPException(422, '同一货批与去向的出库行重复，请合并数量')
    lots = _lock_lots(db, [lid for lid, _, _ in lines])
    by_id = {lot.id: lot for lot in lots}
    need = {}
    for lid, q, _ in lines:
        need[lid] = need.get(lid, Decimal('0')) + q
    for lid, q in need.items():
        _assert_usable(by_id[lid], q)
    ev = LotEvent(type=GenealogyEventType.outbound.value, order_code=data.order_code,
                  actor=actor, note=data.note, created_at=time.time())
    db.add(ev); db.flush()
    for lid, q, dest in lines:
        lot = by_id[lid]
        lot.available_quantity = Decimal(lot.available_quantity) - q
        _add_line(db, ev.id, 'in', lid, q, destination=dest)
    return ev
def descendants(db, root_ids):
    """沿拆合关系（事件 out 方向）收集全部后代，含根本身。"""
    reached = set()
    frontier = list(root_ids)
    while frontier:
        rows = db.execute(select(LotEventLine.lot_id, LotEventLine.event_id)
                          .where(LotEventLine.direction == 'in',
                                 LotEventLine.lot_id.in_(frontier))).all()
        event_ids = {eid for _, eid in rows}
        reached.update(frontier)
        if not event_ids:
            break
        outs = db.scalars(select(LotEventLine.lot_id).where(
            LotEventLine.direction == 'out', LotEventLine.event_id.in_(event_ids))).all()
        frontier = [lid for lid in outs if lid not in reached]
    return reached
def _trace(db, start_lot_id, find_direction, next_direction):
    """沿事件边 BFS。find_direction 是在当前货批上找的边方向，
    next_direction 是同一事件里继续走的对侧边方向。"""
    seen_events, seen_lots, frontier = set(), set(), [start_lot_id]
    while frontier:
        rows = db.scalars(select(LotEventLine).where(
            LotEventLine.direction == find_direction,
            LotEventLine.lot_id.in_(frontier))).all()
        event_ids = {r.event_id for r in rows} - seen_events
        if not event_ids:
            break
        next_frontier = []
        for eid in event_ids:
            seen_events.add(eid)
            for line in db.scalars(select(LotEventLine).where(LotEventLine.event_id == eid)).all():
                if line.direction == next_direction and line.lot_id not in seen_lots:
                    seen_lots.add(line.lot_id)
                    next_frontier.append(line.lot_id)
        frontier = next_frontier
    return seen_events
def genealogy_graph(db, lot_id):
    """返回某货批的上下游谱系事件。祖先链沿 out→in 回溯，后代链沿 in→out 追踪。"""
    up = _trace(db, lot_id, 'out', 'in')
    down = _trace(db, lot_id, 'in', 'out')
    result = []
    for eid in sorted(up | down):
        ev = db.get(LotEvent, eid)
        lines = db.scalars(select(LotEventLine).where(LotEventLine.event_id == eid)).all()
        direction = 'ancestor' if eid in up and eid not in down else (
            'descendant' if eid in down and eid not in up else 'both')
        result.append({'event': ev, 'lines': lines, 'direction': direction})
    return result
