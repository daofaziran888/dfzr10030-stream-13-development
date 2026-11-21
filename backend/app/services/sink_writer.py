"""数据落盘业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "sink_writer"
LIST_FIELDS = ["槽位编号", "输出类型", "目标地址", "写入模式", "批次大小", "刷新间隔", "压缩算法", "分区策略"]
REQUIRED_FIELDS = ["槽位编号", "输出类型", "目标地址"]
STATUS_ORDER = ["待配置", "写入中", "已暂停", "写入失败"]
ACTION_RULES = {"启动写入": "写入中", "暂停写入": "已暂停", "标记失败": "写入失败"}
NEGATIVE_ACTIONS = []


class SinkWriterService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for field, expected in (filters or {}).items():
            rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
        if keyword:
            rows = [row for row in rows if keyword.casefold() in str(row.get("槽位编号", "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = (page - 1) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in LIST_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"输出槽位 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据落盘可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"输出槽位已{action}"


# ---------------------------------------------------------------------------
# 质量审核放行批次的落盘消费
#
# 落盘只消费 status == "已放行" 且放行依据与当前检查轮次一致的批次；
# 每个报告项按槽位实际状态决定是否入账，结果写回批次的 写入结果。
# ---------------------------------------------------------------------------
from datetime import datetime  # noqa: E402

from app.services import quality_release as _release_module  # noqa: E402


def _release_service() -> Any:
    """运行时取服务实例，避免模块导入顺序影响路由注册。"""
    return _release_module.service


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ReleaseSinkWriter:
    """把质量审核放行批次落到已经启动写入的输出槽位。"""

    def list_batches(self) -> list[dict[str, Any]]:
        batches: list[dict[str, Any]] = []
        for batch in store.rows("quality_release"):
            availability = _release_service().write_availability(batch)
            reports = _release_service().report_view(batch)
            availability["报告项"] = reports
            availability["已入账项"] = sum(
                1 for item in reports if item["写入状态"] == "已入账"
            )
            availability["未入账项"] = sum(
                1 for item in reports if item["写入状态"] != "已入账"
            )
            batches.append(availability)
        return batches

    def write_batch(self, batch_id: int) -> tuple[dict[str, Any] | None, str]:
        batch = store.find("quality_release", batch_id)
        if batch is None:
            return None, f"放行批次 {batch_id} 不存在或已归档"

        availability = _release_service().write_availability(batch)
        if not availability["可写入"]:
            return None, (
                f"批次「{batch.get('批次编号')}」当前状态为 {batch.get('status')}，"
                f"不能落盘：{availability['不可写入原因']}"
            )

        batch["写入轮次"] = int(batch.get("写入轮次", 0)) + 1
        write_round = batch["写入轮次"]
        release_round = availability["检查轮次"]
        previous = list(batch.get("写入结果", []))
        results: list[dict[str, Any]] = []
        indexed = {
            (str(item.get("槽位编号", "")), str(item.get("指标编号", ""))): item
            for item in previous
        }

        slots = {str(row.get("槽位编号", "")): row for row in store.rows(MODULE)}
        accepted = 0
        failed = 0
        for report in batch.get("报告项", []):
            slot_no = str(report.get("槽位编号", ""))
            metric_no = str(report.get("指标编号", ""))
            existing = indexed.get((slot_no, metric_no))
            if existing is not None and existing.get("写入状态") == "已入账":
                # 已经入账的项不重复写，重跑只补仍未入账的范围。
                results.append(dict(existing))
                accepted += 1
                continue

            slot = slots.get(slot_no)
            if slot is None:
                written, reason = False, f"输出槽位 {slot_no} 不存在，无法写入"
            elif slot.get("status") != "写入中":
                written, reason = False, (
                    f"输出槽位 {slot_no} 当前为「{slot.get('status')}」，"
                    f"需要先启动写入"
                )
            else:
                written, reason = True, ""

            record = {
                "槽位编号": slot_no,
                "指标编号": metric_no,
                "指标名称": report.get("指标名称"),
                "监控对象": report.get("监控对象"),
                "写入状态": "已入账" if written else "未入账",
                "说明": reason,
                "写入轮次": write_round,
                "放行轮次": release_round,
                "写入时间": _now() if written else None,
            }
            if existing is None:
                results.append(record)
                indexed[(slot_no, metric_no)] = record
            else:
                kept = dict(record)
                kept["首次写入轮次"] = existing.get("首次写入轮次") or existing.get("写入轮次")
                retained = dict(existing)
                retained.update(kept)
                results.append(retained)
                indexed[(slot_no, metric_no)] = retained
            if written:
                accepted += 1
            else:
                failed += 1

        batch["写入结果"] = results
        total = len(batch.get("报告项", []))
        if accepted >= total and failed == 0:
            batch["落盘状态"] = "全部入账"
            message = f"第 {write_round} 次落盘完成：{accepted}/{total} 个报告项已入账"
        elif accepted:
            batch["落盘状态"] = "部分入账"
            message = (
                f"第 {write_round} 次落盘：{accepted}/{total} 个报告项已入账，"
                f"{failed} 项待补齐"
            )
        else:
            batch["落盘状态"] = "未入账"
            message = f"第 {write_round} 次落盘：{total} 个报告项均未入账"
        batch["落盘结论"] = message
        return batch, message
