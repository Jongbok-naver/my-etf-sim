import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global Multi-ETF", layout="wide")

# 2. 한국 ETF 리스트 (캐싱)
@st.cache_data(ttl=86400)
def get_kr_list():
    try:
        df = fdr.StockListing('ETF/KR')
        return df[['Symbol', 'Name']].rename(columns={'Symbol': 'Code'}) if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

# 3. 가격 데이터 로딩 (멀티인덱스 완벽 대응)
def get_current_price(symbol, market):
    try:
        if market == "한국":
            # 한국은 fdr로 가져오는 것이 가장 정확하고 빠름
            df = fdr.DataReader(symbol)
            if not df.empty:
                return float(df['Close'].iloc[-1])
        
        # 미국 또는 fdr 실패 시 yfinance
        ticker_symbol = f"{symbol}.KS" if market == "한국" else symbol
        # 데이터를 1개만 가져오지 말고 넉넉히 가져와서 마지막 가격 추출
        df = yf.download(ticker_symbol, period="5d", interval="1d", progress=False)
        
        if not df.empty:
            # [핵심] 멀티인덱스 구조에서 무조건 'Close' 컬럼의 마지막 값만 추출
            if 'Close' in df.columns:
                close_data = df['Close']
                # 데이터가 시리즈면 마지막 값, 데이터프레임이면 첫 번째 열의 마지막 값
                if isinstance(close_data, pd.Series):
                    return float(close_data.iloc[-1])
                else:
                    return float(close_data.iloc[-1, 0])
    except:
        pass
    return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
usd_krw = 1380.0

with st.sidebar:
    st.header("📍 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    etf_configs = []
    
    for i in range(num_etfs):
        # --- 요청하신 초기값 설정 ---
        if i == 0:
            d_search, d_qty, d_pay, d_dist = "미국AI", 5090.0, 0, 1.25
        elif i == 1:
            d_search, d_qty, d_pay, d_dist = "배당", 3532.0, 500000, 1.75
        else:
            d_search, d_qty, d_pay, d_dist = "", 10.0, 300000, 0.5

        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                search = st.text_input(f"종목명 검색 #{i+1}", value=d_search, key=f"s_{i}")
                filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)] if not kr_list.empty else pd.DataFrame()
                if not filtered.empty:
                    sel = st.selectbox(f"종목 선택 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", index=0, key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")
                else:
                    st.warning("결과 없음"); code, name = None, None
            else:
                code = st.text_input(f"미국 티커 #{i+1}", "QQQ", key=f"c_{i}").upper()
                name = code
                
            q = st.number_input(f"현재 수량 #{i+1}", min_value=0.0, value=float(d_qty), key=f"q_{i}")
            v = st.number_input(f"월 적립금(원) #{i+1}", min_value=0, value=int(d_pay), key=f"v_{i}")
            d = st.number_input(f"연 분배율(%) #{i+1}", 0.0, 30.0, value=float(d_dist), key=f"d_{i}", step=0.01)
            
            etf_configs.append({'idx':i+1, 'code':code, 'name':name, 'mkt':mkt, 'qty':q, 'val':v, 'dist':d})

    st.header("📅 시나리오 설정")
    start_date = st.date_input("투자 시작일", datetime.now())
    end_date = st.date_input("투자 종료일", datetime(2035, 12, 31))
    growth = st.slider("연 성장률(%)", -10, 20, 5)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 엔진 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code']]
    
    if not valid_configs:
        st.error("종목을 확정해주세요.")
    else:
        with st.spinner("최신 가격 로딩 중..."):
            months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            month_range = pd.date_range(start=start_date, periods=max(months_diff, 1), freq='MS')
            
            all_results = []
            for config in valid_configs:
                price = get_current_price(config['code'], config['mkt'])
                
                if price is None or price <= 0:
                    st.error(f"❌ {config['code']} 가격을 가져오지 못했습니다.")
                    continue
                
                # 원화 환산
                p = price * usd_krw if config['mkt'] == "미국" else price
                qty = float(config['qty'])
                inv = qty * p # 초기 투자금
                
                m_g = (1 + growth/100)**(1/12) - 1
                m_d = (config['dist'] / 100) / 12
                
                history = []
                for i, date in enumerate(month_range):
                    if i > 0: p *= (1 + m_g) # 가격 변동
                    if i > 0: # 월 적립
                        qty += config['val'] / p
                        inv += config['val']
                    
                    eval_amt = qty * p
                    div = eval_amt * m_d # 분배금
                    if reinvest: qty += div / p # 재투자
                    
                    history.append({
                        "날짜": date.strftime('%Y-%m'),
                        f"#{config['idx']} 평가금": eval_amt,
                        f"#{config['idx']} 분배금": div,
                        f"#{config['idx']} 투자금": inv
                    })
                all_results.append(pd.DataFrame(history).set_index("날짜"))

            if all_results:
                res = pd.concat(all_results, axis=1)
                res['총평가금'] = res.filter(like='평가금').sum(axis=1)
                res['총투자금'] = res.filter(like='투자금').sum(axis=1)
                res['총분배금'] = res.filter(like='분배금').sum(axis=1)
                
                f = res.iloc[-1]
                st.divider()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
                c2.metric("마지막 달 분배금", f"{int(f['총분배금']):,}원")
                roi = ((f['총평가금']-f['총투자금'])/f['총투자금']*100) if f['총투자금'] > 0 else 0
                c3.metric("누적 수익률", f"{roi:.1f}%")
                
                st.line_chart(res[['총평가금', '총투자금']])
                
                with st.expander("📝 상세 내역 확인"):
                    formatted_df = res.fillna(0).copy()
                    for col in formatted_df.columns:
                        formatted_df[col] = formatted_df[col].apply(lambda x: f"{int(x):,}")
                    st.dataframe(formatted_df, use_container_width=True)
