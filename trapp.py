import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(page_title="ETF Simulator", layout="wide")

@st.cache_data(ttl=3600)
def get_kr_list():
    try:
        df = fdr.StockListing('ETF/KR')
        return df[['Symbol', 'Name']].dropna()
    except:
        return pd.DataFrame(columns=['Symbol', 'Name'])

@st.cache_data(ttl=3600)
def get_price(symbol, market):
    try:
        # 미국/한국 모두 fdr로 통합 호출 (가장 안정적)
        df = fdr.DataReader(symbol)
        return df
    except:
        return pd.DataFrame()

# 환율 정보
try:
    usd_krw = fdr.DataReader('USD/KRW').iloc[-1]['Close']
except:
    usd_krw = 1380.0

st.title("📱 스마트폰 호환 통합 시뮬레이터")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    num = st.slider("종목 수", 1, 3, 1)
    configs = []
    
    for i in range(num):
        with st.expander(f"종목 #{i+1}", expanded=True):
            mkt = st.radio("시장", ["한국", "미국"], key=f"m{i}", horizontal=True)
            if mkt == "한국":
                code = st.text_input("코드(6자리)", "465350", key=f"c{i}")
                name = "국내ETF"
            else:
                code = st.text_input("티커(예: QQQ)", "QQQ", key=f"c{i}").upper()
                name = code
            
            val = st.number_input("월 투자(원)", 0, 10000000, 300000, step=100000, key=f"v{i}")
            configs.append({'code': code, 'mkt': mkt, 'val': val})

    growth = st.slider("연 수익률(%)", -10, 20, 5)
    months = st.number_input("기간(개월)", 1, 600, 60)

# 시뮬레이션 실행
if st.button("🚀 실행하기", use_container_width=True):
    results = []
    for c in configs:
        df = get_price(c['code'], c['mkt'])
        if df.empty:
            st.error(f"{c['code']} 데이터를 찾을 수 없습니다.")
            continue
            
        p = float(df['Close'].iloc[-1])
        if c['mkt'] == "미국": p *= usd_krw
        
        # 단순 복리 계산 (에러 방지를 위해 로직 단순화)
        m_g = (1 + growth/100)**(1/12) - 1
        current_asset = 0
        total_invest = 0
        history = []
        
        for m in range(1, months + 1):
            current_asset = (current_asset + c['val']) * (1 + m_g)
            total_invest += c['val']
            history.append({"월": m, "자산": current_asset, "원금": total_invest})
        
        res_df = pd.DataFrame(history).set_index("월")
        results.append(res_df)

    if results:
        # 합산 및 출력
        final = pd.concat(results, axis=1).sum(axis=1, level=0) # 동일 컬럼 합산
        
        st.metric("최종 자산", f"{int(final['자산'].iloc[-1]):,}원")
        st.line_chart(final[['자산', '원금']])
        st.success("시뮬레이션 완료!")
