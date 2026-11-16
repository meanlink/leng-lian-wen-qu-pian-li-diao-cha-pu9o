import hashlib, json
from decimal import Decimal
def num(v):
    if isinstance(v, Decimal): return float(v)
    return v
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def lot_dict(lot):
    return {'id': lot.id, 'code': lot.code, 'name': lot.name, 'dataset_id': lot.dataset_id,
            'registered_quantity': num(lot.registered_quantity),
            'available_quantity': num(lot.available_quantity),
            'unit': lot.unit, 'status': lot.status,
            'created_at': lot.created_at, 'quarantined_at': lot.quarantined_at}
def event_line_dict(line):
    return {'id': line.id, 'event_id': line.event_id, 'direction': line.direction,
            'lot_id': line.lot_id, 'quantity': num(line.quantity), 'destination': line.destination}
def event_dict(ev, lines):
    return {'id': ev.id, 'type': ev.type, 'order_code': ev.order_code, 'note': ev.note,
            'actor': ev.actor, 'created_at': ev.created_at,
            'lines': [event_line_dict(x) for x in lines]}
def recall_dict(r):
    return {'id': r.id, 'reason': r.reason, 'job_id': r.job_id, 'dataset_id': r.dataset_id,
            'status': r.status, 'created_by': r.created_by, 'created_at': r.created_at,
            'confirmed_at': r.confirmed_at, 'finished_at': r.finished_at,
            'root_lot_ids': r.root_lot_ids or []}
def recall_lot_dict(x):
    return {'id': x.id, 'recall_id': x.recall_id, 'lot_id': x.lot_id, 'stage': x.stage,
            'frozen_available': num(x.frozen_available), 'quarantined_at': x.quarantined_at}
def notification_dict(n):
    return {'id': n.id, 'recall_id': n.recall_id, 'lot_id': n.lot_id, 'lot_code': n.lot_code,
            'event_id': n.event_id, 'order_code': n.order_code, 'destination': n.destination,
            'quantity': num(n.quantity), 'created_at': n.created_at}
