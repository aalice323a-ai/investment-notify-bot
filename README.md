# 株式監視 → LINE自動通知システム

保有銘柄・監視銘柄について、YouTube動画要約/株価・出来高・チャート/マクロイベントカレンダー/弱気シナリオを、平日2回LINEに自動通知するシステムです。

> 個別銘柄のニュース検索・新規監視銘柄の提案機能は、Google Custom Search JSON APIが新規プロジェクトで利用不可になった(Google側の方針変更)ため、現在は無効化しています。詳細は「運用上の注意」を参照してください。

- 日本株パート: 平日 21:00 JST(東証終値確定後)
- 米国株パート: 平日 翌7:00 JST(米国市場引け後)
- 東証休場日(祝日・年末年始等)は日本株パートをスキップ、米国市場休場日は米国株パートをスキップします

実行基盤は GitHub Actions です。追加のサーバー管理は不要ですが、**このリポジトリを public にする必要があります**(チャート画像を `raw.githubusercontent.com` 経由でLINEに配信するため。private リポジトリの場合は別途 Imgur 等への切替が必要です)。

## セットアップ手順

### 1. GitHubリポジトリを作成してpush

このディレクトリの内容を、新規作成した **public** リポジトリにpushしてください。

### 2. Secretsを登録

リポジトリの `Settings → Secrets and variables → Actions → New repository secret` から、以下をすべて登録してください(値はコードに直接書き込まないでください):

| Secret名 | 内容 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging APIのチャネルアクセストークン |
| `LINE_USER_ID` | 通知先のLINEユーザーID |
| `GEMINI_API_KEY` | Google Gemini APIキー(要約・判定・レポート生成に使用。無料枠のFlash系モデルを想定) |

### 3. 監視するYouTubeチャンネルを登録

`data/channels.json` に `{"url": ..., "channel_id": "UC..."}` の形式で追記してください(初期状態は空配列 `[]`)。

```json
[
  {"url": "https://www.youtube.com/@example1", "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx"}
]
```

APIキーは不要ですが、**channelId(`UC`から始まる24文字の文字列)は事前に調べて登録する必要があります**(チャンネルページのHTMLを実行時にスクレイピングしてchannelIdを解決する方式は、YouTubeが返すページ内容が環境やリクエストのたびに変わり信頼できなかったため廃止しました)。

channelIdの調べ方: チャンネルページ(`https://www.youtube.com/@handle`)を開き、ページのソースを表示して `rel="canonical" href="https://www.youtube.com/channel/UCxxxx..."` を探すと確実です。新しいチャンネルを追加したい場合は、そのURLを伝えていただければ代わりに調べて追記します。

### 4. 動作確認

GitHubの `Actions` タブから各ワークフローを `Run workflow`(手動実行)で動かし、LINEにメッセージが届くか確認してください。

ローカルで確認する場合は、上記3つの環境変数をセットした上で:

```bash
pip install -r requirements.txt
python src/main_jp.py
python src/main_us.py
```

## 保有銘柄・監視銘柄の変更

`config/holdings.py` / `config/watchlist.py` を直接編集してください。長期配当目的保有(買い増し・売却判定の対象外)の銘柄は `holdings.py` 内で `dividend_hold=True` として管理しています。

## 運用上の注意

- **LINE無料メッセージ枠**: LINE Messaging APIの無料プランは月あたりのメッセージ数に上限があります(目安 月200通程度、時期により変動)。このシステムはチャート画像を「値動きが目立った銘柄」のみに絞って送信することで枠消費を抑える設計です。アラートが多発する月は枠を超過する可能性があるため、必要に応じて有料プランへの切替を検討してください。
- **API利用料**: Gemini APIは無料枠(Flash系モデルで目安 1分あたり数リクエスト、モデルや契約状況により変動)内に収まるよう、乖離率判定は全銘柄まとめて1回のAPI呼び出しにバッチ化し、429(レート制限)発生時はサーバー指定の待機時間に従って自動リトライする設計にしています。モデル名(既定値 `gemini-flash-latest`)が古くなった場合はエラーになることがあるため、その場合は [Gemini APIのモデル一覧](https://ai.google.dev/gemini-api/docs/models) を確認し、GitHub Secretsに `GEMINI_MODEL` を追加して現行の無料枠モデル名を明示的に指定してください。
- **ニュース検索・新規監視銘柄提案は現在無効**: Google Custom Search JSON APIが新規プロジェクトで使えなくなったため、個別銘柄のニュース深掘り検索と、それを元にした新規監視銘柄の提案機能は削除しています(`GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_CX`への依存も完全に削除済み)。将来的に無料で使える代替の検索手段が見つかれば復活を検討してください。
- **マクロイベントカレンダーは検索APIを使わず固定日程で判定**: FOMC・日銀金融政策決定会合・米雇用統計・CPIはいずれも各公式サイト(FRB・日銀・BLS)が年単位で確定日程を事前公表しているため、`src/macro_calendar.py` に日程を直接ハードコードして持たせています。**年が変わったら翌年分の日程を手動で追記する必要があります**(現在は2026年分のみ登録済み)。米雇用統計・CPIは政府機関の一時閉鎖等で数日ずれることがある点に注意してください。
- **休場日判定の限界**: `jpholiday` ライブラリ + 年末年始固定ロジックによる近似判定です。イレギュラーな臨時休場等には対応していません。米国市場は `pandas_market_calendars`(NYSEカレンダー)で判定しています。
- **状態の永続化**: 処理済みYouTube動画ID(`state/processed_videos.json`)とチャート画像(`charts/`)は、Actions実行のたびにこのリポジトリへ自動コミットされます。

## エラー通知

データ取得(YouTube・株価・Gemini要約等)のいずれかが失敗した場合、無言で終わらせず「◯◯の取得に失敗」という形でLINEに通知します。スクリプト全体が想定外のエラーで停止した場合も、可能な範囲で緊急通知を送ります。
