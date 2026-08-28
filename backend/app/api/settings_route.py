"""设置相关 REST API：查询与更新（输出目录可配置）。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.settings.service import SettingsService
from app.schemas.settings import AppSettings, SettingsUpdateRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_settings(request: Request) -> SettingsService:
    return request.app.state.settings


SettingsDep = Annotated[SettingsService, Depends(get_settings)]


@router.get("", response_model=AppSettings)
def get_app_settings(settings: SettingsDep):
    return settings.get_settings()


@router.put("", response_model=AppSettings)
def update_settings(
    body: SettingsUpdateRequest,
    settings: SettingsDep,
):
    """更新设置（输出目录）：校验 → 持久化 → 返回新值。"""
    return settings.set_output_dir(body.output_dir)