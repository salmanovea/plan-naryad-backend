"""
FastAPI приложение План-наряд
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, ProgrammingError, DBAPIError
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import engine, Base, get_db
from .mock_data.seed import seed_database
from .mock_data.workforce_seed import seed_workforce

# Импортируем все роутеры
from .api import (
    housings,
    works,
    contractors,
    plans,
    facts,
    reconciliation,
    alerts,
    dashboard,
    workforce,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    print("Запуск приложения План-наряд...")
    
    # Создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Таблицы созданы")
    
    # Заполняем базу тестовыми данными если она пустая
    async for db in get_db():
        await seed_database(db)
        await seed_workforce(db)
        break
    
    print("Приложение готово к работе")
    
    yield
    
    # Shutdown
    print("Завершение работы приложения...")
    await engine.dispose()


# Создаём приложение
app = FastAPI(
    title="План-наряд API",
    description="API для управления план-нарядами строительных работ",
    version="1.0.0",
    lifespan=lifespan
)


# Глобальные обработчики ошибок для UUID валидации
@app.exception_handler(DataError)
async def data_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": "Некорректный формат данных (возможно, невалидный UUID)"})

@app.exception_handler(ProgrammingError) 
async def programming_error_handler(request, exc):
    if "invalid input syntax for type uuid" in str(exc):
        return JSONResponse(status_code=400, content={"detail": "Некорректный формат UUID"})
    raise exc

@app.exception_handler(DBAPIError)
async def dbapi_error_handler(request, exc):
    err = str(exc).lower()
    if "invalid uuid" in err or "invalid input" in err:
        return JSONResponse(status_code=400, content={"detail": "Некорректный формат UUID"})
    return JSONResponse(status_code=500, content={"detail": "Ошибка базы данных"})

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://emiltools.ru", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(housings.router)
app.include_router(works.router)
app.include_router(contractors.router)
app.include_router(plans.router)
app.include_router(facts.router)
app.include_router(reconciliation.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(workforce.router)


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "План-наряд API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    return {
        "status": "healthy",
        "database": "connected"
    }