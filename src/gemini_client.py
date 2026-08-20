"""Google Gemini API ラッパー: 動画判定・乖離率の定性判定・レポート合成。

GEMINI_API_KEY は環境変数からのみ取得する。無料枠(Gemini Flash系モデル)の
呼び出し回数を抑えるため、動画要約・週足乖離率判定はいずれも対象を1回の
API呼び出しにまとめて送る(件数分だけ呼び出さない)。1セッションあたりの
呼び出し回数は概ね、動画判定1回+乖離率判定1回+レポート生成1〜2回。

モデル名はAPIの世代交代が早いため環境変数 GEMINI_MODEL で上書き可能にしてある。
既定値がエラーになる場合は https://ai.google.dev/gemini-api/docs/models で
現行の無料枠モデル名を確認し、GitHub Secrets or Actions変数で上書きすること。
"""
from __future__ import annotations

import json
import os
import re
import time

from google import genai
from google.genai import types

from src.log import log

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

# 銘柄・動画ごとにクライアントを作り直すと(SDK内部の非同期後始末のタイミング次第で)
# "client has been closed" 系のエラーになることがあるため、プロセス内で1つだけ生成して使い回す。
_client_instance: genai.Client | None = None

# 無料枠は1分あたりのリクエスト数が非常に少ない(モデルによっては5RPM程度)ため、
# 429(RESOURCE_EXHAUSTED)時はサーバー指定の待機時間(retryDelay)に従ってリトライする。
# 503(UNAVAILABLE/モデル過負荷)は待機時間がレスポンスに含まれないことが多いため、
# 固定60秒待ってリトライする。いずれも初回+最大3回リトライ(計4試行)。
_MAX_RETRIES = 4
_DEFAULT_BACKOFF_SECONDS = 20.0
_OVERLOAD_BACKOFF_SECONDS = 60.0
_RETRY_DELAY_RE = re.compile(r"retryDelay[\"':\s]+(\d+(?:\.\d+)?)s")
# エラーメッセージがGoogle側の判断で日本語化されて返ってくることがあるため、
# 英語・日本語どちらのキーワードも見る(実例: "このモデルは現在高い需要を抱えています")。
_RATE_LIMIT_MARKERS = ("429", "RESOURCE_EXHAUSTED")
_OVERLOAD_MARKERS = (
    "503", "UNAVAILABLE", "overloaded", "high demand",
    "高い需要", "過負荷", "混雑",
)


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        log("[Gemini] creating client (once per process)")
        _client_instance = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client_instance


def _error_status_code(e: Exception) -> int | None:
    """例外オブジェクトからHTTPステータスコードを取り出す(メッセージの言語に依存しない判定用)。"""
    for attr in ("code", "status_code"):
        val = getattr(e, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(e, "response", None)
    val = getattr(resp, "status_code", None)
    return val if isinstance(val, int) else None


def _retry_wait_seconds(e: Exception) -> float | None:
    """リトライすべきエラーなら待機秒数を、リトライ対象外ならNoneを返す。

    日次クォータ(PerDay)超過は数十秒待っても解消しないため、
    無駄なリトライはせず早期に失敗させる。
    """
    text = str(e)
    if "PerDay" in text or "per day" in text.lower():
        return None
    m = _RETRY_DELAY_RE.search(text)
    if m:
        return float(m.group(1))
    status = _error_status_code(e)
    if status == 503 or any(marker in text for marker in _OVERLOAD_MARKERS):
        return _OVERLOAD_BACKOFF_SECONDS
    if status == 429 or any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return _DEFAULT_BACKOFF_SECONDS
    return None


def _generate(system: str, prompt: str, max_output_tokens: int, json_output: bool = False) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_output_tokens,
        temperature=0.3,
        response_mime_type="application/json" if json_output else "text/plain",
    )
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = _client().models.generate_content(model=_MODEL, contents=prompt, config=config)
            return (resp.text or "").strip()
        except Exception as e:
            wait = _retry_wait_seconds(e)
            if wait is None:
                log(f"[Gemini] non-retryable error ({type(e).__name__}): {str(e)[:300]}")
                raise
            if attempt == _MAX_RETRIES:
                log(f"[Gemini] giving up after {_MAX_RETRIES} attempts: {str(e)[:300]}")
                raise
            log(f"[Gemini] retryable error (attempt {attempt}/{_MAX_RETRIES}), waiting {wait:.0f}s: {str(e)[:200]}")
            time.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# ① YouTube動画の採用判定・要約(新着動画をまとめて1回のAPI呼び出しで判定する)
