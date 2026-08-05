"""YouTubeチャンネルの新着動画取得・字幕取得(APIキー不要)。

チャンネルIDの解決はページHTMLのスクレイピング、新着動画一覧は
YouTube公式RSSフィード、字幕取得は youtube-transcript-api を用いる。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests
from youtube_transcript_api import YouTubeTranscriptApi

_CHANNEL_ID_RE = re.compile(r'"channelId":"(UC[0-9A-Za-z_-]{22})"')
_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_YT_NS = "{http://www.youtube.com/xml/schemas/2015}"


@dataclass
class Video:
    video_id: str
    title: str
    published: str
    url: str


def resolve_channel_id(channel_url: str) -> str:
    """@handle や /channel/UC... 等、任意形式のチャンネルURLからchannelIdを解決する。"""
    m = re.search(r"/channel/(UC[0-9A-Za-z_-]{22})", channel_url)
    if m:
        return m.group(1)
    resp = requests.get(channel_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    m = _CHANNEL_ID_RE.search(resp.text)
    if not m:
        raise ValueError(f"channelIdを解決できませんでした: {channel_url}")
    return m.group(1)


def fetch_new_videos(channel_id: str, known_ids: set[str]) -> list[Video]:
    """RSSフィードから、known_idsに無い新着動画のみを返す(前回チェック以降のみ対象)。"""
    resp = requests.get(_RSS_URL.format(channel_id=channel_id), timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    videos: list[Video] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        video_id = entry.findtext(f"{_YT_NS}videoId")
        if not video_id or video_id in known_ids:
            continue
        title = entry.findtext(f"{_ATOM_NS}title") or ""
        published = entry.findtext(f"{_ATOM_NS}published") or ""
        videos.append(
            Video(
                video_id=video_id,
                title=title,
                published=published,
                url=f"https://www.youtube.com/watch?v={video_id}",
            )
        )
    return videos


def fetch_transcript(video_id: str) -> str | None:
    """日本語字幕を優先し、無ければ英語字幕を取得する。両方無ければNoneを返す。"""
    api = YouTubeTranscriptApi()
    for lang in (["ja"], ["en"]):
        try:
            fetched = api.fetch(video_id, languages=lang)
            return " ".join(snippet.text for snippet in fetched)
        except Exception:
            continue
    return None
