"""测试配置：每个测试前重置 store 保证隔离。"""
import copy

import pytest
from app.store import store as _store, Store


@pytest.fixture(autouse=True)
def fresh_store():
    _store._tables.clear()
    from app.seed import SEED_ROWS
    for name, rows in SEED_ROWS.items():
        _store._tables[name] = copy.deepcopy(rows)
    yield