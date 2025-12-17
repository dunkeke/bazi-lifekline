from typing import Dict, List, Optional

import pandas as pd

# 十神原始喜忌表（身强/身弱），与五行喜忌解耦，便于插值后再乘生克修正
STRONG_TEN_GOD_WEIGHTS: Dict[str, float] = {
    "官": -0.40,
    "杀": -0.40,
    "印": -0.30,
    "枭": -0.30,
    "比": 0.35,
    "劫": 0.35,
    "食": 0.30,
    "伤": 0.30,
    "财": 0.25,
    "才": 0.25,
}

WEAK_TEN_GOD_WEIGHTS: Dict[str, float] = {
    "官": -0.35,
    "杀": -0.35,
    "印": 0.40,
    "枭": 0.40,
    "比": 0.35,
    "劫": 0.35,
    "食": -0.30,
    "伤": -0.30,
    "财": -0.25,
    "才": -0.25,
}

# 五行生克乘数表：对插值后的十神喜忌做细调
WUXING_MULTIPLIER: Dict[str, float] = {
    "生我": 0.20,
    "同我": 0.10,
    "我克": 0.05,
    "克我": -0.15,
    "我生": -0.10,
}

# 刑冲合害基础分表（关系强度，不含十神）
RELATION_BASE_SCORE: Dict[str, float] = {
    "三合": 6,
    "六合": 4,
    "半合": 2,
    "冲": -5,
    "刑": -3,
    "害": -2,
    "破": -1,
}

# 典型格局直接覆盖十神喜忌（不再插值）
SPECIAL_PATTERN_WEIGHTS: Dict[str, Dict[str, float]] = {
    "从旺": {
        "比": 0.45, "劫": 0.45, "食": 0.35, "伤": 0.35, "印": -0.35, "枭": -0.35, "财": 0.20, "才": 0.20, "官": -0.45, "杀": -0.45,
    },
    "专旺": {
        "比": 0.50, "劫": 0.50, "印": -0.40, "枭": -0.40, "食": 0.30, "伤": 0.30, "财": 0.10, "才": 0.10, "官": -0.50, "杀": -0.50,
    },
    "化气": {
        "食": 0.40, "伤": 0.40, "财": 0.35, "才": 0.35, "官": -0.40, "杀": -0.40, "印": -0.20, "枭": -0.20, "比": -0.10, "劫": -0.10,
    },
    "两气成象": {
        "比": 0.30, "劫": 0.30, "印": 0.25, "枭": 0.25, "食": 0.25, "伤": 0.25, "财": -0.25, "才": -0.25, "官": -0.30, "杀": -0.30,
    },
}

# 关键字强弱项：在 bazi.py 的大运/流年描述中常见到“刑冲破害”“合生贵财”等
DEFAULT_RISK: Dict[str, float] = {
    "刑": 0.9,
    "冲": 1.1,
    "破": 0.8,
    "害": 1.0,
    "劫": 0.6,
    "空亡": 1.2,
}

DEFAULT_BOOST: Dict[str, float] = {
    "合": 0.9,
    "生": 0.6,
    "禄": 0.8,
    "喜": 0.6,
    "财": 0.7,
    "官": 0.8,
    "贵": 0.9,
}


def _score_keywords(text: str, boost: Dict[str, float], risk: Dict[str, float]) -> float:
    score = 0.0
    for k, v in boost.items():
        if k in text:
            score += v
    for k, v in risk.items():
        if k in text:
            score -= v
    return score


def compute_strength_index(features: Dict[str, float]) -> float:
    """
    输入得令/得地/得势/通根等要素的归一化计数，按经验权重混合后压缩到 [0,1]。

    参数示例：{"得令": 0.8, "得地": 0.6, "得势": 0.7, "通根": 0.5}
    """

    weights = {"得令": 0.4, "得地": 0.2, "得势": 0.2, "通根": 0.2}
    score = 0.0
    for key, w in weights.items():
        score += float(features.get(key, 0.0)) * w
    return max(0.0, min(1.0, score))


