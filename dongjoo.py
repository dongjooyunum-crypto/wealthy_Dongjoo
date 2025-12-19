import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai
import numpy as np
from datetime import datetime

# 1. UI 및 다크 테마 설정
st.set_page_config(page_title="Wealthy Dongjoo", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0d1117; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    h1 { color: #58a6ff; font-style: italic; font-weight: 900 !important; }
    h2, h3 { color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-top: 35px; }
    </style>
""", unsafe_allow_html=True)

# 2. 세션 상태 관리
if 'menu' not in st.session_state: st.session_state.menu = "Dashboard"
if 'user_lang' not in st.session_state: st.session_state.user_lang = "KO"
if 'user_currency' not in st.session_state: st.session_state.user_currency = "USD"

# --- [언어 팩] ---
L = {
    "KO": {
        "dash": "📊 대시보드", "set": "⚙️ 설정", "lang_sel": "언어 선택", "curr_sel": "통화 선택",
        "input_ticker": "분석할 티커 입력", "tm_title": "🕰️ What IF", "tm_start": "투자 시작 연도",
        "sim_title": "📊 자산성장 예측표", "init_cash": "초기 원금", "monthly_cash": "월 적립액",
        "inv_years": "투자 기간 (년)", "real": "현실적", "bull": "낙관적", "bear": "비관적", "principal": "누적 원금",
        "cur_p": "현재 주가", "list_p": "상장가", "per": "PER", "roe": "ROE", "vol": "변동성",
        "final_asset": "최종 자산", "profit": "순수익"
    },
    "EN": {
        "dash": "📊 Dashboard", "set": "⚙️ Settings", "lang_sel": "Language", "curr_sel": "Currency",
        "input_ticker": "Enter Ticker", "tm_title": "🕰️ What IF", "tm_start": "Start Year",
        "sim_title": "📊 Asset Growth Projection", "init_cash": "Initial Principal", "monthly_cash": "Monthly Deposit",
        "inv_years": "Period (Yrs)", "real": "Realistic", "bull": "Bullish", "bear": "Bearish", "principal": "Total Principal",
        "cur_p": "Current Price", "list_p": "Listing Price", "per": "PER", "roe": "ROE", "vol": "Vol",
        "final_asset": "Final Asset", "profit": "Net Profit"
    }
}[st.session_state.user_lang]

# 3. 환율 정보
@st.cache_data(ttl=3600)
def get_exchange_rates():
    try:
        c_rate = yf.Ticker("USDCAD=X").history(period="1d")['Close'].iloc[-1]
        k_rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
        return {"USD": 1.0, "CAD": c_rate, "KRW": k_rate}
    except:
        return {"USD": 1.0, "CAD": 1.40, "KRW": 1400.0}

rates = get_exchange_rates()
curr_symbol = {"USD": "$", "CAD": "C$", "KRW": "₩"}[st.session_state.user_currency]

# --- [사이드바 메뉴] ---
st.sidebar.title("Wealthy Dongjoo")
if st.sidebar.button(L["dash"]): st.session_state.menu = "Dashboard"
if st.sidebar.button(L["set"]): st.session_state.menu = "Settings"

# --- [화면 1: 설정창] ---
if st.session_state.menu == "Settings":
    st.title(L["set"])
    st.session_state.user_lang = st.radio(L["lang_sel"], ["KO", "EN"], index=0 if st.session_state.user_lang == "KO" else 1)
    st.session_state.user_currency = st.selectbox(L["curr_sel"], ["USD", "CAD", "KRW"], index=["USD", "CAD", "KRW"].index(st.session_state.user_currency))
    st.session_state.api_key = st.text_input("Gemini API Key", type="password")

# --- [화면 2: 대시보드] ---
else:
    ticker = st.text_input(L["input_ticker"], ).upper()
    if ticker:
        try:
            stock = yf.Ticker(ticker); info = stock.info
            hist_full = stock.history(period="max"); hist_5y = stock.history(period="5y")
            stock_currency = info.get('currency', 'USD')
            
            # [1] 기업 분석 지표 (PER, ROE, 현재가 등 복구)
            raw_p = info.get('currentPrice') or info.get('regularMarketPrice') or 0
            display_price = (raw_p / rates.get(stock_currency, 1.0)) * rates[st.session_state.user_currency]
            
            st.subheader(f"📍 {ticker} Analysis")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(L["cur_p"], f"{curr_symbol}{display_price:,.2f}")
            c2.metric(L["per"], f"{info.get('forwardPE', 0):.2f}")
            c3.metric(L["roe"], f"{info.get('returnOnEquity', 0)*100:.1f}%")
            vol_val = hist_5y['Close'].pct_change().std() * np.sqrt(252)
            c4.metric(L["vol"], f"{vol_val*100:.1f}%")
            st.caption(f"Listing: {hist_full.index[0].year} | {L['list_p']}: {curr_symbol}{(hist_full['Close'].iloc[0] / rates.get(stock_currency, 1.0)) * rates[st.session_state.user_currency]:,.2f}")

            # [2] What IF (과거 시뮬레이션 금액)
            st.subheader(L["tm_title"])
            list_yr = hist_full.index[0].year
            available_yrs = list(range(list_yr, datetime.now().year))
            selected_yr = st.selectbox(L["tm_start"], available_yrs[::-1], index=available_yrs[::-1].index(max(list_yr, 2000)) if max(list_yr, 2000) in available_yrs else 0)
            
            w_init = st.number_input(L["init_cash"], value=1000, key="wi")
            w_month = st.number_input(L["monthly_cash"], value=200, key="wm")

            p_data = hist_full.loc[f"{selected_yr}-01-01":]['Close']
            p_data_m = p_data.resample('ME').last()
            init_u = w_init / rates[st.session_state.user_currency]
            month_u = w_month / rates[st.session_state.user_currency]
            shares = init_u / (p_data.iloc[0] / rates.get(stock_currency, 1.0))
            for p in p_data_m: shares += month_u / (p / rates.get(stock_currency, 1.0))
            
            final_v_past = shares * (p_data.iloc[-1] / rates.get(stock_currency, 1.0)) * rates[st.session_state.user_currency]
            total_i_past = (w_init + (w_month * len(p_data_m)))
            
            wc1, wc2 = st.columns(2)
            wc1.metric(f"Past {L['final_asset']}", f"{curr_symbol}{final_v_past:,.0f}")
            wc2.metric(f"Past {L['profit']}", f"{curr_symbol}{final_v_past - total_i_past:,.0f}", f"{((final_v_past-total_i_past)/total_i_past)*100:.1f}%")

            # [3] 자산성장 예측표 (미래 시뮬레이션 및 하단 상세 수치 복구)
            st.divider(); st.subheader(L["sim_title"])
            inv_y = st.slider(L["inv_years"], 1, 30, 10)
            
            auto_cagr = ((hist_full['Close'].iloc[-1] / hist_full['Close'].iloc[0]) ** (1/max(1, (hist_full.index[-1]-hist_full.index[0]).days/365.25))) - 1
            years_arr = np.arange(inv_y + 1)
            
            def run_sim(r, v):
                c = w_init / rates[st.session_state.user_currency]; m = w_month / rates[st.session_state.user_currency]
                path = []
                for y in years_arr:
                    if y > 0: c = (c + (m * 12)) * (1 + r + np.random.normal(0, v))
                    path.append(max(0, c * rates[st.session_state.user_currency]))
                return path

            p_real = run_sim(auto_cagr, vol_val*0.7); p_bull = run_sim(auto_cagr*1.3, vol_val*0.5); p_bear = run_sim(auto_cagr*0.6, vol_val*1.2)
            principal_path = [(w_init + (w_month * 12 * y)) for y in years_arr]

            fig_f = go.Figure()
            fig_f.add_trace(go.Scatter(x=years_arr, y=p_real, name=f"{L['real']} ({curr_symbol}{p_real[-1]:,.0f})", line=dict(color='#10b981', width=4)))
            fig_f.add_trace(go.Scatter(x=years_arr, y=p_bull, name=f"{L['bull']} ({curr_symbol}{p_bull[-1]:,.0f})", line=dict(dash='dash', color='#3b82f6')))
            fig_f.add_trace(go.Scatter(x=years_arr, y=p_bear, name=f"{L['bear']} ({curr_symbol}{p_bear[-1]:,.0f})", line=dict(dash='dot', color='#ef4444')))
            fig_f.add_trace(go.Scatter(x=years_arr, y=principal_path, name=f"{L['principal']} ({curr_symbol}{principal_path[-1]:,.0f})", line=dict(color='#ffffff', dash='dot')))
            fig_f.update_layout(template="plotly_dark", hovermode="x unified")
            st.plotly_chart(fig_f, use_container_width=True)

            # --- [하단 결과 요약 섹션 복구] ---
            st.markdown(f"### 📈 {L['sim_title']} 상세 결과")
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.metric(f"{L['real']} {L['final_asset']}", f"{curr_symbol}{p_real[-1]:,.0f}")
                st.caption(f"{L['profit']}: {curr_symbol}{p_real[-1] - principal_path[-1]:,.0f}")
            with rc2:
                st.metric(f"{L['bull']} {L['final_asset']}", f"{curr_symbol}{p_bull[-1]:,.0f}")
                st.caption(f"{L['profit']}: {curr_symbol}{p_bull[-1] - principal_path[-1]:,.0f}")
            with rc3:
                st.metric(L['principal'], f"{curr_symbol}{principal_path[-1]:,.0f}")
                st.caption("누적 원금 합계")

        except Exception as e: st.error(f"Error: {e}")
