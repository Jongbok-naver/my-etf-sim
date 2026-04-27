import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta
import io

# 1. 한글 폰트 설정
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

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
        # 최신 환율 가져오기 (실패 시 기본값 1,350원)
        df = fdr.DataReader('USD/KRW', datetime.now() - timedelta(days=7))
        return float(df['Close'].iloc[-1])
    except:
        return 1350.0

def get_price_data(symbol, market):
    try:
        if market == "한국":
            df = fdr.DataReader(symbol)
        else:
            df = yf.download(symbol, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        st.error(f"{symbol} 데이터 로드 실패: {e}")
        return pd.DataFrame()

# --- UI 설정 ---
st.set_page_config(page_title="글로벌 멀티 ETF 시뮬레이터", layout="wide")
st.title("💰 글로벌 멀티 ETF 통합 시뮬레이터")
st.caption("포트폴리오별 자산 성장과 월별 예상 분배금을 시뮬레이션합니다.")

krx_list = get_krx_list()
current_usd_krw = get_exchange_rate()

with st.sidebar:
    st.header("📍 1단계: 포트폴리오 구성")
    num_etfs = st.slider("ETF 개수", 1, 3, 2)
    
    etf_configs = []
    for i in range(num_etfs):
        with st.expander(f"ETF #{i+1} 설정", expanded=True):
            market = st.radio(f"시장 #{i+1}", ["한국", "미국"], horizontal=True, key=f"m_{i}")
            
            if market == "한국":
                search = st.text_input(f"종목명/코드 검색", "미국AI", key=f"s_{i}")
                filtered = krx_list[
                    krx_list['Name'].str.contains(search, case=False, na=False) | 
                    krx_list['Code'].str.contains(search, case=False, na=False)
                ]
                if not filtered.empty:
                    sel = st.selectbox(f"종목 선택", filtered['Name'] + " (" + filtered['Code'] + ")", key=f"sel_{i}")
                    code = sel.split("(")[-1].replace(")", "")
                    name = sel.split(" (")
                else:
                    st.warning("결과 없음")
                    code, name = None, None
            else:
                code = st.text_input(f"티커 입력 (예: SCHD, JEPI)", "SCHD" if i==0 else "JEPI", key=f"c_{i}").upper()
                name = code

            init_qty = st.number_input(f"현재 보유 수량", min_value=0.0, value=10.0, key=f"q_{i}")
            monthly_val = st.number_input(f"월 적립금 (원)", min_value=0, value=300000, step=50000, key=f"v_{i}")
            dist_rate = st.number_input(f"예상 월 분배율 (%)", 0.0, 5.0, 0.8, step=0.1, key=f"d_{i}", help="월간 배당 수익률을 입력하세요.")
            
            etf_configs.append({
                'idx': i+1, 'code': code, 'name': name, 'market': market, 
                'init_qty': init_qty, 'monthly_val': monthly_val, 'dist_rate': dist_rate
            })

    st.header("⚙️ 2단계: 공통 시나리오")
    growth_scenario = st.select_slider("예상 연간 주가 성장률 (%)", options=[-10, -5, 0, 3, 5, 8, 10, 15, 20], value=5)
    reinvest_on = st.checkbox("분배금 재투자 하기", value=True)
    start_date = st.date_input("투자 시작일", datetime.now())
    end_date = st.date_input("예상 종료일", datetime(2030, 12, 31))

# --- 시뮬레이션 엔진 ---
if st.button("🚀 통합 시뮬레이션 시작", width="stretch"):
    if not all(c['code'] for c in etf_configs):
        st.error("모든 ETF를 선택해주세요.")
    else:
        with st.spinner("데이터 분석 및 시뮬레이션 중..."):
            results_by_etf = []
            for config in etf_configs:
                df_h = get_price_data(config['code'], config['market'])
                if df_h.empty: continue
                
                last_price = float(df_h['Close'].iloc[-1])
                if config['market'] == "미국":
                    last_price *= current_usd_krw
                
                curr_p, qty, invested = last_price, float(config['init_qty']), float(config['init_qty']) * last_price
                m_growth, m_dist = (1 + growth_scenario/100)**(1/12) - 1, (config['dist_rate']/100)
                
                months = pd.date_range(start_date, end_date, freq='MS')
                etf_data = []
                for i, date in enumerate(months):
                    if i > 0: curr_p *= (1 + m_growth)
                    
                    # 월 분배금 계산 (현재 자산 가치 기준)
                    monthly_income = (qty * curr_p) * m_dist
                    
                    if reinvest_on:
                        qty += monthly_income / curr_p
                    
                    qty += config['monthly_val'] / curr_p
                    invested += config['monthly_val']
                    
                    etf_data.append({
                        '날짜': date.strftime('%Y-%m'),
                        f"#{config['idx']} {config['name']}_평가금": qty * curr_p,
                        f"#{config['idx']} {config['name']}_분배금": monthly_income,
                        f"#{config['idx']} {config['name']}_투자금": invested
                    })
                results_by_etf.append(pd.DataFrame(etf_data).set_index('날짜'))

            final_df = pd.concat(results_by_etf, axis=1)
            
            # 총합 계산 (중복 컬럼 방지 로직 적용됨)
            eval_cols = [c for c in final_df.columns if '평가금' in c]
            dist_cols = [c for c in final_df.columns if '분배금' in c]
            inv_cols = [c for c in final_df.columns if '투자금' in c]
            
            final_df['총평가금액'] = final_df[eval_cols].sum(axis=1)
            final_df['총월분배금'] = final_df[dist_cols].sum(axis=1)
            final_df['총투자금'] = final_df[inv_cols].sum(axis=1)
            
            # --- 결과 리포트 ---
            st.divider()
            f_row = final_df.iloc[-1]
            i_row = final_df.iloc[0]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("최종 자산", f"{int(f_row['총평가금액']):,}원", 
                      delta=f"{int(f_row['총평가금액'] - f_row['총투자금']):,}원 수익")
            c2.metric("최종 월 분배금", f"{int(f_row['총월분배금']):,}원",
                      delta=f"{int(f_row['총월분배금'] - i_row['총월분배금']):,}원 증액")
            c3.metric("총 투입 원금", f"{int(f_row['총투자금']):,}원")
            c4.metric("누적 수익률", f"{((f_row['총평가금액']-f_row['총투자금'])/f_row['총투자금']*100):.1f}%")

            # 시각화 차트 (탭으로 구분)
            tab1, tab2 = st.tabs(["📈 자산 및 원금 성장", "💵 월 배당금 흐름"])
            with tab1:
                st.area_chart(final_df[['총평가금액', '총투자금']])
            with tab2:
                st.bar_chart(final_df['총월분배금'])

            with st.expander("📝 월별 상세 내역 (데이터 테이블)"):
                st.dataframe(final_df.style.format('{:,.0f}원'), width="stretch")

            # 엑셀 저장
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, sheet_name='시뮬레이션_상세')
            st.download_button(label="📥 시뮬레이션 결과 엑셀 저장", data=buffer.getvalue(), 
                               file_name=f"global_portfolio_{datetime.now().strftime('%y%m%d')}.xlsx")

st.info(f"💡 현재 환율: 1 USD = {current_usd_krw:,.2f} KRW (미국 종목은 원화 환산 시뮬레이션 적용)")
