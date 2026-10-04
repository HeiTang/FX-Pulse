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

- **三家一眼比較**：並列 VISA、Mastercard、JCB 的台幣換算金額，清楚標示最低換算額與差額。

- **雙向金額試算**：輸入外幣消費金額比較台幣換算額，或點選雙向箭頭，從台幣預算反推可換得的外幣金額。

- **手機輕鬆操作**：大字金額、國旗幣別捷徑與簡潔版面，方便在旅途中查詢。

- **歷史匯率查詢**：選擇日期查看當天匯率，搭配 7 天、30 天或全部歷史走勢，掌握匯率變化。

- **每日自動更新**：持續整理每日參考匯率，清楚顯示資料日期。

- **Bot 防護處理**：使用 curl-cffi 模擬瀏覽器 TLS 指紋；遇到 Cloudflare 阻擋時會明確回報，避免反覆無效重試。

- **自動回補缺漏**：每日分開時段檢查近 7 天缺少的日期、來源與幣別並嘗試回補；已成功的資料會保留，JCB 週末自動略過。

- **彈性 CLI**：可指定來源、日期、區間或月份，支援 dry-run 預覽；JCB 月份抓取採逐日循序請求。

本專案為非官方工具。**換算額未計銀行手續費、回饋及實際入帳日期，非實際帳單；JCB 為交叉匯率估算。**

## 🚀 快速開始

### 啟動網頁

需求：Node.js 22.12+、Git。

```bash
git clone https://github.com/HeiTang/FX-Pulse.git
cd FX-Pulse/web
npm ci
npm run dev
```