def blend_ten_god_weights(
    strength_index: float, special_pattern: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    按日主强度 I∈[0,1] 对身强/身弱表做线性插值，特殊格局可直接覆盖。
    """

    if special_pattern:
        return special_pattern

    i = max(0.0, min(1.0, strength_index))
    blended = {}
    for key in STRONG_TEN_GOD_WEIGHTS.keys():
        strong_v = STRONG_TEN_GOD_WEIGHTS.get(key, 0.0)
        weak_v = WEAK_TEN_GOD_WEIGHTS.get(key, 0.0)
        blended[key] = i * strong_v + (1 - i) * weak_v
    return blended


def score_ten_god(
    shishen: str,
    wuxing_relation: Optional[str],
    strength_index: float,
    special_pattern: Optional[Dict[str, float]] = None,
) -> float:
    """
    十神喜忌 = 插值后的“专属喜忌表” × (1 + 五行生克乘数)。
    wuxing_relation 可选值：生我/同我/我克/克我/我生，缺省按 0 处理。
    """

    weights = blend_ten_god_weights(strength_index, special_pattern)
    base = weights.get(shishen, 0.0)
    multi = WUXING_MULTIPLIER.get(wuxing_relation or "", 0.0)
    return base * (1.0 + multi)


def score_relation(relations: List[str], trigger_coeff: float = 1.0) -> float:
    """
    刑冲合害的基础分 × 触发系数；relations 传入命盘/流年的触发列表。
    """

    total = 0.0
    for rel in relations:
        total += RELATION_BASE_SCORE.get(rel, 0.0) * trigger_coeff
    return total


def _locate_dayun(age: int, dayun_df: pd.DataFrame) -> Optional[pd.Series]:
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
    boost: Optional[Dict[str, float]] = None,
    risk: Optional[Dict[str, float]] = None,
    dayun_risk_weight: float = 0.6,
    strength_index: float = 0.5,
    special_pattern: Optional[Dict[str, float]] = None,
    relation_trigger: float = 1.0,
    ten_god_weight: float = 10.0,
) -> pd.Series:
    """
    结合周期性涨跌、十神喜忌插值、五行乘数与刑冲合害（或关键词）生成逐年信号。
    返回 index=年份 的 pd.Series；缺少字段时自动回落到关键词打分。
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

        shishen = str(row.get("shishen", "")).strip()
        wuxing_relation = str(row.get("wuxing_relation", "")).strip() or None
        ten_score = 0.0
        if shishen:
            ten_score = score_ten_god(
                shishen=shishen,
                wuxing_relation=wuxing_relation,
                strength_index=strength_index,
                special_pattern=special_pattern,
            ) * ten_god_weight

        relations_raw = row.get("relations", [])
        if isinstance(relations_raw, str):
            # 兼容“刑/冲/合”字符串或以空格分隔
            parts = [p for token in relations_raw.split("/") for p in token.split(" ") if p]
            relations = parts
        else:
            relations = list(relations_raw) if relations_raw is not None else []
        if dayun is not None and "relations" in dayun and isinstance(dayun["relations"], (list, tuple)):
            relations = relations + list(dayun["relations"])
        relation_score = score_relation(relations, trigger_coeff=relation_trigger) if relations else 0.0

        # 额外强调“大运凶”对该阶段流年的拖累
        if any(k in dayun_desc for k in risk.keys()):
            keyword_score -= dayun_risk_weight

        signals[row["year"]] = cyc + keyword_score + ten_score + relation_score

    return pd.Series(signals)

WEAK_TEN_GOD_WEIGHTS = {
    "官": -0.35,
    "杀": -0.35,
    "印": 0.40,
    "枭": 0.40,
    "比": 0.35,
    "劫": 0.35,
    "食": -0.30,
    "伤": -0.30,
    "财": -0.25,
    "才": -0.25,
}

# 五行生克乘数表：对插值后的十神喜忌做细调
WUXING_MULTIPLIER = {
    "生我": 0.20,
    "同我": 0.10,
    "我克": 0.05,
    "克我": -0.15,
    "我生": -0.10,
}

# 刑冲合害基础分表（关系强度，不含十神）
RELATION_BASE_SCORE = {
    "三合": 6,
    "六合": 4,
    "半合": 2,
    "冲": -5,
    "刑": -3,
    "害": -2,
    "破": -1,
}

# 典型格局直接覆盖十神喜忌（不再插值）
SPECIAL_PATTERN_WEIGHTS = {
    "从旺": {
        "比": 0.45, "劫": 0.45, "食": 0.35, "伤": 0.35, "印": -0.35, "枭": -0.35, "财": 0.20, "才": 0.20, "官": -0.45, "杀": -0.45,
    },
    "专旺": {
        "比": 0.50, "劫": 0.50, "印": -0.40, "枭": -0.40, "食": 0.30, "伤": 0.30, "财": 0.10, "才": 0.10, "官": -0.50, "杀": -0.50,
    },
    "化气": {
        "食": 0.40, "伤": 0.40, "财": 0.35, "才": 0.35, "官": -0.40, "杀": -0.40, "印": -0.20, "枭": -0.20, "比": -0.10, "劫": -0.10,
    },
    "两气成象": {
        "比": 0.30, "劫": 0.30, "印": 0.25, "枭": 0.25, "食": 0.25, "伤": 0.25, "财": -0.25, "才": -0.25, "官": -0.30, "杀": -0.30,
    },
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


def compute_strength_index(features: dict[str, float]) -> float:
    """
    输入得令/得地/得势/通根等要素的归一化计数，按经验权重混合后压缩到 [0,1]。

    参数示例：{"得令": 0.8, "得地": 0.6, "得势": 0.7, "通根": 0.5}
    """

    weights = {"得令": 0.4, "得地": 0.2, "得势": 0.2, "通根": 0.2}
    score = 0.0
    for key, w in weights.items():
        score += float(features.get(key, 0.0)) * w
    return max(0.0, min(1.0, score))


def blend_ten_god_weights(strength_index: float, special_pattern: dict[str, float] | None = None) -> dict[str, float]:
    """
    按日主强度 I∈[0,1] 对身强/身弱表做线性插值，特殊格局可直接覆盖。
    """

    if special_pattern:
        return special_pattern

    i = max(0.0, min(1.0, strength_index))
    blended = {}
    for key in STRONG_TEN_GOD_WEIGHTS.keys():
        strong_v = STRONG_TEN_GOD_WEIGHTS.get(key, 0.0)
        weak_v = WEAK_TEN_GOD_WEIGHTS.get(key, 0.0)
        blended[key] = i * strong_v + (1 - i) * weak_v
    return blended


def score_ten_god(
    shishen: str,
    wuxing_relation: str | None,
    strength_index: float,
    special_pattern: dict[str, float] | None = None,
) -> float:
    """
    十神喜忌 = 插值后的“专属喜忌表” × (1 + 五行生克乘数)。
    wuxing_relation 可选值：生我/同我/我克/克我/我生，缺省按 0 处理。
    """

    weights = blend_ten_god_weights(strength_index, special_pattern)
    base = weights.get(shishen, 0.0)
    multi = WUXING_MULTIPLIER.get(wuxing_relation or "", 0.0)
    return base * (1.0 + multi)


def score_relation(relations: list[str], trigger_coeff: float = 1.0) -> float:
    """
    刑冲合害的基础分 × 触发系数；relations 传入命盘/流年的触发列表。
    """

    total = 0.0
    for rel in relations:
        total += RELATION_BASE_SCORE.get(rel, 0.0) * trigger_coeff
    return total


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
    strength_index: float = 0.5,
    special_pattern: dict[str, float] | None = None,
    relation_trigger: float = 1.0,
    ten_god_weight: float = 10.0,
) -> pd.Series:
    """
    结合周期性涨跌、十神喜忌插值、五行乘数与刑冲合害（或关键词）生成逐年信号。
    返回 index=年份 的 pd.Series；缺少字段时自动回落到关键词打分。
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

        shishen = str(row.get("shishen", "")).strip()
        wuxing_relation = str(row.get("wuxing_relation", "")).strip() or None
        ten_score = 0.0
        if shishen:
            ten_score = score_ten_god(
                shishen=shishen,
                wuxing_relation=wuxing_relation,
                strength_index=strength_index,
                special_pattern=special_pattern,
            ) * ten_god_weight

        relations_raw = row.get("relations", [])
        if isinstance(relations_raw, str):
            # 兼容“刑/冲/合”字符串或以空格分隔
            parts = [p for token in relations_raw.split("/") for p in token.split(" ") if p]
            relations = parts
        else:
            relations = list(relations_raw) if relations_raw is not None else []
        if dayun is not None and "relations" in dayun and isinstance(dayun["relations"], (list, tuple)):
            relations = relations + list(dayun["relations"])
        relation_score = score_relation(relations, trigger_coeff=relation_trigger) if relations else 0.0

        # 额外强调“大运凶”对该阶段流年的拖累
        if any(k in dayun_desc for k in risk.keys()):
            keyword_score -= dayun_risk_weight

        signals[row["year"]] = cyc + keyword_score + ten_score + relation_score

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
