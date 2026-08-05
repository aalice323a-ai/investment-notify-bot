"""main_jp.py / main_us.py から共通で使うデータ収集・オーケストレーション処理。"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from config.holdings import Holding
from src import claude_client, git_publish, line_client, news, stocks, youtube

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "state" / "processed_videos.json"
CHANNELS_PATH = REPO_ROOT / "data" / "channels.json"
CHARTS_ROOT = REPO_ROOT / "charts"

# 前日比この%以上、または出来高が過去20日平均の2倍以上で「値動きが目立った銘柄」とみなす
MOVE_ALERT_PCT = 3.0
# 週足乖離率の過去分布percentileがこの値以上なら「過熱懸念」候補としてチャート画像を送る対象にする
OVERHEAT_PERCENTILE = 90.0


# ---------------------------------------------------------------------------
# 状態(処理済み動画ID)・チャンネル一覧
# ---------------------------------------------------------------------------

def load_processed_videos() -> dict[str, list[str]]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_processed_videos(state: dict[str, list[str]]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_channels() -> list[str]:
    if CHANNELS_PATH.exists():
        return json.loads(CHANNELS_PATH.read_text(encoding="utf-8"))
    return []


# ---------------------------------------------------------------------------
# ① YouTube動画の要約(日本株パートのみで呼び出す)
# ---------------------------------------------------------------------------

def collect_video_facts(target_names: list[str]) -> tuple[list[dict], dict[str, list[str]]]:
    channels = load_channels()
    state = load_processed_videos()
    summaries: list[dict] = []

    for url in channels:
        try:
            channel_id = youtube.resolve_channel_id(url)
        except Exception as e:
            line_client.notify_failure(f"YouTubeチャンネル({url})の解決", str(e))
            continue

        known_ids = set(state.get(channel_id, []))
        try:
            new_videos = youtube.fetch_new_videos(channel_id, known_ids)
        except Exception as e:
            line_client.notify_failure(f"YouTubeチャンネル({url})の新着動画取得", str(e))
            continue

        for video in new_videos:
            # 採否に関わらず処理済みとして記録し、重複処理を防ぐ
            state.setdefault(channel_id, []).append(video.video_id)

            transcript = youtube.fetch_transcript(video.video_id)
            if not transcript:
                continue

            try:
                judgement = claude_client.judge_video(video.title, transcript, target_names)
            except Exception as e:
                line_client.notify_failure(f"動画『{video.title}』の要約", str(e))
                continue

            if judgement.get("relevant"):
                summaries.append(
                    {
                        "title": video.title,
                        "url": video.url,
                        "summary": judgement.get("summary", ""),
                    }
                )

    return summaries, state


# ---------------------------------------------------------------------------
# ② 株価・出来高・チャート情報 / ③ ニュース収集
# ---------------------------------------------------------------------------

def _merge_targets(holdings: list[Holding], watchlist: list[Holding]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for h in holdings:
        merged[h.yf_ticker] = {"holding": h, "watchlist": None}
    for w in watchlist:
        if w.yf_ticker in merged:
            merged[w.yf_ticker]["watchlist"] = w
        else:
            merged[w.yf_ticker] = {"holding": None, "watchlist": w}
    return merged


def collect_ticker_facts(
    holdings: list[Holding], watchlist: list[Holding], chart_dir: Path
) -> tuple[list[dict], list[Path]]:
    merged = _merge_targets(holdings, watchlist)
    facts: list[dict] = []
    chart_paths: list[Path] = []

    for roles in merged.values():
        ref = roles["holding"] or roles["watchlist"]
        try:
            snap = stocks.fetch_snapshot(ref.code, ref.name, ref.yf_ticker)
        except Exception as e:
            line_client.notify_failure(f"{ref.name}({ref.code})の株価データ", str(e))
            continue

        is_mover = snap.volume_alert or abs(snap.change_pct) >= MOVE_ALERT_PCT
        is_overheat_candidate = (
            snap.dev25w_percentile is not None and snap.dev25w_percentile >= OVERHEAT_PERCENTILE
        )

        entry: dict = {
            "code": snap.code,
            "name": snap.name,
            "is_holding": roles["holding"] is not None,
            "is_watchlist": roles["watchlist"] is not None,
            "dividend_hold": bool(roles["holding"] and roles["holding"].dividend_hold),
            "close": round(snap.close, 2),
            "change_pct": round(snap.change_pct, 2),
            "volume_ratio_vs_20d_avg": round(snap.volume_ratio, 2),
            "volume_alert": snap.volume_alert,
            "trend": snap.trend,
        }
        if snap.dev25w_pct is not None:
            entry["dev25w_pct"] = round(snap.dev25w_pct, 2)
        if snap.dev75w_pct is not None:
            entry["dev75w_pct"] = round(snap.dev75w_pct, 2)

        # 値動きが目立った銘柄・過熱懸念候補のみチャート画像を生成(LINE無料枠を圧迫しないため)
        if is_mover or is_overheat_candidate:
            try:
                stocks.render_charts(snap, chart_dir)
                for p in (snap.daily_chart_path, snap.weekly_chart_path):
                    if p:
                        chart_paths.append(p)
            except Exception as e:
                line_client.notify_failure(f"{ref.name}のチャート生成", str(e))

        if snap.dev25w_pct is not None:
            try:
                entry["deviation_judgement"] = claude_client.classify_deviation(
                    snap.name,
                    snap.dev25w_pct,
                    snap.dev75w_pct,
                    snap.dev25w_percentile,
                    snap.ma25w_slope_pct,
                    snap.trend,
                )
            except Exception as e:
                line_client.notify_failure(f"{ref.name}の乖離率判定", str(e))

        # 「簡易チェック」= 数値のみ。深掘りニュース検索は値動きが目立った銘柄のみ
        if is_mover:
            try:
                entry["news"] = news.search_stock_news(snap.name, snap.code)
            except Exception as e:
                line_client.notify_failure(f"{ref.name}のニュース検索", str(e))

        facts.append(entry)

    return facts, chart_paths


# ---------------------------------------------------------------------------
# ④ 新規監視銘柄の提案材料 / ⑤ マクロイベントカレンダー
# ---------------------------------------------------------------------------

def collect_macro_events() -> list[dict]:
    try:
        return news.search_macro_events()
    except Exception as e:
        line_client.notify_failure("マクロイベントカレンダー", str(e))
        return []


def collect_new_candidate_research() -> list[dict]:
    try:
        return news.search_new_candidates()
    except Exception as e:
        line_client.notify_failure("新規監視銘柄候補の検索", str(e))
        return []


# ---------------------------------------------------------------------------
# 画像・状態の永続化
# ---------------------------------------------------------------------------

def publish_charts_and_state(chart_paths: list[Path]) -> list[str]:
    """chart_pathsとstateファイルをコミット・pushし、画像のraw URL一覧を返す。"""
    paths = list(chart_paths) + [STATE_PATH]
    git_publish.commit_and_push(paths, f"chore: update charts/state ({dt.date.today().isoformat()})")
    return [git_publish.raw_url(p) for p in chart_paths]
