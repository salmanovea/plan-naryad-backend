from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from typing import List, Optional

from ..database import get_session
from ..models import housing, work, contractor, plan, fact, reconciliation, alert
from ..schemas import housing as schemas
from ..services import autogeneration, reconciliation as recon_service, alerts as alert_service


router = APIRouter(prefix="/api/v1/housings", tags=["housings"])


@router.get("/", response_model=List[schemas.Housing])
async def get_housings(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Получить список корпусов"""
    result = await session.execute(
        select(housing.Housing).offset(skip).limit(limit)
    )
    housings = result.scalars().all()
    return housings


@router.get("/{housing_id}", response_model=schemas.Housing)
async def get_housing(
    housing_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить корпус по ID"""
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    housing_obj = result.scalar_one_or_none()
    
    if not housing_obj:
        raise HTTPException(status_code=404, detail="Housing not found")
    
    return housing_obj


@router.get("/{housing_id}/structure", response_model=schemas.HousingStructure)
async def get_housing_structure(
    housing_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Получить структуру корпуса (секции + этажи)"""
    # Получаем корпус
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    housing_obj = result.scalar_one_or_none()
    
    if not housing_obj:
        raise HTTPException(status_code=404, detail="Housing not found")
    
    # Получаем секции
    result = await session.execute(
        select(housing.Section)
        .where(housing.Section.housing_id == housing_id)
        .order_by(housing.Section.section_number)
    )
    sections = result.scalars().all()
    
    # Собираем структуру
    structure_sections = []
    for section in sections:
        # Получаем этажи для секции
        result = await session.execute(
            select(housing.Floor)
            .where(housing.Floor.section_id == section.id)
            .order_by(housing.Floor.floor_number)
        )
        floors = result.scalars().all()
        
        structure_sections.append({
            "section_id": section.id,
            "section_name": section.name,
            "floors": [
                {
                    "floor_id": f.id,
                    "floor_number": f.floor_number
                }
                for f in floors
            ]
        })
    
    return schemas.HousingStructure(
        housing_id=housing_obj.id,
        housing_name=housing_obj.name,
        complex_name=housing_obj.complex_name,
        sections=structure_sections
    )


@router.post("/", response_model=schemas.Housing)
async def create_housing(
    housing_data: schemas.HousingCreate,
    session: AsyncSession = Depends(get_session)
):
    """Создать новый корпус"""
    db_housing = housing.Housing(**housing_data.dict())
    session.add(db_housing)
    await session.commit()
    await session.refresh(db_housing)
    return db_housing


@router.put("/{housing_id}", response_model=schemas.Housing)
async def update_housing(
    housing_id: str,
    housing_update: schemas.HousingUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Обновить корпус"""
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    db_housing = result.scalar_one_or_none()
    
    if not db_housing:
        raise HTTPException(status_code=404, detail="Housing not found")
    
    update_data = housing_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_housing, field, value)
    
    await session.commit()
    await session.refresh(db_housing)
    return db_housing


@router.delete("/{housing_id}")
async def delete_housing(
    housing_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Удалить корпус"""
    result = await session.execute(
        select(housing.Housing).where(housing.Housing.id == housing_id)
    )
    db_housing = result.scalar_one_or_none()
    
    if not db_housing:
        raise HTTPException(status_code=404, detail="Housing not found")
    
    await session.delete(db_housing)
    await session.commit()
    
    return {"message": "Housing deleted successfully"}