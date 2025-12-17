import datetime as dt
import math
from typing import Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from parse_bazi_output import parse_dayun_liunian, run_bazi_py
from score_model import (
    DEFAULT_BOOST,
    DEFAULT_RISK,
    build_life_index,
    build_year_signal,
    to_decade_ohlc,
)

# 常见城市的时区与经度，便于做真太阳时矫正
LOCATIONS = {
    "北京 (UTC+08:00)": {"tz": "Asia/Shanghai", "offset": 8.0, "longitude": 116.407},
    "伦敦 (UTC+00:00)": {"tz": "Europe/London", "offset": 0.0, "longitude": -0.1276},
    "纽约 (UTC-05:00)": {"tz": "America/New_York", "offset": -5.0, "longitude": -74.006},
    "悉尼 (UTC+10:00)": {"tz": "Australia/Sydney", "offset": 10.0, "longitude": 151.2093},
    "自定义偏移": {"tz": "custom", "offset": 8.0, "longitude": 116.407},
}


def _equation_of_time_minutes(date_obj: dt.date) -> float:
    """NOAA 近似公式，返回分钟偏移（真太阳 - 平太阳）。"""

    n = date_obj.timetuple().tm_yday
    b = math.radians((360 / 365) * (n - 81))
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def _resolve_timezone(tz_label: str, offset_hours: float) -> dt.tzinfo:
    tz_value = LOCATIONS.get(tz_label, {}).get("tz", tz_label)
    if tz_value == "custom":
        return dt.timezone(dt.timedelta(hours=offset_hours))
    try:
        return ZoneInfo(tz_value)
    except ZoneInfoNotFoundError:
        return dt.timezone.utc


def to_beijing_time(
    year: int,
    month: int,
    day: int,
    hour: int,
    tz_label: str,
    offset_hours: float,
    use_true_solar: bool = False,
    longitude: float = 116.407,
) -> Tuple[dt.datetime, float, dt.datetime]:
    """
    校准出生地时间到北京时区，并可选真太阳时矫正。

    use_true_solar: 是否从标准时换算到真太阳时（需提供经度）。
    longitude: 经度（东经为正，西经为负），用来修正地方时。

    返回： (北京时, 真太阳时分钟差, 校准后的当地时间)
    """

    local_dt = dt.datetime(year, month, day, hour)
    local_dt = local_dt.replace(tzinfo=_resolve_timezone(tz_label, offset_hours))
    solar_delta_minutes = 0.0

    if use_true_solar:
        tz_offset_hours = (local_dt.utcoffset().total_seconds() / 3600.0) if local_dt.utcoffset() else 0.0
        standard_meridian = tz_offset_hours * 15
        eq_time = _equation_of_time_minutes(local_dt.date())
        solar_delta_minutes = 4 * (longitude - standard_meridian) + eq_time
        local_dt = local_dt + dt.timedelta(minutes=solar_delta_minutes)

    beijing_dt = local_dt.astimezone(ZoneInfo("Asia/Shanghai"))
    return beijing_dt, solar_delta_minutes, local_dt


st.set_page_config(page_title="八字人生K线", layout="wide")
st.title("八字排盘 × 大运流年 × 人生K线（不改动源程序）")

