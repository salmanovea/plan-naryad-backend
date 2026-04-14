from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID
from typing import Optional, List
from decimal import Decimal


class PlanGenerateRequest(BaseModel):
    """Запрос на генерацию план-наряда"""
    date: date
    housing_id: UUID


class PlanConfirmRequest(BaseModel):
    """Подтверждение план-наряда РС"""
    confirmed_by: str = "rs-user"
    comment: Optional[str] = None


class PlanAdjustRequest(BaseModel):
    """Корректировка план-наряда РС"""
    changes: list = []
    reason: str = ""
    adjusted_by: str = "rs-user"


class PlanItem(BaseModel):
    """Элемент план-наряда"""
    id: UUID
    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    planned_volume: Decimal
    unit: str
    rs_confirmed: bool = False
    source: str = "auto"
    work_name: Optional[str] = None
    section_name: Optional[str] = None
    floor_number: Optional[int] = None

    class Config:
        from_attributes = True


class DailyPlanResponse(BaseModel):
    """Ответ: план-наряд на день"""
    date: date
    housing_id: str
    housing_name: Optional[str] = None
    total_items: int = 0
    contractors: list = []
    items: List[PlanItem] = []


class ContractorPlanResponse(BaseModel):
    """Ответ: план-наряд для конкретного подрядчика"""
    date: date
    contractor_id: UUID
    contractor_name: Optional[str] = None
    housing_id: Optional[str] = None
    items: List[PlanItem] = []
    total_items: int = 0


class RSStatsResponse(BaseModel):
    """Статистика корректировок РС"""
    rs_user_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_plans: int = 0
    total_adjustments: int = 0
    deviation_rate: Decimal = Decimal("0")
    top_adjustment_reasons: list = []
