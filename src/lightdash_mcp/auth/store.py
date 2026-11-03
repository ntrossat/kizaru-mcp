"""Redis storage, every value encrypted with Fernet. Token keys are stored as sha256 digests."""

import hashlib
from typing import TypeVar

from cryptography.fernet import Fernet
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.asyncio.lock import Lock

M = TypeVar("M", bound=BaseModel)

PREFIX = "lightdash-mcp"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, redis: Redis, fernet_key: str) -> None:
        self._redis = redis
        self._fernet = Fernet(fernet_key)

    def _key(self, kind: str, key: str) -> str:
        return f"{PREFIX}:{kind}:{key}"

    async def put(self, kind: str, key: str, value: BaseModel, ttl: int | None = None) -> None:
        data = self._fernet.encrypt(value.model_dump_json().encode())
        await self._redis.set(self._key(kind, key), data, ex=max(ttl, 1) if ttl is not None else None)

    async def get(self, kind: str, key: str, model: type[M]) -> M | None:
        data = await self._redis.get(self._key(kind, key))
        return None if data is None else model.model_validate_json(self._fernet.decrypt(data))

    async def pop(self, kind: str, key: str, model: type[M]) -> M | None:
        """Get and delete in one step, so a single-use value can't be used twice."""
        data = await self._redis.getdel(self._key(kind, key))
        return None if data is None else model.model_validate_json(self._fernet.decrypt(data))

    async def delete(self, kind: str, *keys: str) -> None:
        if keys:
            await self._redis.delete(*(self._key(kind, key) for key in keys))

    def lock(self, kind: str, key: str) -> Lock:
        return self._redis.lock(self._key(f"lock:{kind}", key), timeout=30, blocking_timeout=30)
