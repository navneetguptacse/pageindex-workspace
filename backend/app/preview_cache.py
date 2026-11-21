from functools import lru_cache
from random import randint
from time import monotonic

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.config import get_settings
from app.models import Document

MAX_VALUE_BYTES = 2 * 1024**2


class PreviewCache:
    def __init__(self, url: str, ttl: int):
        self.client = Redis.from_url(
            url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            retry=Retry(NoBackoff(), 0),
            max_connections=8,
        )
        self.ttl = ttl
        self.retry_at = 0.0

    def get(self, key: str) -> bytes | None:
        if monotonic() < self.retry_at:
            return None
        try:
            return self.client.get(key)
        except RedisError:
            self.retry_at = monotonic() + 5
            return None

    def set(self, key: str, value: bytes) -> None:
        if len(value) > MAX_VALUE_BYTES or monotonic() < self.retry_at:
            return
        try:
            self.client.set(key, value, ex=self.ttl - randint(0, self.ttl // 10))
        except RedisError:
            self.retry_at = monotonic() + 5


@lru_cache(maxsize=1)
def _cache(url: str, ttl: int) -> PreviewCache:
    return PreviewCache(url, ttl)


def preview_cache() -> PreviewCache | None:
    settings = get_settings()
    url = settings.redis_url.get_secret_value()
    return (
        _cache(url, settings.preview_cache_ttl_seconds)
        if url and settings.preview_cache_ttl_seconds
        else None
    )


def page_cache_key(document: Document, page: int, content: str) -> str:
    return f"pageindex:pdf:v1:{document.owner_id or 'local'}:{document.id}:{document.status}:{page}:{content}"