開啟 [http://localhost:4321](http://localhost:4321)，選擇消費幣別、輸入金額，再選擇匯率日期，即可查看換算結果與歷史走勢。

前端直接使用專案內的匯率資料，啟動網頁不需另外啟動 API。

### 更新匯率資料

需求：Python 3.12+、Poetry。另開終端機，在專案根目錄執行：

```bash
cd api
poetry install
poetry run fetch-rates
```

這會抓取今日匯率並更新 `web/src/data/rates.json`。指定日期、試跑與回補方式見下方「CLI 用法」。

## 🛠 CLI 用法

先依快速開始安裝 Python 套件，以下指令皆在 `api/` 目錄執行。未加 `--dry-run` 時，成功取得的匯率會寫入 `web/src/data/rates.json`。

### `fetch-rates` — 抓取匯率

```bash
# 抓取今日全部來源
poetry run fetch-rates

# 指定來源，可用逗號分隔，大小寫不限
poetry run fetch-rates --source VISA,JCB

# 指定單日
poetry run fetch-rates --date 2026-04-15

# 指定月份
poetry run fetch-rates --month 2026-04

# 指定日期區間，設定幣別請求間隔為 2 秒
poetry run fetch-rates --from 2026-04-01 --to 2026-04-16 --delay 2

# 查詢並印出結果，不寫入匯率資料
poetry run fetch-rates --source JCB --date 2026-04-15 --dry-run
```

`--date`、`--month`、`--from/--to` 三種日期選擇方式不可混用；`--from` 與 `--to` 必須成對使用。不接受未來日期，當月只抓到今天。JCB 月份抓取採逐日循序請求。

### `backfill-rates` — 回補缺漏

```bash
# 檢查近 7 天（預設），並抓取缺少的日期與來源
poetry run backfill-rates

# 指定回溯天數
poetry run backfill-rates --days 14

# 只回補指定來源
poetry run backfill-rates --source VISA,Mastercard

# 只列出缺漏，不查詢外部來源，也不寫入匯率資料
poetry run backfill-rates --days 7 --dry-run
```

回補只請求缺少的幣別，並與既有資料合併；不會重抓已完整的日期／來源。JCB 略過週末；來源阻擋或未發布資料時，仍可能無法補齊。

### 儲存執行報告

兩個指令都支援 `--result-file`，方便查看執行結果或交由自動化程式判斷：

```bash
poetry run fetch-rates --result-file scrape_result.json
poetry run backfill-rates --days 7 --result-file backfill_result.json
```

結果檔記錄整體與各來源的執行狀態、錯誤資訊；回補報告另記錄缺漏日期／來源組數（`missing_found`／`missing_remaining`）、補回與仍缺少的日期／來源／幣別筆數（`currencies_recovered`／`currencies_remaining`），以及冷卻來源的 `next_retry_at`（UTC）。這些報告與匯率資料分開儲存。自動化應檢查報告的 `status`，不要只依 CLI 退出碼判斷抓取成功。

### 查看完整參數

```bash
poetry run fetch-rates --help
poetry run backfill-rates --help
```

## API 使用

若需要透過 HTTP 取得匯率，可在已安裝套件的 `api/` 目錄啟動 FastAPI：

```bash
poetry run uvicorn fx_pulse.main:app --reload
```

- 最新匯率：`http://127.0.0.1:8000/rates/latest?source=VISA`
- 歷史匯率：`http://127.0.0.1:8000/rates/history/JPY?source=VISA&days=30`
- API 文件：`http://127.0.0.1:8000/docs`

歷史 API 的天數是截至最新儲存日期的日曆日範圍；來源缺資料不會自動填入。

## 環境變數（選用）

一般使用不需要設定，後端會採用預設值。需要調整抓取逾時、請求間隔、追蹤幣別或資料檔案路徑時，才使用這些設定。

可參考 [.env.example](.env.example)，在專案根目錄建立 `.env`，例如將抓取逾時調整為 30 秒：

```dotenv
FX_SCRAPER_TIMEOUT=30
```

CLI 下次執行時會讀取新設定；已啟動的 API 需重新啟動。也可透過執行環境設定相同的 `FX_` 變數，環境變數優先於 `.env`。

這些設定作用於後端，前端建置仍讀取 `web/src/data/rates.json`；若另設資料輸出路徑，需自行將資料同步回該檔案。


| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `FX_DATA_FILE` | `web/src/data/rates.json` | 資料檔案路徑 |
| `FX_CURRENCIES` | `["USD","JPY","EUR","GBP","HKD","AUD","KRW","SGD"]` | 追蹤幣別（JSON 陣列） |
| `FX_SCRAPER_STATE_FILE` | `api/scrape_state.json`（專案根目錄下） | 跨次執行的來源冷卻狀態 |
| `FX_SCRAPER_TIMEOUT` | `20` | HTTP 逾時秒數 |
| `FX_SCRAPER_MAX_RETRIES` | `3` | 單次請求最大嘗試次數，包含首次 |
| `FX_SCRAPER_DELAY_MIN` | `3` | 幣別／日期請求最小間隔秒數 |
| `FX_SCRAPER_DELAY_MAX` | `6` | 幣別／日期請求最大間隔秒數 |
| `FX_SCRAPER_BACKOFF_BASE` | `5` | 指數退避起始秒數 |
| `FX_SCRAPER_BACKOFF_CAP` | `60` | 重試等待上限秒數 |

## 資料說明

- 網頁使用 `web/src/data/rates.json` 建置，開啟頁面時不會即時查詢外部匯率。匯率日期與資料檔最後寫入時間分開顯示；缺少來源時不混用其他日期。
- VISA 查詢設定 `fee=0`，Mastercard 設定 `bank_fee=0`。JCB 使用 jcb.jp 公開 USD 基準頁，依 `TWD/外幣 = (TWD/USD sell) / (外幣/USD buy)` 估算；USD 分母為 1。
- 輸入幣別為 JPY／KRW 時限整數，TWD 與其他追蹤幣別最多兩位小數；金額須大於零，上限 10 億。切換方向保留金額數字；反向使用同日參考匯率倒數試算，非銀行換匯報價。
- 歷史走勢的 7／30 天以日曆日計算，缺資料日不補造匯率，線段可能跨過缺資料日。
- 每日分開時段抓取與回補近 7 天缺漏；JCB 週末略過，不以週五資料冒充週末匯率。來源阻擋、假日或格式變更仍可能造成缺漏。
- JSON 以暫存檔原子替換，寫入中斷不截斷舊資料；空匯率集合不能覆蓋既有來源。

## 開發驗證

以下指令分別從專案根目錄執行，並先完成對應套件安裝。

### 後端

```bash
cd api
poetry run ruff check src tests scripts
poetry run ruff format --check src tests scripts
poetry run pytest -q
```

### 前端

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

瀏覽器測試涵蓋桌面與手機尺寸的主要操作，CI 也會執行這些檢查。若使用 Mac 已安裝的 Chrome，可將瀏覽器測試指令改為 `PW_BROWSER_CHANNEL=chrome npm run test:e2e`，不必另下載 Chromium。

---

圖示來源與授權：[素材說明](web/ASSETS.md)。
