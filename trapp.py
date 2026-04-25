import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta
import io

# 에러 유발 가능성이 높은 matplotlib 설정 및 한글 폰트 관련 코드를 모두 제거했습니다.

@st.cache_data(ttl=3600)
def get_krx_list():
    try:
        df = fdr.StockListing('ETF/KR')
        if 'Symbol' in df.columns:
            df = df.rename(columns={'Symbol': 'Code'})
        return df[['Code', 'Name']].dropna()
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        df = fdr.DataReader('USD/KRW', datetime.now() - timedelta(days=7))
        return float(df['Close'].iloc[-1])
    except:
        return 1350.0

def get_price_data(symbol, market):
    try:
        if market == "한국":
            # 한국 데이터는 fdr 사용
            df = fdr.DataReader(symbol)
            return df
        else:
            # 미국 데이터는 yfinance 사용
            df = yf.download(symbol, period="10y", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
    except:
        return pd.DataFrame()

# --- UI 레이아웃 ---
st.set_page_config(page_title="ETF Simulator", layout="wide")
st.title("💰 글로벌 ETF 통합 시뮬레이터")

krx_list = get_krx_list()
usd_krw = get_exchange_rate()

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 투자 설정")
    num_etfs = st.slider("ETF 개수", 1, 3, 1)
    
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1}", expanded=True):
            market = st.radio(f"시장 #{i+1}", ["한국", "미국"], key=f"m_{i}")
            if market == "한국":
                search = st.text_input("종목명 검색", "KODEX 미국AI", key=f"s_{i}")
                filtered = krx_list[krx_list['Name'].str.contains(search, na=False)]
                if not filtered.empty:
                    sel = st.selectbox("종목 선택", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")[0]
                else:
                    code, name = None, None
            else:
                code = st.text_input("티커 입력 (예: QQQ)", "QQQ", key=f"c_{i}").upper()
                name = code
            
            qty = st.number_input("보유 수량", min_value=0.0, value=10.0, key=f"q_{i}")
            monthly = st.number_input("월 적립금(원)", min_value=0, value=300000, key=f"v_{i}")
            dist = st.number_input("월 분배율(%)", 0.0, 5.0, 0.5, key=f"d_{i}")
            
            etf_configs.append({'idx': i+1, 'code': code, 'name': name, 'market': market, 'qty': qty, 'monthly': monthly, 'dist': dist})

    st.header("📈 시나리오")
    growth = st.slider("연 성장률(%)", -10, 20, 5)
    reinvest = st.checkbox("분배금 재투자", value=True)
    months_count = st.number_input("투자 기간(개월)", 1, 360, 60)

# --- 계산 및 결과 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code']]
    if not valid_configs:
        st.error("종목을 선택해주세요.")
    else:
        all_dfs = []
        for config in valid_configs:
            df_h = get_price_data(config['code'], config['market'])
            if df_h.empty: continue
            
            p = float(df_h['Close'].iloc[-1])
            if config['market'] == "미국": p *= usd_krw
            
            q, inv = config['qty'], config['qty'] * p
            m_g, m_d = (1+growth/100)**(1/12)-1, config['dist']/100
            
            data = []
            for m in range(months_count + 1):
                if m > 0: p *= (1 + m_g)
                income = (q * p) * m_d
                if reinvest: q += income / p
                if m > 0:
                    q += config['monthly'] / p
                    inv += config['monthly']
                
                data.append({
                    "월": m,
                    f"#{config['idx']} 평가금": q * p,
                    f"#{config['idx']} 분배금": income,
                    f"#{config['idx']} 투자금": inv
                })
            all_dfs.append(pd.DataFrame(data).set_index("월"))
        
        if all_dfs:
            res = pd.concat(all_dfs, axis=1)
            # 중복 컬럼 합산
            res['총평가금'] = res[[c for c in res.columns if '평가금' in c]].sum(axis=1)
            res['총투자금'] = res[[c for c in res.columns if '투자금' in c]].sum(axis=1)
            res['총분배금'] = res[[c for c in res.columns if '분배금' in c]].sum(axis=1)
            
            f = res.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("최종 자산", f"{int(f['총평가금']):,}원")
            c2.metric("최종 월분배금", f"{int(f['총분배금']):,}원")
            c3.metric("수익률", f"{((f['총평가금']-f['총투자금'])/f['총투자금']*100):.1f}%")
            
            st.subheader("자산 성장 추이")
            st.line_chart(res[['총평가금', '총투자금']])
            
            st.subheader("월 분배금 추이")
            st.bar_chart(res['총분배금'])
            
            st.dataframe(res.astype(int))
