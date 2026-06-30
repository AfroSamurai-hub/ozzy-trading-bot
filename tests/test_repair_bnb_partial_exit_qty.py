import sqlite3
from datetime import UTC, datetime

import pytest

from scripts import repair_bnb_partial_exit_qty as repair


FIXED_UTC_TIME = datetime(2026, 6, 30, 10, 0, 0, tzinfo=UTC)


def exact_fills():
    return [
        {
            "id": 143517400,
            "orderId": 1775544504,
            "time": 1782792512398,
            "side": "BUY",
            "positionSide": "SHORT",
            "qty": "4.53",
        },
        {
            "id": 143517525,
            "orderId": 1775555147,
            "time": 1782792554141,
            "side": "BUY",
            "positionSide": "SHORT",
            "qty": "3.40",
        },
    ]


def make_db(tmp_path):
    db_path = tmp_path / "trades.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, qty REAL);
            CREATE TABLE exits (
                id INTEGER PRIMARY KEY, trade_id INTEGER, exit_type TEXT,
                pnl_contribution REAL, qty_pct REAL, notes TEXT
            );
            INSERT INTO trades VALUES (100373, 'BNBUSDT', 'SELL', 18.13);
            INSERT INTO exits VALUES (1027, 100373, 'milestone_0', 5.85737090535025, 0.25, 'milestone note');
            INSERT INTO exits VALUES (1028, 100373, 'regime_aware_chop_profit_taken', 4.646296655, 0.25, 'chop note');
            INSERT INTO exits VALUES (1029, 999999, 'unrelated', 1.0, 0.25, 'untouched');
        """)
    return db_path


def snapshot_all_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM exits ORDER BY id")}


class FakeClient:
    def __init__(self, positions=None, normal_orders=None, algo_orders=None):
        self.positions = positions or []
        self.normal_orders = normal_orders or []
        self.algo_orders = algo_orders or []

    def futures_position_information(self):
        return self.positions

    def futures_get_open_orders(self):
        return self.normal_orders

    def futures_get_open_algo_orders(self):
        return self.algo_orders


def test_validate_evidence_requires_exact_unique_fill_mapping():
    mapping = repair.validate_exchange_evidence(exact_fills())
    assert mapping[1027]["orderId"] == 1775544504
    assert mapping[1028]["id"] == 143517525


def test_validate_evidence_rejects_competing_candidate():
    fills = exact_fills() + [
        {
            "id": 999,
            "orderId": 888,
            "time": 1782792515000,
            "side": "BUY",
            "positionSide": "SHORT",
            "qty": "4.53",
        }
    ]
    with pytest.raises(RuntimeError, match="ambiguous"):
        repair.validate_exchange_evidence(fills)


def test_apply_repair_backs_up_then_changes_only_two_qty_fractions(tmp_path):
    db_path = make_db(tmp_path)
    before = snapshot_all_rows(db_path)

    backup_path = repair.apply_repair(db_path, exact_fills(), now=FIXED_UTC_TIME)

    after = snapshot_all_rows(db_path)
    assert backup_path.exists()
    assert after[1027]["qty_pct"] == pytest.approx(4.53 / 18.13)
    assert after[1028]["qty_pct"] == pytest.approx(3.40 / 18.13)
    assert before[1027]["notes"] == after[1027]["notes"]
    assert before[1028]["pnl_contribution"] == after[1028]["pnl_contribution"]
    assert before[1029] == after[1029]


def test_apply_mode_refuses_any_open_exchange_position():
    client = FakeClient(positions=[{"symbol": "BTCUSDT", "positionAmt": "0.01"}])
    with pytest.raises(RuntimeError, match="exchange is not flat"):
        repair.assert_flat_exchange(client)


def test_apply_mode_refuses_unverifiable_algo_order_state():
    client = FakeClient()
    client.futures_get_open_algo_orders = lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))
    with pytest.raises(RuntimeError, match="cannot verify exchange algo-order state"):
        repair.assert_flat_exchange(client)
