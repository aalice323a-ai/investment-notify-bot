"""保有銘柄・監視対象の銘柄マスタ定義。

銘柄の追加・削除・dividend_hold(長期配当目的保有=買い増し/売却判定対象外)の
変更は、このファイルを直接編集してください。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    market: str  # "JP" or "US"
    dividend_hold: bool = False

    @property
    def yf_ticker(self) -> str:
        """yfinance用のティッカーシンボル"""
        return f"{self.code}.T" if self.market == "JP" else self.code


JP_HOLDINGS: list[Holding] = [
    Holding("2802", "味の素", "JP"),
    Holding("285A", "キオクシアHD", "JP"),
    Holding("3110", "日東紡績", "JP"),
    Holding("4980", "デクセリアルズ", "JP"),
    Holding("5020", "ENEOS", "JP"),
    Holding("5243", "NOTE", "JP"),
    Holding("5401", "日本製鉄", "JP"),
    Holding("5802", "住友電工", "JP"),
    Holding("5803", "フジクラ", "JP"),
    Holding("5985", "サンコール", "JP"),
    Holding("6479", "ミネベアミツミ", "JP"),
    Holding("6701", "日本電気(NEC)", "JP"),
    Holding("6758", "ソニーグループ", "JP"),
    Holding("6762", "TDK", "JP"),
    Holding("7011", "三菱重工業", "JP"),
    Holding("7013", "IHI", "JP"),
    Holding("8001", "伊藤忠商事", "JP", dividend_hold=True),
    Holding("8058", "三菱商事", "JP", dividend_hold=True),
    Holding("8306", "三菱UFJフィナンシャル・グループ", "JP", dividend_hold=True),
    Holding("8316", "三井住友フィナンシャルグループ", "JP", dividend_hold=True),
    Holding("8591", "オリックス", "JP", dividend_hold=True),
    Holding("9432", "NTT", "JP", dividend_hold=True),
]

US_HOLDINGS: list[Holding] = [
    Holding("AMD", "AMD", "US"),
    Holding("AVGO", "ブロードコム", "US"),
    Holding("GOOG", "アルファベット", "US"),
    Holding("TSM", "台湾セミコンダクター(TSMC)", "US"),
]


def all_holdings() -> list[Holding]:
    return JP_HOLDINGS + US_HOLDINGS
