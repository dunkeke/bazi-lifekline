import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {
    # 十神权重：你可以在 UI 中做 slider 调整
    "比": 0.6, "劫": 0.2, "印": 0.7, "枭": 0.4,
    "食": 0.5, "伤": 0.2,
    "财": 0.6, "才": 0.4,
    "官": 0.7, "杀": 0.3,
}

# 关键字强弱项：在 bazi.py 的大运/流年描述中常见到“刑冲破害”“合生贵财”等
DEFAULT_RISK = {
    "刑": 0.9,
    "冲": 1.1,
    "破": 0.8,
    "害": 1.0,
    "劫": 0.6,
    "空亡": 1.2,
}

DEFAULT_BOOST = {
    "合": 0.9,
    "生": 0.6,
    "禄": 0.8,
    "喜": 0.6,
    "财": 0.7,
    "官": 0.8,
    "贵": 0.9,
}


def _score_keywords(text: str, boost: dict[str, float], risk: dict[str, float]) -> float:
    score = 0.0
    for k, v in boost.items():
        if k in text:
            score += v
    for k, v in risk.items():
        if k in text:
            score -= v
    return score


def _locate_dayun(age: int, dayun_df: pd.DataFrame) -> pd.Series | None:
    """找到该年龄所在的大运行，方便把“刑冲破害”叠加到流年评分。"""

    if dayun_df.empty:
        return None

    sorted_df = dayun_df.sort_values("start_age")
    current = sorted_df[sorted_df["start_age"] <= age].tail(1)
    if current.empty:
        return None
    return current.iloc[0]


def build_year_signal(
    liunian_df: pd.DataFrame,
    dayun_df: pd.DataFrame,
    base_up: float,
    base_down: float,
    cycle: int,
    boost: dict[str, float] | None = None,
    risk: dict[str, float] | None = None,
    dayun_risk_weight: float = 0.6,
) -> pd.Series:
    """
    结合周期性涨跌、流年/大运描述中的刑冲破害/合生喜贵等关键词，生成逐年信号。
    返回 index=年份 的 pd.Series
    """

    boost = boost or DEFAULT_BOOST
    risk = risk or DEFAULT_RISK

    signals = {}
    liunian_df = liunian_df.sort_values("year").reset_index(drop=True)
    for idx, row in liunian_df.iterrows():
        cyc = base_up if (idx % cycle) < cycle / 2 else -base_down
        desc = str(row.get("desc", ""))
        dayun = _locate_dayun(int(row.get("age", 0)), dayun_df)
        dayun_desc = str(dayun["desc"]) if dayun is not None else ""

        keyword_score = _score_keywords(desc + " " + dayun_desc, boost, risk)

        # 额外强调“大运凶”对该阶段流年的拖累
        if any(k in dayun_desc for k in risk.keys()):
            keyword_score -= dayun_risk_weight

        signals[row["year"]] = cyc + keyword_score

    return pd.Series(signals)

def build_life_index(liunian_df: pd.DataFrame, year_signal: pd.Series, base=100.0):
    """
    year_signal: 每年一个分数（正=上行，负=回撤），index=year
    以年份升序保证“逐年累计”与表格展示一致，并把信号数值回填到输出中便于校验。
    """
    liunian_df = liunian_df.sort_values("year").copy()
    liunian_df["year_signal"] = liunian_df["year"].map(year_signal).fillna(0.0)

    vals = []
    v = base
    for y, sig in zip(liunian_df["year"], liunian_df["year_signal"]):
        v = v * (1.0 + float(sig) / 100.0)
        vals.append(v)

    liunian_df["life_index"] = vals
    return liunian_df

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
