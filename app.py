import datetime as dt
import json
import math
import os
from typing import Tuple

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore
except ImportError:  # Python < 3.9 fallback
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from openai import OpenAI

from parse_bazi_output import parse_dayun_liunian, run_bazi_py
from score_model import (
    DEFAULT_BOOST,
    DEFAULT_RISK,
    SPECIAL_PATTERN_WEIGHTS,
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

st.set_page_config(page_title="探索人生起伏，解锁命理奥秘", layout="wide", page_icon="📜")


def apply_chinese_theme():
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(circle at 20% 20%, rgba(255, 244, 232, 0.55), rgba(255, 255, 255, 0.05)),
                        linear-gradient(135deg, #0f1b2c 0%, #1e2a3a 30%, #2b1b1a 100%);
            color: #2b2118;
        }
        .hero-banner {
            background: linear-gradient(120deg, rgba(233, 215, 182, 0.9), rgba(255, 255, 255, 0.95));
            border: 1px solid #d8c2a3;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.25);
            padding: 32px 28px;
            border-radius: 18px;
            margin-bottom: 16px;
            position: relative;
            overflow: hidden;
        }
        .hero-banner:before {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at 80% 10%, rgba(255,255,255,0.35), transparent 40%),
                        radial-gradient(circle at 10% 90%, rgba(199,155,100,0.25), transparent 35%);
            pointer-events: none;
        }
        .hero-title {
            font-size: 32px;
            font-weight: 800;
            letter-spacing: 2px;
            color: #2c1b0f;
            font-family: "Noto Serif SC", "STKaiti", "Songti SC", serif;
            text-shadow: 0 2px 6px rgba(0,0,0,0.15);
        }
        .hero-sub {
            margin-top: 6px;
            font-size: 16px;
            color: #624a2e;
            font-family: "LXGW WenKai", "STSong", "KaiTi", serif;
        }
        .hero-tags {
            margin-top: 12px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .tag-pill {
            background: linear-gradient(120deg, #c79b64, #f1d8b2);
            color: #2b1b12;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid rgba(82,60,30,0.25);
            font-weight: 600;
            font-size: 12px;
        }
        .section-card {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 14px;
            padding: 16px;
            border: 1px solid rgba(214, 190, 156, 0.8);
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12);
            height: 100%;
        }
        .section-title {
            font-weight: 700;
            color: #2c1b0f;
            font-size: 16px;
            letter-spacing: 1px;
        }
        .section-desc {
            color: #4b3a28;
            font-size: 13px;
            line-height: 1.6;
            margin-top: 6px;
        }
        div[data-testid="stSidebar"] > div {
            background: linear-gradient(180deg, rgba(29, 36, 52, 0.95), rgba(56, 40, 33, 0.95));
            color: #f6eadf;
            border-right: 1px solid #c7a56f;
        }
        div[data-testid="stSidebar"] * {
            color: #f6eadf !important;
        }
        .stButton>button {
            background: linear-gradient(120deg, #c79b64, #f0d2a3);
            color: #2c1b0f;
            border: 1px solid #b88d57;
            border-radius: 12px;
            font-weight: 800;
            letter-spacing: 1px;
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.18);
        }
        .stButton>button:hover {
            background: linear-gradient(120deg, #d9b278, #ffe4bc);
            border-color: #d9b278;
        }
        .callout {
            border-left: 4px solid #c79b64;
            padding-left: 12px;
            color: #3f3122;
            font-size: 13px;
        }
        .metric-badge {
            background: rgba(255,255,255,0.75);
            border: 1px solid rgba(215, 186, 146, 0.8);
            border-radius: 12px;
            padding: 12px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_chinese_theme()

st.markdown(
    """
    <div class="hero-banner">
        <div class="hero-title">探索人生起伏，解锁命理奥秘</div>
        <div class="hero-sub">以古韵国风的推演体验，串联八字排盘、流年大运与人生K线，观星辰之势，悟起伏之理。</div>
        <div class="hero-tags">
            <span class="tag-pill">月令日主</span>
            <span class="tag-pill">刑冲合害</span>
            <span class="tag-pill">十神权重</span>
            <span class="tag-pill">指数映射</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("以“古韵·沉稳”的视觉呈现，保留原有推盘与可视化逻辑，仅焕新体验与名称。")


def analyze_bazi_with_deepseek(raw_bazi_output: str, api_key: str) -> str:
    """
    通过 DeepSeek（OpenAI 兼容 SDK）对 bazi.py 原始输出进行命理解读。
    """

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    system_prompt = """你是一位精通中国传统八字命理学的专家，擅长从八字排盘中分析人生运势、性格特点和发展方向。

请根据提供的八字排盘原始输出，以专业、客观且富有建设性的方式进行解读，内容包括：
1. 命盘总览：简要总结八字的基本格局和特点
2. 五行分析：分析五行强弱、平衡与喜用神
3. 大运走势：解读大运阶段的运势起伏和关键节点
4. 流年提示：指出需要注意的关键年份和机遇
5. 人生建议：基于命理分析给出务实的发展建议

请使用专业但易懂的语言，避免过度玄学化，注重实际指导意义。"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下八字排盘结果：\n\n{raw_bazi_output}"},
            ],
            stream=True,
            max_tokens=2000,
            temperature=0.7,
        )

        parts = []
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)
    except Exception as exc:  # noqa: BLE001
        return f"API调用失败：{exc}\n请检查API密钥与网络连接。"


