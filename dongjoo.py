import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from datetime import datetime

# 0. yfinance 캐시용 헬퍼 함수들 --------------------
@st.cache_data(ttl=3600)
def get_exchange_rates_cached():
    try:
        usd_cad = yf.Ticker("USDCAD=X")
        usd_krw = yf.Ticker("USDKRW=X")
        c_rate = usd_cad.info.get("regularMarketPrice", 1.42)
        k_rate = usd_krw.info.get("regularMarketPrice", 1410.0)
        return {"USD": 1.0, "CAD": c_rate, "KRW": k_rate}
    except Exception:
        return {"USD": 1.0, "CAD": 1.42, "KRW": 1410.0}

@st.cache_data(ttl=3600)
def load_stock_all(ticker: str):
    """티커 정보 + 전체/5년 히스토리 캐시"""
    stock = yf.Ticker(ticker)
    info = stock.info
    hist_full = stock.history(period="max")
    hist_5y = stock.history(period="5y")
    return info, hist_full, hist_5y

# 레버리지 감지 + 경고 --------------------
def detect_leveraged_from_info(info: dict) -> bool:
    name = (info.get("shortName") or "").upper()
    longname = (info.get("longName") or "").upper()
    desc = (info.get("longBusinessSummary") or "").upper()
    text = name + " " + longname + " " + desc

    lev_keywords_en = ["2X", "3X", "ULTRA", "LEVERAGED", "LEVERAGE", "INVERSE", "BULL", "BEAR"]
    lev_keywords_ko = ["레버리지", "레버리지형", "곱버스", "인버스"]
    return any(k in text for k in lev_keywords_en + lev_keywords_ko)

def leveraged_warning_text(lang: str = "KO") -> str:
    if lang == "KO":
        return (
            "⚠️ 레버리지 / 인버스 상품 경고\n"
            "- 이 상품은 지수를 여러 배로 추종하거나 반대로 추종하는 **고위험 파생상품 ETF**입니다.\n"
            "- **일일 수익률 기준으로 레버리지를 재조정**하기 때문에, 변동성이 클수록 "
            "지수가 장기적으로 올라도 **원금이 빠르게 녹을 수 있습니다.**[web:392][web:402]\n"
            "- 일반적으로 이러한 상품은 **단기 트레이딩 용도**이며, "
            "**장기 투자·초보 투자자에게는 적합하지 않을 수 있습니다.**[web:389][web:396]\n"
            "- 이 앱의 시뮬레이션에서도 레버리지 상품은 **최악의 경우 원금 대폭 손실**이 자주 나타날 수 있습니다. "
            "실제 투자 전, 반드시 상품설명서와 위험고지를 확인하세요.[web:393][web:399]\n"
        )
    else:
        return (
            "⚠️ Warning: Leveraged / Inverse ETF\n"
            "- This product is a **high‑risk ETF** using leverage or inverse exposure to amplify index moves.\n"
            "- Because leverage is **reset daily**, volatility can cause your capital to **erode over time**, "
            "even if the underlying index rises in the long run.[web:389][web:402]\n"
            "- These products are generally **short‑term trading tools** and may **not be suitable for long‑term, "
            "buy‑and‑hold retail investors**.[web:396][web:403]\n"
            "- In this app’s simulations, leveraged products may show **severe loss of principal** in many paths. "
            "Always read the ETF prospectus and risk disclosures before investing.[web:393][web:399]\n"
        )

# 1. UI 및 다크 테마 설정 ---------------------------------
st.set_page_config(page_title="Wealthy Dongjoo", layout="centered")
st.markdown(
    """
    <style>
    .main { background-color: #0d1117; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    h1 { color: #58a6ff; font-style: italic; font-weight: 900 !important; }
    h2, h3 { color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-top: 35px; }
    .info-box { background-color: #161b22; padding: 15px; border-radius: 10px; border-left: 4px solid #58a6ff; margin: 10px 0; }
    </style>
""",
    unsafe_allow_html=True,
)

