"""质量审核放行接口：批次检查、样本修正与放行视图。

放行视图不是一张静态表：每个批次都带当前轮次的逐项结论、缺失环节和
报告项写入状态，前端据此解释每个槽位为什么已经入账或仍未入账。
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, PageResult
from app.services.quality_release import (
    ACTION_ALIASES, ACTIONS, MODULE, STATUS_ORDER, QualityReleaseService,
)

router = APIRouter(prefix="/api/quality_release", tags=["质量审核放行"])

service = QualityReleaseService()

LIST_FIELDS = ["批次编号", "指标批次", "说明"]


def query_filters(request: Request) -> dict[str, str]:
    return {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in LIST_FIELDS and value.strip()
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    keyword: str | None = Query(default=None, description="按批次编号检索"),
    status: str | None = Query(default=None, description="、".join(STATUS_ORDER)),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    """按批次字段、编号关键字与状态过滤放行批次。"""
    items, total = service.list_batches(
        filters=query_filters(request), keyword=keyword, status=status,
        page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    """下载当前筛选条件下的 UTF-8 CSV；必须声明在 /{entry_id} 之前。"""
    items, _ = service.list_batches(
        filters=query_filters(request), keyword=keyword, status=status,
        page=1, size=1000000,
    )
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "id", *LIST_FIELDS, "status", "检查轮次", "检查进度",
        "通过数", "超阈值数", "缺样本数", "缺失环节", "已入账项", "未入账项",
    ])
    for item in items:
        row = []
        for value in [
            item.get("id"), *(item.get(field, "") for field in LIST_FIELDS),
            item.get("status", ""), item.get("检查轮次", 0), item.get("检查进度", ""),
            item.get("通过数", 0), item.get("超阈值数", 0), item.get("缺样本数", 0),
            item.get("缺失环节", ""), item.get("已入账项", 0), item.get("未入账项", 0),
        ]:
            text = "" if value is None else str(value)
            row.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
        writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="quality_release.csv"'},
    )


@router.get("/publish-view", response_model=dict)
def publish_view() -> dict:
    """同一个放行视图的“能不能发布”摘要，供流式质检页面引用。"""
    items = service.publish_summary()
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "releasable": sum(1 for item in items if item["可发布"]),
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单个放行批次的检查视图、放行视图与报告项写入结果。"""
    entry = service.detail(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"放行批次 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: dict[str, object]) -> ActionResult:
    """登记一个放行批次，把监控对象、阈值和指标批次绑在一起。"""
    entry, message = service.create_batch(payload)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.detail(entry["id"]))


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: dict[str, object]) -> ActionResult:
    """开始检查、检查一项、完成检查、中断检查或重试检查。"""
    action = str(payload.get("action") or "").strip()
    action = ACTION_ALIASES.get(action, action)
    if action not in ACTIONS:
        return ActionResult(
            ok=False, message=f"动作「{action}」不属于质量审核放行可执行范围",
        )
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.detail(entry_id))


@router.post("/{entry_id}/samples", response_model=ActionResult)
def update_samples(entry_id: int, payload: dict[str, object]) -> ActionResult:
    """修正样本后旧结论失效，需要重新走一轮检查。"""
    samples = payload.get("samples")
    entry, message = service.update_samples(
        entry_id, samples if isinstance(samples, dict) else {},
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.detail(entry_id))


@router.post("/{entry_id}/write", response_model=ActionResult)
def write_batch(entry_id: int) -> ActionResult:
    """落盘入口的便捷别名：等价于数据落盘的批次写入。"""
    from app.services.sink_writer import ReleaseSinkWriter

    batch, message = ReleaseSinkWriter().write_batch(entry_id)
    entry = service.detail(entry_id)
    if batch is None or entry is None:
        return ActionResult(ok=False, message=message, entry=entry)
    return ActionResult(ok=True, message=message, entry=entry)


__all__ = ["router", "MODULE"]
