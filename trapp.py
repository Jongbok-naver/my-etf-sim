import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Global Multi-ETF", layout="wide")

# 2. 한국 ETF 리스트 (캐싱 및 예외 처리)
@st.cache_data(ttl=86400)
def get_kr_list():
    try:
        df = fdr.StockListing('ETF/KR')
        if df is not None and not df.empty:
            return df[['Symbol', 'Name']].rename(columns={'Symbol': 'Code'})
        return pd.DataFrame(columns=['Code', 'Name'])
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

# 3. 가격 데이터 로딩 (가장 강력한 예외 처리)
def get_current_price(symbol, market):
    try:
        ticker_symbol = f"{symbol}.KS" if market == "한국" else symbol
        # 1일치 데이터만 아주 가볍게 가져옴
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1d")
        if df.empty:
            return None
        
        # 데이터 구조(멀티인덱스 등)에 상관없이 마지막 종가 추출
        last_price = df['Close'].iloc[-1]
        
        # 만약 결과가 Series라면 첫 번째 값 선택
        if isinstance(last_price, pd.Series):
            last_price = last_price.iloc[0]
        return float(last_price)
    except Exception as e:
        return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")
kr_list = get_kr_list()
usd_krw = 1380.0

with st.sidebar:
    st.header("📍 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 3, 1)
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            if mkt == "한국":
                search = st.text_input(f"종목명 검색 #{i+1}", "KODEX 200", key=f"s_{i}")
                if not kr_list.empty:
                    filtered = kr_list[kr_list['Name'].str.contains(search, na=False, case=False)]
                    if not filtered.empty:
                        sel = st.selectbox(f"종목 선택 #{i+1}", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
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
            d = st.number_input(f"월 분배율(%) #{i+1}", 0.0, 5.0, 0.5, key=f"d_{i}")
            etf_configs.append({'idx':i+1, 'code':code, 'name':name, 'mkt':mkt, 'qty':q, 'val':v, 'dist':d})

    st.header("📅 시나리오 설정")
    start_date = st.date_input("투자 시작일", datetime.now())
    end_date = st.date_input("투자 종료일", datetime(2030, 12, 31))
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
            if months_diff < 1:
                months_diff = 1
            month_range = pd.date_range(start=start_date, periods=months_diff + 1, freq='MS')
            all_results = []
            for config in valid_configs:
                price = get_current_price(config['code'], config['mkt'])
                if price is None:
                    st.error(f"❌ '{config['name']}({config['code']})'의 가격 데이터를 가져오지 못했습니다.")
                    continue
                p = price * usd_krw if config['mkt'] == "미국" else price
                qty, inv = float(config['qty']), float(config['qty']) * p
                m_g = (1 + growth/100)**(1/12) - 1
                m_d = config['dist'] / 100
                history = []
                for i, date in enumerate(month_range):
                    if i > 0:
                        p *= (1 + m_g)
                    div = (qty * p) * m_d
                    if reinvest:
                        qty += div / p
                    if i > 0:
                        qty += config['val'] / p
                        inv += config['val']
                    history.append({
                        "날짜": date.strftime('%Y-%m'),
                        f"#{config['idx']} 평가금": qty * p,
                        f"#{config['idx']} 분배금": div,
                        f"#{config['idx']} 투자금": inv
                    })
                all_results.append(pd.DataFrame(history).set_index("날짜"))

            if all_results:
                res = pd.concat(all_results, axis=1)
                res['총평가금'] = res[[c for c in res.columns if '평가금' in c]].sum(axis=1)
                res['총투자금'] = res[[c for c in res.columns if '투자금' in c]].sum(axis=1)
                res['총분배금'] = res[[c for c in res.columns if '분배금' in c]].sum(axis=1)
                f = res.iloc[-1]
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
                c2.metric("최종 월분배금", f"{int(f['총분배금']):,}원")
                c3.metric("누적 수익률", f"{((f['총평가금']-f['총투자금'])/f['총투자금']*100):.1f}%")
                st.subheader("📈 자산 성장 추이")
                st.line_chart(res[['총평가금', '총투자금']])
                st.subheader("💵 월별 예상 분배금")
                st.bar_chart(res['총분배금'])
                with st.expander("📝 상세 내역 보기"):
                    st.dataframe(res.astype(int), use_container_width=True)