# 2. 세션 상태 관리 ---------------------------------
if "menu" not in st.session_state:
    st.session_state.menu = "Dashboard"
if "user_lang" not in st.session_state:
    st.session_state.user_lang = "KO"
if "user_currency" not in st.session_state:
    st.session_state.user_currency = "USD"

# 언어 팩 ---------------------------------
L = {
    "KO": {
        "dash": "📊 대시보드",
        "set": "⚙️ 설정",
        "input_ticker": "분석할 주식 입력",
        "ticker_help": """
**검색 방법 예시:**
- 🇺🇸 미국: AAPL, TSLA, MSFT
- 🇰🇷 한국: 005930.KS (삼성전자), 035720.KS (카카오)
- 🇨🇦 캐나다: SHOP.TO, TD.TO
- 💼 ETF: SPY, QQQ, VFV.TO
        
**주의:** 주식 이름이 아닌 **티커 심볼**로 입력하세요!
        """,
        "company_info": "기업 정보",
        "tm_title": "🕰️ What IF",
        "tm_start": "투자 시작 연도",
        "sim_title": "📊 자산성장 예측표",
        "init_cash": "초기 원금",
        "monthly_cash": "월 적립액",
        "inv_years": "투자 기간 (년)",
        "real": "현실적",
        "bull": "낙관적",
        "bear": "비관적",
        "principal": "누적 원금",
        "cur_p": "Current Price",
        "list_p": "상장가",
        "per": "P/E Ratio",
        "per_info": "주가수익비율 - 낮을수록 저평가 (일반적으로 15-25가 적정)",
        "roe": "ROE",
        "roe_info": "자기자본이익률 - 높을수록 좋음 (15% 이상 우수)",
        "pbr": "P/B Ratio",
        "pbr_info": "주가순자산비율 - 낮을수록 저평가 (1 이하면 저평가)",
        "vol": "Volatility",
        "vol_info": "연간 변동성 - 낮을수록 안정적 (20% 이하 안정적)",
        "high_low": "52W High/Low",
        "high_low_info": "52주 최고가/최저가 대비 현재 위치",
        "final_asset": "최종 자산",
        "profit": "순수익",
        "eval_title": "🔍 종합 가치 평가",
        "eval_help": "현재 주가가 Graham/DCF 적정가 대비 얼마나 비싼지/싼지 통합해서 보여주는 섹션입니다.",
        "status": "현재 상태",
        "undervalued": "💎 저평가 (매수 매력 높음)",
        "fair": "⚖️ 적정 가치",
        "overvalued": "⚠️ 고평가 주의",
        "gap_label": "적정가 대비 괴리율",
        "graham_label": "Graham 적정가",
        "graham_help": "Graham 적정가는 벤저민 그레이엄의 공식으로 계산한 주당 이론적 가치(보수적인 성장 가정 기준)입니다.",
        "dcf_label": "DCF 적정가",
        "dcf_help": "DCF 적정가는 미래 현금흐름을 할인해 계산한 주당 이론적 가치(현금창출력 중심)입니다.",
        "avg_label": "평균 적정가",
        "growth_used": "적용 성장률",
        "etf_warning": "ℹ️ ETF는 여러 종목 묶음 상품이라 Graham / DCF 같은 개별 주식 적정가 모델을 그대로 적용하기 어렵습니다. 지수 추종, 보수, 배당수익률 등을 중심으로 봐 주세요.",
        "whatif_help": "What IF는 과거 특정 연도부터 매달 투자했다고 가정했을 때 지금까지 수익률이 얼마나 되었는지 계산해 줍니다.",
        "disclaimer": """
⚠️ **투자 책임 고지**

본 앱은 기업 분석 및 통계적 수학 계산을 보조하는 도구입니다. 
실제 투자 가이드가 아니며, 투자로 인한 손실에 대해 책임지지 않습니다.
모든 투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다.
        """,
    },
    "EN": {
        "dash": "📊 Dashboard",
        "set": "⚙️ Settings",
        "input_ticker": "Enter Stock Symbol",
        "ticker_help": """
**Search Examples:**
- 🇺🇸 US: AAPL, TSLA, MSFT
- 🇰🇷 Korea: 005930.KS (Samsung), 035720.KS (Kakao)
- 🇨🇦 Canada: SHOP.TO, TD.TO
- 💼 ETF: SPY, QQQ, VFV.TO
        
**Note:** Use **ticker symbol**, not company name!
        """,
        "company_info": "Company Info",
        "tm_title": "🕰️ What IF",
        "tm_start": "Start Year",
        "sim_title": "📊 Asset Growth Projection",
        "init_cash": "Initial Principal",
        "monthly_cash": "Monthly Deposit",
        "inv_years": "Period (Yrs)",
        "real": "Realistic",
        "bull": "Bullish",
        "bear": "Bearish",
        "principal": "Total Principal",
        "cur_p": "Current Price",
        "list_p": "Listing Price",
        "per": "P/E Ratio",
        "per_info": "Price-to-Earnings - Lower is better (15-25 is typical)",
        "roe": "ROE",
        "roe_info": "Return on Equity - Higher is better (15%+ is excellent)",
        "pbr": "P/B Ratio",
        "pbr_info": "Price-to-Book - Lower is better (below 1 is undervalued)",
        "vol": "Volatility",
        "vol_info": "Annual Volatility - Lower is more stable (below 20% is stable)",
        "high_low": "52W High/Low",
        "high_low_info": "Current position vs 52-week high/low",
        "final_asset": "Final Asset",
        "profit": "Net Profit",
        "eval_title": "🔍 Value Assessment",
        "eval_help": "This section shows whether the stock looks cheap or expensive versus Graham/DCF fair values.",
        "status": "Status",
        "undervalued": "💎 Undervalued",
        "fair": "⚖️ Fair Value",
        "overvalued": "⚠️ Overvalued",
        "gap_label": "Gap from Intrinsic",
        "graham_label": "Graham Value",
        "graham_help": "Graham Value is a conservative fair value estimate using Benjamin Graham's intrinsic value formula.",
        "dcf_label": "DCF Value",
        "dcf_help": "DCF Value is a fair value estimate based on discounted future cash flows per share.",
        "avg_label": "Average Value",
        "growth_used": "Growth Rate Used",
        "etf_warning": "ℹ️ This is an ETF (a basket of many stocks), so Graham / DCF single-stock fair value models are not directly applicable. Evaluate it by index, fees, and yield.",
        "whatif_help": "What IF shows the return if you had started investing from that year with monthly contributions.",
        "disclaimer": """
⚠️ **Investment Disclaimer**

This app is a calculation tool for company analysis and statistical modeling.
It is NOT actual investment advice. We are not responsible for investment losses.
All investment decisions must be made at your own judgment and risk.
        """,
    },
}[st.session_state.user_lang]

