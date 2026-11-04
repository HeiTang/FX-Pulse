# FX Pulse GA4

## 後台設定

2026-11-04 以已登入的 GA 後台核對：資源 `561582782`，網站串流 `FX Pulse Web` / `16238397265`，網址 `https://fx.purr.tw`，評估 ID `G-4CXCX1QQP7`。

加強型評估目前關閉，程式以 `send_page_view: false` 加上一次手動 `page_view` 記錄進站頁。修改試算條件的 `history.replaceState` 不當作新瀏覽。若之後啟用加強型評估，需關閉「依據瀏覽器歷史紀錄事件的網頁變更」，避免自動頁面瀏覽與手動計數混用。

所有 GA 事件只在正式 origin 啟用。本機與測試不傳送到 Google；測試以正式 hostname 代理本機建置，並攔截 Google 收集端點。

## 事件

| 事件 | 觸發條件 | 參數 |
| --- | --- | --- |
| `page_view` | 每次頁面載入一次 | 進站 pathname 與允許的 UTM；不含試算 query |
| `calculate` | 修改條件後的有效試算，去抖與相同條件去重；預設結果不算 | `foreign_currency`、`conversion_direction` |
| `rate_tab_view` | 文件在前景，所選頁籤內容至少 10% 進入可視區；每次頁面載入每個頁籤只記一次 | `tab_name`、首次觀看時的 `foreign_currency` |
| `chart_filter_change` | 使用者實際變更期間或來源；重點目前值不送出，切回先前值算一次變更 | `filter_type`、`filter_value`、`foreign_currency` |

切換幣別不重設頁籤觀看去重；重新載入才重設。後台分頁不記觀看，返回前景時才記錄仍在可視區的所選頁籤。所有參數均為有限選項，不記錄金額或所選日期。

GA 標籤在 idle 載入（1000ms timeout、timer 備援），事件立即排隊。排隊不代表 Google 已收到；封鎖器、網路錯誤及極短停留都可能使事件未送達。

## 事件範圍自訂維度

| 後台名稱 | 參數 | 值 |
| --- | --- | --- |
| 試算外幣 | `foreign_currency` | 8 種支援幣別 |
| 換算方向 | `conversion_direction` | `foreign-to-twd`、`twd-to-foreign` |
| 匯率頁籤 | `tab_name` | `chart`、`history`、`method` |
| 圖表篩選類型 | `filter_type` | `range`、`source` |
| 圖表篩選值 | `filter_value` | 期間：`7`、`30`、`all`；來源：`all`、`VISA`、`Mastercard`、`JCB` |

前兩項原已建立；後三項於 2026-11-04 建立。定義已在 GA 後台生效，網站新事件需等此 PR 部署後才會由正式站送出。一般報表的處理有延遲，定義不會替過去未收集的互動補資料。

建議先按工作階段比較有試算互動的比例，再看各頁籤使用率與圖表篩選分布；事件次數不能直接當成人數。

參考：[GA 手動與自動網頁瀏覽](https://developers.google.com/analytics/devguides/collection/ga4/views)、[自訂維度](https://support.google.com/analytics/answer/14240153)。
