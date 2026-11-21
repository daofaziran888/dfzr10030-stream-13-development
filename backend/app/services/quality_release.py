"""质量审核放行业务规则：批次检查、放行判定和视图口径都收在这里。

一个放行批次把三类东西绑在一起：

* 监控对象与检查阈值（``检查项``）；
* 准备落盘的指标批次（``指标批次``）及其报告项（``报告项``）；
* 本次检查的逐项结论和放行依据（``当前检查`` / ``放行依据``）。

放行只认“本批次当前轮次已经完成的检查”：中断的轮次、上一轮的合格结论、
其它批次的结论都不能作为依据。落盘只消费 ``status == "已放行"`` 的批次。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "quality_release"
LIST_FIELDS = ["批次编号", "指标批次", "说明"]

# 批次状态。只有「已放行」允许下游落盘。
STATUS_PENDING = "待检查"
STATUS_CHECKING = "检查中"
STATUS_INTERRUPTED = "检查中断"
STATUS_RELEASED = "已放行"
STATUS_REJECTED = "拒绝放行"
STATUS_MISSING = "缺少样本"
STATUS_ORDER = [
    STATUS_PENDING, STATUS_CHECKING, STATUS_INTERRUPTED,
    STATUS_RELEASED, STATUS_REJECTED, STATUS_MISSING,
]

VERDICT_PASS = "通过"
VERDICT_OVER = "超阈值"
VERDICT_MISSING = "缺少样本"
VERDICT_PENDING = "未检查"

ACTION_START = "开始检查"
ACTION_STEP = "检查一项"
ACTION_FINISH = "完成检查"
ACTION_INTERRUPT = "中断检查"
ACTION_RETRY = "重试检查"
ACTIONS = [ACTION_START, ACTION_STEP, ACTION_FINISH, ACTION_INTERRUPT, ACTION_RETRY]
# 兼容页面以外的调用口径，统一收敛到上面五个动作。
ACTION_ALIASES = {
    "发起检查": ACTION_START,
    "启动检查": ACTION_START,
    "继续检查": ACTION_STEP,
    "检查下一项": ACTION_STEP,
    "结束检查": ACTION_FINISH,
    "检查完成": ACTION_FINISH,
    "停止检查": ACTION_INTERRUPT,
    "中断": ACTION_INTERRUPT,
    "重试": ACTION_RETRY,
    "重新检查": ACTION_RETRY,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _item_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("监控对象", "")), str(item.get("检查项", "")))


def _result_key(result: dict[str, Any]) -> tuple[str, str]:
    return (str(result.get("监控对象", "")), str(result.get("检查项", "")))


def evaluate_sample(item: dict[str, Any]) -> dict[str, Any]:
    """按当前样本和阈值给出单项结论，缺测与超阈值分开表达。"""
    monitor = str(item.get("监控对象", ""))
    check = str(item.get("检查项", ""))
    sample = _num(item.get("样本值"))
    low = _num(item.get("阈值下限"))
    high = _num(item.get("阈值上限"))
    threshold = {"下限": low, "上限": high}

    if sample is None:
        return {
            "监控对象": monitor, "检查项": check, "结论": VERDICT_MISSING,
            "当前值": item.get("样本值"), "阈值": threshold,
            "说明": "本批次没有采集到该对象的样本，无法判断是否合格",
        }
    if high is not None and sample > high:
        return {
            "监控对象": monitor, "检查项": check, "结论": VERDICT_OVER,
            "当前值": sample, "阈值": threshold,
            "说明": f"样本 {sample:g} 高于上限 {high:g}",
        }
    if low is not None and sample < low:
        return {
            "监控对象": monitor, "检查项": check, "结论": VERDICT_OVER,
            "当前值": sample, "阈值": threshold,
            "说明": f"样本 {sample:g} 低于下限 {low:g}",
        }
    return {
        "监控对象": monitor, "检查项": check, "结论": VERDICT_PASS,
        "当前值": sample, "阈值": threshold,
        "说明": f"样本 {sample:g} 落在阈值区间内",
    }


class QualityReleaseService:
    # ------------------------------------------------------------------
    # 基础读取
    # ------------------------------------------------------------------
    def list_batches(
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
            rows = [
                row for row in rows
                if expected.casefold() in str(row.get(field, "")).casefold()
            ]
        if keyword:
            rows = [row for row in rows if keyword.casefold() in str(row.get("批次编号", "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = (page - 1) * size
        return [self.decorate(row) for row in rows[start:start + size]], total

    def get_batch(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def list_release_batches(self) -> list[dict[str, Any]]:
        """供数据落盘消费：只暴露放行判断所需字段和可写入结论。"""
        return [self.write_availability(row) for row in store.rows(MODULE)]

    # ------------------------------------------------------------------
    # 视图口径
    # ------------------------------------------------------------------
    def check_view(self, batch: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = list(batch.get("检查项", []))
        current = batch.get("当前检查")
        results: list[dict[str, Any]] = list(current.get("检查项结果", [])) if current else []
        result_map = {_result_key(result): result for result in results}

        rows: list[dict[str, Any]] = []
        missing_objects: list[str] = []
        for item in items:
            result = result_map.get(_item_key(item))
            if result is None:
                missing_objects.append(str(item.get("监控对象", "")))
            low = _num(item.get("阈值下限"))
            high = _num(item.get("阈值上限"))
            rows.append({
                "监控对象": item.get("监控对象"),
                "检查项": item.get("检查项"),
                "阈值上限": item.get("阈值上限"),
                "阈值下限": item.get("阈值下限"),
                "阈值": f"[{low:g}, {high:g}]" if low is not None and high is not None else "—",
                "样本值": item.get("样本值"),
                "结论": result["结论"] if result else VERDICT_PENDING,
                "结论说明": result["说明"] if result else "本轮尚未检查到该对象",
            })

        total = len(items)
        checked = len(results)
        round_no = current.get("轮次") if current else int(batch.get("检查轮次", 0))
        state = current.get("状态") if current else "未开始"
        counts = {
            VERDICT_PASS: sum(1 for result in results if result.get("结论") == VERDICT_PASS),
            VERDICT_OVER: sum(1 for result in results if result.get("结论") == VERDICT_OVER),
            VERDICT_MISSING: sum(1 for result in results if result.get("结论") == VERDICT_MISSING),
        }

        if current is None:
            prefix = f"第 {round_no} 轮已失效，" if round_no else ""
            gap = f"{prefix}尚未开始新一轮检查，缺少全部 {total} 个对象的结论"
        elif checked < total:
            gap = (
                f"第 {round_no} 轮只完成 {checked}/{total}，"
                f"缺少 {'、'.join(missing_objects)} 的结论"
            )
        elif counts[VERDICT_MISSING]:
            missing_names = [
                str(result.get("监控对象")) for result in results
                if result.get("结论") == VERDICT_MISSING
            ]
            gap = f"第 {round_no} 轮已检查完，但 {'、'.join(missing_names)} 缺少样本"
        else:
            gap = "无"

        return {
            "轮次": round_no,
            "状态": state,
            "进度": f"{checked}/{total}",
            "已检查": checked,
            "总数": total,
            "通过": counts[VERDICT_PASS],
            "超阈值": counts[VERDICT_OVER],
            "缺少样本": counts[VERDICT_MISSING],
            "缺失环节": gap,
            "检查项": rows,
            "未检查对象": missing_objects if checked < total else [],
        }

    def decision(self, batch: dict[str, Any]) -> dict[str, Any]:
        view = self.check_view(batch)
        current = batch.get("当前检查")
        status = str(batch.get("status", STATUS_PENDING))
        round_no = view["轮次"]
        reasons: list[str] = []

        if status == STATUS_RELEASED:
            text = f"第 {round_no} 轮检查全部通过，允许下游落盘"
        elif status == STATUS_REJECTED:
            text = f"第 {round_no} 轮检查有 {view['超阈值']} 个对象超阈值，不能放行"
        elif status == STATUS_MISSING:
            text = f"第 {round_no} 轮检查有 {view['缺少样本']} 个对象缺少样本，不能放行"
        elif status == STATUS_INTERRUPTED:
            text = f"第 {round_no} 轮检查中断于 {view['进度']}，本轮不能放行"
        elif status == STATUS_CHECKING:
            text = f"第 {round_no} 轮检查进行中（{view['进度']}），本轮不能放行"
        else:
            text = "尚未开始检查，没有可用的放行依据"

        conflict = view["通过"] > 0 and view["超阈值"] > 0
        conflict_text = ""
        if conflict:
            conflict_text = (
                f"{view['通过']} 个对象已通过，但同批口径要求全部监控对象合格，"
                f"本批仍不能放行；准时出数与同批口径在这里冲突"
            )
            reasons.append(conflict_text)
        if view["缺少样本"]:
            reasons.append(f"{view['缺少样本']} 个对象缺测，补样本后重试检查才能判断")
        if view["未检查对象"]:
            reasons.append("本轮检查未齐，缺少 " + "、".join(view["未检查对象"]))

        evidence = batch.get("放行依据")
        return {
            "状态": status,
            "轮次": round_no,
            "进度": view["进度"],
            "结论说明": text,
            "冲突": conflict,
            "冲突说明": conflict_text,
            "阻断原因": reasons,
            "放行依据": evidence,
            "检查完成": bool(current and current.get("状态") == "完成"),
        }

    def report_view(self, batch: dict[str, Any]) -> list[dict[str, Any]]:
        view = self.check_view(batch)
        verdict_by_object = {
            str(item["监控对象"]): item for item in view["检查项"]
        }
        status = str(batch.get("status", STATUS_PENDING))
        decision = self.decision(batch)

        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for result in batch.get("写入结果", []):
            latest[(str(result.get("槽位编号", "")), str(result.get("指标编号", "")))] = result

        reports: list[dict[str, Any]] = []
        for item in batch.get("报告项", []):
            slot = str(item.get("槽位编号", ""))
            metric = str(item.get("指标编号", ""))
            monitor = str(item.get("监控对象", ""))
            check = verdict_by_object.get(monitor, {})
            verdict = str(check.get("结论", VERDICT_PENDING))
            write = latest.get((slot, metric))

            if write is not None and write.get("写入状态") == "已入账":
                write_status = "已入账"
                reason = ""
                evidence = (
                    f"第 {write.get('放行轮次')} 轮放行依据 + "
                    f"落盘第 {write.get('写入轮次')} 次写入"
                )
            elif write is not None:
                write_status = "未入账"
                reason = str(write.get("说明") or "落盘未成功")
                evidence = ""
            else:
                write_status = "待写入"
                reason = self._blocked_reason(status, verdict, decision)
                evidence = ""

            reports.append({
                "槽位编号": slot,
                "指标编号": metric,
                "指标名称": item.get("指标名称"),
                "指标值": item.get("指标值"),
                "监控对象": monitor,
                "对象结论": verdict,
                "对象结论说明": check.get("结论说明", "本轮尚未检查到该对象"),
                "写入状态": write_status,
                "写入轮次": write.get("写入轮次") if write else None,
                "放行轮次": write.get("放行轮次") if write else None,
                "写入时间": write.get("写入时间") if write else None,
                "入账依据": evidence,
                "未入账原因": reason,
            })
        return reports

    def _blocked_reason(self, status: str, verdict: str, decision: dict[str, Any]) -> str:
        if verdict == VERDICT_OVER:
            return "监控对象超阈值，批次拒绝放行"
        if verdict == VERDICT_MISSING:
            return "监控对象缺少样本，批次无法放行"
        if verdict == VERDICT_PENDING:
            return "该监控对象本轮尚未检查，批次不具备放行依据"
        if status == STATUS_RELEASED:
            return "批次已放行，等待落盘写入"
        if decision["冲突"]:
            return "同批口径未放行：本对象虽已通过，但同批仍有对象超阈值"
        return f"批次未放行：{decision['结论说明']}"

    def decorate(self, batch: dict[str, Any]) -> dict[str, Any]:
        """列表用浅拷贝，视图字段不污染仓库里的批次记录。"""
        row = dict(batch)
        check = self.check_view(batch)
        decision = self.decision(batch)
        reports = self.report_view(batch)
        row.update({
            "检查轮次": check["轮次"],
            "检查进度": check["进度"],
            "检查状态": check["状态"],
            "通过数": check["通过"],
            "超阈值数": check["超阈值"],
            "缺样本数": check["缺少样本"],
            "缺失环节": check["缺失环节"],
            "未检查对象": check["未检查对象"],
            "结论说明": decision["结论说明"],
            "放行冲突": decision["冲突"],
            "冲突说明": decision["冲突说明"],
            "阻断原因": decision["阻断原因"],
            "已入账项": sum(1 for item in reports if item["写入状态"] == "已入账"),
            "未入账项": sum(1 for item in reports if item["写入状态"] != "已入账"),
            "落盘状态": batch.get("落盘状态", "未落盘"),
            "落盘结论": batch.get("落盘结论"),
            "报告项视图": reports,
        })
        return row

    def detail(self, entry_id: int) -> dict[str, Any] | None:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None
        row = self.decorate(batch)
        row["检查视图"] = self.check_view(batch)
        row["放行视图"] = self.decision(batch)
        row["样本修正记录"] = list(batch.get("样本修正记录", []))
        row["检查历史"] = list(batch.get("检查历史", []))
        row["写入历史"] = list(batch.get("写入历史", []))
        return row

    def create_batch(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """从质检侧登记一个放行批次：绑定监控对象、阈值与指标批次。"""
        code = str(values.get("批次编号") or "").strip()
        metric_batch = str(values.get("指标批次") or "").strip()
        checks = values.get("检查项")
        reports = values.get("报告项")
        if not code:
            return None, "缺少必填字段：批次编号"
        if not metric_batch:
            return None, "缺少必填字段：指标批次"
        if not isinstance(checks, list) or not checks:
            return None, "缺少必填字段：检查项（至少一个监控对象）"
        if not isinstance(reports, list) or not reports:
            return None, "缺少必填字段：报告项（至少一个待落盘指标）"

        for check in checks:
            if not str(check.get("监控对象") or "").strip():
                return None, "检查项缺少监控对象"
            if check.get("阈值上限") is None and check.get("阈值下限") is None:
                return None, f"监控对象 {check.get('监控对象')} 缺少检查阈值"
        monitor_names = {str(check.get("监控对象")) for check in checks}
        for report in reports:
            if not str(report.get("槽位编号") or "").strip():
                return None, "报告项缺少槽位编号"
            if not str(report.get("指标编号") or "").strip():
                return None, "报告项缺少指标编号"
            if str(report.get("监控对象")) not in monitor_names:
                return None, (
                    f"报告项 {report.get('指标编号')} 的监控对象 "
                    f"{report.get('监控对象')} 不在本批检查项里"
                )

        rows = store.rows(MODULE)
        if any(row.get("批次编号") == code for row in rows):
            return None, f"批次编号 {code} 已存在"
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
            "批次编号": code,
            "指标批次": metric_batch,
            "说明": values.get("说明") or "",
            "检查项": [
                {
                    "监控对象": str(item.get("监控对象")),
                    "检查项": item.get("检查项") or "检查项",
                    "阈值上限": item.get("阈值上限"),
                    "阈值下限": item.get("阈值下限"),
                    "样本值": item.get("样本值"),
                }
                for item in checks
            ],
            "报告项": [
                {
                    "槽位编号": str(item.get("槽位编号")),
                    "指标编号": str(item.get("指标编号")),
                    "指标名称": item.get("指标名称"),
                    "指标值": item.get("指标值"),
                    "监控对象": str(item.get("监控对象")),
                }
                for item in reports
            ],
            "当前检查": None,
            "检查历史": [],
            "放行依据": None,
            "放行结论": None,
            "样本修正记录": [],
            "写入结果": [],
            "写入历史": [],
            "落盘状态": "未落盘",
        }
        rows.append(entry)
        return entry, f"放行批次 {code} 已登记，等待检查"

    # ------------------------------------------------------------------
    # 状态流转
    # ------------------------------------------------------------------
    def start_check(self, entry_id: int, *, retry: bool = False) -> tuple[dict[str, Any] | None, str]:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None, f"放行批次 {entry_id} 不存在或已归档"
        current = batch.get("当前检查")
        if current and current.get("状态") == "检查中":
            return None, f"第 {current.get('轮次')} 轮检查仍在进行中，不能重复开始"

        had_evidence = bool(batch.get("放行依据"))
        if current is not None:
            # 旧轮次无论是否完成都归档：新轮次不得借用旧结论。
            self._archive_current(batch)
        # 放行依据一旦被新轮次取代，旧轮次的落盘结果不能再挂在当前视图上。
        if retry or had_evidence:
            self._detach_writes(batch)

        round_no = int(batch.get("检查轮次", 0)) + 1
        batch["检查轮次"] = round_no
        batch["当前检查"] = {
            "轮次": round_no,
            "状态": "检查中",
            "检查项结果": [],
            "开始时间": _now(),
        }
        batch["status"] = STATUS_CHECKING
        batch["pending"] = True
        batch["abnormal"] = False
        batch["放行依据"] = None
        batch["放行结论"] = None
        batch.pop("复核说明", None)
        action = "重试检查" if retry else "开始检查"
        return batch, f"第 {round_no} 轮检查已开始（{action}，不沿用历史结论）"

    def step_check(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None, f"放行批次 {entry_id} 不存在或已归档"
        current = batch.get("当前检查")
        if current is None or current.get("状态") != "检查中":
            return None, "当前没有进行中的检查轮次，请先开始检查"
        items = list(batch.get("检查项", []))
        results = current.setdefault("检查项结果", [])
        if len(results) >= len(items):
            return None, "本轮检查项已经全部检查完，无需继续"

        item = items[len(results)]
        result = evaluate_sample(item)
        result["检查时间"] = _now()
        results.append(result)
        if len(results) >= len(items):
            self._finalize(batch)
            return batch, (
                f"第 {current['轮次']} 轮检查完成：{self.decision(batch)['结论说明']}"
            )
        return batch, (
            f"已检查 {result['监控对象']}：{result['结论']}（"
            f"{len(results)}/{len(items)}）"
        )

    def finish_check(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        batch, message = self.step_check(entry_id)
        if batch is None:
            return None, message
        current = batch.get("当前检查") or {}
        items = list(batch.get("检查项", []))
        while current.get("状态") == "检查中" and len(current.get("检查项结果", [])) < len(items):
            batch, message = self.step_check(entry_id)
            if batch is None:
                return None, message
            current = batch.get("当前检查") or {}
        return batch, f"第 {current.get('轮次')} 轮检查完成：{self.decision(batch)['结论说明']}"

    def interrupt_check(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None, f"放行批次 {entry_id} 不存在或已归档"
        current = batch.get("当前检查")
        if current is None or current.get("状态") != "检查中":
            return None, "当前没有进行中的检查轮次可中断"
        current["状态"] = "中断"
        current["中断时间"] = _now()
        batch["status"] = STATUS_INTERRUPTED
        batch["pending"] = True
        batch["放行依据"] = None
        view = self.check_view(batch)
        return batch, (
            f"第 {current['轮次']} 轮检查已中断于 {view['进度']}，"
            f"缺少 {'、'.join(view['未检查对象']) or '无'} 的结论"
        )

    def update_samples(
        self, entry_id: int, samples: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None, f"放行批次 {entry_id} 不存在或已归档"
        current = batch.get("当前检查")
        if current and current.get("状态") == "检查中":
            return None, "检查进行中不能修正样本，请先中断检查"
        if not isinstance(samples, dict) or not samples:
            return None, "未提供要修正的样本"

        items = list(batch.get("检查项", []))
        index = {str(item.get("监控对象", "")): item for item in items}
        changed: list[str] = []
        unknown: list[str] = []
        for monitor, value in samples.items():
            item = index.get(str(monitor))
            if item is None:
                unknown.append(str(monitor))
                continue
            item["样本值"] = value
            changed.append(str(monitor))
        if unknown:
            return None, f"监控对象 {('、'.join(unknown))} 不属于本批次"
        if not changed:
            return None, "没有可修正的监控对象"

        batch.setdefault("样本修正记录", []).append({
            "修正时间": _now(),
            "监控对象": changed,
            "样本": {str(monitor): samples[monitor] for monitor in changed},
        })
        # 样本变了，旧结论和旧放行依据都不能再用。
        self._invalidate(batch, "样本已修正，需重新检查")
        return batch, (
            f"已修正 {('、'.join(changed))} 的样本；旧结论与放行依据已失效，请重新检查"
        )

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        batch = self.get_batch(entry_id)
        if batch is None:
            return None, f"放行批次 {entry_id} 不存在或已归档"
        action = ACTION_ALIASES.get(action, action)
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于质量审核放行可执行范围"
        if action == ACTION_START:
            return self.start_check(entry_id)
        if action == ACTION_STEP:
            return self.step_check(entry_id)
        if action == ACTION_FINISH:
            return self.finish_check(entry_id)
        if action == ACTION_INTERRUPT:
            return self.interrupt_check(entry_id)
        return self.start_check(entry_id, retry=True)

    # ------------------------------------------------------------------
    # 内部：归档、失效与判定
    # ------------------------------------------------------------------
    def _archive_current(self, batch: dict[str, Any]) -> None:
        current = batch.get("当前检查")
        if not current:
            return
        record = dict(current)
        record["检查项结果"] = [dict(item) for item in current.get("检查项结果", [])]
        record["归档时间"] = _now()
        batch.setdefault("检查历史", []).append(record)
        batch["当前检查"] = None

    def _detach_writes(self, batch: dict[str, Any]) -> None:
        """新检查轮次开始后，上一轮落盘结果归档，当前视图只反映本轮。"""
        if batch.get("写入结果"):
            batch.setdefault("写入历史", []).extend(
                dict(item) for item in batch["写入结果"]
            )
            batch["写入结果"] = []
            batch["落盘状态"] = "未落盘"

    def _invalidate(self, batch: dict[str, Any], reason: str) -> None:
        had_writes = bool(batch.get("写入结果") or batch.get("写入历史"))
        self._archive_current(batch)
        self._detach_writes(batch)
        batch["放行依据"] = None
        batch["放行结论"] = None
        batch["status"] = STATUS_PENDING
        batch["pending"] = True
        batch["abnormal"] = False
        batch["复核说明"] = reason
        batch["落盘状态"] = "依据失效" if had_writes else "未落盘"

    def _finalize(self, batch: dict[str, Any]) -> None:
        current = batch.get("当前检查") or {}
        results = list(current.get("检查项结果", []))
        current["状态"] = "完成"
        current["结束时间"] = _now()
        over = [r for r in results if r.get("结论") == VERDICT_OVER]
        missing = [r for r in results if r.get("结论") == VERDICT_MISSING]
        passed = [r for r in results if r.get("结论") == VERDICT_PASS]
        total = len(batch.get("检查项", []))

        if len(results) < total:
            # 理论上不会走到这里；留一条兜底，避免未检查完就放行。
            batch["status"] = STATUS_CHECKING
            batch["pending"] = True
            batch["abnormal"] = False
            return

        if over:
            batch["status"] = STATUS_REJECTED
            batch["pending"] = False
            batch["abnormal"] = True
            batch["放行依据"] = None
            batch["放行结论"] = (
                f"第 {current.get('轮次')} 轮检查发现 {len(over)} 个对象超阈值，拒绝放行"
            )
        elif missing:
            batch["status"] = STATUS_MISSING
            batch["pending"] = True
            batch["abnormal"] = False
            batch["放行依据"] = None
            batch["放行结论"] = (
                f"第 {current.get('轮次')} 轮检查有 {len(missing)} 个对象缺少样本，暂不放行"
            )
        else:
            batch["status"] = STATUS_RELEASED
            batch["pending"] = False
            batch["abnormal"] = False
            batch["放行依据"] = {
                "检查轮次": current.get("轮次"),
                "检查完成时间": current.get("结束时间"),
                "已通过对象": [r.get("监控对象") for r in passed],
                "指标批次": batch.get("指标批次"),
                "结论": f"第 {current.get('轮次')} 轮检查全部通过",
            }
            batch["放行结论"] = batch["放行依据"]["结论"]
        batch["落盘状态"] = batch.get("落盘状态") or "未落盘"
        batch.pop("复核说明", None)

    # ------------------------------------------------------------------
    # 供数据落盘消费
    # ------------------------------------------------------------------
    def publish_summary(self) -> list[dict[str, Any]]:
        """质检扫描口径：每个指标批次当前能不能发布，以及为什么。"""
        summary: list[dict[str, Any]] = []
        for batch in store.rows(MODULE):
            decision = self.decision(batch)
            availability = self.write_availability(batch)
            summary.append({
                "批次编号": batch.get("批次编号"),
                "指标批次": batch.get("指标批次"),
                "状态": batch.get("status"),
                "可发布": availability["可写入"],
                "检查进度": decision["进度"],
                "结论": decision["结论说明"],
                "阻断原因": decision["阻断原因"],
                "已入账项": sum(
                    1 for item in self.report_view(batch)
                    if item["写入状态"] == "已入账"
                ),
                "报告项数": len(batch.get("报告项", [])),
            })
        return summary

    def write_availability(self, batch: dict[str, Any]) -> dict[str, Any]:
        decision = self.decision(batch)
        current = batch.get("当前检查") or {}
        evidence = batch.get("放行依据")
        writable = (
            batch.get("status") == STATUS_RELEASED
            and current.get("状态") == "完成"
            and bool(evidence)
            and evidence.get("检查轮次") == current.get("轮次")
        )
        if writable:
            reason = ""
        elif batch.get("status") == STATUS_RELEASED:
            reason = "放行依据与当前检查轮次不一致，不能落盘"
        else:
            reason = decision["结论说明"]
        return {
            "id": batch.get("id"),
            "批次编号": batch.get("批次编号"),
            "指标批次": batch.get("指标批次"),
            "status": batch.get("status"),
            "检查轮次": current.get("轮次") if current else int(batch.get("检查轮次", 0)),
            "检查状态": current.get("状态") if current else "未开始",
            "放行依据": evidence,
            "可写入": writable,
            "不可写入原因": reason,
            "报告项数": len(batch.get("报告项", [])),
            "落盘状态": batch.get("落盘状态", "未落盘"),
        }


service = QualityReleaseService()