# 3. 환율 정보 (캐시 사용) ---------------------------
def get_exchange_rates():
    return get_exchange_rates_cached()

rates = get_exchange_rates()
curr_symbol = {"USD": "$", "CAD": "C$", "KRW": "₩"}[st.session_state.user_currency]

# 4. 기업 정보 추출 ---------------------------
def get_company_sector(info):
    sector = info.get("sector", "")
    industry = info.get("industry", "")

    sector_map = {
        "Technology": "기술",
        "Healthcare": "헬스케어",
        "Financial Services": "금융",
        "Consumer Cyclical": "경기소비재",
        "Industrials": "산업재",
        "Communication Services": "통신서비스",
        "Consumer Defensive": "필수소비재",
        "Energy": "에너지",
        "Basic Materials": "소재",
        "Real Estate": "부동산",
        "Utilities": "유틸리티",
    }

    if st.session_state.user_lang == "KO":
        sector = sector_map.get(sector, sector)

    if sector and industry:
        return f"{sector} - {industry}"
    if sector:
        return sector
    if industry:
        return industry
    return "N/A"

# 5. 성장률 계산 ---------------------------
def get_smart_growth_rate(info, hist_data):
    growth_rates = []

    earnings_growth = info.get("earningsGrowth")
    revenue_growth = info.get("revenueGrowth")
    earnings_quarterly_growth = info.get("earningsQuarterlyGrowth")

    if earnings_growth and abs(earnings_growth) < 1:
        growth_rates.append(earnings_growth * 100)
    if revenue_growth and abs(revenue_growth) < 1:
        growth_rates.append(revenue_growth * 100)
    if earnings_quarterly_growth and abs(earnings_quarterly_growth) < 1:
        growth_rates.append(earnings_quarterly_growth * 100)

    if len(hist_data) > 252 * 2:
        try:
            years = min(5, len(hist_data) / 252)
            start_price = hist_data["Close"].iloc[0]
            end_price = hist_data["Close"].iloc[-1]
            historical_cagr = ((end_price / start_price) ** (1 / years) - 1) * 100
            if 0 < historical_cagr < 50:
                growth_rates.append(historical_cagr)
        except Exception:
            pass

    if growth_rates:
        growth_rates = [g for g in growth_rates if -20 < g < 40]
        if growth_rates:
            avg_growth = np.mean(growth_rates)
            if avg_growth > 20:
                return 12
            if avg_growth > 15:
                return avg_growth * 0.7
            if avg_growth < 0:
                return 5
            return avg_growth

    return 8

