from src.models.dbo.base_model import Base  # noqa: F401
from src.models.dbo.mixins import IDMixin, SortOrderMixin, TimestampMixin  # noqa: F401

# Import all table modules so Alembic can detect every model via Base.metadata.
from src.models.dbo.tables.alert import Alert, AlertLevel, AlertType, RecipientRole  # noqa: F401
from src.models.dbo.tables.contractor import Contractor, ContractorAssignment  # noqa: F401
from src.models.dbo.tables.fact import FactSource, WorkFact  # noqa: F401
from src.models.dbo.tables.housing import Floor, Housing, Section  # noqa: F401
from src.models.dbo.tables.plan import PlanAdjustment, PlanItem, PlanSource, PlanStatus  # noqa: F401
from src.models.dbo.tables.reconciliation import (  # noqa: F401
    DailySummary,
    ReconciliationPattern,
    ReconciliationResult,
    ReconciliationStatus,
)
from src.models.dbo.tables.work import DependencyType, TechSequenceItem, WorkGroup, WorkType  # noqa: F401
from src.models.dbo.tables.workforce import (  # noqa: F401
    WfArticleMapping,
    WfBudgetItem,
    WfBudgetPeriod,
    WfChallenge,
    WfChallengeItem,
    WfContractorAssignment,
    WfHeadcountFact,
    WfHeadcountPlan,
    WfMobilizationCheckpoint,
    WfMobilizationPlan,
    WfProject,
    WfProjectObject,
    WfViolation,
    WfWorkforceNorm,
)
