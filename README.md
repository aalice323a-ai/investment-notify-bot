# 株式監視 → LINE自動通知システム

保有銘柄・監視銘柄について、YouTube動画要約/株価・出来高情報/マクロイベントカレンダー/弱気シナリオを、平日2回LINEに自動通知するシステムです。

> 個別銘柄のニュース検索・新規監視銘柄の提案機能は、Google Custom Search JSON APIが新規プロジェクトで利用不可になった(Google側の方針変更)ため、現在は無効化しています。詳細は「運用上の注意」を参照してください。

- 日本株パート: 平日 21:00 JST(東証終値確定後)
- 米国株パート: 平日 翌7:00 JST(米国市場引け後)
- 東証休場日(祝日・年末年始等)は日本株パートをスキップ、米国市場休場日は米国株パートをスキップします

実行基盤は GitHub Actions です。追加のサーバー管理は不要です。チャート画像の生成・送信機能は削除済みで、外部に公開するファイルが無いため、**このリポジトリはpublicである必要はありません**(privateで運用できます)。

## セットアップ手順

### 1. GitHubリポジトリを作成してpush

このディレクトリの内容を、新規作成したリポジトリにpushしてください(保有銘柄など個人の情報を含むため、privateでの運用を推奨します)。

### 2. Secretsを登録

リポジトリの `Settings → Secrets and variables → Actions → New repository secret` から、以下をすべて登録してください(値はコードに直接書き込まないでください):

| Secret名 | 内容 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging APIのチャネルアクセストークン |
| `LINE_USER_ID` | 通知先のLINEユーザーID |
| `ANTHROPIC_API_KEY` | Anthropic Claude APIキー(要約・判定・レポート生成に使用。既定モデルは Haiku 4.5) |

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

GitHubの `Actions` タブから各ワークフローを `Run workflow`(手動実行)で動かし、LINEにメッセージが届くか確認してください。全部で5つのワークフローがあります:

| ワークフロー | 用途 |
|---|---|
| `JP Session (21:00 JST)` | 日本株パート本番(cron + 手動実行) |
| `US Session (7:00 JST)` | 米国株パート本番(cron + 手動実行) |
| `Test LINE Send (manual)` | 株価取得・YouTube・Claude要約に一切依存せず、LINE Messaging APIへの送信だけを検証する最小限のワークフロー(`LINE_CHANNEL_ACCESS_TOKEN`/`LINE_USER_ID`のみで動作)。LINE送信そのものが疑わしい場合はまずこれを実行して切り分ける |
| `Update Holdings (manual)` | 保有銘柄リストの更新(詳細は次項) |
| `Update Watchlist (manual)` | 監視銘柄リストの更新(詳細は次項) |

ローカルで確認する場合は、上記3つの環境変数をセットした上で:

```bash
pip install -r requirements.txt
python src/main_jp.py
python src/main_us.py
```

## 保有銘柄・監視銘柄の変更

### 保有銘柄(`data/holdings.json`)

保有銘柄はLINEからのメッセージで直接更新する仕組み(Webhookサーバーが必要になり構成が複雑になるため見送り)ではなく、**GitHub Actionsの `Update Holdings (manual)` ワークフローをブラウザから手動実行し、テキスト入力欄に保有銘柄リストを貼り付けることで更新**します。

1. `Actions` タブ → `Update Holdings (manual)` → `Run workflow`
2. `holdings_text` の入力欄に、1行1銘柄で以下の形式で貼り付ける(この内容で **リスト全体を置き換え** ます。部分更新ではありません):
   ```
   2802,味の素,JP
   8001,伊藤忠商事,JP,dividend_hold
   AMD,AMD,US
   ```
   `コード,名称,市場(JP/US)[,dividend_hold]`。長期配当目的保有(買い増し・売却判定の対象外)にしたい銘柄だけ4つ目に `dividend_hold` を付けます。
3. 実行すると `data/holdings.json` がコミットされ、更新結果(銘柄数・一覧)がLINEに届きます。1行でも形式が不正な場合は更新を行わずエラー通知します。

`data/holdings.json` を直接編集しても構いません。`config/holdings.py` は単にこのJSONを読み込むローダーです。

### 監視銘柄(`data/watchlist.json`)

