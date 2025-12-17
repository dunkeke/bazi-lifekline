import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {
    # 十神权重：你可以在 UI 中做 slider 调整
    "比": 0.6, "劫": 0.2, "印": 0.7, "枭": 0.4,
    "食": 0.5, "伤": 0.2,
    "财": 0.6, "才": 0.4,
    "官": 0.7, "杀": 0.3,
}

def build_life_index(liunian_df: pd.DataFrame, year_signal: pd.Series, base=100.0):
    """
    year_signal: 每年一个分数（正=上行，负=回撤），index=year
    """
    years = liunian_df["year"].values
    vals = []
    v = base
    for y in years:
        v = v * (1.0 + float(year_signal.get(y, 0.0))/100.0)
        vals.append(v)
    out = liunian_df.copy()
    out["life_index"] = vals
    return out

def to_decade_ohlc(life_df: pd.DataFrame):
    """
    把逐年 life_index 聚合成每个大运段/十年K线也可以，这里先按10年窗口聚合
    """
    life_df = life_df.sort_values("year").copy()
    life_df["bucket"] = (life_df["year"] // 10) * 10
    g = life_df.groupby("bucket")["life_index"]
    ohlc = pd.DataFrame({
        "bucket": g.apply(lambda s: int(s.index.min()) if False else 0)  # 占位，不用也行
    })
    ohlc = g.agg(open="first", high="max", low="min", close="last").reset_index()
    ohlc.rename(columns={"bucket":"decade"}, inplace=True)
    return ohlc
