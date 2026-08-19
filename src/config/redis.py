"""
Redis client.

Copied into src/config/redis.py by the initial-setup skill.
Do not edit this template inside the skill — adjust the copy in src/config/.
"""

from redis import asyncio as aioredis

from src.config.settings import app_config

redis = aioredis.from_url(app_config.redis_url)