with st.sidebar:
    st.header("出生信息")
    cal_type = st.radio("日期类型", ["公历", "农历"], horizontal=True)
    year = st.number_input("年", min_value=1850, max_value=2100, value=1990)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    day = st.number_input("日", min_value=1, max_value=31, value=1)
    hour = st.number_input("时(0-23)", min_value=0, max_value=23, value=12)

    st.markdown("### 出生地校准（北京时间基准）")
    tz_label = st.selectbox("选择出生地/时区", list(LOCATIONS.keys()), index=0)
    default_offset = LOCATIONS.get(tz_label, {}).get("offset", 8.0)
    offset = st.slider(
        "自定义偏移（小时）",
        -12.0,
        14.0,
        default_offset,
        0.5,
        help="仅在选择“自定义偏移”时生效",
    )

    st.markdown("### 真太阳时校准")
    use_true_solar = st.checkbox("使用真太阳时（需要经度）", value=False)
    default_longitude = LOCATIONS.get(tz_label, {}).get("longitude", 116.407)
    longitude = st.number_input(
        "出生地经度 (东经+/西经-)",
        min_value=-180.0,
        max_value=180.0,
        value=float(default_longitude),
        step=0.5,
        help="默认北京经度 116.407°，勾选后按公式换算真太阳时",
    )

    sex = st.radio("性别", ["男", "女"], horizontal=True)
    is_leap = st.checkbox("农历闰月（仅农历有效）", value=False)

    st.divider()
    st.header("评分与指数映射（可调）")
    base = st.number_input("指数起点", min_value=10.0, max_value=1000.0, value=100.0, step=10.0)
    up = st.slider("基准上行年 +%", 0.0, 5.0, 1.2, 0.1)
    down = st.slider("基准回撤年 -%", 0.0, 5.0, 1.0, 0.1)
    cycle = st.slider("周期(年)", 2, 12, 6, 1, help="用于构造波段节奏，结合刑冲破害进行修正")
    keyword_boost = st.slider("喜用/合生等加分", 0.0, 1.5, 0.6, 0.1)
    keyword_risk = st.slider("刑冲破害等扣分", 0.0, 1.5, 1.0, 0.1)
    dayun_drag = st.slider("大运凶象拖累", 0.0, 2.0, 0.6, 0.1)
    ma_short = st.slider("逐年短期均线", 2, 10, 4, 1)
    ma_long = st.slider("逐年长期均线", 5, 20, 9, 1)
    ma_decade_short = st.slider("十年均线1", 2, 6, 2, 1)
    ma_decade_long = st.slider("十年均线2", 2, 10, 4, 1)

run = st.button("开始批算 + 可视化", type="primary")

