import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta
import io
import matplotlib.pyplot as plt

# 1. 서버 환경(리눅스)에서도 안 터지는 폰트 설정
plt.rcParams['axes.unicode_minus'] = False
# 서버에 한글 폰트가 없으므로, 차트 제목 등에서 한글이 깨질 수 있으나 
# 프로그램 자체가 멈추는(Oh no!) 현상을 막기 위해 설정을 최소화합니다.

@st.cache_data(ttl=3600)
def get_krx_list():
    try:
        df = fdr.StockListing('ETF/KR')
        df = df.rename(columns={'Symbol': 'Code'}) if 'Symbol' in df.columns else df
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
            df = fdr.DataReader(symbol)
        else:
            # 미국 ETF 데이터 로드 (서버 환경 대응)
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="10y")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        return pd.DataFrame()

# --- UI 설정 ---
st.set_page_config(page_title="Global Multi-ETF Simulator", layout="wide")
st.title("💰 글로벌 멀티 ETF 시뮬레이터")

krx_list = get_krx_list()
current_usd_krw = get_exchange_rate()

with st.sidebar:
    st.header("📍 1단계: 포트폴리오 구성")
    num_etfs = st.sidebar.slider("ETF 개수", 1, 3, 2)
    
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            market = st.radio(f"시장 #{i+1}", ["한국", "미국"], horizontal=True, key=f"m_{i}")
            
            if market == "한국":
                search = st.text_input(f"종목명/코드 검색", "미국AI", key=f"s_{i}")
                if not krx_list.empty:
                    filtered = krx_list[
                        krx_list['Name'].str.contains(search, case=False, na=False) | 
                        krx_list['Code'].str.contains(search, case=False, na=False)
                    ]
                    if not filtered.empty:
                        sel = st.selectbox(f"종목 선택", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                        code = sel.split("(")[-1].replace(")", "")
                        name = sel.split(" (")[0]
                    else:
                        st.warning("결과 없음")
                        code, name = None, None
                else: code, name = None, None
            else:
                code = st.text_input(f"티커 (예: QQQ, JEPI)", "QQQ" if i==0 else "JEPI", key=f"c_{i}").upper()
                name = code

            init_qty = st.number_input(f"현재 보유 수량", min_value=0.0, value=10.0, key=f"q_{i}")
            monthly_val = st.number_input(f"월 적립금 (원)", min_value=0, value=300000, step=50000, key=f"v_{i}")
            dist_rate = st.number_input(f"예상 월 분배율 (%)", 0.0, 5.0, 0.5, step=0.1, key=f"d_{i}")
            
            etf_configs.append({
                'idx': i+1, 'code': code, 'name': name, 'market': market, 
                'init_qty': init_qty, 'monthly_val': monthly_val, 'dist_rate': dist_rate
            })

    st.header("⚙️ 2단계: 공통 설정")
    growth_scenario = st.select_slider("연 성장률 (%)", options=[-10, -5, 0, 3, 5, 8, 10, 15, 20], value=5)
    reinvest_on = st.checkbox("분배금 재투자", value=True)
    end_date = st.date_input("종료일", datetime(2030, 12, 31))

# --- 실행 ---
if st.button("🚀 시뮬레이션 시작", use_container_width=True):
    valid_configs = [c for c in etf_configs if c['code']]
    if not valid_configs:
        st.error("ETF를 선택해 주세요.")
    else:
        with st.spinner("계산 중..."):
            results_by_etf = []
            for config in valid_configs:
                df_h = get_price_data(config['code'], config['market'])
                if df_h.empty: continue
                
                last_price = float(df_h['Close'].iloc[-1])
                if config['market'] == "미국": last_price *= current_usd_krw
                
                curr_p, qty, invested = last_price, float(config['init_qty']), float(config['init_qty']) * last_price
                m_growth, m_dist = (1 + growth_scenario/100)**(1/12)-1, (config['dist_rate']/100)
                
                months = pd.date_range(datetime.now(), end_date, freq='MS')
                etf_data = []
                for i, date in enumerate(months):
                    if i > 0: curr_p *= (1 + m_growth)
                    m_income = (qty * curr_p) * m_dist
                    if reinvest_on: qty += m_income / curr_p
                    qty += config['monthly_val'] / curr_p
                    invested += config['monthly_val']
                    etf_data.append({
                        '날짜': date.strftime('%Y-%m'),
                        f"#{config['idx']} {config['name']}_평가금": qty * curr_p,
                        f"#{config['idx']} {config['name']}_분배금": m_income,
                        f"#{config['idx']} {config['name']}_투자금": invested
                    })
                results_by_etf.append(pd.DataFrame(etf_data).set_index('날짜'))

            if results_by_etf:
                final_df = pd.concat(results_by_etf, axis=1)
                
                e_cols = [c for c in final_df.columns if '평가금' in c]
                d_cols = [c for c in final_df.columns if '분배금' in c]
                i_cols = [c for c in final_df.columns if '투자금' in c]
                
                final_df['총평가금액'] = final_df[e_cols].sum(axis=1)
                final_df['총월분배금'] = final_df[d_cols].sum(axis=1)
                final_df['총투자금'] = final_df[i_cols].sum(axis=1)
                
                f_row = final_df.iloc[-1]
                c1, c2, c3 = st.columns(3)
                c1.metric("최종 자산", f"{int(f_row['총평가금액']):,}원")
                c2.metric("최종 월분배금", f"{int(f_row['총월분배금']):,}원")
                c3.metric("누적 수익률", f"{((f_row['총평가금액']-f_row['총투자금'])/f_row['총투자금']*100):.1f}%")

                st.subheader("📈 자산 성장")
                st.line_chart(final_df[['총평가금액', '총투자금']])
                
                st.subheader("💵 월 분배금 흐름")
                st.bar_chart(final_df['총월분배금'])
                
                with st.expander("📝 상세 내역 보기"):
                    st.dataframe(final_df.style.format('{:,.0f}원'))
            else:
                st.error("데이터를 불러오지 못했습니다. 종목명을 확인해 주세요.")

st.info(f"💡 현재 환율: 1 USD = {current_usd_krw:,.2f} KRW")
