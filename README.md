# 台股看盤小幫手（線上版）

給長輩看盤的一頁式網站：大字、紅漲綠跌、每檔數字都有白話說明、可自己增刪自選股、可試算買賣價。
資料每天自動更新，手機／平板打開網址就能看。

## 檔案

| 檔案 | 作用 |
|---|---|
| `index.html` | 網站本體（讀 `data.json`） |
| `update.py` | 抓行情的腳本（Yahoo Finance + 證交所） |
| `data.json` | 行情資料（由腳本產生，Actions 會自動更新） |
| `.github/workflows/update.yml` | 每天 09:05、13:45（台北）自動更新 |

## 部署到 GitHub Pages（一次就好）

1. 到 https://github.com/new 建立一個 **Public** repo，例如 `stock-helper`。
2. 把這 4 個檔案上傳（或用 git push）。
3. repo → **Settings → Pages** → Source 選 **Deploy from a branch** → Branch: `main` / `/ (root)` → Save。
4. 等 1～2 分鐘，網址會是：
   `https://<你的帳號>.github.io/stock-helper/`
5. repo → **Actions** 分頁確認 `update-data` 有跑過；之後每個交易日 09:05、13:45 會自動更新 `data.json`。

> 手機／平板直接打開上面那個網址即可，會自動載入最新資料。

## 自動更新時間

- **09:05（台北）**：抓「昨收＋今日開盤」，均線用昨天為止的日線算。
- **13:45（台北）**：抓「當日收盤完整」資料。
- 週六日不跑；國定假日跑到的話，抓到的是最近一個交易日，數字不會亂跳。

GitHub 的排程用 UTC，換算已寫在 workflow 裡；實際觸發可能延遲幾分鐘屬正常。

## 收錄哪些股票

自動取「成交金額前 120 名」的上市股票，再加上 `update.py` 的 `DEFAULT_WATCH`（預設持股）。

- 要調檔數：改 `TOP_N`（預設 120）。
- 要固定保留某檔：把代號加進 `DEFAULT_WATCH`。
- 網頁「＋新增股票」從這些股票裡挑；清單外想加的，把代號加進 `DEFAULT_WATCH` 再讓 Actions 跑一次即可。

## 想在自己電腦先看

在資料夾開終端機：

```
python update.py data.json
python -m http.server 8000
```

瀏覽器開 http://localhost:8000/ 。（直接雙擊 index.html 會被瀏覽器擋住讀取 data.json，要透過 http 伺服器。）

## 注意

- 資料來源 Yahoo Finance 為非官方免費來源，偶爾延遲或被限流；證交所為官方來源（三大法人）。
- 支撐／壓力取「近 30 日最低／最高」，是簡化版，不是精密技術分析。
- 年線（240 日）建議用還原股價看，除息跳空會讓長期均線失真。
- 本工具只做整理與白話說明，不構成買賣建議。