if run:
    calibrated, solar_delta, local_dt = to_beijing_time(
        int(year), int(month), int(day), int(hour), tz_label, offset, use_true_solar, longitude
    )
    args = [
        str(calibrated.year),
        str(calibrated.month),
        str(calibrated.day),
        str(calibrated.hour),
    ]

    if cal_type == "公历":
        args = ["-g"] + args
    if sex == "女":
        args = ["-n"] + args
    if cal_type == "农历" and is_leap:
        args = ["-r"] + args

    raw = run_bazi_py("bazi.py", args)

    tab1, tab2, tab3 = st.tabs(["📈 人生K线", "🧾 大运流年表", "🖨️ 原始输出"])

    solar_note = " (已按真太阳时矫正 {:+.1f} 分钟)".format(solar_delta) if use_true_solar else ""
    st.caption(
        f"出生地时间 {local_dt.year}-{local_dt.month:02d}-{local_dt.day:02d} {local_dt.hour:02d}:00 在 {tz_label} 校准为北京时间 "
        f"{calibrated.year}-{calibrated.month:02d}-{calibrated.day:02d} {calibrated.hour:02d}:00{solar_note}。"
    )

    df_dayun, df_liunian = parse_dayun_liunian(raw)
    df_dayun = df_dayun.sort_values("start_age").reset_index(drop=True)
    df_liunian = df_liunian.sort_values("year").reset_index(drop=True)

    with tab3:
        st.subheader("bazi.py 原始输出（用于校验解析）")
        st.code(raw, language="text")

    if df_liunian.empty:
        st.error("未解析到流年数据：请把 tab3 的原始输出里流年段落贴出来，我帮你把正则规则一次对齐。")
        st.stop()

    year_signal = build_year_signal(
        df_liunian,
        df_dayun,
        base_up=up,
        base_down=down,
        cycle=cycle,
        boost={k: v * keyword_boost for k, v in DEFAULT_BOOST.items()},
        risk={k: v * keyword_risk for k, v in DEFAULT_RISK.items()},
        dayun_risk_weight=dayun_drag,
    )

    life = build_life_index(df_liunian, year_signal, base=base)
    life["ma_short"] = life["life_index"].rolling(window=ma_short, min_periods=1).mean()
    life["ma_long"] = life["life_index"].rolling(window=ma_long, min_periods=1).mean()

    ohlc = to_decade_ohlc(life)
    ohlc["ma_short"] = ohlc["close"].rolling(window=ma_decade_short, min_periods=1).mean()
    ohlc["ma_long"] = ohlc["close"].rolling(window=ma_decade_long, min_periods=1).mean()

    with tab1:
        auto_marks = pd.concat([life.nlargest(2, "life_index"), life.nsmallest(2, "life_index")])
        default_marks = sorted(auto_marks["year"].unique().tolist())
        important_years = st.multiselect(
            "标记关键年份（默认高点/低点）",
            options=life["year"].tolist(),
            default=default_marks,
        )

        st.subheader("人生K线（按十年聚合）")
        fig = go.Figure(data=[
            go.Candlestick(
                x=ohlc["decade"].astype(str),
                open=ohlc["open"],
                high=ohlc["high"],
                low=ohlc["low"],
                close=ohlc["close"],
                increasing_line_color="#f5a87f",
                decreasing_line_color="#7bc8a4",
                whiskerwidth=0.4,
                hovertemplate="年代段 %{x}<br>开盘 %{open:.2f}<br>最高 %{high:.2f}<br>最低 %{low:.2f}<br>收盘 %{close:.2f}<extra></extra>",
            )
        ])
        fig.add_trace(
            go.Scatter(
                x=ohlc["decade"].astype(str),
                y=ohlc["ma_short"],
                mode="lines",
                name=f"MA{ma_decade_short}(十年)",
                line=dict(color="#f7d794", width=3),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=ohlc["decade"].astype(str),
                y=ohlc["ma_long"],
                mode="lines",
                name=f"MA{ma_decade_long}(十年)",
                line=dict(color="#778beb", width=2, dash="dash"),
            )
        )
        fig.update_layout(
            height=520,
            xaxis_title="年代段",
            yaxis_title="LifeIndex",
            xaxis_rangeslider_visible=True,
            hovermode="x unified",
            template="simple_white",
            margin=dict(l=40, r=20, t=30, b=30),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("逐年曲线（含均线与标记）")
        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=life["year"],
                y=life["life_index"],
                mode="lines",
                name="LifeIndex",
                line=dict(color="#5b8a72", width=3),
            )
        )
        fig2.add_trace(
            go.Scatter(
                x=life["year"],
                y=life["ma_short"],
                mode="lines",
                name=f"MA{ma_short}",
                line=dict(color="#f5a87f", dash="dot", width=2),
            )
        )
        fig2.add_trace(
            go.Scatter(
                x=life["year"],
                y=life["ma_long"],
                mode="lines",
                name=f"MA{ma_long}",
                line=dict(color="#778beb", dash="dash"),
            )
        )

        marks = life[life["year"].isin(important_years)]
        if not marks.empty:
            fig2.add_trace(
                go.Scatter(
                    x=marks["year"],
                    y=marks["life_index"],
                    mode="markers+text",
                    name="重要年份",
                    marker=dict(size=11, color="#e27d60", line=dict(width=1, color="#ffffff")),
                    text=[f"{y}" for y in marks["year"]],
                    textposition="top center",
                )
            )
            for y in marks["year"].tolist():
                fig2.add_vline(x=y, line_dash="dot", line_color="#e27d60", opacity=0.25)

        fig2.update_layout(
            height=420,
            xaxis_title="年份",
            yaxis_title="LifeIndex",
            hovermode="x unified",
            template="simple_white",
            margin=dict(l=40, r=20, t=20, b=30),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        st.subheader("大运")
        st.dataframe(df_dayun, use_container_width=True, hide_index=True)
        st.subheader("流年")
        st.dataframe(
            life[["age", "year", "gz", "desc", "year_signal", "life_index"]],
            use_container_width=True,
            hide_index=True,
        )
