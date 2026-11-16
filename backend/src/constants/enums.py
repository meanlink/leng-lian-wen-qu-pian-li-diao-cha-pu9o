from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
# 货物批次状态：active 可用于拆合/出库，quarantined 已被召回隔离
class LotStatus(str, Enum):
    active = 'active'
    quarantined = 'quarantined'
# 谱系事件类型：register 登记测温批次 / split 拆分 / merge 合批 / outbound 出库
class GenealogyEventType(str, Enum):
    register = 'register'
    split = 'split'
    merge = 'merge'
    outbound = 'outbound'
# 召回状态：propagating 隔离传播中（中断可恢复），completed 全部后代核对完成
class RecallStatus(str, Enum):
    propagating = 'propagating'
    completed = 'completed'
class RecallStage(str, Enum):
    root = 'root'
    descendant = 'descendant'
    outbound = 'outbound'