# ---------------------------------------------------------------------------

_JUDGE_BATCH_SYSTEM = """あなたは株式投資家向けのアナリストです。複数のYouTube動画の字幕(抜粋)を読み、
それぞれについて、保有銘柄・監視銘柄に関連する投資判断材料として採用すべきか動画ごとに判定してください。

【採用基準(優先順位順)】
1. AI・半導体産業の構造変化に関する内容
2. サプライチェーンに関する内容
3. 業績への影響に関する内容
4. バリュエーション(株価水準の割高・割安)に関する内容
5. チャート(テクニカル)分析

重要な制約: チャート(テクニカル)分析の話題「だけ」の動画は採用しないこと。
チャートの話題を含む場合でも、業績との整合性(ファンダメンタルズとの整合)が
語られていなければ採用基準を満たさないと判断すること。

出力は必ず次のJSON形式のみで返すこと(動画IDをキーとする):
{"<動画ID>": {"relevant": true または false, "reason": "採用/除外の理由(1文)", "summary": "採用時のみ:保有銘柄・監視銘柄への影響を中心とした要約(150字程度)"}, ...}
入力に含まれる全ての動画IDを必ずキーとして含めること。"""


def judge_videos_batch(videos: list[dict], target_names: list[str]) -> dict[str, dict]:
    """複数動画の採用判定・要約を1回のAPI呼び出しでまとめて取得する。

    videos: [{"video_id", "title", "transcript"}, ...]
    戻り値: {video_id: {"relevant", "reason", "summary"}, ...}(失敗時は空dict)
    """
    if not videos:
        return {}
    items = [
        {
            "video_id": v["video_id"],
            "title": v["title"],
            # 動画本数分プロンプトが膨らむため、単体判定時(12000字)より短く切り詰める
            "transcript_excerpt": v["transcript"][:6000],
        }
        for v in videos
    ]
    prompt = (
        f"保有・監視対象銘柄: {', '.join(target_names)}\n\n"
        f"動画一覧(JSON):\n{json.dumps(items, ensure_ascii=False, indent=2)}"
    )
    max_tokens = min(400 * len(videos) + 200, 6000)
    text = _generate(_JUDGE_BATCH_SYSTEM, prompt, max_output_tokens=max_tokens, json_output=True)
    try:
        return _parse_json(text)
    except json.JSONDecodeError:
        log(f"[Gemini] failed to parse batched video judgement response: {text[:200]}")
        return {}


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise


# ---------------------------------------------------------------------------
# ② 週足乖離率の定性判定(全銘柄まとめて1回のAPI呼び出しで取得し、レート制限を回避する)
# ---------------------------------------------------------------------------

_DEVIATION_BATCH_SYSTEM = """あなたは株式テクニカルアナリストです。複数銘柄それぞれについて、
週足の25週線・75週線からの乖離率データを見て、
「上昇トレンド中の健全な乖離」「過熱懸念」「下落トレンド中の戻り待ち」「弱含み」等、
直近のトレンド方向も踏まえて銘柄ごとに簡潔に(30字程度)判定してください。

出力は必ず次のJSON形式のみで返すこと(入力された銘柄コードをキーとする):
{"<銘柄コード>": "<判定文>", "<銘柄コード>": "<判定文>", ...}
入力に含まれる全ての銘柄コードを必ずキーとして含めること。"""


