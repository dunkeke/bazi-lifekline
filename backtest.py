"""回测与个性化权重拟合模块。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from score_model import (
    DEFAULT_BOOST,
    DEFAULT_RISK,
    STRONG_TEN_GOD_WEIGHTS,
    WEAK_TEN_GOD_WEIGHTS,
    build_life_index,
    build_year_signal,
)


@dataclass
class Annotation:
    """用户在 K 线图上标记的真实事件。"""

    year: int
    label: str
    outcome: str  # 正向/负向
    intensity: float = 1.0

    def sentiment(self) -> float:
        outcome = self.outcome.strip()
        if any(k in outcome for k in ["喜", "正", "好", "升", "成功"]):
            return 1.0
        if any(k in outcome for k in ["悲", "负", "跌", "裁", "失"]):
            return -1.0
        return 1.0 if self.intensity >= 0 else -1.0


@dataclass
class BacktestConfig:
    base_up: float
    base_down: float
    cycle: int
    keyword_boost: float
    keyword_risk: float
    dayun_drag: float
    strength_index: float
    special_pattern: Optional[Dict[str, float]]
    relation_trigger: float
    ten_god_weight: float
    base: float


@dataclass
class BacktestResult:
    tuned_life: pd.DataFrame
    strong_weights: Dict[str, float]
    weak_weights: Dict[str, float]
    adjustments: List[Tuple[str, float]]


def serialize_annotations(annotations: Sequence[Annotation]) -> List[Dict[str, Any]]:
    return [annotation.__dict__ for annotation in annotations]


def deserialize_annotations(data: Sequence[Dict[str, Any]]) -> List[Annotation]:
    annotations: List[Annotation] = []
    for item in data:
        try:
            annotations.append(
                Annotation(
                    year=int(item.get("year")),
                    label=str(item.get("label", "")),
                    outcome=str(item.get("outcome", "")),
                    intensity=float(item.get("intensity", 1.0)),
                )
            )
        except (TypeError, ValueError):
            continue
    return annotations


def _clamp(value: float, lower: float = -0.8, upper: float = 0.8) -> float:
    return max(lower, min(upper, value))


def tune_ten_god_weights(
    liunian_df: pd.DataFrame,
    annotations: Sequence[Annotation],
    learning_rate: float = 0.05,
) -> Tuple[Dict[str, float], Dict[str, float], List[Tuple[str, float]]]:
    """根据用户反馈微调十神权重，返回新表与调整记录。"""

    strong = dict(STRONG_TEN_GOD_WEIGHTS)
    weak = dict(WEAK_TEN_GOD_WEIGHTS)
    adjustments: List[Tuple[str, float]] = []

    for ann in annotations:
        match = liunian_df[liunian_df["year"] == ann.year]
        if match.empty:
            continue
        shishen = str(match.iloc[0].get("shishen", "")).strip()
        if not shishen:
            continue

        direction = ann.sentiment() * ann.intensity
        delta = learning_rate * direction
        if shishen in strong:
            strong[shishen] = _clamp(strong.get(shishen, 0.0) + delta)
            weak[shishen] = _clamp(weak.get(shishen, 0.0) + delta)
            adjustments.append((shishen, delta))
    return strong, weak, adjustments


def apply_feedback_loop(
    liunian_df: pd.DataFrame,
    dayun_df: pd.DataFrame,
    annotations: Sequence[Annotation],
    config: BacktestConfig,
    learning_rate: float = 0.05,
) -> BacktestResult:
    """按照用户标记进行回测，返回拟合后的 life index 与权重。"""

    strong, weak, adjustments = tune_ten_god_weights(
        liunian_df, annotations, learning_rate=learning_rate
    )

    year_signal = build_year_signal(
        liunian_df,
        dayun_df,
        base_up=config.base_up,
        base_down=config.base_down,
        cycle=config.cycle,
        boost={k: v * config.keyword_boost for k, v in DEFAULT_BOOST.items()},
        risk={k: v * config.keyword_risk for k, v in DEFAULT_RISK.items()},
        dayun_risk_weight=config.dayun_drag,
        strength_index=config.strength_index,
        special_pattern=config.special_pattern,
        relation_trigger=config.relation_trigger,
        ten_god_weight=config.ten_god_weight,
        strong_weights=strong,
        weak_weights=weak,
    )
    tuned_life = build_life_index(liunian_df, year_signal, base=config.base)
    return BacktestResult(
        tuned_life=tuned_life,
        strong_weights=strong,
        weak_weights=weak,
        adjustments=adjustments,
    )
