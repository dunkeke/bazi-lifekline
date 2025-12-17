import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from parse_bazi_output import parse_dayun_liunian, run_bazi_py
from score_model import build_life_index, to_decade_ohlc


LOCATION_TIMEZONES = {
    "北京 (UTC+08:00)": "Asia/Shanghai",
    "伦敦 (UTC+00:00)": "Europe/London",
    "纽约 (UTC-05:00)": "America/New_York",
    "悉尼 (UTC+10:00)": "Australia/Sydney",
    "自定义偏移": "custom",
}


def to_beijing_time(year: int, month: int, day: int, hour: int, tz_label: str, offset_hours: float):
    """校准出生地时间到北京时区，避免跨日误差。"""

    def _as_timezone(base_dt: dt.datetime):
        tz_value = LOCATION_TIMEZONES.get(tz_label, tz_label)
        if tz_value == "custom":
            return base_dt.replace(tzinfo=dt.timezone(dt.timedelta(hours=offset_hours)))
        try:
            return base_dt.replace(tzinfo=ZoneInfo(tz_value))
        except ZoneInfoNotFoundError:
            return base_dt.replace(tzinfo=dt.timezone.utc)

    local_dt = _as_timezone(dt.datetime(year, month, day, hour))
    beijing_dt = local_dt.astimezone(ZoneInfo("Asia/Shanghai"))
    return beijing_dt

st.set_page_config(page_title="八字人生K线", layout="wide")

st.title("八字排盘 × 大运流年 × 人生K线（不改动源程序）")

with st.sidebar:
    st.header("输入")
    cal_type = st.radio("日期类型", ["公历", "农历"], horizontal=True)
    year = st.number_input("年", min_value=1850, max_value=2100, value=1990)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    day = st.number_input("日", min_value=1, max_value=31, value=1)
    hour = st.number_input("时(0-23)", min_value=0, max_value=23, value=12)

    st.markdown("### 出生地校准（北京时间基准）")
    tz_label = st.selectbox("选择出生地/时区", list(LOCATION_TIMEZONES.keys()), index=0)
    offset = st.slider("自定义偏移（小时）", -12.0, 14.0, 8.0, 0.5, help="仅在选择“自定义偏移”时生效")

    sex = st.radio("性别", ["男", "女"], horizontal=True)
    is_leap = st.checkbox("农历闰月（仅农历有效）", value=False)

    st.divider()
    st.header("人生指数映射（可调）")
    base = st.number_input("指数起点", min_value=10.0, max_value=1000.0, value=100.0, step=10.0)

    # 先给最简“每年固定波动”示例，后续你可以改成“从流年行解析十神/神煞->分数”
    up = st.slider("上行年 +%", 0.0, 5.0, 1.2, 0.1)
    down = st.slider("回撤年 -%", 0.0, 5.0, 1.0, 0.1)
    cycle = st.slider("周期(年)", 2, 12, 6, 1)

run = st.button("开始批算 + 可视化", type="primary")

if run:
    calibrated = to_beijing_time(int(year), int(month), int(day), int(hour), tz_label, offset)
    args = [
        str(calibrated.year),
        str(calibrated.month),
        str(calibrated.day),
        str(calibrated.hour),
    ]

    # 1) 组装 bazi.py 参数（完全不改动源程序，只传参运行）
    if cal_type == "公历":
        args = ["-g"] + args
    if sex == "女":
        args = ["-n"] + args
    if cal_type == "农历" and is_leap:
        args = ["-r"] + args

    # 2) 运行 bazi.py（黑盒）
    raw = run_bazi_py("bazi.py", args)

    tab1, tab2, tab3 = st.tabs(["📈 人生K线", "🧾 大运流年表", "🖨️ 原始输出"])

    st.caption(
        f"出生地时间 {int(year)}-{int(month):02d}-{int(day):02d} {int(hour):02d}:00 在 {tz_label} 校准为北京时间 "
        f"{calibrated.year}-{calibrated.month:02d}-{calibrated.day:02d} {calibrated.hour:02d}:00。"
    )

    # 3) 解析大运/流年
    df_dayun, df_liunian = parse_dayun_liunian(raw)
    df_liunian = df_liunian.sort_values("year").reset_index(drop=True)

    with tab3:
        st.subheader("bazi.py 原始输出（用于校验解析）")
        st.code(raw, language="text")

    if df_liunian.empty:
        st.error("未解析到流年数据：请把 tab3 的原始输出里流年段落贴出来，我帮你把正则规则一次对齐。")
        st.stop()

    # 4) 构造一个“可解释”的年信号（示例：周期性起落；你后续替换成真正命理映射）
    years = df_liunian["year"].tolist()
    sig = {}
    for i, y in enumerate(years):
        phase = i % cycle
        sig[y] = (up if phase < cycle/2 else -down)
    year_signal = pd.Series(sig)

    life = build_life_index(df_liunian, year_signal, base=base)
    life["ma5"] = life["life_index"].rolling(window=5, min_periods=1).mean()
    life["ma10"] = life["life_index"].rolling(window=10, min_periods=1).mean()

    ohlc = to_decade_ohlc(life)
    ohlc["ma2"] = ohlc["close"].rolling(window=2, min_periods=1).mean()
    ohlc["ma3"] = ohlc["close"].rolling(window=3, min_periods=1).mean()

    with tab1:
        auto_marks = pd.concat([life.nlargest(2, "life_index"), life.nsmallest(2, "life_index")])
        default_marks = sorted(auto_marks["year"].unique().tolist())
        important_years = st.multiselect(
            "标记关键年份（默认高点/低点）",
            options=life["year"].tolist(),
            default=default_marks,
        )

        st.subheader("人生K线（按十年聚合）")
        fig = go.Figure(data=[go.Candlestick(
            x=ohlc["decade"].astype(str),
            open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"],
            increasing_line_color="#e74c3c", decreasing_line_color="#2ecc71",
        )])
        fig.add_trace(go.Scatter(x=ohlc["decade"].astype(str), y=ohlc["ma2"], mode="lines", name="MA2(十年)", line=dict(color="#f1c40f")))
        fig.add_trace(go.Scatter(x=ohlc["decade"].astype(str), y=ohlc["ma3"], mode="lines", name="MA3(十年)", line=dict(color="#3498db")))
        fig.update_layout(height=520, xaxis_title="年代段", yaxis_title="LifeIndex", xaxis_rangeslider_visible=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("逐年曲线（更细）")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=life["year"], y=life["life_index"], mode="lines", name="LifeIndex"))
        fig2.add_trace(go.Scatter(x=life["year"], y=life["ma5"], mode="lines", name="MA5", line=dict(color="#f39c12", dash="dot")))
        fig2.add_trace(go.Scatter(x=life["year"], y=life["ma10"], mode="lines", name="MA10", line=dict(color="#1abc9c", dash="dash")))

        marks = life[life["year"].isin(important_years)]
        if not marks.empty:
            fig2.add_trace(go.Scatter(
                x=marks["year"],
                y=marks["life_index"],
                mode="markers+text",
                name="重要年份",
                marker=dict(size=10, color="#e74c3c"),
                text=[f"{y}" for y in marks["year"]],
                textposition="top center",
            ))

        fig2.update_layout(height=420, xaxis_title="年份", yaxis_title="LifeIndex", hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        st.subheader("大运")
        st.dataframe(df_dayun, use_container_width=True, hide_index=True)
        st.subheader("流年")
        st.dataframe(
            life[["age", "year", "gz", "year_signal", "life_index"]],
            use_container_width=True,
            hide_index=True,
        )
