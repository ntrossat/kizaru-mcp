"""Redis storage, every value encrypted with Fernet. Token keys are stored as sha256 digests."""

import hashlib
from typing import TypeVar

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.asyncio.lock import Lock

M = TypeVar("M", bound=BaseModel)

PREFIX = "kizaru-mcp"
LOCK_TIMEOUT = 30


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

    def _load(self, data: bytes | None, model: type[M]) -> M | None:
        """A value encrypted with another key, as after FERNET_KEY changes, counts as missing: clients sign in again."""
        if data is None:
            return None
        try:
            return model.model_validate_json(self._fernet.decrypt(data))
        except InvalidToken:
            return None

    async def get(self, kind: str, key: str, model: type[M]) -> M | None:
        return self._load(await self._redis.get(self._key(kind, key)), model)

    async def pop(self, kind: str, key: str, model: type[M]) -> M | None:
        """Get and delete in one step, so a single-use value can't be used twice."""
        return self._load(await self._redis.getdel(self._key(kind, key)), model)

    async def touch(self, kind: str, key: str, ttl: int) -> None:
        await self._redis.expire(self._key(kind, key), ttl)

    async def delete(self, kind: str, key: str) -> None:
        await self._redis.delete(self._key(kind, key))

    async def ping(self) -> None:
        await self._redis.ping()

    def lock(self, kind: str, key: str) -> Lock:
        return self._redis.lock(self._key(f"lock:{kind}", key), timeout=LOCK_TIMEOUT, blocking_timeout=LOCK_TIMEOUT)
