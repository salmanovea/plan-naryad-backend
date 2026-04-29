#!/bin/bash
echo "Starting alembic migrations"
alembic upgrade head

echo "Starting FastAPI server"
uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1 --access-log --proxy-headers
