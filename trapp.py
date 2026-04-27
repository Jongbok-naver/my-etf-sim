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

# 3. 가격 데이터 로딩 (멀티인덱스 완벽 대응 및 타입 강제 변환)
def get_current_price(symbol, market):
    if not symbol: return None
    try:
        if market == "한국":
            # 한국은 fdr로 마지막 종가를 가져오는 것이 가장 확실함
            df = fdr.DataReader(symbol)
            if not df.empty:
                return float(df['Close'].iloc[-1])
        
        # 미국 시장 또는 한국 fdr 실패 시 yf 사용
        ticker_symbol = f"{symbol}.KS" if market == "한국" else symbol
        df = yf.download(ticker_symbol, period="5d", interval="1d", progress=False)
        
        if not df.empty:
            if 'Close' in df.columns:
                close_data = df['Close']
                target_val = close_data.iloc[-1, 0] if isinstance(close_data, pd.DataFrame) else close_data.iloc[-1]
                return float(target_val)
    except:
        pass
    return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
usd_krw = 1380.0

# 세션 상태 초기화 (종목 선택 유지를 위해)
if 'selected_codes' not in st.session_state:
    st.session_state.selected_codes = {}

with st.sidebar:
    st.header("📍 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    etf_configs = []
    
    for i in range(num_etfs):
        # 초기값 설정
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
                    # selectbox에서 선택 시 즉시 반영되도록 처리
                    options = (filtered['Name'] + " (" + filtered['Code'] + ")").tolist()
                    sel = st.selectbox(f"종목 선택 #{i+1}", options, key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")[0]
                else:
                    st.warning("결과 없음")
                    code, name = None, None
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
    growth = st.slider("기대 연 성장률(%)", -10, 20, 5)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 엔진 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code']]
    
    if not valid_configs:
        st.error("종목을 선택해주세요.")
    else:
        with st.spinner("선택하신 종목의 최신 주가를 가져오는 중..."):
            months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            month_range = pd.date_range(start=start_date, periods=max(months_diff, 1), freq='MS')
            
            all_results = []
            for config in valid_configs:
                # [핵심] 루프 안에서 각기 다른 code로 가격을 새로 호출함
                price = get_current_price(config['code'], config['mkt'])
                
                if price is None or price <= 0:
                    st.error(f"❌ {config['name']} ({config['code']}) 가격을 불러오지 못했습니다.")
                    continue
                
                # 원화 가격 환산
                p = price * usd_krw if config['mkt'] == "미국" else price
                qty = float(config['qty'])
                inv = qty * p 
                
                m_g = (1 + growth/100)**(1/12) - 1
                m_d = (config['dist'] / 100) / 12  
                
                history = []
                for i, date in enumerate(month_range):
                    if i > 0:
                        p *= (1 + m_g)
                        qty += config['val'] / p
                        inv += config['val']
                    
                    eval_amt = qty * p
                    div = eval_amt * m_d
                    if reinvest:
                        qty += div / p
                    
                    history.append({
                        "날짜": date.strftime('%Y-%m'),
                        f"#{config['idx']} 평가금": eval_amt,
                        f"#{config['idx']} 분배금": div,
                        f"#{config['idx']} 투자금": inv,
                        f"#{config['idx']} 가격": p # 확인용 가격 데이터 추가
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
                
                st.subheader("📈 자산 성장 곡선")
                st.line_chart(res[['총평가금', '총투자금']])
                
                with st.expander("📝 상세 데이터 보기 (종목별 가격 확인 가능)"):
                    formatted_df = res.fillna(0).copy()
                    # 가격 컬럼은 소수점까지 표시, 나머지는 콤마 적용
                    for col in formatted_df.columns:
                        if '가격' in col:
                            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:,.0f}")
                        else:
                            formatted_df[col] = formatted_df[col].apply(lambda x: f"{int(x):,}")
                    st.dataframe(formatted_df, use_container_width=True)
