import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="ETF Simulator", layout="wide")

# 2. 가격 데이터 가져오기 함수 (안정성 최우선)
def get_price(symbol, market):
    try:
        # 한국 종목은 .KS(코스피) 또는 .KQ(코스닥)를 붙여야 yfinance에서 읽힘
        if market == "한국":
            ticker = symbol if ".K" in symbol else f"{symbol}.KS"
        else:
            ticker = symbol
        
        data = yf.download(ticker, period="5d", progress=False)
        if data.empty:
            return None
        
        # 최신 종가 가져오기 (멀티인덱스 방어 로직)
        if isinstance(data.columns, pd.MultiIndex):
            price = float(data['Close'].iloc[-1].values[0])
        else:
            price = float(data['Close'].iloc[-1])
        return price
    except:
        return None

# 3. 메인 화면
st.title("📱 스마트폰 전용 ETF 시뮬레이터")
st.info("한국 종목은 6자리 숫자(예: 069500), 미국은 티커(예: QQQ)를 입력하세요.")

# 환율 (고정값 또는 간단 호출)
usd_krw = 1380.0 

# 설정 구역
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        mkt = st.selectbox("시장 선택", ["한국", "미국"])
        code = st.text_input("종목코드/티커", "069500" if mkt=="한국" else "QQQ")
    with col2:
        monthly = st.number_input("월 투자금(원)", value=500000, step=100000)
        growth = st.slider("예상 연수익률(%)", 0, 20, 7)

    months = st.number_input("투자 기간(개월)", value=60)
    dist_rate = st.number_input("월 분배율(%)", value=0.0, step=0.1)

# 실행 버튼
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    with st.spinner("데이터 로딩 중..."):
        price = get_price(code, mkt)
        
        if price is None and mkt == "한국":
            # 코스피로 안되면 코스닥으로 재시도
            price = get_price(f"{code}.KQ", "미국") # 구조적 우회

        if price:
            if mkt == "미국":
                price_krw = price * usd_krw
            else:
                price_krw = price
            
            # 계산 로직
            m_growth = (1 + growth/100)**(1/12) - 1
            m_dist = dist_rate / 100
            
            asset = 0
            principal = 0
            history = []
            
            for m in range(1, months + 1):
                asset = (asset + monthly) * (1 + m_growth)
                dividend = asset * m_dist
                asset += dividend # 분배금 재투자 가정
                principal += monthly
                history.append({"개월": m, "자산": asset, "원금": principal, "월배당": dividend})
            
            df = pd.DataFrame(history).set_index("개월")
            
            # 결과 표시
            st.success(f"현재가 {int(price_krw):,}원 기준 분석 완료")
            
            m1, m2 = st.columns(2)
            m1.metric("최종 자산", f"{int(df['자산'].iloc[-1]):,}원")
            m2.metric("최종 월 배당금", f"{int(df['월배당'].iloc[-1]):,}원")
            
            st.subheader("📈 자산 성장 곡선")
            st.line_chart(df[['자산', '원금']])
            
            with st.expander("상세 내역 보기"):
                st.dataframe(df.astype(int), use_container_width=True)
        else:
            st.error("종목 코드를 확인해주세요. (yfinance가 해당 코드를 찾지 못함)")
