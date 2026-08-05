"""新規検討候補として監視している銘柄マスタ定義。

Claudeが「新規監視銘柄の提案」を行った場合も、自動追加はせず、
このファイルへの追記はユーザー判断で行ってください。
"""
from config.holdings import Holding

JP_WATCHLIST: list[Holding] = [
    Holding("8035", "東京エレクトロン", "JP"),
    Holding("7735", "SCREENホールディングス", "JP"),
    Holding("6762", "TDK", "JP"),
    Holding("5803", "フジクラ", "JP"),
    Holding("5801", "古河電気工業", "JP"),
    Holding("5802", "住友電気工業", "JP"),
    Holding("4062", "イビデン", "JP"),
    Holding("2802", "味の素", "JP"),
    Holding("6855", "日本電子材料", "JP"),
    Holding("3110", "日東紡績", "JP"),
    Holding("4078", "堺化学工業", "JP"),
    Holding("4980", "デクセリアルズ", "JP"),
    Holding("285A", "キオクシアHD", "JP"),
    Holding("6315", "TOWA", "JP"),
    Holding("6701", "日本電気(NEC)", "JP"),
    Holding("7011", "三菱重工業", "JP"),
    Holding("7013", "IHI", "JP"),
    Holding("9503", "関西電力", "JP"),
    Holding("9508", "九州電力", "JP"),
    Holding("4043", "トクヤマ", "JP"),
]

US_WATCHLIST: list[Holding] = [
    Holding("NVDA", "NVIDIA", "US"),
    Holding("AVGO", "ブロードコム", "US"),
    Holding("MU", "マイクロン", "US"),
    Holding("TSM", "台湾セミコンダクター(TSMC)", "US"),
    Holding("AMD", "AMD", "US"),
    Holding("MSFT", "マイクロソフト", "US"),
    Holding("GOOG", "アルファベット(Google)", "US"),
    Holding("AMZN", "アマゾン", "US"),
    Holding("TSLA", "テスラ", "US"),
]


def all_watchlist() -> list[Holding]:
    return JP_WATCHLIST + US_WATCHLIST
