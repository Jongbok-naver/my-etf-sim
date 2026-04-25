import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global Multi-ETF", layout="wide")

# 2. 가격 데이터 가져오기 함수 (검증된 방식)
def get_price(symbol, market):
    try:
        ticker = f"{symbol}.KS" if market == "한국" and ".K" not in symbol else symbol
        data = yf.download(ticker, period="5d", progress=False)
        if data.empty: return None
        
        # 멀티인덱스 및 단일인덱스 모두 대응
        if isinstance(data.columns, pd.MultiIndex):
            return float(data['Close'].iloc[-1].values[0])
        return float(data['Close'].iloc[-1])
    except:
        return None

# --- UI 메인 ---
st.title("💰 글로벌 멀티 ETF 시뮬레이터")
st.info("한국 종목(예: 069500), 미국 티커(예: QQQ, SCHD)를 입력하세요.")

usd_krw = 1380.0 # 환율 고정 (필요시 수정)

# 사이드바 설정
with st.sidebar:
    st.header("📍 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 3, 2)
    
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            code = st.text_input(f"종목코드/티커 #{i+1}", "069500" if i==0 else "QQQ", key=f"c_{i}").upper()
            init_qty = st.number_input(f"현재 수량 #{i+1}", min_value=0.0, value=10.0, key=f"q_{i}")
            monthly = st.number_input(f"월 적립금(원) #{i+1}", min_value=0, value=200000, step=50000, key=f"v_{i}")
            dist = st.number_input(f"월 분배율(%) #{i+1}", 0.0, 5.0, 0.5, step=0.1, key=f"d_{i}")
            
            etf_configs.append({'idx': i+1, 'code': code, 'mkt': mkt, 'qty': init_qty, 'monthly': monthly, 'dist': dist})

    st.header("📈 공통 시나리오")
    growth = st.slider("연 예상 성장률(%)", -10, 20, 5)
    months_count = st.number_input("투자 기간(개월)", 1, 600, 60)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 계산 ---
if st.button("🚀 통합 시뮬레이션 시작", use_container_width=True):
    with st.spinner("데이터 분석 중..."):
        all_etf_results = []
        
        for config in etf_configs:
            price = get_price(config['code'], config['mkt'])
            if price is None:
                st.error(f"종목 {config['code']} 데이터를 불러올 수 없습니다.")
                continue
            
            # 원화 환산
            p = price * usd_krw if config['mkt'] == "미국" else price
            q = float(config['qty'])
            inv = q * p
            m_g = (1 + growth/100)**(1/12) - 1
            m_d = config['dist'] / 100
            
            history = []
            for m in range(months_count + 1):
                if m > 0: p *= (1 + m_g) # 주가 상승
                
                div_income = (q * p) * m_d # 분배금 발생
                if reinvest: q += div_income / p # 재투자
                
                if m > 0:
                    q += config['monthly'] / p # 월 적립
                    inv += config['monthly'] # 투자원금 증가
                
                history.append({
                    "월": m,
                    f"#{config['idx']} 평가금": q * p,
                    f"#{config['idx']} 분배금": div_income,
                    f"#{config['idx']} 투자금": inv
                })
            all_etf_results.append(pd.DataFrame(history).set_index("월"))

        if all_etf_results:
            # 모든 데이터 합치기
            res = pd.concat(all_etf_results, axis=1)
            
            # 합계 컬럼 계산
            res['총평가금'] = res[[c for c in res.columns if '평가금' in c]].sum(axis=1)
            res['총투자금'] = res[[c for c in res.columns if '투자금' in c]].sum(axis=1)
            res['총분배금'] = res[[c for c in res.columns if '분배금' in c]].sum(axis=1)
            
            # 결과 리포트
            f = res.iloc[-1] # 마지막 달 데이터
            st.divider()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
            c2.metric("최종 월 분배금", f"{int(f['총분배금']):,}원")
            c3.metric("누적 수익률", f"{((f['총평가금']-f['총투자금'])/f['총투자금']*100):.1f}%")
            
            # 차트
            tab1, tab2 = st.tabs(["📈 자산 성장 곡선", "💵 월 분배금 흐름"])
            with tab1:
                st.line_chart(res[['총평가금', '총투자금']])
            with tab2:
                st.bar_chart(res['총분배금'])
                
            with st.expander("📝 월별 상세 내역 보기"):
                st.dataframe(res.astype(int), use_container_width=True)
