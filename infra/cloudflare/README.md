# FX Pulse 快取設定

狀態：**待套用，尚未修改正式站**。網站部署於 GitHub Pages；此目錄不會被 GitHub Pages 部署流程自動執行。

`hashed-assets-cache-rule.json` 是 Cloudflare **Cache Response Rule** 的單一規則，套用 phase 為 `http_response_cache_settings`。Cloudflare Free 支援此類規則。

## 規則範圍

- Host：`fx.purr.tw`。
- 方法：GET、HEAD；狀態：200、304。
- 路徑：`/_astro/*.*.js`，例如 `/_astro/chart.OQXj0sPx.js`。
- Cache-Control：`public, max-age=31536000, immutable`，供瀏覽器及 CDN 使用。
- 首頁、幣別 HTML、sitemap、非 hash 的 `app.js` 與錯誤回應不符合此規則。HTML 目前的短快取保留。

`/_astro/` 必須持續只放 Astro / Vite 產生、內容變更即換檔名的資產。若之後新增固定檔名的 JS，先調整規則。

## 套用方式（需另行核准正式站設定變更）

1. 進入 Cloudflare 的 `purr.tw` Zone → Caching → Cache Response Rules，新增規則，使用 JSON 中的 expression 與 action parameters。
2. API 操作時，先讀取該 phase 的 entrypoint。若不存在，建立 `kind: zone`、`phase: http_response_cache_settings` 的 ruleset 並將本規則加入 `rules`。若已存在，新增此規則並保留既有規則；不要以單一規則覆蓋整份 ruleset。
3. 使用 Rules simulator 確認：實際建置出的 JS 命中；`/jpy/`、`/sitemap.xml`、`/_astro/app.js` 及不存在的 JS 不命中。
4. 檢查實際 JS 回應的 Cache-Control 包含一年 max-age 與 immutable；HTML 仍為短快取，404 未被延長快取。CDN HIT 與瀏覽器快取需分別驗證。

2026-11-04 唯讀檢查：Zone 使用 Free，Rulesets 清單未見此 phase。現有 token 可讀 Zone / Rulesets，但 Zone Settings 與 RUM API 未授權；未以 API 寫入或驗證此規則。這份 JSON 是新增單一規則的 payload，沒有可直接觸發套用的 workflow 或腳本。

## 分析工具

GA4 記錄 landing page 與 `calculate` 事件（幣別、方向，不含金額）；Cloudflare Beacon 可提供 RUM 效能資料。此修改保留兩者，GA 的事件立即排隊，標籤程式改在瀏覽器空閒時載入，最多等待 1 秒（實際執行仍受主執行緒及背景分頁節流影響）；不支援 requestIdleCallback 時使用下一個 timer task。極短停留仍可能在標籤載入完成前離開，排隊不等於 Google 已收到事件。

Cloudflare Beacon 由正式站邊緣注入，儲存庫沒有該標籤；本 PR 未變更其注入設定。

## 參考

- [Cache Response Rules](https://developers.cloudflare.com/cache/how-to/cache-response-rules/)
- [動作參數與 expression 欄位](https://developers.cloudflare.com/cache/how-to/cache-response-rules/settings/)
- [API 套用與既有規則保留](https://developers.cloudflare.com/cache/how-to/cache-response-rules/create-api/)
- [Cloudflare RUM beacon](https://developers.cloudflare.com/speed/observatory/rum-beacon/)
