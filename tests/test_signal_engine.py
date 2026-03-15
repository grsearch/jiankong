from datetime import datetime, timedelta, timezone

from app.models import Side, TokenProfile, TokenRuntime, TradeEvent
from app.signal_engine import SignalEngine


def test_buy_combo_signal_triggered():
    now = datetime.now(timezone.utc)
    runtime = TokenRuntime(profile=TokenProfile(mint="A" * 32, symbol="ABC"))
    for i in range(6):
        runtime.trades.append(
            TradeEvent(
                mint=runtime.profile.mint,
                wallet=f"w{i}",
                side=Side.BUY,
                amount_usd=100,
                timestamp=now - timedelta(seconds=50 - i),
                is_bundle_wallet=False,
            )
        )
    for i in range(4):
        runtime.trades.append(
            TradeEvent(
                mint=runtime.profile.mint,
                wallet=f"b{i}",
                side=Side.BUY,
                amount_usd=1000,
                timestamp=now - timedelta(seconds=2),
                is_bundle_wallet=True,
                wallet_roi=260,
                wallet_win_rate=70,
            )
        )

    signals = SignalEngine().evaluate(runtime)
    names = {s.signal for s in signals}
    assert "Pump Detector" in names
    assert "Bundle Wallet Buy" in names
    assert "Strong Buy Combo" in names
