"""能力探测：已注册解析器清单（前端据此展示支持的链接形态）。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.url.registry import UrlParserRegistry

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def get_registry(request: Request) -> UrlParserRegistry:
    return request.app.state.registry


RegistryDep = Annotated[UrlParserRegistry, Depends(get_registry)]


@router.get("")
def capabilities(registry: RegistryDep):
    return {"parsers": registry.capabilities()}