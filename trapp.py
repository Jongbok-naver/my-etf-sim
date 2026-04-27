import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global ETF Simulator", layout="wide")

# 2. 데이터 로딩 함수 (정확도 우선)
@st.cache_data(ttl=3600)
def get_usd_krw():
    try:
        # 환율은 시뮬레이션의 핵심이므로 안정적인 데이터 사용
        data = yf.download("USDKRW=X", period="5d", interval="1d", progress=False)
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
        df = yf.download(ticker_symbol, period="5d", interval="1d", progress=False)
        if not df.empty:
            return float(df['Close'].iloc[-1])
        return None
    except:
        return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
current_usd_krw = get_usd_krw()

tab_config, tab_scenario = st.tabs(["📍 포트폴리오 구성", "📅 시나리오 설정"])

with tab_config:
    st.info(f"기준 환율: 1$ = {current_usd_krw:,.1f}원")
    num_etfs = st.slider("ETF 개수", 1, 5, 1)
    etf_configs = []
    
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                search = st.text_input(f"종목 검색 #{i+1} (이름 입력)", "KODEX 200", key=f"s_{i}")
                filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)] if not kr_list.empty else pd.DataFrame()
                if not filtered.empty:
                    sel = st.selectbox(f"종목 확정 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    display_name = sel.split(" (")[0]
                else:
                    st.warning("검색 결과가 없습니다.")
                    code, display_name = None, None
            else:
                code = st.text_input(f"미국 티커 #{i+1}", "QQQ", key=f"c_{i}").upper()
                display_name = code
            
            c1, c2, c3 = st.columns(3)
            q = c1.number_input(f"초기 수량", min_value=0.0, value=0.0, key=f"q_{i}")
            v = c2.number_input(f"월 적립금(원)", min_value=0, value=1000000, key=f"v_{i}", step=100000)
            d = c3.number_input(f"연 분배율(%)", 0.0, 20.0, 1.0, key=f"d_{i}", step=0.1)
            
            etf_configs.append({
                'code': code, 'name': display_name, 'mkt': mkt, 
                'qty': q, 'monthly_pay': v, 'dist_rate': (d/100)/12
            })

with tab_scenario:
    c1, c2 = st.columns(2)
    start_date = c1.date_input("투자 시작일", datetime.now())
    end_date = c2.date_input("투자 종료일", datetime(2030, 12, 31))
    growth = st.slider("연 성장률(%)", -10, 20, 5)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 엔진 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True, type="primary"):
    valid_configs = [c for c in etf_configs if c['code']]
    
    if not valid_configs:
        st.error("설정된 종목이 없습니다.")
    elif start_date >= end_date:
        st.error("날짜 설정을 확인해주세요.")
    else:
        # 개월 수 계산
        months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        month_range = pd.date_range(start=start_date, periods=max(months_diff, 1), freq='MS')
        
        all_dfs = []
        
        for config in valid_configs:
            raw_price = get_current_price(config['code'], config['mkt'])
            if raw_price is None: continue
            
            # 초기 설정
            # 미국 주식은 달러 가격으로 수량 계산, 한국 주식은 원화 가격으로 계산
            current_price = raw_price 
            qty = float(config['qty'])
            
            # 초기 투자금 계산 (원화 기준)
            price_krw = current_price * current_usd_krw if config['mkt'] == "미국" else current_price
            cum_invest = qty * price_krw
            
            m_growth = (1 + growth/100)**(1/12) - 1
            history = []
            
            for i, date in enumerate(month_range):
                # 1. 자산 평가 (현재 가격 기준)
                price_krw = current_price * current_usd_krw if config['mkt'] == "미국" else current_price
                eval_amount = qty * price_krw
                
                # 2. 분배금 발생 (평가 금액 기반)
                monthly_div = eval_amount * config['dist_rate']
                
                # 3. 분배금 재투자 (선택 시 수량 증가)
                if reinvest and monthly_div > 0:
                    qty += (monthly_div / price_krw)
                
                # 4. 월 적립 (매달 지정한 '원화'만큼 수량 매수)
                if i > 0:
                    added_qty = config['monthly_pay'] / price_krw
                    qty += added_qty
                    cum_invest += config['monthly_pay']
                
                history.append({
                    "날짜": date.strftime('%Y-%m'),
                    f"{config['name']}_평가금": eval_amount,
                    f"{config['name']}_투자금": cum_invest,
                    f"{config['name']}_분배금": monthly_div
                })
                
                # 5. 다음 달 가격 변동
                current_price *= (1 + m_growth)

            all_dfs.append(pd.DataFrame(history).set_index("날짜"))

        if all_dfs:
            res = pd.concat(all_dfs, axis=1)
            res['총평가금'] = res.filter(like='_평가금').sum(axis=1)
            res['총투자금'] = res.filter(like='_투자금').sum(axis=1)
            res['총분배금'] = res.filter(like='_분배금').sum(axis=1)
            
            last = res.iloc[-1]
            st.divider()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("최종 자산", f"{int(last['총평가금']):,}원")
            m2.metric("최종 월 분배금", f"{int(last['총분배금']):,}원")
            roi = ((last['총평가금'] - last['총투자금']) / last['총투자금'] * 100) if last['총투자금'] > 0 else 0
            m3.metric("누적 수익률", f"{roi:.1f}%")
            
            st.subheader("📈 성장 추이")
            st.line_chart(res[['총평가금', '총투자금']])
            
            with st.expander("📝 상세 내역 보기 (단위: 원)"):
                st.dataframe(res.astype(int).applymap(lambda x: f"{x:,}"), use_container_width=True)
