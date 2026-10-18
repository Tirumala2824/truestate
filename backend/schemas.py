from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TransactionInput(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    supplier_id: str = Field(min_length=1, max_length=150)
    supplier_name: str = Field(min_length=1, max_length=250)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    occurred_at: datetime
    reference: str = Field(default='', max_length=200)
    account_fingerprint: str = Field(min_length=8, max_length=128)
    previous_account_fingerprint: str | None = Field(default=None, max_length=128)
    document_ids: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('occurred_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('occurred_at must include a timezone')
        return value


class Finding(StrictModel):
    summary: str = Field(max_length=3000)
    risk: Literal['low', 'medium', 'high', 'unknown']
    evidence_ids: list[str] = Field(max_length=40)
    policy_ids: list[str] = Field(max_length=20)
    gaps: list[str] = Field(max_length=20)
    contradictions: list[str] = Field(max_length=20)
    obligations: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)


class Resolution(StrictModel):
    summary: str = Field(max_length=4000)
    disposition: Literal['ready', 'hold', 'needs_evidence', 'review']
    evidence_ids: list[str] = Field(max_length=40)
    next_steps: list[str] = Field(max_length=20)
    disagreements: list[str] = Field(max_length=20)


class ExplainInput(StrictModel):
    section: Literal['decision', 'evidence', 'policy', 'next_steps']


class DecisionInput(StrictModel):
    disposition: Literal['ready', 'hold']
    reason: str = Field(min_length=15, max_length=2000)
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
