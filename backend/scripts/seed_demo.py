import time, json
from decimal import Decimal
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import (User, Dataset, Job, Report, Delivery, Audit, GoodsLot, Recall)
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import genealogy
from src.services.recall import create_recall
from src.schemas.genealogy import (LotRegisterInput, SplitInput, MergeInput,
                                   OutboundInput, QuantityLine, OutboundLine, RecallInput)
from src.utils.security import hash_password
from src.utils.serialization import checksum
def seed_genealogy(db, dataset, admin):
    """演示一条可追查的谱系：测温登记 → 出库/拆分 → 合批 → 召回隔离。"""
    if db.scalar(select(GoodsLot.id).where(GoodsLot.code == 'LOT-DEMO-A')):
        return
    root = genealogy.register(db, LotRegisterInput(
        name='沪东 B 线试剂批 · 11 月', code='LOT-DEMO-A', dataset_id=dataset.id,
        quantity=Decimal('200'), unit='件'), 'seed')
    c1 = genealogy.register(db, LotRegisterInput(
        name='分装批 C1', code='LOT-DEMO-C1', quantity=Decimal('0.001'), unit='件'), 'seed')
    c2 = genealogy.register(db, LotRegisterInput(
        name='分装批 C2', code='LOT-DEMO-C2', quantity=Decimal('0.001'), unit='件'), 'seed')
    g1 = genealogy.register(db, LotRegisterInput(
        name='再分装批 G1', code='LOT-DEMO-G1', quantity=Decimal('0.001'), unit='件'), 'seed')
    db.flush()
    # 召回前已有出库去向
    genealogy.outbound(db, OutboundInput(order_code='OUT-DEMO-1', lines=[
        OutboundLine(lot_id=root.id, quantity=Decimal('40'), destination='南京中心医院')]), 'seed')
    genealogy.split(db, SplitInput(source_lot_id=root.id, outputs=[
        QuantityLine(lot_id=c1.id, quantity=Decimal('60')),
        QuantityLine(lot_id=c2.id, quantity=Decimal('50'))], note='分装线拆分'), 'seed')
    genealogy.split(db, SplitInput(source_lot_id=c1.id, outputs=[
        QuantityLine(lot_id=g1.id, quantity=Decimal('20'))], note='二次分装'), 'seed')
    merged = genealogy.merge(db, MergeInput(sources=[
        QuantityLine(lot_id=c2.id, quantity=Decimal('30')),
        QuantityLine(lot_id=g1.id, quantity=Decimal('10'))],
        output_name='合批试剂 M-DEMO', output_code='LOT-DEMO-M', unit='件'), 'seed')
    genealogy.outbound(db, OutboundInput(order_code='OUT-DEMO-2', lines=[
        OutboundLine(lot_id=c1.id, quantity=Decimal('15'), destination='苏州社区诊所')]), 'seed')
    db.flush()
    # 一条对照在库货批（不召回）
    genealogy.register(db, LotRegisterInput(
        name='沪东 A 线对照批', code='LOT-DEMO-OK', dataset_id=dataset.id,
        quantity=Decimal('120'), unit='件'), 'seed')
    db.flush()
    # 按温区调查结论发起召回：隔离 root 全部后代并通知既有出库
    create_recall(db, RecallInput(
        reason='沪东 B 线温区偏离（KS 显著、超温率升高），按调查发起召回',
        lot_ids=[root.id]), 'seed')
    db.add(Audit(actor='seed', action='demo.genealogy',
                 detail={'root': root.id, 'merged': merged.id}, at=time.time()))
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        admin=db.scalar(select(User).where(User.role=='admin'))
        seed_genealogy(db, d, admin)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,GoodsLot,Recall]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
