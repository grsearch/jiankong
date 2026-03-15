require("dotenv").config();
const WebSocket = require("ws");
const axios = require("axios");

const API_KEY = process.env.BIRDEYE_API_KEY;
if (!API_KEY) {
  throw new Error("Missing BIRDEYE_API_KEY in .env");
}

const TOKEN_MINT = process.env.TOKEN_MINT || "So11111111111111111111111111111111111111112";
const CHAIN = "solana";
const WS_URL = `wss://public-api.birdeye.so/socket/${CHAIN}?x-api-key=${API_KEY}`;
const HOLDER_URL = "https://public-api.birdeye.so/defi/v3/token/holder";
const DISTRIBUTION_URL = "https://public-api.birdeye.so/holder/v1/distribution";

const HOLDER_REFRESH_MS = 30 * 1000;
const HOLDER_LIMIT = Number(process.env.HOLDER_LIMIT || 20);

let ws;
let reconnectTimer = null;
let lastStatsHolderCount = null;
let lastHolderSnapshotHash = null;
let lastHolderPullAt = 0;

function extractHolderCount(stats) {
  if (!stats || typeof stats !== "object") return null;
  const candidates = [
    stats.holders,
    stats.holder,
    stats.holderCount,
    stats.holdersCount,
    stats.totalHolders,
    stats.uniqueHolders,
  ];

  for (const value of candidates) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) return Number(value);
  }
  return null;
}

function extractStatsPayload(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw.data && typeof raw.data === "object") return raw.data;
  if (raw.response && typeof raw.response === "object") return raw.response;
  return raw;
}

function buildHolderSnapshotHash(holderList) {
  if (!Array.isArray(holderList)) return "";
  return holderList
    .map((x) => {
      const owner = x.owner || x.wallet || x.address || x.holder || x.ownerAddress || "unknown";
      const amount = x.amount || x.balance || x.uiAmount || x.tokenAmount || 0;
      return `${owner}:${amount}`;
    })
    .join("|");
}

async function fetchTopHolders(address) {
  const res = await axios.get(HOLDER_URL, {
    params: { address, offset: 0, limit: HOLDER_LIMIT },
    headers: { accept: "application/json", "X-API-KEY": API_KEY, "x-chain": CHAIN },
    timeout: 15000,
  });
  const root = res.data || {};
  const data = root.data || root;
  const items = data.items || data.holders || data.list || data.result || [];
  return Array.isArray(items) ? items : [];
}

async function fetchHolderDistribution(address) {
  const res = await axios.get(DISTRIBUTION_URL, {
    params: { address, include_list: false },
    headers: { accept: "application/json", "X-API-KEY": API_KEY, "x-chain": CHAIN },
    timeout: 15000,
  });
  return res.data || {};
}

async function refreshTopHolders(reason = "manual") {
  try {
    lastHolderPullAt = Date.now();
    const holders = await fetchTopHolders(TOKEN_MINT);
    const hash = buildHolderSnapshotHash(holders);

    if (hash === lastHolderSnapshotHash) {
      console.log(`[TOP HOLDERS NO CHANGE] reason=${reason} time=${new Date().toISOString()}`);
      return;
    }

    console.log(`\n[TOP HOLDERS CHANGED] reason=${reason} time=${new Date().toISOString()}`);
    lastHolderSnapshotHash = hash;
    holders.slice(0, 10).forEach((h, idx) => {
      const owner = h.owner || h.wallet || h.address || h.holder || h.ownerAddress || "unknown";
      const amount = h.amount || h.balance || h.uiAmount || h.tokenAmount || 0;
      const percent = h.percentage || h.percent || h.share || h.ownershipPercentage || null;
      console.log(`${idx + 1}. owner=${owner} amount=${amount}${percent != null ? ` percent=${percent}` : ""}`);
    });
  } catch (err) {
    const msg = err?.response?.data ? JSON.stringify(err.response.data) : err.message;
    console.error("[fetchTopHolders] error:", msg);
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, 3000);
}

function sendSubscribe(wsClient) {
  const payload = { type: "SUBSCRIBE_TOKEN_STATS", data: { address: TOKEN_MINT } };
  wsClient.send(JSON.stringify(payload));
  console.log("[WS] subscribed:", payload);
}

function connectWs() {
  console.log("[WS] connecting...", WS_URL);
  ws = new WebSocket(WS_URL);

  ws.on("open", async () => {
    console.log("[WS] connected");
    sendSubscribe(ws);
    await refreshTopHolders("ws_open");
  });

  ws.on("message", async (buf) => {
    try {
      const msg = JSON.parse(buf.toString());
      const payload = extractStatsPayload(msg);
      const holderCount = extractHolderCount(payload);

      if (holderCount != null && holderCount !== lastStatsHolderCount) {
        console.log(`[HOLDER COUNT CHANGED] ${lastStatsHolderCount} -> ${holderCount} @ ${new Date().toISOString()}`);
        lastStatsHolderCount = holderCount;
        await refreshTopHolders("holder_count_changed");
        return;
      }

      if (Date.now() - lastHolderPullAt >= HOLDER_REFRESH_MS) {
        await refreshTopHolders("periodic_refresh");
      }
    } catch (err) {
      console.error("[WS message parse error]", err.message);
    }
  });

  ws.on("close", (code, reason) => {
    console.error("[WS] closed:", code, reason?.toString?.() || "");
    scheduleReconnect();
  });

  ws.on("error", (err) => {
    console.error("[WS] error:", err.message);
  });
}

setInterval(async () => {
  try {
    const data = await fetchHolderDistribution(TOKEN_MINT);
    const root = data.data || data;
    const dist = root.items || root.list || root.result || root;
    console.log("\n[DISTRIBUTION SNAPSHOT]", new Date().toISOString());
    console.log(JSON.stringify(dist, null, 2).slice(0, 1500));
  } catch (err) {
    const msg = err?.response?.data ? JSON.stringify(err.response.data) : err.message;
    console.error("[fetchHolderDistribution] error:", msg);
  }
}, 5 * 60 * 1000);

connectWs();
