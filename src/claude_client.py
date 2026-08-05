"""Anthropic Claude APIラッパー: 動画判定・乖離率の定性判定・レポート合成。

ANTHROPIC_API_KEY は環境変数からのみ取得する(Anthropic SDKが自動で読む)。
"""
from __future__ import annotations

import json
import os

from anthropic import Anthropic

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")


def _client() -> Anthropic:
    return Anthropic()


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

出力は必ず以下のJSON形式のみで返すこと(前置きや```json```での囲みは不要):
{"relevant": true または false, "reason": "採用/除外の理由(1文)", "summary": "採用時のみ:保有銘柄・監視銘柄への影響を中心とした要約(150字程度)"}
"""


def judge_video(title: str, transcript: str, target_names: list[str]) -> dict:
    prompt = (
        f"動画タイトル: {title}\n"
        f"保有・監視対象銘柄: {', '.join(target_names)}\n\n"
        f"字幕(先頭12000字):\n{transcript[:12000]}"
    )
    resp = _client().messages.create(
        model=_MODEL,
        max_tokens=600,
        system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(resp.content[0].text)


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
# ② 週足乖離率の定性判定
# ---------------------------------------------------------------------------

_DEVIATION_SYSTEM = """あなたは株式テクニカルアナリストです。週足の25週線・75週線からの乖離率データを見て、
「上昇トレンド中の健全な乖離」「過熱懸念」「下落トレンド中の戻り待ち」「弱含み」等、
直近のトレンド方向も踏まえて簡潔に(30字程度)判定してください。
出力は判定結果の文字列のみとし、前置きや説明は不要です。"""


def classify_deviation(
    name: str,
    dev25w_pct: float | None,
    dev75w_pct: float | None,
    dev25w_percentile: float | None,
    ma25w_slope_pct: float | None,
    trend: str,
) -> str:
    prompt = (
        f"銘柄: {name}\n"
        f"直近トレンド(日足ベース): {trend}\n"
        f"25週線乖離率: {dev25w_pct}\n"
        f"75週線乖離率: {dev75w_pct}\n"
        f"25週線乖離率の過去2年分布内での位置(パーセンタイル、大きいほど乖離が高水準): {dev25w_percentile}\n"
        f"25週線の直近8週間の傾き: {ma25w_slope_pct}"
    )
    resp = _client().messages.create(
        model=_MODEL,
        max_tokens=100,
        system=_DEVIATION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


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
    text = _generate_report(payload)
    if _needs_bear_case_retry(text):
        reminder = (
            "\n\n【重要な再確認】前回の出力には、買い候補または保有継続とした銘柄に対する"
            "弱気シナリオ・懸念点が不足していました。該当する全ての銘柄について、必ず懸念点を"
            "最低1つ明記した上で、レポート全文を再生成してください。"
        )
        text = _generate_report(payload + reminder)
    return text


def _generate_report(user_content: str) -> str:
    resp = _client().messages.create(
        model=_MODEL,
        max_tokens=3000,
        system=_REPORT_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    return resp.content[0].text.strip()


def _needs_bear_case_retry(text: str) -> bool:
    has_recommendation = any(kw in text for kw in _RECOMMEND_KEYWORDS)
    if not has_recommendation:
        return False
    return not any(kw in text for kw in _BEAR_KEYWORDS)
