"""Unit and integration tests for STRATLAB API Gateway."""

import unittest
from fastapi.testclient import TestClient
from shared.schemas.execution import OrderSide, OrderType
from shared.schemas.provenance import DataQuality
from backend.app.api.main import app
from backend.app.strategy.ir.models import (
    ComparisonOperator,
    ConditionGroup,
    ConditionNode,
    LogicalOp,
    Operand,
    OperandKind,
    RiskParams,
    StopLossConfig,
    StrategyIR,
    TakeProfitConfig,
)


class TestAPIGateway(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_market_instruments_and_candles(self):
        # 1. Instruments catalog
        resp = self.client.get("/api/v1/market/instruments")
        self.assertEqual(resp.status_code, 200)
        instruments = resp.json()
        self.assertGreaterEqual(len(instruments), 3)
        self.assertTrue(any(i["symbol"] == "RELIANCE" for i in instruments))

        # 2. Historical candles
        resp_c = self.client.get("/api/v1/market/candles?instrument_id=INS_NSE_RELIANCE&limit=15")
        self.assertEqual(resp_c.status_code, 200)
        candles = resp_c.json()
        self.assertEqual(len(candles), 15)
        self.assertIn("provenance", candles[0])

        # 3. Volume profile
        resp_p = self.client.get("/api/v1/market/orderflow/profile?instrument_id=INS_NSE_RELIANCE")
        self.assertEqual(resp_p.status_code, 200)
        profile = resp_p.json()
        self.assertIn("poc_price", profile)
        self.assertIn("vah_price", profile)
        self.assertIn("val_price", profile)

    def test_strategy_components_and_compilation(self):
        # 1. Components catalog
        resp = self.client.get("/api/v1/strategies/components")
        self.assertEqual(resp.status_code, 200)
        comps = resp.json()
        self.assertTrue(any(c["name"] == "ema" for c in comps))
        self.assertTrue(any(c["name"] == "footprint_stacked_imbalance_buy" for c in comps))

        # 2. Compile valid strategy
        ir = StrategyIR(
            name="API Test Strategy",
            entry_long=ConditionGroup(
                operator=LogicalOp.AND,
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.INDICATOR, name="ema", params={"period": 20}),
                    )
                ]
            )
        )
        resp_comp = self.client.post("/api/v1/strategies/compile", json={"strategy": ir.model_dump()})
        self.assertEqual(resp_comp.status_code, 200)
        comp_data = resp_comp.json()
        self.assertEqual(comp_data["status"], "ok")
        self.assertIn("candle", comp_data["required_feeds"])

        # 3. Compile with provenance mismatch (requires Level A, feeding Level D)
        ir_strict = StrategyIR(
            name="Strict Footprint Strategy",
            entry_long=ConditionGroup(
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.ORDER_FLOW, name="footprint_stacked_imbalance_buy"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.CONSTANT, value=2.0),
                    )
                ]
            )
        )
        resp_strict = self.client.post(
            "/api/v1/strategies/compile",
            json={"strategy": ir_strict.model_dump(), "target_feed_quality": DataQuality.LEVEL_D_OHLCV_PROXY},
        )
        self.assertEqual(resp_strict.status_code, 400)
        self.assertEqual(resp_strict.json()["detail"]["error"], "PROVENANCE_INCOMPATIBLE")

    def test_backtest_execution(self):
        ir = StrategyIR(
            name="Quick Backtest",
            entry_long=ConditionGroup(
                operator=LogicalOp.AND,
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.CONSTANT, value=102.0),
                    )
                ]
            ),
            risk=RiskParams(
                stop_loss=StopLossConfig(mode="pct", value=1.5),
                take_profit=TakeProfitConfig(mode="pct", value=3.0),
            )
        )
        resp = self.client.post("/api/v1/strategies/backtest", json={"strategy": ir.model_dump()})
        self.assertEqual(resp.status_code, 200)
        result = resp.json()
        self.assertIn("metrics", result)
        self.assertIn("equity_curve", result)
        self.assertGreater(len(result["equity_curve"]), 0)

    def test_paper_trading_endpoints(self):
        # 1. Account summary
        resp_acc = self.client.get("/api/v1/paper/account")
        self.assertEqual(resp_acc.status_code, 200)
        acc = resp_acc.json()
        self.assertIn("equity", acc)
        self.assertIn("cash", acc)

        # 2. Submit paper order
        order_payload = {
            "order_id": "ORD_API_01",
            "account_id": "ACC_USER",
            "instrument_id": "INS_NSE_RELIANCE",
            "side": OrderSide.BUY.value,
            "order_type": OrderType.MARKET.value,
            "quantity": 25,
            "created_time_utc": 1000,
            "updated_time_utc": 1000,
        }
        resp_order = self.client.post("/api/v1/paper/orders", json=order_payload)
        self.assertEqual(resp_order.status_code, 200)
        order_res = resp_order.json()
        self.assertEqual(order_res["order_id"], "ORD_API_01")
        self.assertTrue(order_res["filled"])

        # 3. List orders
        resp_list = self.client.get("/api/v1/paper/orders")
        self.assertEqual(resp_list.status_code, 200)
        self.assertTrue(any(o["order_id"] == "ORD_API_01" for o in resp_list.json()))

    def test_websocket_streaming(self):
        with self.client.websocket_connect("/ws/market/stream") as ws:
            # Ping pong
            ws.send_json({"action": "ping"})
            resp = ws.receive_json()
            self.assertEqual(resp, {"action": "pong"})

            # Subscribe channel
            ws.send_json({"action": "subscribe", "channel": "candles:INS_NSE_RELIANCE"})
            resp_sub = ws.receive_json()
            self.assertEqual(resp_sub["status"], "subscribed")
            self.assertEqual(resp_sub["channel"], "candles:INS_NSE_RELIANCE")


if __name__ == "__main__":
    unittest.main()
