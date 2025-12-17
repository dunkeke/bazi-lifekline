import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from parse_bazi_output import run_bazi_py, parse_dayun_liunian
from score_model import build_life_index, to_decade_ohlc

st.set_page_config(page_title="八字人生K线", layout="wide")

st.title("八字排盘 × 大运流年 × 人生K线（不改动源程序）")

with st.sidebar:
    st.header("输入")
    cal_type = st.radio("日期类型", ["公历", "农历"], horizontal=True)
    year = st.number_input("年", min_value=1850, max_value=2100, value=1990)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    day = st.number_input("日", min_value=1, max_value=31, value=1)
    hour = st.number_input("时(0-23)", min_value=0, max_value=23, value=12)

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
    # 1) 组装 bazi.py 参数（完全不改动源程序，只传参运行）
    args = [str(year), str(month), str(day), str(hour)]
    if cal_type == "公历":
        args = ["-g"] + args
    if sex == "女":
        args = ["-n"] + args
    if cal_type == "农历" and is_leap:
        args = ["-r"] + args

    # 2) 运行 bazi.py（黑盒）
    raw = run_bazi_py("bazi.py", args)

    tab1, tab2, tab3 = st.tabs(["📈 人生K线", "🧾 大运流年表", "🖨️ 原始输出"])

    # 3) 解析大运/流年
    df_dayun, df_liunian = parse_dayun_liunian(raw)

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
    ohlc = to_decade_ohlc(life)

    with tab1:
        st.subheader("人生K线（按十年聚合）")
        fig = go.Figure(data=[go.Candlestick(
            x=ohlc["decade"].astype(str),
            open=ohlc["open"], high=ohlc["high"], low=ohlc["low"], close=ohlc["close"],
        )])
        fig.update_layout(height=520, xaxis_title="年代段", yaxis_title="LifeIndex")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("逐年曲线（更细）")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=life["year"], y=life["life_index"], mode="lines"))
        fig2.update_layout(height=360, xaxis_title="年份", yaxis_title="LifeIndex")
        st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        st.subheader("大运")
        st.dataframe(df_dayun, use_container_width=True, hide_index=True)
        st.subheader("流年")
        st.dataframe(life[["age","year","gz","life_index"]], use_container_width=True, hide_index=True)