def add_deepseek_analysis_tab(raw_bazi_output: str):
    """
    在 Streamlit 中渲染 DeepSeek AI 解读入口。
    """

    st.markdown("### 🧠 AI深度解读：洞悉命理玄机")

    preset_key = os.getenv("DEEPSEEK_API_KEY", "")
    col1, col2 = st.columns([3, 1])
    with col1:
        api_key = st.text_input(
            "DeepSeek API密钥",
            type="password",
            value=preset_key,
            help="密钥可在 DeepSeek 平台创建，建议以环境变量 DEEPSEEK_API_KEY 预填。",
            placeholder="输入以 sk- 开头的密钥",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_button = st.button("开始AI解读", type="secondary")

    with st.expander("ℹ️ 如何获取/使用 DeepSeek API 密钥"):
        st.markdown(
            """
            1. 访问 [DeepSeek 平台](https://platform.deepseek.com/) 注册/登录。
            2. 在「API Keys」页面创建新的密钥，新用户通常会有免费额度。
            3. 复制以 `sk-` 开头的密钥，粘贴到上方输入框，或在部署时设置环境变量 `DEEPSEEK_API_KEY`。
            4. 请求示例：
            """,
            unsafe_allow_html=True,
        )
        sample_payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "命理分析专家"},
                {"role": "user", "content": "请分析以下八字排盘结果：..."},
            ],
            "stream": True,
        }
        st.code(json.dumps(sample_payload, ensure_ascii=False, indent=2), language="json")

    analysis = None
    if analyze_button:
        if not api_key:
            st.error("请先输入 API 密钥，或在环境变量 DEEPSEEK_API_KEY 中配置。")
        elif not api_key.startswith("sk-"):
            st.warning("API 密钥格式似乎不正确，应以 sk- 开头。")
        else:
            with st.spinner("🧐 AI 正在深度分析命盘，探寻人生玄机……"):
                analysis = analyze_bazi_with_deepseek(raw_bazi_output, api_key)

    if analysis:
        st.markdown("---")
        st.markdown("### 📜 AI命理分析报告")
        st.markdown(
            """
            <style>
            .ai-analysis {
                background: linear-gradient(135deg, #fdfcfb 0%, #f5f7fa 100%);
                border-left: 4px solid #c79b64;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
                margin: 15px 0;
            }
            .ai-analysis p {
                line-height: 1.7;
                color: #4b3a28;
                margin: 0;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for section in analysis.split("\n\n"):
            if section.strip():
                st.markdown(f'<div class="ai-analysis">{section}</div>', unsafe_allow_html=True)

        st.download_button(
            label="📥 下载分析报告",
            data=analysis,
            file_name="八字命理分析报告.txt",
            mime="text/plain",
        )


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


feature_cols = st.columns(3)
with feature_cols[0]:
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">日月风骨 · 排盘</div>
            <div class="section-desc">兼容公历/农历，含真太阳时矫正与性别顺逆排盘，稳准对齐原有命盘推演流程。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with feature_cols[1]:
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">刑冲合害 · 评分</div>
            <div class="section-desc">内置十神权重插值、刑冲合害触发与喜忌关键词放大，助你调教出个性化的流年节奏。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with feature_cols[2]:
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">长线短波 · 视觉</div>
            <div class="section-desc">十年K线与逐年均线并陈，可标注关键节点，沉浸式呈现人生起伏与大运趋势。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()

with st.sidebar:
    st.header("📜 起局信息")
    cal_type = st.radio("日期类型", ["公历", "农历"], horizontal=True)
    year = st.number_input("年", min_value=1850, max_value=2100, value=1990)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    day = st.number_input("日", min_value=1, max_value=31, value=1)
    hour = st.number_input("时(0-23)", min_value=0, max_value=23, value=12)

    st.markdown("### 📍 出生地校准（北京时间基准）")
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

    st.markdown("### 🌞 真太阳时校准")
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
    st.header("📈 评分与指数映射（可调）")
    base = st.number_input("指数起点", min_value=10.0, max_value=1000.0, value=100.0, step=10.0)
    strength_index = st.slider("日主强度指数 I", 0.0, 1.0, 0.5, 0.05, help="得令/得地/得势/通根插值后的强度，0=身弱，1=身强")
    special_label = st.selectbox("特殊格局覆盖", ["无"] + list(SPECIAL_PATTERN_WEIGHTS.keys()))
    special_pattern = None if special_label == "无" else SPECIAL_PATTERN_WEIGHTS.get(special_label)
    up = st.slider("基准上行年 +%", 0.0, 5.0, 1.2, 0.1)
    down = st.slider("基准回撤年 -%", 0.0, 5.0, 1.0, 0.1)
    cycle = st.slider("周期(年)", 2, 12, 6, 1, help="用于构造波段节奏，结合刑冲破害进行修正")
    ten_god_weight = st.slider("十神/五行评分权重", 0.0, 30.0, 10.0, 0.5, help="将十神喜忌 × 五行生克的结果放大到年度波动")
    relation_trigger = st.slider("刑冲合害触发系数", 0.0, 3.0, 1.0, 0.1, help="控制三合六合刑冲破害的影响强度")
    keyword_boost = st.slider("喜用/合生等加分", 0.0, 1.5, 0.6, 0.1)
    keyword_risk = st.slider("刑冲破害等扣分", 0.0, 1.5, 1.0, 0.1)
    dayun_drag = st.slider("大运凶象拖累", 0.0, 2.0, 0.6, 0.1)
    ma_short = st.slider("逐年短期均线", 2, 10, 4, 1)
    ma_long = st.slider("逐年长期均线", 5, 20, 9, 1)
    ma_decade_short = st.slider("十年均线1", 2, 6, 2, 1)
    ma_decade_long = st.slider("十年均线2", 2, 10, 4, 1)

st.markdown(
    """
    <div class="callout">
        <strong>提示：</strong> 保持原有算法与参数名不变，仅对界面做国风重制。侧边栏调校完毕后，点击下方按钮即可推演。
    </div>
    """,
    unsafe_allow_html=True,
)

run = st.button("揽星起盘 · 开启推演", type="primary")

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

    tab1, tab2, tab3, tab4 = st.tabs(["📈 长线星迹·人生K", "🧾 运程账本", "🖨️ 原始输出", "🤖 AI深度解读"])

    solar_note = " (已按真太阳时矫正 {:+.1f} 分钟)".format(solar_delta) if use_true_solar else ""
    st.caption(
        f"出生地时间 {local_dt.year}-{local_dt.month:02d}-{local_dt.day:02d} {local_dt.hour:02d}:00 在 {tz_label} 校准为北京时间 "
        f"{calibrated.year}-{calibrated.month:02d}-{calibrated.day:02d} {calibrated.hour:02d}:00{solar_note}。"
    )
    meta_cols = st.columns(3)
    meta_cols[0].markdown(
        f"""
        <div class="metric-badge">
            <div class="section-title">校准北京时间</div>
            <div class="section-desc">{calibrated.year}-{calibrated.month:02d}-{calibrated.day:02d} {calibrated.hour:02d}:00</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    meta_cols[1].markdown(
        f"""
        <div class="metric-badge">
            <div class="section-title">真太阳时修正</div>
            <div class="section-desc">{solar_delta:+.1f} 分钟 · 经度 {longitude:.2f}°</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    meta_cols[2].markdown(
        f"""
        <div class="metric-badge">
            <div class="section-title">节奏参数</div>
            <div class="section-desc">MA {ma_short}/{ma_long} · 十年 {ma_decade_short}/{ma_decade_long}</div>
        </div>
        """,
        unsafe_allow_html=True,
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
        strength_index=strength_index,
        special_pattern=special_pattern,
        relation_trigger=relation_trigger,
        ten_god_weight=ten_god_weight,
    )

    life = build_life_index(df_liunian, year_signal, base=base)
    life["ma_short"] = life["life_index"].rolling(window=ma_short, min_periods=1).mean()
    life["ma_long"] = life["life_index"].rolling(window=ma_long, min_periods=1).mean()

    ohlc = to_decade_ohlc(life)
    ohlc["ma_short"] = ohlc["close"].rolling(window=ma_decade_short, min_periods=1).mean()
    ohlc["ma_long"] = ohlc["close"].rolling(window=ma_decade_long, min_periods=1).mean()

    with tab1:
        st.markdown(
            """
            <div class="callout" style="margin-bottom:10px;">
                <strong>解读：</strong> 上方以十年为一烛，可捕捉长线大势；下方逐年曲线配合均线、年份标记，适合回看与自定义关键拐点。
            </div>
            """,
            unsafe_allow_html=True,
        )
        auto_marks = pd.concat([life.nlargest(2, "life_index"), life.nsmallest(2, "life_index")])
        default_marks = sorted(auto_marks["year"].unique().tolist())
        important_years = st.multiselect(
            "标记关键年份（默认高点/低点）",
            options=life["year"].tolist(),
            default=default_marks,
        )

        st.subheader("长线人生K线（按十年聚合）")
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
        st.markdown(
            """
            <div class="callout" style="margin-bottom:10px;">
                <strong>对照：</strong> 先看大运段落的气势与刑冲合害，再逐年核对喜忌和 LifeIndex；表格支持筛选与排序，便于校对原始输出。
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("大运")
        st.dataframe(df_dayun, use_container_width=True, hide_index=True)
        st.subheader("流年")
        st.dataframe(
            life[["age", "year", "gz", "desc", "year_signal", "life_index"]],
            use_container_width=True,
            hide_index=True,
        )

    with tab4:
        add_deepseek_analysis_tab(raw)