保有銘柄と同じ仕組みです。**`Update Watchlist (manual)` ワークフローをブラウザから手動実行し、テキスト入力欄に監視銘柄リストを貼り付けることで更新**します。

1. `Actions` タブ → `Update Watchlist (manual)` → `Run workflow`
2. `watchlist_text` の入力欄に、1行1銘柄で以下の形式で貼り付ける(この内容で **リスト全体を置き換え** ます。部分更新ではありません):
   ```
   8035,東京エレクトロン,JP
   NVDA,NVIDIA,US
   ```
   `コード,名称,市場(JP/US)`。監視銘柄には長期配当保有の概念が無いため、保有銘柄と違って `dividend_hold` フィールドはありません(常に3フィールド)。
3. 実行すると `data/watchlist.json` がコミットされ、更新結果(銘柄数・一覧)がLINEに届きます。1行でも形式が不正な場合は更新を行わずエラー通知します。

`data/watchlist.json` を直接編集しても構いません。`config/watchlist.py` は単にこのJSONを読み込むローダーです。

## 運用上の注意

- **LINE無料メッセージ枠**: LINE Messaging APIの無料プランは月あたりのメッセージ数に上限があります(目安 月200通程度、時期により変動)。1回のセッションにつきテキストメッセージ1〜数通(4500字超で自動分割)のみを送信する設計のため、平日2回運用でも枠に収まりやすいはずです。
- **API利用料**: Anthropic Claude APIは従量課金です。コストを抑えるため既定モデルは **Claude Haiku 4.5**(`claude-haiku-4-5-20251001`)にしており、モデルを変更したい場合はGitHub Secretsに `CLAUDE_MODEL` を追加すれば上書きできます。また、動画判定・週足乖離率判定はいずれも対象をまとめて1回のAPI呼び出しに送るバッチ設計にしており(件数分だけ呼び出さない)、system prompt(判断基準・出力フォーマットなど毎回変わらない部分)には[プロンプトキャッシュ](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)(`cache_control: ephemeral`)を付与して、繰り返し呼び出す際の入力トークンコストを削減しています。ただし各system promptは現状Haikuのキャッシュ最小トークン数を下回っている可能性があり、その場合キャッシュは効果を発揮しません(エラーにはなりません)。429(レート制限)・529(サーバー過負荷)発生時は自動リトライ(最大6回、過負荷時90秒待機)します。
- **ニュース検索・新規監視銘柄提案は現在無効**: Google Custom Search JSON APIが新規プロジェクトで使えなくなったため、個別銘柄のニュース深掘り検索と、それを元にした新規監視銘柄の提案機能は削除しています(`GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_CX`への依存も完全に削除済み)。将来的に無料で使える代替の検索手段が見つかれば復活を検討してください。
- **マクロイベントカレンダーは検索APIを使わず固定日程で判定**: FOMC・日銀金融政策決定会合・米雇用統計・CPIはいずれも各公式サイト(FRB・日銀・BLS)が年単位で確定日程を事前公表しているため、`src/macro_calendar.py` に日程を直接ハードコードして持たせています。**年が変わったら翌年分の日程を手動で追記する必要があります**(現在は2026年分のみ登録済み)。米雇用統計・CPIは政府機関の一時閉鎖等で数日ずれることがある点に注意してください。
- **休場日判定の限界**: `jpholiday` ライブラリ + 年末年始固定ロジックによる近似判定です。イレギュラーな臨時休場等には対応していません。米国市場は `pandas_market_calendars`(NYSEカレンダー)で判定しています。
- **状態の永続化**: 処理済みYouTube動画ID(`state/processed_videos.json`)は、Actions実行のたびにこのリポジトリへ自動コミットされます。
- **チャート画像は非搭載**: 以前は日足・週足チャート画像を生成してLINEに送信していましたが、画質が粗く実用性が低かったため機能ごと削除しました。株価・出来高・移動平均トレンド・週足乖離率の判定はテキストのみで届きます。

## エラー通知

データ取得(YouTube・株価・Claude要約等)のいずれかが失敗した場合、無言で終わらせず「◯◯の取得に失敗」という形でLINEに通知します。スクリプト全体が想定外のエラーで停止した場合も、可能な範囲で緊急通知を送ります。
