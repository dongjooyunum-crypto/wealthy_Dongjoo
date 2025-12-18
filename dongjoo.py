import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai
import numpy as np
from datetime import datetime

# 1. UI 및 다크 테마 설정 (절대 고정)
st.set_page_config(page_title="Wealthy Dongjoo Master", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #0d1117; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    h1 { color: #58a6ff; font-style: italic; font-weight: 900 !important; }
    h2, h3 { color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-top: 35px; }
    .tooltip { border-bottom: 1px dotted #8b949e; color: #8b949e; cursor: help; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

# 2. 사이드바 - 통화 및 디폴트 투자 설정
st.sidebar.header("🌍 통화 및 투자 설정")
user_currency = st.sidebar.selectbox("표시 통화 선택", ["USD", "CAD", "KRW"], index=0)

# 실시간 환율 정보 (USD 기준)
@st.cache_data(ttl=3600)
def get_exchange_rates():
    try:
        c_rate = yf.Ticker("USDCAD=X").history(period="1d")['Close'].iloc[-1]
        k_rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
        return {"USD": 1.0, "CAD": c_rate, "KRW": k_rate}
    except:
        return {"USD": 1.0, "CAD": 1.40, "KRW": 1400.0}

rates = get_exchange_rates()
curr_symbol = {"USD": "$", "CAD": "C$", "KRW": "₩"}[user_currency]

# 명령 사항: 디폴트값 초기 원금 1000, 매달 적립 200 설정
init_cash_in = st.sidebar.number_input(f"초기 투자 원금 ({user_currency})", value=1000)
monthly_cash_in = st.sidebar.number_input(f"매달 추가 적립액 ({user_currency})", value=200)
invest_years = st.sidebar.slider("미래 투자 기간 (년)", 1, 30, 10)
api_key = st.sidebar.text_input("Gemini API Key (선택)", type="password")

# 내부 계산용 USD 변환
init_cash_usd = init_cash_in / rates[user_currency]
monthly_cash_usd = monthly_cash_in / rates[user_currency]

st.title("🏦 Wealthy Dongjoo : AI 종합 투자 도우미")
ticker = st.text_input("분석할 티커 입력", "VFV.TO").upper()

if ticker:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist_full = stock.history(period="max")
        hist_5y = stock.history(period="5y")

        if hist_full.empty:
            st.error("데이터를 찾을 수 없습니다.")
        else:
            # --- [교정] 종목 통화 인식 및 환율 변환 ---
            stock_currency = info.get('currency', 'USD')
            raw_curr_p = info.get('currentPrice') or info.get('regularMarketPrice') or 0
            
            # 주가 데이터를 USD로 먼저 변환한 후 사용자 통화로 재변환
            price_in_usd = raw_curr_p / rates.get(stock_currency, 1.0)
            display_price = price_in_usd * rates[user_currency]
            
            # 3. 실시간 주가 차트 (현재 주가 그래프 유지)
            st.subheader(f"📈 {ticker} 실시간 주가 흐름 (5년, 단위: {user_currency})")
            adj_hist = (hist_5y['Close'] / rates.get(stock_currency, 1.0)) * rates[user_currency]
            fig_curr = go.Figure()
            fig_curr.add_trace(go.Scatter(x=hist_5y.index, y=adj_hist, name='주가', line=dict(color='#58a6ff', width=2)))
            fig_curr.update_layout(template="plotly_dark", height=300, hovermode="x unified")
            st.plotly_chart(fig_curr, use_container_width=True)

            # 4. 핵심 지표 분석 (툴팁 설명 포함)
            st.subheader("📍 핵심 지표 분석")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("현재 주가", f"{curr_symbol}{display_price:,.2f}")
                st.caption(f"상장가: {curr_symbol}{(hist_full['Close'].iloc[0] / rates.get(stock_currency, 1.0)) * rates[user_currency]:,.2f}")
            with c2:
                per = info.get('forwardPE', 0)
                st.metric("PER (수익 가치)", f"{per:.2f}")
                st.markdown('<div class="tooltip" title="낮을수록 저평가. 주가가 이익의 몇 배인지 나타냄.">❓ PER 분석</div>', unsafe_allow_html=True)
            with c3:
                roe = info.get('returnOnEquity', 0) * 100
                st.metric("ROE (자본 효율)", f"{roe:.1f}%")
                st.markdown('<div class="tooltip" title="높을수록 우량. 기업이 자본을 얼마나 잘 쓰는지 나타냄.">❓ ROE 분석</div>', unsafe_allow_html=True)
            with c4:
                vol = hist_5y['Close'].pct_change().std() * np.sqrt(252) * 100
                st.metric("변동성 (Vol)", f"{vol:.1f}%")
                st.markdown('<div class="tooltip" title="낮을수록 안정적. 주가의 연간 흔들림 정도.">❓ 변동성 분석</div>', unsafe_allow_html=True)

            # 5. 종합 리포트 및 AI 분석
            st.divider()
            ai_score = 1.0
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = f"종목:{ticker}, PER:{per}, ROE:{roe}%. {user_currency} 기준 리포트와 SCORE:0.5~1.5를 작성해줘."
                    with st.spinner('AI 분석 리포트 생성 중...'):
                        res = model.generate_content(prompt)
                        st.markdown(f"### 💬 AI 실시간 종합 리포트\n{res.text}")
                        if "SCORE:" in res.text: ai_score = float(res.text.split("SCORE:")[-1].strip().split()[0])
                except: st.warning("AI 호출 지연")
            else:
                st.markdown("### 📊 퀀트 자동 분석 리포트 (기본)")

            # 6. 역사적 타임머신 (5년 갭)
            st.divider()
            st.subheader("🕰️ 역사적 타임머신")
            start_years = [y for y in range(1900, datetime.now().year, 5) if y >= hist_full.index[0].year]
            selected_year = st.selectbox("투자 시작 연도 선택", start_years[::-1])
            if selected_year:
                p_data = hist_full.loc[f"{selected_year}-01-01":]
                p_start_usd = p_data['Close'].iloc[0] / rates.get(stock_currency, 1.0)
                p_curr_usd = hist_full['Close'].iloc[-1] / rates.get(stock_currency, 1.0)
                p_years = datetime.now().year - selected_year
                total_inv_past = (init_cash_usd + (monthly_cash_usd * 12 * p_years)) * rates[user_currency]
                
                m_hist = p_data['Close'].resample('ME').last()
                shares = init_cash_usd / p_start_usd
                for p in m_hist: shares += monthly_cash_usd / (p / rates.get(stock_currency, 1.0))
                final_val_past = shares * p_curr_usd * rates[user_currency]
                
                tc1, tc2, tc3 = st.columns(3)
                tc1.metric(f"{selected_year}년 시작가", f"{curr_symbol}{p_start_usd * rates[user_currency]:,.2f}")
                tc2.metric("현재 자산 가치", f"{curr_symbol}{final_val_past:,.0f}")
                tc3.metric("누적 수익률", f"{((final_val_past - total_inv_past) / total_inv_past) * 100:.1f}%")

            # 7. 미래 자산 성장 시뮬레이션 (원금 선 & 모든 시나리오 가격 표시)
            st.divider()
            st.subheader("📈 미래 자산 성장 시뮬레이션 (AI 리얼리티)")
            n_y_total = max(1, datetime.now().year - hist_full.index[0].year)
            cagr = ((price_in_usd / (hist_full['Close'].iloc[0] / rates.get(stock_currency, 1.0))) ** (1/n_y_total) - 1)
            real_rate = cagr * ai_score
            years = np.arange(invest_years + 1)
            
            def get_path(r, n):
                vals = []; c = init_cash_usd
                for y in years:
                    if y > 0: c = (c + (monthly_cash_usd * 12)) * (1 + r + np.random.normal(0, n/100))
                    vals.append(max(0, c * rates[user_currency]))
                return vals

            p_real = get_path(real_rate, vol*0.7)
            p_bull = get_path(real_rate*1.3, vol*0.5)
            p_bear = get_path(real_rate*0.6, vol*1.2)
            principal_path = [(init_cash_usd + (monthly_cash_usd * 12 * y)) * rates[user_currency] for y in years]

            fig_future = go.Figure()
            # 명령 사항: 현실적, 낙관적, 비관적 모든 선에 최종 가격 표시 고정
            fig_future.add_trace(go.Scatter(x=years, y=p_real, name=f"현실적 ({curr_symbol}{p_real[-1]:,.0f})", line=dict(color='#10b981', width=4)))
            fig_future.add_trace(go.Scatter(x=years, y=p_bull, name=f"낙관적 ({curr_symbol}{p_bull[-1]:,.0f})", line=dict(color='#3b82f6', dash='dash')))
            fig_future.add_trace(go.Scatter(x=years, y=p_bear, name=f"비관적 ({curr_symbol}{p_bear[-1]:,.0f})", line=dict(color='#ef4444', dash='dot')))
            # 명령 사항: 흰색 원금 선 추가
            fig_future.add_trace(go.Scatter(x=years, y=principal_path, name=f"누적 원금 ({curr_symbol}{principal_path[-1]:,.0f})", line=dict(color='#ffffff', width=2, dash='dot')))
            
            fig_future.update_layout(template="plotly_dark", height=450, yaxis_title=f"자산 가치 ({user_currency})", hovermode="x unified")
            st.plotly_chart(fig_future, use_container_width=True)

            # 최종 결과 섹션
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("현실적 최종 자산", f"{curr_symbol}{p_real[-1]:,.0f}", f"{((p_real[-1]-principal_path[-1])/principal_path[-1])*100:.1f}%")
            sc2.metric("낙관적 최종 자산", f"{curr_symbol}{p_bull[-1]:,.0f}", f"{((p_bull[-1]-principal_path[-1])/principal_path[-1])*100:.1f}%")
            sc3.metric("누적 투자 원금", f"{curr_symbol}{principal_path[-1]:,.0f}")

    except Exception as e:
        st.error(f"오류 발생: {e}")