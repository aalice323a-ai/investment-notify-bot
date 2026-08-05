"""LINE Messaging API送信ラッパー。

LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID は環境変数からのみ取得し、
コードに直接書き込まない。
"""
from __future__ import annotations

import os

import requests

_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_TEXT_CHUNK_LIMIT = 4500
_MAX_MESSAGES_PER_CALL = 5


def _headers() -> dict:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _user_id() -> str:
    return os.environ["LINE_USER_ID"]


def _chunk_text(text: str, limit: int = _TEXT_CHUNK_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _send(messages: list[dict]) -> None:
    for i in range(0, len(messages), _MAX_MESSAGES_PER_CALL):
        batch = messages[i : i + _MAX_MESSAGES_PER_CALL]
        resp = requests.post(
            _PUSH_URL,
            headers=_headers(),
            json={"to": _user_id(), "messages": batch},
            timeout=30,
        )
        resp.raise_for_status()


def push_report(text: str, image_urls: list[str] | None = None) -> None:
    """レポート本文(必要なら分割)とチャート画像をまとめて送信する。"""
    messages: list[dict] = []
    if text.strip():
        messages.extend({"type": "text", "text": chunk} for chunk in _chunk_text(text))
    for url in image_urls or []:
        messages.append({"type": "image", "originalContentUrl": url, "previewImageUrl": url})
    if messages:
        _send(messages)


def notify_failure(component: str, error: str) -> None:
    """他モジュールの障害に影響されないよう、最小限の依存で即時通知する。"""
    try:
        message = f"⚠️ {component}の取得に失敗: {error}"[:1000]
        requests.post(
            _PUSH_URL,
            headers=_headers(),
            json={"to": _user_id(), "messages": [{"type": "text", "text": message}]},
            timeout=30,
        )
    except Exception:
        pass
