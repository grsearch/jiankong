# SOL Meme Monitor (Birdeye + Helius)

通过 webhook 接收代币和交易数据，自动纳入白名单，实时展示并触发交易信号。

## 功能

- `POST /webhook/token`：接收新代币，加入白名单。
- `POST /webhook/trade`：接收成交事件，计算 8 大核心信号与组合信号。
- Dashboard（`/`）：实时显示
  - 白名单：`symbol / FDV or MCAP / holders / volume / 合约地址(gmgn可点击)`
  - 交易信号触发记录（含触发信号名和评分）
- 命中信号后，将结果 webhook 到 `BOT_WEBHOOK_URL`（自动交易机器人服务器）。

## 环境变量

```bash
BIRDEYE_API_KEY=xxx
HELIUS_API_KEY=xxx
BOT_WEBHOOK_URL=http://your-bot-server/webhook
```

## 运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Webhook 示例

```bash
curl -X POST http://127.0.0.1:8000/webhook/token \
  -H 'content-type: application/json' \
  -d '{"mint":"G9uBiZM26J7D3jrD64FuTKZthNXmK9zQPFf3ahVYpump","symbol":"SYMPLE"}'

curl -X POST http://127.0.0.1:8000/webhook/trade \
  -H 'content-type: application/json' \
  -d '{"mint":"G9uBiZM26J7D3jrD64FuTKZthNXmK9zQPFf3ahVYpump","wallet":"wallet1","side":"buy","amount_usd":1500,"is_bundle_wallet":true,"wallet_roi":260,"wallet_win_rate":70,"price":0.0021,"holder_count":320,"liquidity_usd":82000}'
```

## 信号引擎实现

- Pump Detector
- Bundle Wallet Buy
- Smart Money Buy
- Volume Spike
- Buy/Sell Ratio
- Holder Growth
- Bundle Wallet Sell
- Leader Wallet Dump
- Liquidity Pull Risk
- 强买/强卖组合信号
