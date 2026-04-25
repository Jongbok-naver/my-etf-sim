import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="Global Multi-ETF", layout="wide")

# 2. 한국 ETF 리스트 로딩 (최적화 및 캐싱)
@st.cache_data(ttl=86400) # 하루 동안 캐시 보관
def get_kr_list():
    try:
        # StockListing이 무거울 수 있어 필요한 컬럼만 추출
        df = fdr.StockListing('ETF/KR')
        if 'Symbol' in df.columns:
            df = df.rename(columns={'Symbol': 'Code'})
        return df[['Code', 'Name']]
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

# 3. 가격 데이터 가져오기 (yfinance 방식 유지)
def get_price(symbol, market):
    try:
        ticker = f"{symbol}.KS" if market == "한국" and ".K" not in symbol else symbol
        data = yf.download(ticker, period="5d", progress=False)
        if data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            return float(data['Close'].iloc[-1].values)
        return float(data['Close'].iloc[-1])
    except:
        return None

# --- UI 메인 ---
st.title("💰 글로벌 ETF 통합 시뮬레이터")

kr_list = get_kr_list()
usd_krw = 1380.0 # 환율

with st.sidebar:
    st.header("📍 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 3, 2)
    
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            mkt = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}", horizontal=True)
            
            if mkt == "한국":
                # 한국 종목 검색 기능
                search_query = st.text_input(f"종목명 검색 #{i+1}", "KODEX 200", key=f"sq_{i}")
                if not kr_list.empty:
                    filtered = kr_list[kr_list['Name'].str.contains(search_query, case=False, na=False)]
                    if not filtered.empty:
                        # "이름 (코드)" 형식으로 선택박스 구성
                        selected = st.selectbox(f"종목 선택 #{i+1}", 
                                              filtered['Name'] + " (" + filtered['Code'] + ")", 
                                              key=f"sel_{i}")
                        code = selected.split("(")[-1].replace(")", "")
                        name = selected.split(" (")[0]
                    else:
                        st.warning("검색 결과가 없습니다.")
                        code, name = None, None
                else:
                    st.error("리스트를 불러올 수 없습니다.")
                    code, name = None, None
            else:
                # 미국 티커 직접 입력 (미국은 검색보다 티커가 정확함)
                code = st.text_input(f"미국 티커 입력 #{i+1}", "QQQ", key=f"c_{i}").upper()
                name = code
            
            init_qty = st.number_input(f"보유 수량 #{i+1}", min_value=0.0, value=10.0, key=f"q_{i}")
            monthly = st.number_input(f"월 적립금(원) #{i+1}", min_value=0, value=200000, key=f"v_{i}")
            dist = st.number_input(f"월 분배율(%) #{i+1}", 0.0, 5.0, 0.5, key=f"d_{i}")
            
            etf_configs.append({'idx': i+1, 'code': code, 'name': name, 'mkt': mkt, 'qty': init_qty, 'monthly': monthly, 'dist': dist})

    st.header("📈 시나리오")
    growth = st.slider("연 성장률(%)", -10, 20, 5)
    months_count = st.number_input("기간(개월)", 1, 600, 60)
    reinvest = st.checkbox("분배금 재투자", value=True)

# --- 계산 및 결과 출력 ---
if st.button("🚀 통합 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code']]
    if not valid_configs:
        st.error("종목을 제대로 선택해 주세요.")
    else:
        with st.spinner("데이터 분석 중..."):
            all_etf_results = []
            for config in valid_configs:
                price = get_price(config['code'], config['mkt'])
                if price is None: continue
                
                p = price * usd_krw if config['mkt'] == "미국" else price
                q, inv = float(config['qty']), float(config['qty']) * p
                m_g, m_d = (1 + growth/100)**(1/12) - 1, config['dist'] / 100
                
                history = []
                for m in range(months_count + 1):
                    if m > 0: p *= (1 + m_g)
                    div_income = (q * p) * m_d
                    if reinvest: q += div_income / p
                    if m > 0:
                        q += config['monthly'] / p
                        inv += config['monthly']
                    history.append({
                        "월": m,
                        f"#{config['idx']} 평가금": q * p,
                        f"#{config['idx']} 분배금": div_income,
                        f"#{config['idx']} 투자금": inv
                    })
                all_etf_results.append(pd.DataFrame(history).set_index("월"))

            if all_etf_results:
                res = pd.concat(all_etf_results, axis=1)
                res['총평가금'] = res[[c for c in res.columns if '평가금' in c]].sum(axis=1)
                res['총투자금'] = res[[c for c in res.columns if '투자금' in c]].sum(axis=1)
                res['총분배금'] = res[[c for c in res.columns if '분배금' in c]].sum(axis=1)
                
                f = res.iloc[-1]
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
                c2.metric("최종 월 분배금", f"{int(f['총분배금']):,}원")
                c3.metric("누적 수익률", f"{((f['총평가금']-f['총투자금'])/f['총투자금']*100):.1f}%")
                
                st.subheader("📈 성장 추이")
                st.line_chart(res[['총평가금', '총투자금']])
                st.subheader("💵 배당 흐름")
                st.bar_chart(res['총분배금'])
                with st.expander("📝 상세 내역 보기"):
                    st.dataframe(res.astype(int), use_container_width=True)