def classify_deviations_batch(items: list[dict]) -> dict[str, str]:
    """複数銘柄の週足乖離率判定を1回のAPI呼び出しでまとめて取得する。

    items: [{"code", "name", "dev25w_pct", "dev75w_pct", "dev25w_percentile",
             "ma25w_slope_pct", "trend"}, ...]
    戻り値: {code: 判定文, ...}(失敗時は空dict)
    """
    if not items:
        return {}
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    text = _generate(
        _DEVIATION_BATCH_SYSTEM, payload, max_output_tokens=2000, json_output=True
    )
    try:
        return _parse_json(text)
    except json.JSONDecodeError:
        log(f"[Gemini] failed to parse batched deviation response: {text[:200]}")
        return {}


# ---------------------------------------------------------------------------
# ③〜⑥ レポート本文の合成
# ---------------------------------------------------------------------------

_REPORT_SYSTEM = """あなたは、個人投資家向けに毎回LINEで届く株式レポートを作成するアナリストです。
ユーザーからJSON形式で渡される事実(facts)のみに基づき、以下のルールでレポート本文(日本語)を作成してください。

【出力フォーマット】(該当する内容がない項目は見出しごと省略し、無理に埋めないこと)
・YouTube要約(保有銘柄への影響・新規検討銘柄)
・出来高/移動平均アラート(該当銘柄のみ)
・弱気シナリオ・懸念点
・今週のマクロイベント(あれば)
・今日チェックすべきアクション

【厳守事項】
- 買い候補として挙げる銘柄、または「保有継続が妥当」と述べる銘柄には、必ずその銘柄について
  弱点・懸念点・悲観シナリオを最低1つ添えること。楽観一辺倒の結論は禁止する。
- facts内で dividend_hold=true の銘柄は、買い増し・売却の判定・提案の対象外とする。
  これらの銘柄は配当や業績の「異常値」が検知された場合のみ触れ、通常の買い/売り判断は述べないこと。
- チャートのみを根拠にした判断は避け、業績との整合性を重視すること。
- LINEで送信するため、全体でおおよそ4000〜4500文字以内に収め、簡潔にまとめること。冗長な前置きは不要。
- 見出しは「・」で始める形式を保ち、絵文字は最小限にすること。
- factsに含まれる情報のみを事実として扱い、根拠のない推測を新たな事実として書かないこと。
- 出力は本文のみとし、前置きや後書き(「以下がレポートです」等)は書かないこと。
"""

_RECOMMEND_KEYWORDS = ("買い増し", "保有継続", "買い候補", "新規購入", "打診")
_BEAR_KEYWORDS = ("懸念", "リスク", "弱気", "下振れ", "警戒")


def compose_report(facts: dict) -> str:
    payload = json.dumps(facts, ensure_ascii=False, indent=2)
    text = _generate(_REPORT_SYSTEM, payload, max_output_tokens=3000)
    if _needs_bear_case_retry(text):
        reminder = (
            "\n\n【重要な再確認】前回の出力には、買い候補または保有継続とした銘柄に対する"
            "弱気シナリオ・懸念点が不足していました。該当する全ての銘柄について、必ず懸念点を"
            "最低1つ明記した上で、レポート全文を再生成してください。"
        )
        text = _generate(_REPORT_SYSTEM, payload + reminder, max_output_tokens=3000)
    if not text.strip():
        # 空文字のままLINEに送るとメッセージオブジェクトが不正になり400になるため、
        # ここで明示的に失敗扱いにする(呼び出し側の固定フォールバック文言に委ねる)。
        raise RuntimeError("Geminiが空のレポート本文を返しました")
    return text


def _needs_bear_case_retry(text: str) -> bool:
    has_recommendation = any(kw in text for kw in _RECOMMEND_KEYWORDS)
    if not has_recommendation:
        return False
    return not any(kw in text for kw in _BEAR_KEYWORDS)
