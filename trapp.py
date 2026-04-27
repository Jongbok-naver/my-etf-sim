import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global ETF Simulator", layout="wide")

# 2. 데이터 로딩 (캐싱)
@st.cache_data(ttl=3600)
def get_usd_krw():
    try:
        data = yf.download("USDKRW=X", period="5d", interval="1d", progress=False)
        return float(data['Close'].iloc[-1])
    except: return 1400.0

@st.cache_data(ttl=86400)
def get_kr_list():
    try:
        df = fdr.StockListing('ETF/KR')
        return df[['Symbol', 'Name']].rename(columns={'Symbol': 'Code'}) if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

def get_current_price(symbol, market):
    try:
        ticker = f"{symbol}.KS" if market == "한국" else symbol
        df = yf.download(ticker, period="5d", interval="1d", progress=False)
        return float(df['Close'].iloc[-1]) if not df.empty else None
    except: return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
current_usd_krw = get_usd_krw()

tab_config, tab_scenario = st.tabs(["📍 포트폴리오 구성", "📅 시나리오 설정"])

with tab_config:
    st.info(f"현재 환율: 1$ = {current_usd_krw:,.1f}원")
    
    # ETF 개수를 2개로 초기 설정
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    configs = []
    
    for i in range(num_etfs):
        # 초기 검색어 설정 (ETF1: 미국AI, ETF2: 배당)
        default_search = "미국AI" if i == 0 else ("배당" if i == 1 else "")
        
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                search = st.text_input(f"종목 검색 #{i+1}", value=default_search, key=f"s_{i}")
                filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)] if not kr_list.empty else pd.DataFrame()
                
                if not filtered.empty:
                    sel = st.selectbox(f"종목 선택 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")[0]
                else:
                    st.warning("검색 결과가 없습니다.")
                    code, name = None, None
            else:
                code = st.text_input(f"미국 티커 #{i+1}", "QQQ", key=f"c_{i}").upper()
                name = code
            
            c1, c2, c3 = st.columns(3)
            q_init = c1.number_input(f"초기 수량", min_value=0.0, value=10.0, key=f"q_{i}")
            m_pay = c2.number_input(f"월 적립금(원)", min_value=0, value=500000, key=f"v_{i}", step=100000)
            d_rate = c3.number_input(f"연 분배율(%)", 0.0, 20.0, 1.0 if i==0 else 4.0, key=f"d_{i}", step=0.1)
            
            configs.append({'code': code, 'name': name, 'mkt': mkt, 'q_init': q_init, 'm_pay': m_pay, 'd_rate': (d_rate/100)/12})

with tab_scenario:
    c1, c2 = st.columns(2)
    start_date = c1.date_input("투자 시작일", datetime.now())
    end_date = c2.date_input("투자 종료일", datetime(2035, 12, 31))
    growth = st.slider("기대 연 성장률(%)", -10, 20, 7)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 시작 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True, type="primary"):
    valid_configs = [c for c in configs if c['code']]
    if not valid_configs:
        st.error("종목을 확인해주세요.")
    else:
        # 개월 수 계산
        months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        dates = pd.date_range(start=start_date, periods=max(months, 1), freq='MS')
        
        all_data = []
        for conf in valid_configs:
            price = get_current_price(conf['code'], conf['mkt'])
            if price is None: continue
            
            curr_p = price * current_usd_krw if conf['mkt'] == "미국" else price
            qty = conf['q_init']
            cum_inv = qty * curr_p
            m_growth = (1 + growth/100)**(1/12) - 1
            
            history = []
            for i, d in enumerate(dates):
                if i > 0: # 2회차부터 적립금 투입
                    qty += (conf['m_pay'] / curr_p)
                    cum_inv += conf['m_pay']
                
                eval_amt = qty * curr_p
                dist_amt = eval_amt * conf['d_rate']
                
                if reinvest:
                    qty += (dist_amt / curr_p)
                
                history.append({
                    "날짜": d.strftime('%Y-%m'),
                    f"{conf['name']}_평가": eval_amt,
                    f"{conf['name']}_투자": cum_inv,
                    f"{conf['name']}_분배": dist_amt
                })
                curr_p *= (1 + m_growth)
                
            all_data.append(pd.DataFrame(history).set_index("날짜"))

        if all_data:
            res = pd.concat(all_data, axis=1)
            res['총평가금'] = res.filter(like='_평가').sum(axis=1)
            res['총투자금'] = res.filter(like='_투자').sum(axis=1)
            res['총분배금'] = res.filter(like='_분배').sum(axis=1)
            
            last = res.iloc[-1]
            st.divider()
            
            # 메트릭 표시
            m1, m2, m3 = st.columns(3)
            m1.metric("최종 자산", f"{int(last['총평가금']):,}원")
            m2.metric("최종 월 분배금", f"{int(last['총분배금']):,}원")
            roi = ((last['총평가금'] - last['총투자금']) / last['총투자금'] * 100) if last['총투자금'] > 0 else 0
            m3.metric("누적 수익률", f"{roi:.1f}%")
            
            st.subheader("📈 자산 성장 곡선")
            st.line_chart(res[['총평가금', '총투자금']])
            
            with st.expander("📝 상세 데이터 확인 (단위: 원)"):
                # 가독성을 위해 정수변환 및 콤마 추가
                st.dataframe(res.astype(int).applymap(lambda x: f"{x:,}"), use_container_width=True)
