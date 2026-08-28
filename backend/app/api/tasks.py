"""任务相关 REST API。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app.api.errors import ApiError
from app.core.task.manager import TaskManager
from app.core.url.base import UnsupportedUrlError
from app.core.url.registry import UrlParserRegistry
from app.schemas.task import TaskCreateRequest, TaskResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_registry(request: Request) -> UrlParserRegistry:
    return request.app.state.registry


def get_tasks(request: Request) -> TaskManager:
    return request.app.state.tasks


RegistryDep = Annotated[UrlParserRegistry, Depends(get_registry)]
TasksDep = Annotated[TaskManager, Depends(get_tasks)]


@router.post("", response_model=list[TaskResponse], status_code=201)
def create_tasks(
    body: TaskCreateRequest,
    registry: RegistryDep,
    tasks: TasksDep,
):
    """提交 URL（可多个）：解析并入队；解析失败返回业务码，不返回 500。"""
    created: list[TaskResponse] = []
    for url in body.urls:
        url = url.strip()
        if not url:
            continue
        try:
            request = registry.dispatch(url)
        except UnsupportedUrlError as e:
            raise ApiError("UNSUPPORTED_URL", str(e), status_code=422)
        # 任务级格式选项覆盖解析器默认（默认 mp3/192）
        request.options.update(
            {"audio_format": body.audio_format, "audio_quality": body.audio_quality}
        )
        task = tasks.enqueue(url, request)
        created.append(tasks.to_response(task))
    if not created:
        raise ApiError("EMPTY_URLS", "没有可创建的任务", status_code=422)
    return created


@router.get("", response_model=list[TaskResponse])
def list_tasks(tasks: TasksDep):
    return [tasks.to_response(t) for t in tasks.list()]


@router.delete("/{task_id}", response_model=TaskResponse)
def cancel_task(task_id: str, tasks: TasksDep):
    task = tasks.cancel(task_id)
    if task is None:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    return tasks.to_response(task)


@router.get("/{task_id}/file")
def download_file(task_id: str, tasks: TasksDep):
    task = tasks.get(task_id)
    if task is None:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    if task.file_path is None:
        raise ApiError("FILE_NOT_READY", "任务尚未完成，无成品文件", status_code=409)
    return FileResponse(task.file_path, filename=task.file_path.rsplit("/", 1)[-1])