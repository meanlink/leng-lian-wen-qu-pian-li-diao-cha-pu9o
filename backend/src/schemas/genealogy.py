from decimal import Decimal
from pydantic import BaseModel, Field
class LotRegisterInput(BaseModel):
    code: str | None = Field(default=None, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    dataset_id: int | None = None
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default='件', max_length=16)
class QuantityLine(BaseModel):
    lot_id: int
    quantity: Decimal = Field(gt=0)
class SplitInput(BaseModel):
    source_lot_id: int
    outputs: list[QuantityLine] = Field(min_length=1)
    note: str = Field(default='', max_length=300)
class MergeInput(BaseModel):
    sources: list[QuantityLine] = Field(min_length=2)
    output_name: str = Field(min_length=2, max_length=160)
    output_code: str | None = Field(default=None, max_length=60)
    unit: str = Field(default='件', max_length=16)
    note: str = Field(default='', max_length=300)
class OutboundLine(BaseModel):
    lot_id: int
    quantity: Decimal = Field(gt=0)
    destination: str = Field(min_length=1, max_length=200)
class OutboundInput(BaseModel):
    order_code: str = Field(min_length=2, max_length=60)
    lines: list[OutboundLine] = Field(min_length=1)
    note: str = Field(default='', max_length=300)
class RecallInput(BaseModel):
    reason: str = Field(min_length=2, max_length=300)
    lot_ids: list[int] = Field(min_length=1)
    job_id: int | None = None
    dataset_id: int | None = None