# 6. Graham's Formula ---------------------------
def calculate_graham_value(eps, growth_rate, stock_currency, user_currency):
    try:
        if eps is None or eps <= 0:
            return None
        g = max(5, min(growth_rate, 20))
        intrinsic_value = eps * (8.5 + 2 * g)
        converted_value = (
            intrinsic_value / rates.get(stock_currency, 1.0)
        ) * rates[user_currency]
        return converted_value
    except Exception:
        return None

# 7. DCF 계산 ---------------------------
def calculate_dcf_value(info, growth_rate, stock_currency, user_currency):
    try:
        operating_cf = info.get("operatingCashflow")
        shares_outstanding = info.get("sharesOutstanding")

        if not operating_cf or not shares_outstanding or operating_cf <= 0:
            return None

        fcf_per_share = operating_cf / shares_outstanding
        g = max(0, min(growth_rate / 100, 0.20))
        discount_rate = 0.12
        terminal_growth = 0.04

        pv_sum = 0
        for year in range(1, 11):
            fcf_future = fcf_per_share * ((1 + g) ** year)
            pv = fcf_future / ((1 + discount_rate) ** year)
            pv_sum += pv

        terminal_fcf = fcf_per_share * ((1 + g) ** 10) * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        pv_terminal = terminal_value / ((1 + discount_rate) ** 10)

        intrinsic_value = pv_sum + pv_terminal
        converted_value = (
            intrinsic_value / rates.get(stock_currency, 1.0)
        ) * rates[user_currency]
        return converted_value
    except Exception:
        return None

# 사이드바 ---------------------------
st.sidebar.title("Wealthy Dongjoo")
if st.sidebar.button(L["dash"]):
    st.session_state.menu = "Dashboard"
if st.sidebar.button(L["set"]):
    st.session_state.menu = "Settings"

# 화면 전환 ---------------------------
if st.session_state.menu == "Settings":
    st.title(L["set"])
    st.session_state.user_lang = st.radio(
        "Language",
        ["KO", "EN"],
        index=0 if st.session_state.user_lang == "KO" else 1,
    )
    st.session_state.user_currency = st.selectbox(
        "Currency",
        ["USD", "CAD", "KRW"],
        index=["USD", "CAD", "KRW"].index(st.session_state.user_currency),
    )

