"""Display labels for entities mirrored from Raport.

Kept in one place because the same rows are labelled by the plan, the reconciliation and
their filter dropdowns — a label that differs between them reads as different data.
"""

from typing import Optional

from src.models.dbo.tables.housing import Floor

# Raport stores an unnamed floor as a literal dash (1787 of 20402 rows), which is not a
# label a user can act on. Anything in this set counts as «no name given».
_EMPTY_NAMES = {"", "-", "—", "–"}


def floor_label(floor: Optional[Floor]) -> Optional[str]:
    """«Кровля», «площадка/нулевой цикл» — or «Этаж 3» when Raport gave no name."""
    if floor is None:
        return None
    name = (floor.name or "").strip()
    if name and name not in _EMPTY_NAMES:
        return name
    if floor.floor_number is not None:
        return f"Этаж {floor.floor_number}"
    return None
