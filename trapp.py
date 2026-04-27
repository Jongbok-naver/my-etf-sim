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
        if df is not None and not df.empty:
            return df[['Symbol', 'Name']].rename(columns={'Symbol': 'Code'})
        return pd.DataFrame(columns=['Code', 'Name'])
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

# 3. 가격 데이터 로딩 (안정성 강화)
def get_current_price(symbol, market):
    try:
        ticker_symbol = f"{symbol}.KS" if market == "한국" else symbol
        # history보다 download가 서버 환경에서 조금 더 안정적입니다.
        df = yf.download(ticker_symbol, period="5d", interval="1d", progress=False)
        if df.empty:
            return None
        return float(df['Close'].iloc[-1])
    except:
        return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
usd_krw = 1380.0 # 필요시 1400 등으로 수정 가능

with st.sidebar:
    st.header("📍 포트폴리오 구성")
    # 초기 ETF 개수를 2개로 설정
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    etf_configs = []
    
    for i in range(num_etfs):
        # 초기 검색어 설정 (ETF1: 미국AI, ETF2: 배당)
        default_search = "미국AI" if i == 0 else ("배당" if i == 1 else "KODEX 200")
        
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                search = st.text_input(f"종목명 검색 #{i+1}", value=default_search, key=f"s_{i}")
                if not kr_list.empty:
                    filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)]
                    if not filtered.empty:
                        # 자동으로 첫 번째 항목 선택되도록 index=0 설정
                        sel = st.selectbox(f"종목 선택 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", index=0, key=f"sel_{i}")
                        code = sel.split("(")[-1].replace(")", "")
                        name = sel.split(" (")[0]
                    else:
                        st.warning("결과 없음")
                        code, name = None, None
                else:
                    code, name = None, None
            else:
                code = st.text_input(f"미국 티커 #{i+1}", "QQQ", key=f"c_{i}").upper()
                name = code
                
            q = st.number_input(f"현재 수량 #{i+1}", min_value=0.0, value=10.0, key=f"q_{i}")
            v = st.number_input(f"월 적립금(원) #{i+1}", min_value=0, value=300000, key=f"v_{i}")
            # 배당률: 연율 단위로 입력받도록 함
            d = st.number_input(f"연 분배율(%) #{i+1}", 0.0, 20.0, 1.0 if i==0 else 4.0, key=f"d_{i}")
            
            etf_configs.append({'idx':i+1, 'code':code, 'name':name, 'mkt':mkt, 'qty':q, 'val':v, 'dist':d})

    st.header("📅 시나리오 설정")
    start_date = st.date_input("투자 시작일", datetime.now())
    end_date = st.date_input("투자 종료일", datetime(2035, 12, 31))
    growth = st.slider("연 성장률(%)", -10, 20, 5)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 시뮬레이션 계산 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code'] is not None]
    
    if not valid_configs:
        st.error("종목이 선택되지 않았습니다.")
    elif start_date >= end_date:
        st.error("종료일은 시작일보다 이후여야 합니다.")
    else:
        with st.spinner("데이터 로딩 및 계산 중..."):
            months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            month_range = pd.date_range(start=start_date, periods=max(months_diff, 1) + 1, freq='MS')
            
            all_results = []
            for config in valid_configs:
                price = get_current_price(config['code'], config['mkt'])
                
                if price is None:
                    st.error(f"❌ '{config['name']}({config['code']})' 데이터를 가져오지 못했습니다.")
                    continue
                
                p = price * usd_krw if config['mkt'] == "미국" else price
                qty = float(config['qty'])
                inv = qty * p
                
                # 월간 성장률 및 월간 분배율 변환
                m_g = (1 + growth/100)**(1/12) - 1
                m_d = (config['dist'] / 100) / 12  # 연 분배율을 12로 나눔
                
                history = []
                for i, date in enumerate(month_range):
                    # 1. 자산 가치 상승 (두 번째 달부터)
                    if i > 0:
                        p *= (1 + m_g)
                    
                    # 2. 월 적립금 투입 (두 번째 달부터)
                    if i > 0:
                        qty += config['val'] / p
                        inv += config['val']
                    
                    # 3. 분배금 발생 및 재투자
                    div = (qty * p) * m_d
                    if reinvest:
                        qty += div / p
                    
                    history.append({
                        "날짜": date.strftime('%Y-%m'),
                        f"#{config['idx']} 평가금": qty * p,
                        f"#{config['idx']} 분배금": div,
                        f"#{config['idx']} 투자금": inv
                    })
                all_results.append(pd.DataFrame(history).set_index("날짜"))

            if all_results:
                res = pd.concat(all_results, axis=1)
                # 동일한 날짜의 데이터들을 합산
                res['총평가금'] = res.filter(like='평가금').sum(axis=1)
                res['총투자금'] = res.filter(like='투자금').sum(axis=1)
                res['총분배금'] = res.filter(like='분배금').sum(axis=1)
                
                f = res.iloc[-1]
                st.divider()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
                c2.metric("최종 월분배금", f"{int(f['총분배금']):,}원")
                roi = ((f['총평가금']-f['총투자금'])/f['총투자금']*100) if f['총투자금'] > 0 else 0
                c3.metric("누적 수익률", f"{roi:.1f}%")
                
                st.subheader("📈 자산 성장 추이")
                st.line_chart(res[['총평가금', '총투자금']])
                
                st.subheader("💵 월별 예상 분배금")
                st.bar_chart(res['총분배금'])
                
                with st.expander("📝 상세 내역 보기"):
                    # 결측치 처리 및 천 단위 콤마 포맷팅
                    formatted_df = res.fillna(0).copy()
                    for col in formatted_df.columns:
                        formatted_df[col] = formatted_df[col].apply(lambda x: f"{int(x):,}")
                    st.dataframe(formatted_df, use_container_width=True)

# --- 진행 팁 ---
# 1. ETF1에 '미국AI'를 입력하면 관련 한국 ETF가 자동 검색됩니다.
# 2. ETF2에 '배당'을 입력하면 고배당 ETF들이 검색됩니다.
# 3. '시뮬레이션 시작'을 누르면 환율 1380원 기준으로 계산이 시작됩니다.
