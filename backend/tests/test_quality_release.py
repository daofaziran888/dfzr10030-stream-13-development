"""质量审核放行验收：通过、超阈值、缺少样本三组样本 + 落盘回写。"""
import pytest

from app.services import quality_release as qr
from app.services.quality_release import QualityReleaseService
from app.services.sink_writer import ReleaseSinkWriter
from app.store import store


@pytest.fixture()
def service() -> QualityReleaseService:
    return QualityReleaseService()


@pytest.fixture()
def writer() -> ReleaseSinkWriter:
    return ReleaseSinkWriter()


def batch_by_code(code: str) -> dict:
    for row in store.rows("quality_release"):
        if row.get("批次编号") == code:
            return row
    raise AssertionError(f"{code} 未在批次清单里")


def finish(service: QualityReleaseService, entry_id: int) -> dict:
    service.start_check(entry_id)
    _, message = service.finish_check(entry_id)
    assert "检查完成" in message
    return service.get_batch(entry_id) or {}


class TestPassBatch:
    def test_all_pass_releases_with_evidence(self, service):
        batch = finish(service, 1)
        assert batch["status"] == "已放行"
        evidence = batch["放行依据"]
        assert evidence["检查轮次"] == 1
        assert evidence["指标批次"] == "MB-ORDER-20261121"
        assert set(evidence["已通过对象"]) == {"stream_transform", "cdc_task", "sink_writer"}

    def test_evidence_matches_current_round(self, service):
        batch = finish(service, 1)
        availability = service.write_availability(batch)
        assert availability["可写入"] is True
        assert availability["放行依据"]["检查轮次"] == availability["检查轮次"]

    def test_reports_start_pending_then_explain(self, service):
        batch = finish(service, 1)
        reports = service.report_view(batch)
        assert [item["写入状态"] for item in reports] == ["待写入"] * 3
        assert all("已放行" in item["未入账原因"] for item in reports)


class TestOverThresholdBatch:
    def test_over_threshold_rejects(self, service):
        batch = finish(service, 2)
        assert batch["status"] == "拒绝放行"
        view = service.check_view(batch)
        assert view["超阈值"] == 1
        assert view["通过"] == 2
        assert view["缺少样本"] == 0

    def test_short_circuit_conflict_reported(self, service):
        batch = finish(service, 2)
        decision = service.decision(batch)
        assert decision["冲突"] is True
        assert "准时出数" in decision["冲突说明"]

    def test_reports_blocked_by_same_batch(self, service):
        batch = finish(service, 2)
        reports = service.report_view(batch)
        by_monitor = {item["监控对象"]: item for item in reports}
        assert by_monitor["stream_transform"]["未入账原因"] == "监控对象超阈值，批次拒绝放行"
        assert "同批仍有对象超阈值" in by_monitor["cdc_task"]["未入账原因"]
        assert all(item["写入状态"] == "待写入" for item in reports)

    def test_cannot_write_rejected_batch(self, service, writer):
        finish(service, 2)
        batch, message = writer.write_batch(2)
        assert batch is None
        assert "拒绝放行" in message


class TestMissingSampleBatch:
    def test_missing_is_not_over_threshold(self, service):
        batch = finish(service, 3)
        assert batch["status"] == "缺少样本"
        view = service.check_view(batch)
        assert view["缺少样本"] == 1
        assert view["超阈值"] == 0
        missing = [item for item in view["检查项"] if item["结论"] == "缺少样本"]
        assert missing[0]["监控对象"] == "dedup_mgr"

    def test_gap_names_the_slot(self, service):
        batch = finish(service, 3)
        view = service.check_view(batch)
        assert "dedup_mgr" in view["缺失环节"]
        assert view["未检查对象"] == []


class TestInterruptAndRetry:
    def test_interrupt_does_not_release(self, service):
        service.start_check(1)
        service.step_check(1)
        batch, message = service.interrupt_check(1)
        assert batch is not None
        assert "缺少 cdc_task、sink_writer" in message
        assert batch["status"] == "检查中断"
        assert batch["放行依据"] is None

    def test_retry_does_not_borrow_previous_results(self, service):
        service.start_check(1)
        service.step_check(1)
        service.interrupt_check(1)
        batch, _ = service.start_check(1, retry=True)
        assert batch is not None
        view = service.check_view(batch)
        assert view["轮次"] == 2
        assert view["已检查"] == 0
        assert batch["status"] == "检查中"
        assert all(item["结论"] == "未检查" for item in view["检查项"])
        assert batch["检查历史"][0]["检查项结果"][0]["结论"] == "通过"

    def test_retried_round_completes_independently(self, service):
        service.start_check(1)
        service.interrupt_check(1)
        batch = finish(service, 1)
        assert batch["status"] == "已放行"
        assert batch["放行依据"]["检查轮次"] == 2

    def test_released_batch_retry_detaches_writes(self, service, writer):
        finish(service, 1)
        store.find("sink_writer", 2)["status"] = "写入中"
        writer.write_batch(1)
        batch = batch_by_code("REL-20261121-01")
        assert batch["落盘状态"] in {"部分入账", "全部入账"}

        service.start_check(1, retry=True)
        assert batch["status"] == "检查中"
        assert batch["放行依据"] is None
        assert batch["写入结果"] == []
        assert batch["写入历史"]
        assert batch["落盘状态"] == "未落盘"


