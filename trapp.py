import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global ETF Simulator", layout="wide")

# 2. 환율 및 데이터 로딩 함수 (캐싱 적용)
@st.cache_data(ttl=3600)
def get_usd_krw():
    try:
        data = yf.Ticker("USDKRW=X").history(period="1d")
        return float(data['Close'].iloc[-1])
    except:
        return 1380.0

@st.cache_data(ttl=86400)
def get_kr_list():
    try:
        df = fdr.StockListing('ETF/KR')
        return df[['Symbol', 'Name']].rename(columns={'Symbol': 'Code'}) if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

def get_current_price(symbol, market):
    try:
        ticker_symbol = f"{symbol}.KS" if market == "한국" else symbol
        df = yf.Ticker(ticker_symbol).history(period="5d")
        return float(df['Close'].iloc[-1]) if not df.empty else None
    except:
        return None

# --- UI 메인 시작 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
current_usd_krw = get_usd_krw()

# 모바일 대응을 위해 사이드바 대신 메인 화면에 탭 생성
tab_config, tab_scenario = st.tabs(["📍 포트폴리오 구성", "📅 시나리오 설정"])

with tab_config:
    st.info(f"실시간 환율: 1$ = {current_usd_krw:,.1f}원")
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    etf_configs = []
    
    # 가독성을 위해 컬럼 사용
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                search = st.text_input(f"종목명 검색 #{i+1}", "KODEX 200", key=f"s_{i}")
                filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)] if not kr_list.empty else pd.DataFrame()
                if not filtered.empty:
                    sel = st.selectbox(f"종목 선택 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                else:
                    st.warning("결과 없음")
                    code = None
            else:
                code = st.text_input(f"미국 티커 #{i+1}", "QQQ", key=f"c_{i}").upper()
            
            c1, c2, c3 = st.columns(3)
            q = c1.number_input(f"수량", min_value=0.0, value=10.0, key=f"q_{i}")
            v = c2.number_input(f"월 적립(원)", min_value=0, value=300000, key=f"v_{i}")
            d = c3.number_input(f"연 분배율(%)", 0.0, 15.0, 1.0, key=f"d_{i}")
            
            etf_configs.append({'code':code, 'mkt':mkt, 'qty':q, 'val':v, 'dist':d/12/100})

with tab_scenario:
    c1, c2 = st.columns(2)
    start_date = c1.date_input("투자 시작일", datetime.now())
    end_date = c2.date_input("투자 종료일", datetime(2030, 12, 31))
    
    growth = st.slider("기대 연 성장률(%)", -10, 20, 7)
    reinvest = st.checkbox("분배금 재투자", value=True)

# 시뮬레이션 버튼 (메인 화면 하단에 큼직하게 배치)
if st.button("🚀 시뮬레이션 시작", use_container_width=True, type="primary"):
    valid_configs = [c for c in etf_configs if c['code'] is not None]
    
    if not valid_configs:
        st.error("종목을 선택해주세요.")
    elif start_date >= end_date:
        st.error("종료일이 시작일보다 빨라야 합니다.")
    else:
        with st.spinner("미래 자산 계산 중..."):
            months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            month_range = pd.date_range(start=start_date, periods=max(months_diff, 1), freq='MS')
            
            all_history = []
            for i, config in enumerate(valid_configs):
                price = get_current_price(config['code'], config['mkt'])
                if price is None: continue
                
                p = price * current_usd_krw if config['mkt'] == "미국" else price
                qty = float(config['qty'])
                inv_total = qty * p
                m_growth = (1 + growth/100)**(1/12) - 1
                
                history = []
                for date in month_range:
                    div_income = (qty * p) * config['dist']
                    if reinvest: qty += div_income / p
                    if date != month_range[0]:
                        qty += config['val'] / p
                        inv_total += config['val']
                    p *= (1 + m_growth)
                    history.append({
                        "날짜": date.strftime('%Y-%m'),
                        f"eval_{i}": qty * p,
                        f"div_{i}": div_income,
                        f"inv_{i}": inv_total
                    })
                all_history.append(pd.DataFrame(history).set_index("날짜"))

            if all_history:
                res = pd.concat(all_history, axis=1)
                res['총평가금'] = res.filter(like='eval_').sum(axis=1)
                res['총투자금'] = res.filter(like='inv_').sum(axis=1)
                res['총분배금'] = res.filter(like='div_').sum(axis=1)
                
                last = res.iloc[-1]
                st.divider()
                
                # 결과 지표
                m1, m2, m3 = st.columns(3)
                m1.metric("최종 자산", f"{int(last['총평가금']):,}원")
                m2.metric("최종 월 분배금", f"{int(last['총분배금']):,}원")
                m3.metric("수익률", f"{((last['총평가금']-last['총투자금'])/last['총투자금']*100):.1f}%")
                
                st.line_chart(res[['총평가금', '총투자금']])
                
                # 상세 내역 콤마 표시 적용
                with st.expander("📝 상세 내역 보기"):
                    formatted_df = res.copy()
                    for col in formatted_df.columns:
                        formatted_df[col] = formatted_df[col].apply(lambda x: f"{int(x):,}")
                    st.dataframe(formatted_df, use_container_width=True)
