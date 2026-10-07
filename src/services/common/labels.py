"""Display labels for entities mirrored from Raport.

Kept in one place because the same rows are labelled by the plan, the reconciliation and
their filter dropdowns — a label that differs between them reads as different data.
"""

from typing import Optional

from src.models.dbo.tables.housing import Floor


def _is_number(name: str) -> bool:
    try:
        int(name)
    except ValueError:
        return False
    return True


def floor_label(floor: Optional[Floor]) -> Optional[str]:
    """The floor's Raport name verbatim; a bare number gets an «Этаж » prefix.

    Raport is the master system for the project structure (DEV-6938/6979): «Кровля» and
    the literal dash «-» (the housing-wide pseudo-floor) are shown exactly as stored.
    The only cosmetics allowed is prefixing a purely numeric name — «3» → «Этаж 3».
    `floor_number` is Raport's sort_order, an ordering key — never part of the label.
    """
    if floor is None:
        return None
    name = (floor.name or "").strip()
    if not name:
        return "—"
    if _is_number(name):
        return f"Этаж {name}"
    return name
