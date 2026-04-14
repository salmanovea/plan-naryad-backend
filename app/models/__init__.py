"""
SQLAlchemy модели для системы "План-наряд".
"""
from ..database import Base

# Импорт всех моделей
from .housing import Housing, Section, Floor
from .work import WorkGroup, WorkType, TechSequenceItem
from .contractor import Contractor, ContractorAssignment
from .plan import PlanItem, PlanAdjustment
from .fact import WorkFact as FactItem  # Alias for services compatibility
from .reconciliation import ReconciliationResult as ReconciliationItem, DailySummary
from .alert import Alert

# Re-export original names too
from .fact import WorkFact
from .reconciliation import ReconciliationResult

__all__ = [
    "Base",
    "Housing", "Section", "Floor",
    "WorkGroup", "WorkType", "TechSequenceItem",
    "Contractor", "ContractorAssignment",
    "PlanItem", "PlanAdjustment",
    "WorkFact", "FactItem",
    "ReconciliationResult", "ReconciliationItem", "DailySummary",
    "Alert",
]