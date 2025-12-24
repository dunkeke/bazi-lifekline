import datetime as dt
import json
import math
import os
from typing import Optional, Tuple

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore
except ImportError:  # Python < 3.9 fallback
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from geopy.geocoders import Nominatim
from lunar_python import Solar
from openai import OpenAI
from timezonefinder import TimezoneFinder

from backtest import (
    Annotation,
    BacktestConfig,
    apply_feedback_loop,
    deserialize_annotations,
    serialize_annotations,
)

try:
    from geopy.geocoders import Nominatim
except ImportError:
    Nominatim = None  # type: ignore

try:
    from timezonefinder import TimezoneFinder
except ImportError:
    TimezoneFinder = None  # type: ignore

try:
    from geopy.geocoders import Nominatim
except ImportError:
    Nominatim = None  # type: ignore

try:
    from timezonefinder import TimezoneFinder
except ImportError:
    TimezoneFinder = None  # type: ignore

try:
    from geopy.geocoders import Nominatim
except ImportError:
    Nominatim = None  # type: ignore

try:
    from timezonefinder import TimezoneFinder
except ImportError:
    TimezoneFinder = None  # type: ignore

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

LOCAL_CITY_CATALOG = {
    "北京": {"lat": 39.9042, "lon": 116.4074, "tz": "Asia/Shanghai"},
    "Beijing": {"lat": 39.9042, "lon": 116.4074, "tz": "Asia/Shanghai"},
    "伦敦": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London"},
    "London": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London"},
    "纽约": {"lat": 40.7128, "lon": -74.006, "tz": "America/New_York"},
    "New York": {"lat": 40.7128, "lon": -74.006, "tz": "America/New_York"},
    "悉尼": {"lat": -33.8688, "lon": 151.2093, "tz": "Australia/Sydney"},
    "Sydney": {"lat": -33.8688, "lon": 151.2093, "tz": "Australia/Sydney"},
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


def analyze_daily_fortune_with_deepseek(
    natal_raw_output: str,
    daily_bazi_summary: str,
    target_date: dt.date,
    api_key: str,
) -> str:
    """
    通过 DeepSeek 对流日八字进行运势分析与建议。
    """

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    system_prompt = """你是一位精通中国传统八字命理学的专家，擅长结合本命八字与流日八字做日运分析。

请根据提供的本命盘原始输出与流日八字，生成一份简洁、可执行的日运分析，包含：
1. 流日概览：当天干支气场与关键词
2. 本命交互：流日与本命的生克、喜忌、冲合提示
3. 运势建议：事业/财务/情感/健康各 1-2 条实用建议
4. 风险提醒：避免事项与可化解的小动作

语言专业但易懂，避免过度玄学化，强调可执行建议。"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"目标日期：{target_date:%Y-%m-%d}\n"
                        f"流日八字：{daily_bazi_summary}\n\n"
                        f"本命八字原始输出：\n{natal_raw_output}"
                    ),
                },
            ],
            stream=True,
            max_tokens=1800,
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
            key="deepseek_api_key",
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


def _get_daily_bazi_summary(date_obj: dt.date, hour: int = 12) -> Tuple[str, str]:
    solar = Solar.fromYmdHms(date_obj.year, date_obj.month, date_obj.day, hour, 0, 0)
    lunar = solar.getLunar()
    ba = lunar.getEightChar()
    gans = [ba.getYearGan(), ba.getMonthGan(), ba.getDayGan(), ba.getTimeGan()]
    zhis = [ba.getYearZhi(), ba.getMonthZhi(), ba.getDayZhi(), ba.getTimeZhi()]
    pillars = [f"{gan}{zhi}" for gan, zhi in zip(gans, zhis)]
    summary = "年柱{} · 月柱{} · 日柱{} · 时柱{}".format(*pillars)
    return summary, pillars[2]


def _calculate_offset_hours(tz_name: str) -> float:
    """
    将时区转换为当前（本地日期）的小时偏移，便于预填自定义偏移。
    """

    try:
        tz_info = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return 8.0

    offset = dt.datetime.now(tz_info).utcoffset()
    return round((offset.total_seconds() / 3600.0) if offset else 0.0, 2)


def geocode_location(name: str) -> Tuple[Optional[Tuple[float, float, str]], str]:
    """
    使用 geopy/Nominatim 解析地点，返回 (lat, lon, timezone)。
    """

    query = name.strip()
    if not query:
        return None, "请输入地点名称。"

    if Nominatim is None:
        fallback = LOCAL_CITY_CATALOG.get(query)
        if fallback:
            return (fallback["lat"], fallback["lon"], fallback["tz"]), ""
        return None, "geopy 未安装：请安装 geopy 或使用内置常用城市/手填经度。"

    geocode_error = ""
    try:
        geolocator = Nominatim(user_agent="bazi-lifekline")
        location = geolocator.geocode(query, language="zh", addressdetails=True, timeout=10)
    except Exception as exc:  # noqa: BLE001
        location = None
        geocode_error = f"地理解析失败：{exc}"

    if location:
        lat, lon = location.latitude, location.longitude
    else:
        fallback = LOCAL_CITY_CATALOG.get(query)
        if fallback:
            return (fallback["lat"], fallback["lon"], fallback["tz"]), ""
        if geocode_error:
            return None, geocode_error
        return None, "未找到对应地点，请尝试更具体的名称或手动输入经度/时区。"

    if TimezoneFinder is None:
        return None, "经纬度已获取，但缺少 timezonefinder 以确定时区；请安装后重试，或手动选择。"

    try:
        tz_finder = TimezoneFinder()
        tz_name = tz_finder.timezone_at(lng=lon, lat=lat) or tz_finder.closest_timezone_at(lng=lon, lat=lat)
    except Exception as exc:  # noqa: BLE001
        return None, f"经纬度获取成功，但时区识别失败：{exc}"

    if not tz_name:
        return None, "经纬度已获取，但无法匹配时区，请手动选择。"

    return (lat, lon, tz_name), ""


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

state = st.session_state
state.setdefault("bazi_result", None)
state.setdefault("offset_source", "auto")
state.setdefault("longitude_source", "auto")
state.setdefault("tz_label", list(LOCATIONS.keys())[0])
state.setdefault("annotations", [])
state.setdefault("backtest_result", None)

if "pending_tz_label" in state:
    state["tz_label"] = state.pop("pending_tz_label")
if "pending_longitude" in state:
    state["longitude_value"] = state.pop("pending_longitude")
if "pending_offset_hours" in state:
    state["offset_hours"] = state.pop("pending_offset_hours")

with st.sidebar:
    st.header("📜 起局信息")
    cal_type = st.radio("日期类型", ["公历", "农历"], horizontal=True)
    year = st.number_input("年", min_value=1850, max_value=2100, value=1990)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    day = st.number_input("日", min_value=1, max_value=31, value=1)
    hour = st.number_input("时(0-23)", min_value=0, max_value=23, value=12)

    st.markdown("### 📍 出生地校准（北京时间基准）")
    tz_options = list(LOCATIONS.keys())
    parsed_timezone = state.get("parsed_timezone")
    if parsed_timezone and parsed_timezone not in tz_options:
        tz_options.append(parsed_timezone)
    if "tz_label" in state and state["tz_label"] not in tz_options:
        state["tz_label"] = tz_options[0]
    tz_label = st.selectbox(
        "选择出生地/时区",
        tz_options,
        index=tz_options.index(state.get("tz_label", tz_options[0])) if tz_options else 0,
        key="tz_label",
    )

    default_offset = LOCATIONS.get(tz_label, {}).get("offset", _calculate_offset_hours(tz_label))
    default_longitude = LOCATIONS.get(tz_label, {}).get("longitude", 116.407)
    tz_set_by_geocode = state.pop("tz_set_by_geocode", False)
    previous_tz_label = state.get("previous_tz_label")
    if "offset_hours" not in state:
        state["offset_hours"] = float(default_offset)
    if "longitude_value" not in state:
        state["longitude_value"] = float(default_longitude)
    if previous_tz_label and previous_tz_label != tz_label and not tz_set_by_geocode:
        state["offset_hours"] = float(default_offset)
        state["longitude_value"] = float(default_longitude)
        state["offset_source"] = "auto"
        state["longitude_source"] = "auto"
    state["previous_tz_label"] = tz_label

    st.markdown("### 🌞 真太阳时校准")
    location_query = st.text_input(
        "地点名称（自动带入经度/时区）",
        key="location_query",
        placeholder="如：北京三里屯 / 纽约曼哈顿 / 悉尼歌剧院",
        help="解析成功将覆盖下方经度，并尝试填充时区与偏移。",
    )
    parse_location = st.button("解析")
    if parse_location:
        parsed_location, geo_error = geocode_location(location_query)
        if parsed_location:
            lat, lon, tz_name = parsed_location
            state["geo_feedback"] = f"解析成功：{location_query} · 纬度 {lat:.4f} · 经度 {lon:.4f} · 时区 {tz_name}"
            state["geo_error"] = ""
            state["parsed_latitude"] = lat
            state["parsed_timezone"] = tz_name
            state["pending_longitude"] = round(lon, 4)
            state["longitude_source"] = "geocode"
            state["pending_tz_label"] = tz_name
            state["tz_set_by_geocode"] = True
            offset_hours = _calculate_offset_hours(tz_name)
            state["pending_offset_hours"] = offset_hours
            state["offset_source"] = "geocode"
        else:
            state["geo_error"] = geo_error
            state["geo_feedback"] = ""

    if state.get("geo_feedback"):
        st.success(state["geo_feedback"])
    elif state.get("geo_error"):
        st.warning(state["geo_error"])

    tz_label = state.get("tz_label", tz_label)
    use_true_solar = st.checkbox("使用真太阳时（需要经度）", value=False)
    longitude = st.number_input(
        "出生地经度 (东经+/西经-)",
        min_value=-180.0,
        max_value=180.0,
        value=float(state.get("longitude_value", default_longitude)),
        step=0.5,
        help="默认北京经度 116.407°，勾选后按公式换算真太阳时",
    )
    offset = st.slider(
        "自定义偏移（小时）",
        -12.0,
        14.0,
        float(state.get("offset_hours", default_offset)),
        0.5,
        help="仅在选择“自定义偏移”时生效",
        key="offset_hours",
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
    relation_trigger = st.slider("刑冲合害触发系数", 0.0, 3.0, 0.8, 0.1, help="控制三合六合刑冲破害的影响强度")
    keyword_boost = st.slider("喜用/合生等加分", 0.0, 1.5, 1.0, 0.1)
    keyword_risk = st.slider("刑冲破害等扣分", 0.0, 1.5, 0.6, 0.1)
    dayun_drag = st.slider("大运凶象拖累", 0.0, 2.0, 0.6, 0.1)
    ma_short = st.slider("逐年短期均线", 1, 10, 4, 1)
    ma_long = st.slider("逐年长期均线", 1, 20, 9, 1)
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

    df_dayun, df_liunian = parse_dayun_liunian(raw)
    df_dayun = df_dayun.sort_values("start_age").reset_index(drop=True)
    df_liunian = df_liunian.sort_values("year").reset_index(drop=True)

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

    state["bazi_result"] = {
        "raw": raw,
        "df_dayun": df_dayun,
        "df_liunian": df_liunian,
        "life": life,
        "ohlc": ohlc,
        "calibrated": calibrated,
        "local_dt": local_dt,
        "solar_delta": solar_delta,
        "tz_label": tz_label,
        "longitude": longitude,
        "ma_short": ma_short,
        "ma_long": ma_long,
        "ma_decade_short": ma_decade_short,
        "ma_decade_long": ma_decade_long,
        "params": {
            "up": up,
            "down": down,
            "cycle": cycle,
            "keyword_boost": keyword_boost,
            "keyword_risk": keyword_risk,
            "dayun_drag": dayun_drag,
            "strength_index": strength_index,
            "special_pattern": special_pattern,
            "relation_trigger": relation_trigger,
            "ten_god_weight": ten_god_weight,
            "base": base,
        },
    }


result = state.get("bazi_result")

if not result:
    st.info("请先填写出生信息并点击“揽星起盘 · 开启推演”后查看结果与 AI 解读。")

if result:
    raw = result["raw"]
    df_dayun = result["df_dayun"]
    df_liunian = result["df_liunian"]
    life = result["life"]
    ohlc = result["ohlc"]
    calibrated = result["calibrated"]
    local_dt = result["local_dt"]
    solar_delta = result["solar_delta"]
    tz_label = result["tz_label"]
    longitude = result["longitude"]
    ma_short = result["ma_short"]
    ma_long = result["ma_long"]
    ma_decade_short = result["ma_decade_short"]
    ma_decade_long = result["ma_decade_long"]

    tab1, tab2, tab3, tab4, tab6, tab5 = st.tabs(
        ["📈 长线星迹·人生K", "🧾 运程账本", "🖨️ 原始输出", "🤖 AI深度解读", "🌞 流日运势", "🧪 回测拟合"]
    )

    solar_note = " (已按真太阳时矫正 {:+.1f} 分钟)".format(solar_delta) if solar_delta else ""
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

    with tab3:
        st.subheader("bazi.py 原始输出（用于校验解析）")
        st.code(raw, language="text")

    with tab2:
        st.markdown(
            """
            <div class="callout" style="margin-bottom:10px;">
                <strong>对照：</strong> 先看大运段落的气势与刑冲合害，再逐年核对喜忌和 LifeIndex；表格支持筛选与排序，便于校对原始输出。
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("年运轨迹（当均线窗口=1 时更贴合逐年走势）")
        decade_bands = sorted(set(life["year"] // 10))
        fig_track = go.Figure()
        for decade in decade_bands:
            start = decade * 10
            end = start + 9
            fig_track.add_vrect(
                x0=start - 0.5,
                x1=end + 0.5,
                fillcolor="rgba(199,155,100,0.06)" if decade % 2 == 0 else "rgba(120,139,235,0.05)",
                line_width=0,
                layer="below",
            )
        fig_track.add_trace(
            go.Scatter(
                x=life["year"],
                y=life["life_index"],
                mode="lines+markers",
                name="年运轨迹",
                line=dict(
                    width=3,
                    color="#c79b64",
                ),
                marker=dict(
                    size=9,
                    color=life["year_signal"],
                    colorscale="RdYlGn",
                    colorbar=dict(title="年信号", tickformat="+.1f"),
                    line=dict(width=0.5, color="#ffffff"),
                ),
                hovertemplate="年份 %{x}<br>LifeIndex %{y:.2f}<br>年信号 %{customdata:.2f}<extra></extra>",
                customdata=life["year_signal"],
            )
        )
        fig_track.add_trace(
            go.Scatter(
                x=life["year"],
                y=life["life_index"],
                mode="lines",
                line=dict(shape="spline", color="rgba(199,155,100,0.35)", width=0),
                fill="tozeroy",
                fillcolor="rgba(199,155,100,0.12)",
                name="底色",
                hoverinfo="skip",
            )
        )
        peaks = pd.concat([life.nlargest(1, "life_index"), life.nsmallest(1, "life_index")])
        if not peaks.empty:
            fig_track.add_trace(
                go.Scatter(
                    x=peaks["year"],
                    y=peaks["life_index"],
                    mode="markers+text",
                    name="极值标记",
                    marker=dict(size=13, color="#e27d60", symbol="diamond", line=dict(width=1, color="#ffffff")),
                    text=[f"{y}" for y in peaks["year"]],
                    textposition="top center",
                    hovertemplate="年份 %{x}<br>LifeIndex %{y:.2f}<extra></extra>",
                )
            )
        fig_track.update_layout(
            height=420,
            xaxis_title="年份",
            yaxis_title="LifeIndex",
            hovermode="x unified",
            template="simple_white",
            margin=dict(l=40, r=20, t=10, b=30),
        )
        st.plotly_chart(fig_track, use_container_width=True)

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

    with tab6:
        st.markdown(
            """
            <div class="callout" style="margin-bottom:10px;">
                <strong>流日提示：</strong> 默认按所选日期中午 12:00 排盘，避免日柱交界波动；若你更关注某个时段，可结合实际时辰自行对照。
            </div>
            """,
            unsafe_allow_html=True,
        )
        tz_info = _resolve_timezone(tz_label, offset)
        today_local = dt.datetime.now(tz_info).date()
        daily_date = st.date_input("选择流日日期", value=today_local, key="daily_date")

        daily_summary, daily_day_pillar = _get_daily_bazi_summary(daily_date)
        st.markdown(
            f"""
            <div class="section-card">
                <div class="section-title">流日八字</div>
                <div class="section-desc">{daily_summary}</div>
                <div class="section-desc">当日主柱：{daily_day_pillar}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### 🤖 AI 流日运势解读")
        preset_key = os.getenv("DEEPSEEK_API_KEY", "")
        api_key_daily = st.text_input(
            "DeepSeek API密钥（可复用上方）",
            type="password",
            value=st.session_state.get("deepseek_api_key", preset_key),
            key="deepseek_api_key_daily",
            help="密钥可在 DeepSeek 平台创建，建议以环境变量 DEEPSEEK_API_KEY 预填。",
            placeholder="输入以 sk- 开头的密钥",
        )
        if api_key_daily:
            st.session_state["deepseek_api_key"] = api_key_daily

        daily_button = st.button("生成流日AI解读", type="secondary")
        daily_analysis = None
        if daily_button:
            if not api_key_daily:
                st.error("请先输入 API 密钥，或在环境变量 DEEPSEEK_API_KEY 中配置。")
            elif not api_key_daily.startswith("sk-"):
                st.warning("API 密钥格式似乎不正确，应以 sk- 开头。")
            else:
                with st.spinner("🌤️ AI 正在分析流日气象，解读运势建议……"):
                    daily_analysis = analyze_daily_fortune_with_deepseek(
                        raw,
                        daily_summary,
                        daily_date,
                        api_key_daily,
                    )

        if daily_analysis:
            st.markdown("---")
            st.markdown("### 📌 流日运势建议")
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
            for section in daily_analysis.split("\n\n"):
                if section.strip():
                    st.markdown(f'<div class="ai-analysis">{section}</div>', unsafe_allow_html=True)

    with tab5:
        st.subheader("人生事件回测与权重拟合")
        st.markdown(
            """
            <div class="callout" style="margin-bottom:10px;">
                <strong>玩法：</strong> 在 K 线上记录“高光/低谷”年份，系统会依据当年的十神喜忌反向微调权重，
                拟合出更贴合你的个性化评分模型。
            </div>
            """,
            unsafe_allow_html=True,
        )

        annotations = deserialize_annotations(state.get("annotations", []))
        if not annotations:
            st.info("示例：2018 年 结婚；2022 年 裁员。描述只写事件本身，情绪另选即可。")

        min_year = int(life["year"].min())
        max_year = int(life["year"].max())
        with st.form("annotation_form"):
            ann_year = st.number_input("标记年份", min_value=min_year, max_value=max_year, value=min_year, step=1)
            ann_label = st.text_input("事件描述", "结婚")
            ann_outcome = st.selectbox("情绪倾向", ["正向 / 大喜", "负向 / 大悲"])
            ann_intensity = st.slider("影响强度", 0.5, 2.0, 1.0, 0.1)
            ann_note = st.text_area(
                "补充笔记（可选）",
                value="",
                placeholder="记录当时的想法、收获或复盘要点，帮助未来回看。",
            )
            submitted = st.form_submit_button("添加标记")

        if submitted:
            auto_note = ann_note.strip()
            if not auto_note:
                auto_note = f"{ann_year} 年，{ann_label}（{ann_outcome}），影响系数 {ann_intensity:.1f}x"
            annotations.append(
                Annotation(
                    year=int(ann_year),
                    label=ann_label,
                    outcome=ann_outcome,
                    note=auto_note,
                    intensity=float(ann_intensity),
                )
            )
            state["annotations"] = serialize_annotations(annotations)
            st.success("已记录标记，可继续添加或点击下方按钮进行回测。")

        if annotations:
            ann_df = pd.DataFrame(
                [
                    {
                        "年份": ann.year,
                        "事件": ann.label,
                        "倾向": ann.outcome,
                        "笔记": ann.note,
                        "强度": ann.intensity,
                    }
                    for ann in annotations
                ]
            )
            st.dataframe(ann_df, use_container_width=True, hide_index=True)
            if st.button("清空标记", type="secondary"):
                state["annotations"] = []
                state["backtest_result"] = None
                annotations = []

        params = result.get("params", {})
        config = BacktestConfig(
            base_up=float(params.get("up", 1.0)),
            base_down=float(params.get("down", 1.0)),
            cycle=int(params.get("cycle", 6)),
            keyword_boost=float(params.get("keyword_boost", 1.0)),
            keyword_risk=float(params.get("keyword_risk", 0.6)),
            dayun_drag=float(params.get("dayun_drag", 0.6)),
            strength_index=float(params.get("strength_index", 0.5)),
            special_pattern=params.get("special_pattern"),
            relation_trigger=float(params.get("relation_trigger", 0.8)),
            ten_god_weight=float(params.get("ten_god_weight", 10.0)),
            base=float(params.get("base", 100.0)),
        )

        if annotations and st.button("根据标记回测并拟合权重", type="primary"):
            feedback = apply_feedback_loop(
                df_liunian,
                df_dayun,
                annotations,
                config=config,
                learning_rate=0.05,
            )
            state["backtest_result"] = feedback

        backtest_result = state.get("backtest_result")
        if backtest_result:
            tuned_life = backtest_result.tuned_life
            tuned_life = tuned_life.sort_values("year").reset_index(drop=True)
            tuned_life["ma_short"] = tuned_life["life_index"].rolling(window=ma_short, min_periods=1).mean()
            tuned_life["ma_long"] = tuned_life["life_index"].rolling(window=ma_long, min_periods=1).mean()

            st.markdown("#### 拟合后的 LifeIndex 轨迹")
            fig_bt = go.Figure()
            fig_bt.add_trace(
                go.Scatter(
                    x=tuned_life["year"],
                    y=tuned_life["life_index"],
                    mode="lines+markers",
                    name="回测结果",
                    line=dict(color="#8b4513", width=3),
                    marker=dict(size=8, color="#f2c94c"),
                )
            )
            for ann in annotations:
                fig_bt.add_vline(x=int(ann.year), line_dash="dot", line_color="#e27d60", opacity=0.3)
            fig_bt.update_layout(
                height=320,
                xaxis_title="年份",
                yaxis_title="LifeIndex",
                template="simple_white",
                margin=dict(l=40, r=20, t=10, b=30),
            )
            st.plotly_chart(fig_bt, use_container_width=True)

            st.markdown("#### 原盘 vs 回测逐年对比（含均线与差值）")
            base_life = life.sort_values("year")[["year", "life_index", "ma_short", "ma_long"]]
            compare_df = base_life.merge(
                tuned_life[["year", "life_index", "ma_short", "ma_long"]],
                on="year",
                suffixes=("_base", "_tuned"),
            )
            compare_df["delta"] = compare_df["life_index_tuned"] - compare_df["life_index_base"]

            fig_cmp = make_subplots(specs=[[{"secondary_y": True}]])
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["life_index_base"],
                    mode="lines",
                    name="原盘 LifeIndex",
                    line=dict(color="#5b8a72", width=3),
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["ma_short_base"],
                    mode="lines",
                    name=f"原盘 MA{ma_short}",
                    line=dict(color="#8acbb5", dash="dot"),
                    opacity=0.65,
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["ma_long_base"],
                    mode="lines",
                    name=f"原盘 MA{ma_long}",
                    line=dict(color="#9aa7e0", dash="dash"),
                    opacity=0.6,
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["life_index_tuned"],
                    mode="lines+markers",
                    name="回测 LifeIndex",
                    line=dict(color="#8b4513", width=3),
                    marker=dict(size=7, color="#f2c94c"),
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["ma_short_tuned"],
                    mode="lines",
                    name=f"回测 MA{ma_short}",
                    line=dict(color="#d8a24a", dash="dot"),
                    opacity=0.6,
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Scatter(
                    x=compare_df["year"],
                    y=compare_df["ma_long_tuned"],
                    mode="lines",
                    name=f"回测 MA{ma_long}",
                    line=dict(color="#c17b63", dash="dash"),
                    opacity=0.55,
                ),
                secondary_y=False,
            )
            fig_cmp.add_trace(
                go.Bar(
                    x=compare_df["year"],
                    y=compare_df["delta"],
                    name="差值 (回测-原盘)",
                    marker_color="#6c5b7b",
                    opacity=0.35,
                ),
                secondary_y=True,
            )
            for ann in annotations:
                fig_cmp.add_vline(x=int(ann.year), line_dash="dot", line_color="#e27d60", opacity=0.25)

            fig_cmp.update_layout(
                height=420,
                xaxis_title="年份",
                yaxis_title="LifeIndex",
                hovermode="x unified",
                template="simple_white",
                margin=dict(l=40, r=20, t=30, b=30),
            )
            fig_cmp.update_yaxes(title_text="差值", secondary_y=True, showgrid=False)
            st.plotly_chart(fig_cmp, use_container_width=True)

            st.markdown("#### 权重微调摘要")
            adjust_df = pd.DataFrame(
                backtest_result.adjustments, columns=["十神", "Δ权重"]
            )
            if adjust_df.empty:
                st.info("当前标记未匹配到流年十神，暂无需要调整的权重。")
            else:
                st.dataframe(adjust_df, use_container_width=True, hide_index=True)

            weights_df = pd.DataFrame(
                [
                    {
                        "十神": k,
                        "身强权重": backtest_result.strong_weights.get(k, 0.0),
                        "身弱权重": backtest_result.weak_weights.get(k, 0.0),
                    }
                    for k in sorted(backtest_result.strong_weights.keys())
                ]
            )
            st.dataframe(weights_df, use_container_width=True, hide_index=True)