class TestSinkConsumption:
    def test_not_released_batch_cannot_write(self, service, writer):
        batch, message = writer.write_batch(1)
        assert batch is None
        assert "不能落盘" in message

    def test_partial_write_then_backfill(self, service, writer):
        finish(service, 1)
        slot2 = store.find("sink_writer", 2)
        assert slot2 is not None
        slot2["status"] = "写入中"
        batch, message = writer.write_batch(1)
        assert batch is not None
        assert "部分入账" in batch["落盘状态"]
        assert "1/3" in message

        store.find("sink_writer", 1)["status"] = "写入中"
        store.find("sink_writer", 3)["status"] = "写入中"
        batch, message = writer.write_batch(1)
        assert batch is not None
        assert batch["落盘状态"] == "全部入账"
        assert "3/3" in message
        # 已入账的项不重复写，保留首次写入轮次。
        first_rounds = {item["槽位编号"]: item["写入轮次"] for item in batch["写入结果"]}
        assert first_rounds["SINK-0002"] == 1

    def test_write_counts_are_visible(self, service, writer):
        finish(service, 1)
        # 种子数据里 SINK-0002 本来就是「写入中」，这里先把三个槽位都置为待配置，
        # 只放开 SINK-0001，确保入账数与槽位状态一一对应。
        for row in store.rows("sink_writer"):
            row["status"] = "待配置"
        store.find("sink_writer", 1)["status"] = "写入中"
        writer.write_batch(1)
        row = service.decorate(batch_by_code("REL-20261121-01"))
        assert row["已入账项"] == 1
        assert row["未入账项"] == 2
        reports = {item["槽位编号"]: item for item in row["报告项视图"]}
        assert reports["SINK-0001"]["入账依据"].startswith("第 1 轮放行依据")
        assert "需要先启动写入" in reports["SINK-0002"]["未入账原因"]

    def test_decorated_row_drops_stale_write_evidence(self, service, writer):
        # 列表浅拷贝只拼当前视图：grid 里看到的入账依据必须来自本轮放行。
        for row in store.rows("sink_writer"):
            row["status"] = "写入中"
        finish(service, 2)
        service.update_samples(2, {"stream_transform": 1200.0})
        finish(service, 2)
        writer.write_batch(2)
        row = service.decorate(batch_by_code("REL-20261121-02"))
        reports = {item["槽位编号"]: item for item in row["报告项视图"]}
        assert all(item["写入状态"] == "已入账" for item in reports.values())
        # 第 2 轮放行 + 第 1 次落盘，依据必须指向当前轮次。
        assert reports["SINK-0001"]["入账依据"] == "第 2 轮放行依据 + 落盘第 1 次写入"
        assert reports["SINK-0001"]["放行轮次"] == 2
        assert row["已入账项"] == 3 and row["未入账项"] == 0

    def test_rejected_batch_cannot_write_after_fix(self, service, writer):
        finish(service, 2)
        for row in store.rows("sink_writer"):
            row["status"] = "写入中"
        service.update_samples(2, {"stream_transform": 1200.0})
        batch, message = writer.write_batch(2)
        assert batch is None
        assert "修正" in message or "待检查" in message or "不能落盘" in message

    def test_sample_fix_invalidates_evidence(self, service, writer):
        finish(service, 1)
        store.find("sink_writer", 1)["status"] = "写入中"
        writer.write_batch(1)

        batch, message = service.update_samples(1, {"stream_transform": 9000.0})
        assert batch is not None
        assert "旧结论与放行依据已失效" in message
        assert batch["status"] == "待检查"
        assert batch["放行依据"] is None
        assert batch["落盘状态"] == "依据失效"
        assert batch["样本修正记录"][0]["监控对象"] == ["stream_transform"]

        _, blocked = writer.write_batch(1)
        assert "不能落盘" in blocked

    def test_fix_then_rerun_only_pending_range(self, service, writer):
        finish(service, 2)
        service.update_samples(2, {"stream_transform": 1200.0})
        batch, message = service.start_check(2, retry=True)
        assert batch is not None
        finish(service, 2)
        batch = batch_by_code("REL-20261121-02")
        assert batch["status"] == "已放行"
        assert batch["放行依据"]["检查轮次"] == 2

        for row in store.rows("sink_writer"):
            row["status"] = "写入中"
        batch, _ = writer.write_batch(2)
        assert batch is not None
        assert batch["落盘状态"] == "全部入账"
        assert {item["槽位编号"] for item in batch["写入结果"]} == {
            "SINK-0001", "SINK-0002", "SINK-0003",
        }

    def test_single_step_actions_surface_round(self, service):
        service.start_check(1)
        _, message = service.step_check(1)
        assert "1/3" in message
        batch = batch_by_code("REL-20261121-01")
        assert batch["status"] == "检查中"
        assert service.check_view(batch)["缺失环节"].startswith("第 1 轮只完成 1/3")


