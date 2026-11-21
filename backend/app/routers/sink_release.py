"""数据落盘消费质量审核放行批次：按批次写入报告项并回写批次结论。

路径挂在 /api/sink_writer/releases 下，与输出槽位 CRUD 的 /{entry_id}
分开注册，避免 “releases” 被当成槽位 id 解析。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ActionResult
from app.services.sink_writer import ReleaseSinkWriter

router = APIRouter(prefix="/api/sink_writer/releases", tags=["数据落盘"])

writer = ReleaseSinkWriter()


@router.get("", response_model=dict)
def list_release_batches() -> dict:
    """列出质量审核放行批次及每个报告项的实际写入结果。"""
    items = writer.list_batches()
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "releasable": sum(1 for item in items if item["可写入"]),
    }


@router.post("/{batch_id}/write", response_model=ActionResult)
def write_release_batch(batch_id: int) -> ActionResult:
    """按批次写入报告项；未放行或放行依据失效的批次会被明确拒绝。"""
    batch, message = writer.write_batch(batch_id)
    if batch is None:
        return ActionResult(ok=False, message=message)
    entry = next(
        (item for item in writer.list_batches() if item["id"] == batch_id), None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"放行批次 {batch_id} 不存在或已归档")
    return ActionResult(ok=True, message=message, entry=entry)
