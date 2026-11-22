from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.config import get_settings
from app.database import current_workspace
from app.provider_checks import provider_failure
from app.provider_settings import workspace_pageindex_key

if TYPE_CHECKING:
    from pageindex import PageExtractClient, PageIndexClient, PageSearchClient

logger = logging.getLogger(__name__)


@contextmanager
def provider_request(operation: str, *, missing_ok: bool = False) -> Iterator[None]:
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        if missing_ok and getattr(exc, "status_code", None) == 404:
            return
        if current_workspace.get() is None:
            logger.exception("PageIndex %s failed", operation)
        else:
            logger.warning("Workspace %s failed (%s)", operation, type(exc).__name__)
            if getattr(exc, "status_code", None) in {401, 402, 403, 429}:
                raise provider_failure("PageIndex", exc) from None
        raise HTTPException(
            status_code=502, detail=f"PageIndex {operation} failed"
        ) from exc


def provider_key() -> str:
    settings = get_settings()
    workspace = current_workspace.get()
    if workspace is None:
        return settings.pageindex_api_key
    return workspace_pageindex_key(workspace, settings)


def get_pageindex_client() -> PageIndexClient:
    from pageindex import PageIndexClient

    if current_workspace.get() is not None:
        return PageIndexClient(index={"api_key": provider_key()})

    settings = get_settings()
    if settings.deepseek_api_key:
        os.environ.setdefault("DEEPSEEK_API_KEY", settings.deepseek_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

    key = provider_key()
    index = {"api_key": key} if key else "cloud"
    return PageIndexClient(index=index, chat=settings.chat_model)


def get_search_client() -> PageSearchClient:
    from pageindex import PageSearchClient

    return PageSearchClient(api_key=provider_key() or None)


def get_extract_client() -> PageExtractClient:
    from pageindex import PageExtractClient

    return PageExtractClient(api_key=provider_key() or None)