class TestQualityScanPublishView:
    def test_scan_explains_publishability(self, service):
        from app.services.pipeline_orchestrator import run_quality_scan

        finish(service, 2)
        result = run_quality_scan()
        rows = {row["批次编号"]: row for row in result["release_batches"]}
        assert set(rows) == {"REL-20261121-01", "REL-20261121-02", "REL-20261121-03"}
        assert rows["REL-20261121-01"]["可发布"] is False
        assert "尚未开始检查" in rows["REL-20261121-01"]["结论"]
        assert rows["REL-20261121-02"]["状态"] == "拒绝放行"
        assert rows["REL-20261121-02"]["阻断原因"]
        assert rows["REL-20261121-02"]["可发布"] is False

    def test_released_batch_is_publishable(self, service):
        from app.services.pipeline_orchestrator import run_quality_scan

        finish(service, 1)
        rows = {row["批次编号"]: row for row in run_quality_scan()["release_batches"]}
        assert rows["REL-20261121-01"]["可发布"] is True
        assert rows["REL-20261121-01"]["检查进度"] == "3/3"
        assert rows["REL-20261121-01"]["已入账项"] == 0


class TestCreateBatch:
    def test_create_binds_monitors_and_metric_batch(self, service):
        entry, message = service.create_batch({
            "批次编号": "REL-NEW-01",
            "指标批次": "MB-NEW",
            "说明": "新登记",
            "检查项": [
                {"监控对象": "cdc_task", "检查项": "吞吐量", "阈值上限": 10, "阈值下限": 0, "样本值": 5},
            ],
            "报告项": [
                {"槽位编号": "SINK-0001", "指标编号": "METR-X", "监控对象": "cdc_task"},
            ],
        })
        assert entry is not None
        assert "已登记" in message
        detail = service.detail(entry["id"])
        assert detail is not None
        assert detail["status"] == "待检查"
        assert detail["检查视图"]["进度"] == "0/1"

    def test_create_rejects_unbound_report(self, service):
        entry, message = service.create_batch({
            "批次编号": "REL-NEW-02",
            "指标批次": "MB-NEW",
            "检查项": [
                {"监控对象": "cdc_task", "检查项": "吞吐量", "阈值上限": 10},
            ],
            "报告项": [
                {"槽位编号": "SINK-0001", "指标编号": "METR-X", "监控对象": "stream_transform"},
            ],
        })
        assert entry is None
        assert "不在本批检查项里" in message

    def test_create_rejects_duplicate_code(self, service):
        entry, message = service.create_batch({
            "批次编号": "REL-20261121-01",
            "指标批次": "MB-NEW",
            "检查项": [{"监控对象": "cdc_task", "阈值上限": 10}],
            "报告项": [{"槽位编号": "SINK-0001", "指标编号": "METR-X", "监控对象": "cdc_task"}],
        })
        assert entry is None
        assert "已存在" in message


class TestStaleEvidence:
    def test_new_round_drops_old_write_evidence(self, service, writer):
        for row in store.rows("sink_writer"):
            row["status"] = "写入中"
        finish(service, 1)
        writer.write_batch(1)
        batch = batch_by_code("REL-20261121-01")
        assert batch["落盘状态"] == "全部入账"

        # 不显式“重试”也必须丢掉上一轮落盘结果：依据已被新轮次取代。
        service.start_check(1)
        assert batch["放行依据"] is None
        assert batch["写入结果"] == []
        assert batch["写入历史"]
        assert batch["落盘状态"] == "未落盘"
        assert all(
            item["写入状态"] == "待写入" for item in service.report_view(batch)
        )