else:
    ticker = st.text_input(L["input_ticker"], "", help=L["ticker_help"]).upper()

    if ticker:
        try:
            # 캐시된 yfinance 호출 사용
            info, hist_full, hist_5y = load_stock_all(ticker)

            stock_currency = info.get("currency", "USD")
            is_etf = info.get("quoteType") == "ETF"

            company_name = info.get("longName") or info.get("shortName") or ticker
            sector_info = get_company_sector(info)

            st.markdown(f"### {company_name}")
            st.caption(f"**{L['company_info']}:** {sector_info}")

            # 레버리지 감지 시 빨간 경고
            if detect_leveraged_from_info(info):
                st.markdown(
                    f"<p style='color:#ff4b4b; font-size:0.9rem; white-space:pre-line;'>{leveraged_warning_text(st.session_state.user_lang)}</p>",
                    unsafe_allow_html=True,
                )

            # 5년 차트
            if len(hist_5y) > 0:
                adj_5y = (
                    hist_5y["Close"] / rates.get(stock_currency, 1.0)
                ) * rates[st.session_state.user_currency]
                fig_market = go.Figure(
                    go.Scatter(
                        x=hist_5y.index,
                        y=adj_5y,
                        name="Price",
                        line=dict(color="#58a6ff", width=2),
                        hovertemplate="%{x|%Y-%m-%d}<br>Price: "
                        + curr_symbol
                        + "%{y:,.2f}<extra></extra>",
                    )
                )
                fig_market.update_layout(
                    template="plotly_dark",
                    height=280,
                    margin=dict(l=10, r=10, t=10, b=10),
                    hovermode="x unified",
                    xaxis=dict(fixedrange=True),
                    yaxis=dict(fixedrange=True),
                )
                st.plotly_chart(
                    fig_market,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )

            raw_p = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or (hist_5y["Close"].iloc[-1] if len(hist_5y) > 0 else None)
            )
            if raw_p is None:
                raise ValueError("현재가 데이터를 가져올 수 없음")

            display_price = (
                raw_p / rates.get(stock_currency, 1.0)
            ) * rates[st.session_state.user_currency]

            st.subheader(f"📍 {ticker} Analysis")

            # 핵심 지표
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(L["cur_p"], f"{curr_symbol}{display_price:,.2f}")
            with c2:
                per_val = info.get("forwardPE") or info.get("trailingPE")
                if per_val:
                    st.metric(L["per"], f"{per_val:.2f}", help=L["per_info"])
                else:
                    st.metric(L["per"], "N/A", help=L["per_info"])
            with c3:
                roe_val = info.get("returnOnEquity")
                if roe_val:
                    st.metric(
                        L["roe"], f"{roe_val*100:.1f}%", help=L["roe_info"]
                    )
                else:
                    st.metric(L["roe"], "N/A", help=L["roe_info"])
            with c4:
                pbr_val = info.get("priceToBook")
                if pbr_val:
                    st.metric(L["pbr"], f"{pbr_val:.2f}", help=L["pbr_info"])
                else:
                    st.metric(L["pbr"], "N/A", help=L["pbr_info"])

            # 변동성 / 52주
            c5, c6 = st.columns(2)
            with c5:
                if len(hist_5y) > 1:
                    vol_val = (
                        hist_5y["Close"].pct_change().std() * np.sqrt(252)
                    )
                    st.metric(
                        L["vol"], f"{vol_val*100:.1f}%", help=L["vol_info"]
                    )
                else:
                    vol_val = 0.2
                    st.metric(L["vol"], "N/A", help=L["vol_info"])
            with c6:
                high_52 = info.get("fiftyTwoWeekHigh")
                low_52 = info.get("fiftyTwoWeekLow")
                if high_52 and low_52:
                    high_conv = (
                        high_52
                        / rates.get(stock_currency, 1.0)
                        * rates[st.session_state.user_currency]
                    )
                    low_conv = (
                        low_52
                        / rates.get(stock_currency, 1.0)
                        * rates[st.session_state.user_currency]
                    )
                    pct_from_high = (
                        (display_price - high_conv) / high_conv * 100
                    )
                    st.metric(
                        L["high_low"],
                        f"{curr_symbol}{high_conv:,.0f} / {curr_symbol}{low_conv:,.0f}",
                        f"{pct_from_high:+.1f}% from high",
                        help=L["high_low_info"],
                    )
                else:
                    st.metric(L["high_low"], "N/A", help=L["high_low_info"])

            if len(hist_full) > 0:
                list_price_display = (
                    hist_full["Close"].iloc[0]
                    / rates.get(stock_currency, 1.0)
                    * rates[st.session_state.user_currency]
                )
                st.caption(
                    f"Listing: {hist_full.index[0].year} | {L['list_p']}: {curr_symbol}{list_price_display:,.2f}"
                )

            # 적정가 평가 + 제목 설명 버튼
            st.divider()
            col_eval_title, col_eval_help = st.columns([4, 1])
            with col_eval_title:
                st.subheader(L["eval_title"])
            with col_eval_help:
                if st.button("ⓘ", key="eval_help_btn"):
                    st.caption(L["eval_help"])

            if is_etf:
                st.info(L["etf_warning"])
            else:
                smart_growth = get_smart_growth_rate(info, hist_5y)
                eps = info.get("forwardEps") or info.get("trailingEps")
                per_check = (
                    info.get("forwardPE") or info.get("trailingPE") or 0
                )
                is_growth_stock = per_check > 50

                if eps is None or eps <= 0:
                    st.warning(
                        "⚠️ EPS가 0 이하이거나 없는 기업입니다. 전통적 밸류에이션 모델의 신뢰도가 낮습니다."
                        if st.session_state.user_lang == "KO"
                        else "⚠️ EPS is non‑positive or missing. Traditional valuation models are less reliable."
                    )
                else:
                    if is_growth_stock:
                        st.warning(
                            "⚠️ PER>50 성장주라 Graham/DCF 정확도가 낮을 수 있습니다."
                            if st.session_state.user_lang == "KO"
                            else "⚠️ High‑growth stock (PER>50). Graham/DCF models may be less accurate."
                        )

                    graham_value = calculate_graham_value(
                        eps,
                        smart_growth,
                        stock_currency,
                        st.session_state.user_currency,
                    )
                    dcf_value = calculate_dcf_value(
                        info,
                        smart_growth,
                        stock_currency,
                        st.session_state.user_currency,
                    )

                    valid_values = [
                        v
                        for v in [graham_value, dcf_value]
                        if v is not None and v > 0
                    ]

                    if valid_values:
                        avg_intrinsic = float(np.mean(valid_values))
                        gap_pct = (
                            (display_price - avg_intrinsic)
                            / avg_intrinsic
                            * 100
                        )

                        if gap_pct < -15:
                            status = L["undervalued"]
                            status_color = "#10b981"
                        elif gap_pct > 15:
                            status = L["overvalued"]
                            status_color = "#ef4444"
                        else:
                            status = L["fair"]
                            status_color = "#fbbf24"

                        st.info(
                            f"📊 {L['growth_used']}: {smart_growth:.1f}%"
                        )

                        vc1, vc2, vc3 = st.columns(3)

                        with vc1:
                            if graham_value:
                                st.metric(
                                    L["graham_label"],
                                    f"{curr_symbol}{graham_value:,.2f}",
                                )
                            else:
                                st.metric(L["graham_label"], "N/A")
                            if st.button("?", key="graham_help_btn"):
                                st.caption(L["graham_help"])

                        with vc2:
                            if dcf_value:
                                st.metric(
                                    L["dcf_label"],
                                    f"{curr_symbol}{dcf_value:,.2f}",
                                )
                            else:
                                st.metric(L["dcf_label"], "N/A")
                            if st.button("?", key="dcf_help_btn"):
                                st.caption(L["dcf_help"])

                        with vc3:
                            st.metric(
                                L["avg_label"],
                                f"{curr_symbol}{avg_intrinsic:,.2f}",
                            )

                        st.markdown(
                            f"### {L['status']}: <span style='color:{status_color};font-weight:bold;'>{status}</span>",
                            unsafe_allow_html=True,
                        )
                        st.metric(L["gap_label"], f"{gap_pct:+.1f}%")

                        fig_val = go.Figure()
                        fig_val.add_trace(
                            go.Bar(
                                x=[L["cur_p"], L["avg_label"]],
                                y=[display_price, avg_intrinsic],
                                marker_color=["#58a6ff", status_color],
                                text=[
                                    f"{curr_symbol}{display_price:,.2f}",
                                    f"{curr_symbol}{avg_intrinsic:,.2f}",
                                ],
                                textposition="auto",
                            )
                        )
                        fig_val.update_layout(
                            template="plotly_dark",
                            height=300,
                            showlegend=False,
                            yaxis_title=st.session_state.user_currency,
                            xaxis=dict(fixedrange=True),
                            yaxis=dict(fixedrange=True),
                        )
                        st.plotly_chart(
                            fig_val,
                            use_container_width=True,
                            config={"displayModeBar": False},
                        )

            # What IF + 설명 버튼
            st.divider()
            col_tm_title, col_tm_help = st.columns([4, 1])
            with col_tm_title:
                st.subheader(L["tm_title"])
            with col_tm_help:
                if st.button("ⓘ", key="whatif_help_btn"):
                    st.caption(L["whatif_help"])

            if len(hist_full) > 0:
                list_yr = hist_full.index[0].year
                available_yrs = list(range(list_yr, datetime.now().year))

                if available_yrs:
                    default_yr = (
                        max(list_yr, 2000)
                        if max(list_yr, 2000) in available_yrs
                        else available_yrs[0]
                    )
                    selected_yr = st.selectbox(
                        L["tm_start"],
                        available_yrs[::-1],
                        index=available_yrs[::-1].index(default_yr),
                    )

                    wi_init = st.number_input(
                        L["init_cash"], value=1000, key="wi_in"
                    )
                    wi_month = st.number_input(
                        L["monthly_cash"], value=200, key="wi_mon"
                    )

                    p_data = hist_full.loc[f"{selected_yr}-01-01":]["Close"]

                    if len(p_data) > 0:
                        p_data_m = p_data.resample("ME").last()
                        init_u = wi_init / rates[st.session_state.user_currency]
                        month_u = wi_month / rates[
                            st.session_state.user_currency
                        ]
                        shares = init_u / (
                            p_data.iloc[0]
                            / rates.get(stock_currency, 1.0)
                        )

                        for p in p_data_m:
                            shares += month_u / (
                                p / rates.get(stock_currency, 1.0)
                            )

                        final_v_past = (
                            shares
                            * (
                                p_data.iloc[-1]
                                / rates.get(stock_currency, 1.0)
                            )
                            * rates[st.session_state.user_currency]
                        )
                        total_i_past = wi_init + wi_month * len(p_data_m)

                        wc1, wc2 = st.columns(2)
                        wc1.metric(
                            f"Past {L['final_asset']}",
                            f"{curr_symbol}{final_v_past:,.0f}",
                        )
                        wc2.metric(
                            f"Past {L['profit']}",
                            f"{curr_symbol}{final_v_past - total_i_past:,.0f}",
                            f"{((final_v_past-total_i_past)/total_i_past)*100:.1f}%",
                        )

            # 자산성장 예측표
            st.divider()
            st.subheader(L["sim_title"])

            inv_y = st.slider(L["inv_years"], 1, 30, 10)

            wi_init_sim = st.number_input(
                L["init_cash"], value=1000, key="sim_in"
            )
            wi_month_sim = st.number_input(
                L["monthly_cash"], value=200, key="sim_mon"
            )

            if len(hist_full) > 1:
                days = max(
                    1, (hist_full.index[-1] - hist_full.index[0]).days / 365.25
                )
                calc_cagr = (
                    hist_full["Close"].iloc[-1]
                    / hist_full["Close"].iloc[0]
                ) ** (1 / days) - 1
            else:
                calc_cagr = 0.08

            years_arr = np.arange(inv_y + 1)

            def run_sim(r, v, init, monthly):
                dt = 1 / 12
                path_yr = [init]
                curr = init / rates[st.session_state.user_currency]
                m_u = monthly / rates[st.session_state.user_currency]
                for _ in range(inv_y):
                    for _ in range(12):
                        growth = (
                            (r - 0.5 * v ** 2) * dt
                            + v * np.sqrt(dt) * np.random.normal()
                        )
                        curr = (curr + m_u) * np.exp(growth)
                    path_yr.append(
                        max(0, curr * rates[st.session_state.user_currency])
                    )
                return path_yr

            p_real = run_sim(calc_cagr, vol_val * 0.7, wi_init_sim, wi_month_sim)
            p_bull = run_sim(
                calc_cagr * 1.3, vol_val * 0.5, wi_init_sim, wi_month_sim
            )
            p_bear = run_sim(
                calc_cagr * 0.6, vol_val * 1.2, wi_init_sim, wi_month_sim
            )
            principal_path = [
                wi_init_sim + wi_month_sim * 12 * y for y in years_arr
            ]

            fig_f = go.Figure()
            fig_f.add_trace(
                go.Scatter(
                    x=years_arr,
                    y=p_real,
                    name=f"{L['real']} ({curr_symbol}{p_real[-1]:,.0f})",
                    line=dict(color="#10b981", width=4),
                    hovertemplate="Year %{x}<br>Value: "
                    + curr_symbol
                    + "%{y:,.0f}<extra></extra>",
                )
            )
            fig_f.add_trace(
                go.Scatter(
                    x=years_arr,
                    y=p_bull,
                    name=f"{L['bull']} ({curr_symbol}{p_bull[-1]:,.0f})",
                    line=dict(dash="dash", color="#3b82f6"),
                    hovertemplate="Year %{x}<br>Value: "
                    + curr_symbol
                    + "%{y:,.0f}<extra></extra>",
                )
            )
            fig_f.add_trace(
                go.Scatter(
                    x=years_arr,
                    y=p_bear,
                    name=f"{L['bear']} ({curr_symbol}{p_bear[-1]:,.0f})",
                    line=dict(dash="dot", color="#ef4444"),
                    hovertemplate="Year %{x}<br>Value: "
                    + curr_symbol
                    + "%{y:,.0f}<extra></extra>",
                )
            )
            fig_f.add_trace(
                go.Scatter(
                    x=years_arr,
                    y=principal_path,
                    name=f"{L['principal']} ({curr_symbol}{principal_path[-1]:,.0f})",
                    line=dict(color="#ffffff", dash="dot"),
                    hovertemplate="Year %{x}<br>Principal: "
                    + curr_symbol
                    + "%{y:,.0f}<extra></extra>",
                )
            )
            fig_f.update_layout(
                template="plotly_dark",
                height=400,
                hovermode="x unified",
                xaxis=dict(fixedrange=True),
                yaxis=dict(fixedrange=True),
            )
            st.plotly_chart(
                fig_f, use_container_width=True, config={"displayModeBar": False}
            )

            rc1, rc2, rc3 = st.columns(3)
            rc1.metric(
                f"{L['real']} {L['final_asset']}",
                f"{curr_symbol}{p_real[-1]:,.0f}",
            )
            rc2.metric(
                f"{L['bull']} {L['final_asset']}",
                f"{curr_symbol}{p_bull[-1]:,.0f}",
            )
            rc3.metric(
                L["principal"],
                f"{curr_symbol}{principal_path[-1]:,.0f}",
            )

            # 맨 아래 경고문 (노란색 글씨)
            st.divider()
            st.markdown(
                f"<span style='color: #facc15;'>{L['disclaimer']}</span>",
                unsafe_allow_html=True,
            )

        except Exception as e:
            msg = str(e)
            # yfinance 레이트 리밋일 때 메시지 구분
            if "Too Many Requests" in msg or "Rate limited" in msg:
                if st.session_state.user_lang == "KO":
                    st.error("⚠️ 데이터 오류: 야후 Finance 요청 한도가 초과되었습니다. 잠시 후 다시 시도해 주세요.")
                else:
                    st.error("⚠️ Data error: Yahoo Finance rate limit exceeded. Please try again later.")
            else:
                st.error(f"⚠️ 데이터 오류: {e}")
