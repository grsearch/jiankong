from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.models import Side, SignalRecord, TokenRuntime, TradeEvent


class SignalEngine:
    WEIGHTS = {
        "pump_detector": 25,
        "bundle_buy": 20,
        "smart_money_buy": 20,
        "volume_spike": 15,
        "buy_sell_ratio": 10,
        "holder_growth": 10,
    }

    def evaluate(self, runtime: TokenRuntime) -> list[SignalRecord]:
        now = datetime.now(timezone.utc)
        trades = sorted(runtime.trades, key=lambda x: x.timestamp)
        if not trades:
            return []

        signals: list[SignalRecord] = []
        active = {
            "pump_detector": self._pump_detector(trades, now),
            "bundle_buy": self._bundle_buy(trades, now),
            "smart_money_buy": self._smart_money_buy(trades, now),
            "volume_spike": self._volume_spike(trades, now),
            "buy_sell_ratio": self._buy_sell_ratio(trades, now),
            "holder_growth": self._holder_growth(trades, now),
        }
        trade_score = sum(self.WEIGHTS[name] for name, ok in active.items() if ok)

        if active["pump_detector"]:
            signals.append(self._record(runtime, "Pump Detector", trade_score, "10秒>=3钱包买入且量能放大"))
        if active["bundle_buy"]:
            signals.append(self._record(runtime, "Bundle Wallet Buy", trade_score, "8秒>=4个bundle钱包集中买入"))
        if active["smart_money_buy"]:
            signals.append(self._record(runtime, "Smart Money Buy", trade_score, "ROI>200% 且胜率>60%钱包买入"))
        if active["volume_spike"]:
            signals.append(self._record(runtime, "Volume Spike", trade_score, "当前10秒成交量>最近1分钟均值x4"))
        if active["buy_sell_ratio"]:
            signals.append(self._record(runtime, "Buy/Sell Ratio", trade_score, "买卖成交量比>3"))
        if active["holder_growth"]:
            signals.append(self._record(runtime, "Holder Growth", trade_score, "10分钟持有人增长>20%"))

        if self._bundle_sell(trades, now):
            signals.append(self._record(runtime, "Bundle Wallet Sell", trade_score, "10秒内>=2个bundle钱包卖出"))
        if self._leader_dump(trades):
            signals.append(self._record(runtime, "Leader Wallet Dump", trade_score, "主bundle钱包累计卖出>30%"))
        if self._liquidity_pull(runtime):
            signals.append(self._record(runtime, "Liquidity Pull Risk", trade_score, "流动性相对基线下降>15%"))

        combo_buy = active["pump_detector"] and active["bundle_buy"] and active["volume_spike"]
        if combo_buy:
            signals.append(self._record(runtime, "Strong Buy Combo", trade_score, "Pump+BundleBuy+VolumeSpike"))

        combo_sell = self._bundle_sell(trades, now) and active["volume_spike"] and self._price_drop(trades, now)
        if combo_sell:
            signals.append(self._record(runtime, "Strong Sell Combo", trade_score, "BundleSell+VolumeSpike+PriceDrop"))

        return signals

    def _record(self, runtime: TokenRuntime, signal: str, score: float, detail: str) -> SignalRecord:
        return SignalRecord(
            mint=runtime.profile.mint,
            symbol=runtime.profile.symbol,
            signal=signal,
            detail=detail,
            score=score,
        )

    def _window(self, trades: list[TradeEvent], now: datetime, seconds: int) -> list[TradeEvent]:
        start = now - timedelta(seconds=seconds)
        return [t for t in trades if t.timestamp >= start]

    def _pump_detector(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_10s = self._window(trades, now, 10)
        buy_wallets = {t.wallet for t in last_10s if t.side == Side.BUY}
        current_volume = sum(t.amount_usd for t in last_10s)
        last_60s = self._window(trades, now, 60)
        baseline = sum(t.amount_usd for t in last_60s) / 6 if last_60s else 0
        return len(buy_wallets) >= 3 and baseline > 0 and current_volume > baseline * 3

    def _bundle_buy(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_8s = self._window(trades, now, 8)
        bundle_buys = [t for t in last_8s if t.side == Side.BUY and t.is_bundle_wallet]
        if len(bundle_buys) < 4:
            return False
        amounts = [t.amount_usd for t in bundle_buys]
        avg = sum(amounts) / len(amounts)
        return all(abs(a - avg) / max(avg, 1) < 0.35 for a in amounts)

    def _smart_money_buy(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_30s = self._window(trades, now, 30)
        return any(
            t.side == Side.BUY and (t.wallet_roi or 0) > 200 and (t.wallet_win_rate or 0) > 60
            for t in last_30s
        )

    def _volume_spike(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_10s = self._window(trades, now, 10)
        v10 = sum(t.amount_usd for t in last_10s)
        last_60s = self._window(trades, now, 60)
        avg_10s = sum(t.amount_usd for t in last_60s) / 6 if last_60s else 0
        return avg_10s > 0 and v10 > avg_10s * 4

    def _buy_sell_ratio(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_30s = self._window(trades, now, 30)
        buy_vol = sum(t.amount_usd for t in last_30s if t.side == Side.BUY)
        sell_vol = sum(t.amount_usd for t in last_30s if t.side == Side.SELL)
        return sell_vol > 0 and (buy_vol / sell_vol) > 3

    def _holder_growth(self, trades: list[TradeEvent], now: datetime) -> bool:
        recent = [t for t in trades if t.holder_count and t.timestamp >= now - timedelta(minutes=10)]
        if len(recent) < 2:
            return False
        first = recent[0].holder_count or 0
        last = recent[-1].holder_count or 0
        return first > 0 and (last - first) / first > 0.2

    def _bundle_sell(self, trades: list[TradeEvent], now: datetime) -> bool:
        last_10s = self._window(trades, now, 10)
        sellers = {t.wallet for t in last_10s if t.side == Side.SELL and t.is_bundle_wallet}
        return len(sellers) >= 2

    def _leader_dump(self, trades: list[TradeEvent]) -> bool:
        bundle_flows = defaultdict(float)
        for t in trades:
            if not t.is_bundle_wallet:
                continue
            if t.side == Side.BUY:
                bundle_flows[t.wallet] += t.amount_usd
            else:
                bundle_flows[t.wallet] -= t.amount_usd
        if not bundle_flows:
            return False
        leader = max(bundle_flows, key=lambda w: abs(bundle_flows[w]))
        buys = sum(t.amount_usd for t in trades if t.wallet == leader and t.side == Side.BUY)
        sells = sum(t.amount_usd for t in trades if t.wallet == leader and t.side == Side.SELL)
        return buys > 0 and sells / buys > 0.3

    def _price_drop(self, trades: list[TradeEvent], now: datetime) -> bool:
        priced = [t for t in self._window(trades, now, 30) if t.price is not None]
        if len(priced) < 2:
            return False
        return priced[-1].price < priced[0].price * 0.95

    def _liquidity_pull(self, runtime: TokenRuntime) -> bool:
        liquidities = [t.liquidity_usd for t in runtime.trades if t.liquidity_usd]
        if not liquidities:
            return False
        if runtime.baseline_liquidity is None:
            runtime.baseline_liquidity = liquidities[0]
            return False
        return liquidities[-1] < runtime.baseline_liquidity * 0.85
