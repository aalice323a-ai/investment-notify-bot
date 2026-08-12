"""Google Gemini API ラッパー: 動画判定・乖離率の定性判定・レポート合成。

GEMINI_API_KEY は環境変数からのみ取得する。無料枠(Gemini Flash系モデル)で
収まる想定の呼び出し頻度(動画要約1本ごと・乖離判定は銘柄ごと・レポート生成は
セッションごとに1〜2回)としている。

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
_MAX_RETRIES = 4
_DEFAULT_BACKOFF_SECONDS = 20.0
_RETRY_DELAY_RE = re.compile(r"retryDelay[\"':\s]+(\d+(?:\.\d+)?)s")


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        log("[Gemini] creating client (once per process)")
        _client_instance = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client_instance


def _extract_retry_delay(error_text: str) -> float:
    m = _RETRY_DELAY_RE.search(error_text)
    return float(m.group(1)) if m else _DEFAULT_BACKOFF_SECONDS


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
            text = str(e)
            is_rate_limited = "429" in text or "RESOURCE_EXHAUSTED" in text
            if not is_rate_limited or attempt == _MAX_RETRIES:
                raise
            wait = _extract_retry_delay(text)
            log(f"[Gemini] 429 rate limited (attempt {attempt}/{_MAX_RETRIES}), waiting {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# ① YouTube動画の採用判定・要約
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """あなたは株式投資家向けのアナリストです。YouTube動画の字幕を読み、
保有銘柄・監視銘柄に関連する投資判断材料として動画を採用すべきか判定してください。

【採用基準(優先順位順)】
1. AI・半導体産業の構造変化に関する内容
2. サプライチェーンに関する内容
3. 業績への影響に関する内容
4. バリュエーション(株価水準の割高・割安)に関する内容
5. チャート(テクニカル)分析

重要な制約: チャート(テクニカル)分析の話題「だけ」の動画は採用しないこと。
チャートの話題を含む場合でも、業績との整合性(ファンダメンタルズとの整合)が
語られていなければ採用基準を満たさないと判断すること。

出力は必ず以下のJSON形式のみで返すこと:
{"relevant": true または false, "reason": "採用/除外の理由(1文)", "summary": "採用時のみ:保有銘柄・監視銘柄への影響を中心とした要約(150字程度)"}
"""


def judge_video(title: str, transcript: str, target_names: list[str]) -> dict:
    prompt = (
        f"動画タイトル: {title}\n"
        f"保有・監視対象銘柄: {', '.join(target_names)}\n\n"
        f"字幕(先頭12000字):\n{transcript[:12000]}"
    )
    text = _generate(_JUDGE_SYSTEM, prompt, max_output_tokens=600, json_output=True)
    return _parse_json(text)


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
・関連ニュースまとめ
・弱気シナリオ・懸念点
・新規監視銘柄の提案(あれば)
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
    return text


def _needs_bear_case_retry(text: str) -> bool:
    has_recommendation = any(kw in text for kw in _RECOMMEND_KEYWORDS)
    if not has_recommendation:
        return False
    return not any(kw in text for kw in _BEAR_KEYWORDS)
