import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta
import io

# [수정] 에러가 발생하는 matplotlib 관련 설정 9~12번 줄을 삭제했습니다.
# Streamlit 내장 차트를 사용하므로 이 부분이 없어도 그래프가 잘 나옵니다.

@st.cache_data(show_spinner="시장 데이터 업데이트 중...")
def get_krx_list():
    try:
        df = fdr.StockListing('ETF/KR')
        df = df.rename(columns={'Symbol': 'Code'}) if 'Symbol' in df.columns else df
        return df[['Code', 'Name']].dropna()
    except:
        return pd.DataFrame(columns=['Code', 'Name'])

@st.cache_data
def get_exchange_rate():
    try:
        df = fdr.DataReader('USD/KRW', datetime.now() - timedelta(days=7))
        return float(df['Close'].iloc[-1])
    except:
        return 1380.0 # 기본값

def get_price_data(symbol, market):
    try:
        if market == "한국":
            df = fdr.DataReader(symbol)
        else:
            # yfinance 멀티인덱스 오류 방지 로직 추가
            df = yf.download(symbol, period="5d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        return df
    except:
        return pd.DataFrame()

# --- UI 설정 ---
st.set_page_config(page_title="글로벌 멀티 ETF 시뮬레이터", layout="wide")
st.title("💰 글로벌 멀티 ETF 통합 시뮬레이터")

krx_list = get_krx_list()
current_usd_krw = get_exchange_rate()

with st.sidebar:
    st.header("📍 1단계: 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 5, 2)
    etf_configs = []
    
    for i in range(num_etfs):
        # [추가] 요청하신 초기 데이터 설정
        if i == 0: # ETF #1
            d_mkt, d_search, d_qty, d_pay, d_dist = "한국", "미국AI", 5090.0, 0, 1.25
        elif i == 1: # ETF #2
            d_mkt, d_search, d_qty, d_pay, d_dist = "한국", "배당", 3532.0, 500000, 1.75
        else:
            d_mkt, d_search, d_qty, d_pay, d_dist = "미국", "SCHD", 10.0, 300000, 0.3
            
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            market = st.radio(f"시장 #{i+1}", ["한국", "미국"], index=0 if d_mkt=="한국" else 1, horizontal=True, key=f"m_{i}")
            
            if market == "한국":
                search = st.text_input(f"종목명/코드 검색", value=d_search, key=f"s_{i}")
                filtered = krx_list[krx_list['Name'].str.contains(search, case=False, na=False)]
                if not filtered.empty:
                    sel = st.selectbox(f"종목 선택", filtered['Name'] + " (" + filtered['Code'] + ")", index=0, key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")
                else:
                    st.warning("결과 없음")
                    code, name = None, None
            else:
                code = st.text_input(f"티커 입력", value=d_search if d_mkt=="미국" else "QQQ", key=f"c_{i}").upper()
                name = code
                
            init_qty = st.number_input(f"현재 보유 수량", min_value=0.0, value=d_qty, key=f"q_{i}")
            monthly_val = st.number_input(f"월 적립금 (원)", min_value=0, value=d_pay, key=f"v_{i}")
            dist_rate = st.number_input(f"예상 월 분배율 (%)", 0.0, 10.0, value=d_dist, key=f"d_{i}")
            
            etf_configs.append({
                'idx': i+1, 'code': code, 'name': name, 'market': market,
                'init_qty': init_qty, 'monthly_val': monthly_val, 'dist_rate': dist_rate
            })

    st.header("⚙️ 2단계: 공통 시나리오")
    growth_scenario = st.select_slider("예상 연간 주가 성장률 (%)", options=[-10, -5, 0, 3, 5, 8, 10, 15, 20], value=5)
    reinvest_on = st.checkbox("분배금 재투자 하기", value=True)
    start_date = st.date_input("투자 시작일", datetime.now())
    end_date = st.date_input("예상 종료일", datetime(2035, 12, 31))

# --- 시뮬레이션 엔진 ---
if st.button("🚀 통합 시뮬레이션 시작", use_container_width=True):
    if not all(c['code'] for c in etf_configs):
        st.error("모든 ETF 종목을 선택해주세요.")
    else:
        with st.spinner("데이터 분석 중..."):
            results_by_etf = []
            for config in etf_configs:
                df_h = get_price_data(config['code'], config['market'])
                if df_h.empty: continue
                
                last_price = float(df_h['Close'].iloc[-1])
                if config['market'] == "미국":
                    last_price *= current_usd_krw
                
                curr_p, qty, invested = last_price, float(config['init_qty']), float(config['init_qty']) * last_price
                m_growth = (1 + growth_scenario/100)**(1/12) - 1
                m_dist = (config['dist_rate']/100)
                
                months = pd.date_range(start_date, end_date, freq='MS')
                etf_data = []
                for i, date in enumerate(months):
                    if i > 0: curr_p *= (1 + m_growth)
                    income = (qty * curr_p) * m_dist
                    if reinvest_on: qty += income / curr_p
                    if i > 0:
                        qty += config['monthly_val'] / curr_p
                        invested += config['monthly_val']
                    
                    etf_data.append({
                        '날짜': date.strftime('%Y-%m'),
                        f"#{config['idx']} {config['name']}_평가금": qty * curr_p,
                        f"#{config['idx']} {config['name']}_분배금": income,
                        f"#{config['idx']} {config['name']}_투자금": invested
                    })
                results_by_etf.append(pd.DataFrame(etf_data).set_index('날짜'))

            if results_by_etf:
                final_df = pd.concat(results_by_etf, axis=1)
                final_df['총평가금액'] = final_df.filter(like='평가금').sum(axis=1)
                final_df['총월분배금'] = final_df.filter(like='분배금').sum(axis=1)
                final_df['총투자금'] = final_df.filter(like='투자금').sum(axis=1)
                
                f_row = final_df.iloc[-1]
                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("최종 자산", f"{int(f_row['총평가금액']):,}원")
                c2.metric("최종 월 분배금", f"{int(f_row['총월분배금']):,}원")
                c3.metric("총 투입 원금", f"{int(f_row['총투자금']):,}원")
                roi = (f_row['총평가금액']-f_row['총투자금'])/f_row['총투자금']*100 if f_row['총투자금']>0 else 0
                c4.metric("누적 수익률", f"{roi:.1f}%")
                
                tab1, tab2 = st.tabs(["📈 자산 성장", "💵 분배금 흐름"])
                with tab1: st.area_chart(final_df[['총평가금액', '총투자금']])
                with tab2: st.bar_chart(final_df['총월분배금'])
                with st.expander("📝 상세 내역"):
                    st.dataframe(final_df.fillna(0).astype(int).style.format('{:,}'), use_container_width=True)
