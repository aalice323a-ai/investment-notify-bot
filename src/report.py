"""main_jp.py / main_us.py から共通で使うデータ収集・オーケストレーション処理。"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from config.holdings import Holding
from src import claude_client, git_publish, line_client, macro_calendar, stocks, youtube
from src.log import log

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


def load_channels() -> list[dict]:
    """[{"url": ..., "channel_id": "UC..."}, ...] を返す(data/channels.json)。"""
    if CHANNELS_PATH.exists():
        return json.loads(CHANNELS_PATH.read_text(encoding="utf-8"))
    return []


# ---------------------------------------------------------------------------
# ① YouTube動画の要約(日本株パートのみで呼び出す)
# ---------------------------------------------------------------------------

def collect_video_facts(target_names: list[str]) -> tuple[list[dict], dict[str, list[str]]]:
    log("[YouTube] start")
    channels = load_channels()
    log(f"[YouTube] {len(channels)} channel(s) registered in data/channels.json")
    state = load_processed_videos()
    summaries: list[dict] = []
    pending: list[dict] = []  # 判定待ちの新着動画(全チャンネル分をまとめて後で1回のAPI呼び出しにする)

    for channel in channels:
        channel_id = channel["channel_id"]
        url = channel.get("url", channel_id)

        known_ids = set(state.get(channel_id, []))
        try:
            new_videos = youtube.fetch_new_videos(channel_id, known_ids)
        except Exception as e:
            log(f"[YouTube] ERROR fetching new videos for {channel_id}: {type(e).__name__}: {e}")
            line_client.notify_failure(f"YouTubeチャンネル({url})の新着動画取得", str(e))
            continue
        log(f"[YouTube] {channel_id}: {len(new_videos)} new video(s)")

        for video in new_videos:
            # 採否に関わらず処理済みとして記録し、重複処理を防ぐ
            state.setdefault(channel_id, []).append(video.video_id)

            log(f"[YouTube] fetching transcript for {video.video_id} ({video.title})")
            transcript = youtube.fetch_transcript(video.video_id)
            if not transcript:
                log(f"[YouTube] no transcript available for {video.video_id}, skipping")
                continue

            pending.append(
                {
                    "video_id": video.video_id,
                    "title": video.title,
                    "url": video.url,
                    "transcript": transcript,
                }
            )

    if pending:
        log(f"[YouTube] requesting batched judgement for {len(pending)} video(s)")
        try:
            judgements = claude_client.judge_videos_batch(pending, target_names)
        except Exception as e:
            log(f"[YouTube] ERROR batched video judgement: {type(e).__name__}: {e}")
            line_client.notify_failure("動画要約(一括)", str(e))
            judgements = {}

        for video in pending:
            judgement = judgements.get(video["video_id"], {})
            log(f"[YouTube] {video['video_id']} relevant={judgement.get('relevant')}")
            if judgement.get("relevant"):
                summaries.append(
                    {
                        "title": video["title"],
                        "url": video["url"],
                        "summary": judgement.get("summary", ""),
                    }
                )

    log(f"[YouTube] done: {len(summaries)} relevant summary(ies)")
    return summaries, state


# ---------------------------------------------------------------------------
# ② 株価・出来高・チャート情報
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
    log(f"[Stocks] start: {len(merged)} ticker(s) to process")
    facts: list[dict] = []
    chart_paths: list[Path] = []
    deviation_items: list[dict] = []  # 週足乖離率判定を後でまとめて1回のAPI呼び出しにするため蓄積

    for roles in merged.values():
        ref = roles["holding"] or roles["watchlist"]
        log(f"[Stocks] {ref.name}({ref.yf_ticker}): fetching snapshot")
        try:
            snap = stocks.fetch_snapshot(ref.code, ref.name, ref.yf_ticker)
        except Exception as e:
            log(f"[Stocks] ERROR fetching {ref.yf_ticker}: {type(e).__name__}: {e}")
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

        log(
            f"[Stocks] {ref.name}: close={entry['close']} change_pct={entry['change_pct']} "
            f"volume_ratio={entry['volume_ratio_vs_20d_avg']} volume_alert={entry['volume_alert']} "
            f"trend={entry['trend']} is_mover={is_mover} is_overheat_candidate={is_overheat_candidate}"
        )

        # 値動きが目立った銘柄・過熱懸念候補のみチャート画像を生成(LINE無料枠を圧迫しないため)
        if is_mover or is_overheat_candidate:
            log(f"[Stocks] {ref.name}: rendering charts")
            try:
                stocks.render_charts(snap, chart_dir)
                for p in (snap.daily_chart_path, snap.weekly_chart_path):
                    if p:
                        chart_paths.append(p)
            except Exception as e:
                log(f"[Stocks] ERROR rendering charts for {ref.name}: {type(e).__name__}: {e}")
                line_client.notify_failure(f"{ref.name}のチャート生成", str(e))

        if snap.dev25w_pct is not None:
            deviation_items.append(
                {
                    "code": snap.code,
                    "name": snap.name,
                    "dev25w_pct": entry.get("dev25w_pct"),
                    "dev75w_pct": entry.get("dev75w_pct"),
                    "dev25w_percentile": snap.dev25w_percentile,
                    "ma25w_slope_pct": snap.ma25w_slope_pct,
                    "trend": snap.trend,
                }
            )

        facts.append(entry)

    if deviation_items:
        log(f"[Stocks] requesting batched deviation judgement for {len(deviation_items)} ticker(s)")
        try:
            judgements = claude_client.classify_deviations_batch(deviation_items)
            for entry in facts:
                if entry["code"] in judgements:
                    entry["deviation_judgement"] = judgements[entry["code"]]
            log(f"[Stocks] batched deviation judgement done: {len(judgements)} result(s)")
        except Exception as e:
            log(f"[Stocks] ERROR batched deviation judgement: {type(e).__name__}: {e}")
            line_client.notify_failure("週足乖離率判定(一括)", str(e))

    log(f"[Stocks] done: {len(facts)} ticker(s) processed, {len(chart_paths)} chart image(s)")
    return facts, chart_paths


# ---------------------------------------------------------------------------
# ⑤ マクロイベントカレンダー(公式発表済みの確定日程を直接参照。検索APIは使わない)
# ---------------------------------------------------------------------------

def collect_macro_events(today: dt.date) -> list[dict]:
    events = macro_calendar.upcoming_events(today)
    log(f"[Macro] {len(events)} event(s) in the next 7 days")
    return events


# ---------------------------------------------------------------------------
# 画像・状態の永続化
# ---------------------------------------------------------------------------

def publish_charts_and_state(chart_paths: list[Path]) -> list[str]:
    """chart_pathsとstateファイルをコミット・pushし、画像のraw URL一覧を返す。"""
    log(f"[GitPublish] committing {len(chart_paths)} chart(s) + state file")
    paths = list(chart_paths) + [STATE_PATH]
    git_publish.commit_and_push(paths, f"chore: update charts/state ({dt.date.today().isoformat()})")
    urls = [git_publish.raw_url(p) for p in chart_paths]
    log(f"[GitPublish] done: {len(urls)} image URL(s)")
    return urls
