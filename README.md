<div align="center">
	<h1>FX Pulse — 匯率脈動</h1>
	<p align="center">
		<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12" />
		<img src="https://img.shields.io/badge/Astro-6-FF5D01?style=flat-square&logo=astro&logoColor=white" alt="Astro 6" />
		<img src="https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind CSS v4" />
		<img src="https://img.shields.io/badge/GitHub_Actions-自動更新-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
	</p>
</div>

<div align="center">
	<p><strong>每日自動抓取 VISA、Mastercard、JCB 三大信用卡組織官方匯率，一眼比較誰最划算。</strong></p>
	<p>透過 Astro 靜態網頁展示歷史走勢，GitHub Actions 全自動更新，零伺服器成本。</p>
</div>

---

## ✨ 功能亮點

- **三來源同步比較**：同一幣別、同一天，三家匯率並排顯示，最優自動標綠、最差標紅。

- **JCB Cross-Rate 解析**：JCB 無公開 API，從 jcb.jp 每日費率頁抓取 USD 基準匯率，以 `TWD/外幣 = (TWD/USD sell) / (外幣/USD buy)` 計算，支援全 8 幣別。

- **Bot 防護繞過**：使用 curl-cffi Chrome TLS 指紋模擬，成功繞過 VISA Cloudflare 與 Mastercard Akamai 防護。

- **互動走勢圖**：ECharts 三線對比圖，點擊幣別卡片即切換，支援滑動縮放。

- **自動回補缺漏**：每日抓取後自動掃描近 7 天缺漏的 `(日期, 來源)` pair，JCB 週末自動跳過，確保歷史資料完整。

- **彈性 CLI**：可指定來源、日期、區間、月份，dry-run 驗證，JCB 整月批量抓取優化（逐日平行請求）。

- **零伺服器成本**：靜態網頁 × GitHub Pages，爬蟲排程 × GitHub Actions，全程無伺服器。

## 🚀 快速開始

### 後端（爬蟲）

```bash
cd api
poetry install
poetry run fetch-rates        # 抓今日全部來源
```

### 前端

```bash
cd web
npm install
npm run dev                   # localhost:4321
```

## 🛠 CLI 用法

### `fetch-rates` — 抓取匯率

```bash
# 抓今日全部來源
poetry run fetch-rates

# 指定來源（逗號分隔，大小寫不限）
poetry run fetch-rates --source VISA,JCB

# 指定單日
poetry run fetch-rates --date 2026-04-15

# 指定月份（展開為每一天）
poetry run fetch-rates --month 2026-04

# 指定區間
poetry run fetch-rates --from 2026-04-01 --to 2026-04-16

# Dry run（印出結果，不寫入 rates.json）
poetry run fetch-rates --source JCB --date 2026-04-15 --dry-run

# 控制請求間隔（秒）
poetry run fetch-rates --month 2026-04 --delay 2.0
```

### `backfill-rates` — 補回缺漏資料

```bash
# 掃描並補回近 7 天缺漏（預設）
poetry run backfill-rates

# 指定回溯天數
poetry run backfill-rates --days 14

# 只補特定來源
poetry run backfill-rates --source VISA,Mastercard

# Dry run（只印出缺漏，不抓資料）
poetry run backfill-rates --dry-run
```

## ⚙️ 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `FX_DATA_FILE` | `web/src/data/rates.json` | 資料輸出路徑 |
| `FX_CURRENCIES` | `["USD","JPY","EUR","GBP","HKD","AUD","KRW","SGD"]` | 追蹤幣別 |
| `FX_SCRAPER_TIMEOUT` | `20` | HTTP 請求逾時（秒）|
| `FX_SCRAPER_MAX_RETRIES` | `5` | 最大重試次數 |
| `FX_SCRAPER_DELAY_MIN` | `1.5` | 請求間最小間隔（秒）|
| `FX_SCRAPER_DELAY_MAX` | `3.5` | 請求間最大間隔（秒）|

透過 `.env` 檔或環境變數設定，所有變數均以 `FX_` 為前綴。

## 🧪 測試

```bash
cd api
poetry run pytest -v
poetry run ruff check src/ tests/
```

## 📁 架構

```
FX-Pulse/
├── api/                        # Python 後端（Poetry）
│   ├── src/fx_pulse/
│   │   ├── cli.py              # fetch-rates / backfill-rates CLI（click）
│   │   ├── config.py           # pydantic-settings 集中管理
│   │   ├── scraper/            # VisaScraper / MastercardScraper / JcbScraper
│   │   └── store/              # JsonStore + find_missing（Repository Pattern）
│   └── tests/
└── web/                        # Astro 前端
    └── src/
        ├── data/rates.json     # CI 自動更新
        └── pages/index.astro
```

## ⚠️ 注意事項

- 本專案為非官方工具，與 VISA、Mastercard、JCB 無官方關聯。

- 資料來源仰賴各信用卡發卡組織官網的匯率查詢，格式與可用性可能隨時變動。

- 本專案使用 jcb.jp 公開費率頁計算 JCB 匯率，非直接引用 JCB 台灣官方 API。
