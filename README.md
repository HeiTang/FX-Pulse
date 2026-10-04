<div align="center">
	<h1>FX Pulse — 匯率脈動</h1>
	<p align="center">
		<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12" />
		<img src="https://img.shields.io/badge/Astro-7-FF5D01?style=flat-square&logo=astro&logoColor=white" alt="Astro 7" />
		<img src="https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind CSS v4" />
		<img src="https://img.shields.io/badge/GitHub_Actions-自動更新-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
	</p>
</div>

<div align="center">
	<p><strong>每日自動收集 VISA、Mastercard 匯率與 JCB 交叉匯率估算，快速比較外幣消費的台幣換算金額。</strong></p>
	<p>透過 Astro 靜態網頁試算消費金額與查看歷史走勢，搭配 GitHub Actions 排程更新。</p>
</div>

---

## ✨ 功能亮點

- **三來源同步比較**：同一幣別、同一天，並列 VISA、Mastercard、JCB 的換算台幣金額與差額，最低換算額自動標示；缺少來源就顯示無資料，不混用其他日期。

- **消費金額試算**：支援 USD、JPY、EUR、GBP、HKD、AUD、KRW、SGD。JPY／KRW 限整數，其他追蹤幣別最多兩位小數；金額須大於零，上限 10 億。

- **手機操作優先**：幣別國旗捷徑、大字金額與可展開的幣別總覽；自訂日期日曆只允許選取有資料的日期。

- **JCB Cross-Rate 解析**：從 jcb.jp 每日公開費率頁取得 USD 基準匯率，以 `TWD/外幣 = (TWD/USD sell) / (外幣/USD buy)` 估算，支援全 8 幣別；USD 分母為 1。

- **互動走勢圖**：ECharts 顯示截至所選日期的 7 個日曆日、30 個日曆日或全部歷史，可切換幣別與來源；缺資料日不補造匯率，線段可能跨過缺資料日。

- **自動回補缺漏**：GitHub Actions 每日抓取後，掃描近 7 天缺漏的「日期＋來源」並嘗試回補；JCB 週末自動略過。來源阻擋、假日或格式變更仍可能造成缺漏。

- **彈性 CLI 與狀態回報**：可指定來源、日期、區間、月份，支援 dry-run 與結果報告；JCB 月份抓取採逐日循序請求。請求失敗有限重試，Cloudflare 阻擋會停止該來源。

- **靜態網站架構**：Astro 讀取 `rates.json` 建置，透過 GitHub Pages 託管，無需常駐 API 伺服器。匯率日期與資料檔最後寫入時間分開顯示，開啟頁面時不會即時查詢外部匯率。

本專案為非官方工具。**換算額未計銀行手續費、回饋及實際入帳日期，不能視為實際帳單或信用卡推薦。** VISA 查詢設定 `fee=0`；Mastercard 設定 `bank_fee=0`。JCB 使用 jcb.jp 公開 USD 基準頁，依 `TWD/外幣 = (TWD/USD sell) / (外幣/USD buy)` 估算；USD 分母為 1。

## 本機開發

需求：Node.js 22.12+、Python 3.12+、Poetry。

```bash
cd web
npm ci
npm run dev                  # http://localhost:4321
```

前端是 Astro 7、Tailwind CSS 4、TypeScript、ECharts 6。開發及預覽不需啟動 API。

```bash
cd api
poetry install
poetry run uvicorn fx_pulse.main:app --reload
```

FastAPI 提供 `/rates/latest?source=VISA` 及 `/rates/history/JPY?source=VISA&days=30`。歷史 API 的天數是截至最新儲存日期的日曆日範圍；來源缺資料不會自動填入。

## 抓取與回補

以下指令會查詢外部資料來源；不加 `--dry-run` 會寫入資料檔案。

```bash
cd api
poetry run fetch-rates
poetry run fetch-rates --source VISA,JCB --date 2026-04-15 --dry-run
poetry run fetch-rates --month 2026-04
poetry run fetch-rates --from 2026-04-01 --to 2026-04-16 --delay 2
poetry run backfill-rates --days 7 --dry-run
poetry run backfill-rates --days 14 --source VISA,Mastercard
```

日期／月份／區間不可混用，也不接受未來日期。JCB 月份抓取以逐日循序請求進行；404 略過，解析失敗會回報錯誤。爬蟲使用有限重試與請求間隔；Cloudflare 阻擋會停止該來源。自動化需透過 `--result-file result.json` 檢查 `status`，CLI 抓取錯誤會保留在結果摘要中。JSON 以暫存檔原子替換，寫入中斷不截斷舊資料；空匯率集合不能覆蓋既有來源。

## 環境變數

設定於 專案根目錄的 `.env` 或環境變數，前綴為 `FX_`。

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `FX_DATA_FILE` | `web/src/data/rates.json` | 資料檔案路徑 |
| `FX_CURRENCIES` | `["USD","JPY","EUR","GBP","HKD","AUD","KRW","SGD"]` | 追蹤幣別（JSON 陣列） |
| `FX_SCRAPER_TIMEOUT` | `20` | HTTP 逾時秒數 |
| `FX_SCRAPER_MAX_RETRIES` | `5` | 最大嘗試次數 |
| `FX_SCRAPER_DELAY_MIN` | `1.5` | 幣別請求最小間隔秒數 |
| `FX_SCRAPER_DELAY_MAX` | `3.5` | 幣別請求最大間隔秒數 |
| `FX_SCRAPER_BACKOFF_CAP` | `60` | 重試等待上限秒數 |

## 驗證

```bash
cd api
poetry run ruff check src tests scripts
poetry run ruff format --check src tests scripts
poetry run pytest -q
```

```bash
cd web
npm run check
npm run format:check
npm test
npm run build
npx playwright install chromium
npm run test:e2e
npm audit
```

若 Mac 已安裝 Chrome，可用 `PW_BROWSER_CHANNEL=chrome npm run test:e2e`。瀏覽器測試啟動獨立的 `127.0.0.1:4322` 預覽，涵蓋 1280、768、680、390、320px、金額／精度、同日換算／差額、缺來源、日曆範圍／鍵盤、走勢切換、總覽、資產載入及 axe 無障礙檢查。手機測試使用 Chromium 模擬，不能代替真機 Safari。後端測試以固定回應與 mock 驗證解析／重試，不呼叫外部匯率站或發送 Discord。

CI 執行前後端檢查及瀏覽器測試。`npm audit` 目前仍回報 Astro 間接依賴 `http-cache-semantics@4.2.0` 的 [GHSA-ch52-4w7c-c8xp](https://github.com/advisories/GHSA-ch52-4w7c-c8xp)，上游尚無修正版（2026-10-04 檢查）。Astro 在遠端圖片建置快取中引用它；本專案只使用本機 SVG／ICO，且輸出靜態 HTML，沒有共享使用者回應快取。仍須追蹤上游更新，不能宣稱 audit 全通過。

## 程式與素材

- `api/src/fx_pulse/`：CLI、FastAPI、來源爬蟲及 JSON 儲存。
- `web/src/pages/index.astro`：頁面結構；`web/src/lib/`：試算、匯率規則、日曆及延後載入的圖表。
- `web/src/data/rates.json`：既有資料介面，由排程更新。
- `web/tests/`、`api/tests/`：可重跑的回歸測試。
- 圖示出處與授權見 [web/ASSETS.md](web/ASSETS.md)；`logo/` 保留專案品牌 SVG 原始素材。
