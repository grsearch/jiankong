from datetime import datetime, timedelta, timezone

from app.models import Side, TokenProfile, TokenRuntime, TradeEvent
from app.signal_engine import SignalEngine


def _trade(runtime: TokenRuntime, **kwargs):
    runtime.trades.append(
        TradeEvent(
            mint=runtime.profile.mint,
            wallet=kwargs.get("wallet", "w"),
            side=kwargs.get("side", Side.BUY),
            amount_usd=kwargs.get("amount_usd", 100),
            timestamp=kwargs.get("timestamp"),
            price=kwargs.get("price"),
            is_bundle_wallet=kwargs.get("is_bundle_wallet", False),
            wallet_roi=kwargs.get("wallet_roi"),
            wallet_win_rate=kwargs.get("wallet_win_rate"),
        )
    )


def test_pump_bundle_strong_combo_triggered():
    now = datetime.now(timezone.utc)
    runtime = TokenRuntime(profile=TokenProfile(mint="A" * 32, symbol="ABC"))

    # 5分钟内构建基线 + 历史高点
    for i in range(30):
        _trade(
            runtime,
            wallet=f"base{i}",
            side=Side.SELL if i % 2 else Side.BUY,
            amount_usd=200,
            timestamp=now - timedelta(seconds=280 - i * 5),
            price=1.0,
        )

    # 最近10笔，买盘占优（>=7）
    for i in range(7):
        _trade(
            runtime,
            wallet=f"buy{i}",
            side=Side.BUY,
            amount_usd=4000,
            timestamp=now - timedelta(seconds=8),
            price=1.03,
            is_bundle_wallet=True,
        )
    for i in range(3):
        _trade(
            runtime,
            wallet=f"sell{i}",
            side=Side.SELL,
            amount_usd=900,
            timestamp=now - timedelta(seconds=7),
            price=1.02,
        )
    _trade(
        runtime,
        wallet="breakout1",
        side=Side.BUY,
        amount_usd=5000,
        timestamp=now - timedelta(seconds=1),
        price=1.07,
        is_bundle_wallet=True,
    )

    signals = SignalEngine().evaluate(runtime)
    names = {s.signal for s in signals}
    assert "Pump Detector" in names
    assert "Bundle Wallet Buy" in names
    assert "Strong Buy Combo" in names


def test_smart_and_pump_can_trigger_strong_combo_without_bundle():
    now = datetime.now(timezone.utc)
    runtime = TokenRuntime(profile=TokenProfile(mint="B" * 32, symbol="XYZ"))

    # baseline/history
    for i in range(40):
        _trade(
            runtime,
            wallet=f"old{i}",
            side=Side.SELL if i % 3 == 0 else Side.BUY,
            amount_usd=150,
            timestamp=now - timedelta(seconds=290 - i * 6),
            price=1.0,
        )

    # smart wallets (2) + pump 条件（但不是bundle）
    _trade(
        runtime,
        wallet="smart1",
        side=Side.BUY,
        amount_usd=12000,
        timestamp=now - timedelta(seconds=5),
        price=1.03,
        wallet_roi=250,
        wallet_win_rate=70,
        is_bundle_wallet=False,
    )
    _trade(
        runtime,
        wallet="smart2",
        side=Side.BUY,
        amount_usd=11000,
        timestamp=now - timedelta(seconds=4),
        price=1.04,
        wallet_roi=260,
        wallet_win_rate=72,
        is_bundle_wallet=False,
    )
    for i in range(8):
        _trade(
            runtime,
            wallet=f"flow{i}",
            side=Side.BUY if i < 7 else Side.SELL,
            amount_usd=3000 if i < 7 else 1000,
            timestamp=now - timedelta(seconds=3),
            price=1.05,
            is_bundle_wallet=False,
        )
    _trade(
        runtime,
        wallet="breakout2",
        side=Side.BUY,
        amount_usd=9000,
        timestamp=now - timedelta(seconds=1),
        price=1.08,
        is_bundle_wallet=False,
    )

    signals = SignalEngine().evaluate(runtime)
    names = {s.signal for s in signals}
    assert "Pump Detector" in names
    assert "Smart Money Buy" in names
    assert "Strong Buy Combo" in names
