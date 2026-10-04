# Issue #1：關閉建議（待審閱，尚未發布）

Issue：https://github.com/HeiTang/FX-Pulse/issues/1

核對日期：2026-10-05（Asia/Taipei）。

建議在本次資料標示改善合併後，貼上下列說明並關閉 Issue。

---

目前 JCB adapter 已改為讀取 jcb.jp 的每日 USD 基準 HTML 表，依
`(TWD/USD sell) / (外幣/USD buy)` 計算交叉匯率估算，已不受原本月份 PDF 的幣別清單限制。

核對目前版本的 `web/src/data/rates.json`：2026-04-01 至 2026-10-02 間，有 133 個日期同時包含 JCB 的 GBP、AUD、SGD；最近一筆為 2026-10-02。因此本 Issue 原先「這三個幣別不支援」的描述已不適用。

這些數字是交叉匯率估算，不能解讀為 JCB 官方直接公布的三組 TWD 刷卡匯率，也不保證每個日期都有資料。此次介面改善已在 JCB 結果旁標示「約」與「交叉匯率估算」；缺資料仍維持同日期的缺漏，不用其他日期替代，週末另說明目前略過抓取的策略。

原議題可關閉；後續若出現特定日期或幣別缺漏，請以日期、幣別與抓取報告另開問題，便於追蹤實際原因。

---

## 可重現核對

```sh
jq '[.rates | to_entries[] | select(.value.JCB.GBP and .value.JCB.AUD and .value.JCB.SGD)] | {count: length, first: .[0].key, last: .[-1].key}' web/src/data/rates.json
```

來源處理：`api/src/fx_pulse/scraper/jcb.py` 的 `fetch_all` 與 `_compute_cross_rate`。
以上證據只確認 adapter 的方法與儲存資料涵蓋，沒有宣稱真實帳單驗證。
