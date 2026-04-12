import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import io

# 1. 한글 폰트 설정
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

@st.cache_data(show_spinner="종목 리스트 업데이트 중...")
def get_stock_list():
    try:
        df = fdr.StockListing('ETF/KR')
        if 'Symbol' in df.columns: df = df.rename(columns={'Symbol': 'Code'})
        return df[['Code', 'Name']]
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame(columns=['Code', 'Name'])

def calculate_cagr(df):
    if len(df) < 20: return 0.0
    three_years_ago = df.index[-1] - timedelta(days=3*365)
    recent_df = df[df.index >= three_years_ago]
    if recent_df.empty or len(recent_df) < 2: return 0.0
    start_val = recent_df['Close'].iloc[0]
    end_val = recent_df['Close'].iloc[-1]
    years = (recent_df.index[-1] - recent_df.index[0]).days / 365.25
    return (end_val / start_val) ** (1 / years) - 1 if years > 0 else 0.0

st.set_page_config(page_title="ETF 적립 시뮬레이터", layout="wide")
st.title("💰 ETF 적립식 & 시나리오별 시뮬레이터")

stock_list = get_stock_list()
search_term = st.text_input("종목명 검색", "미국AI")

if not stock_list.empty:
    filtered = stock_list[
        stock_list['Name'].str.contains(search_term, case=False, na=False) | 
        stock_list['Code'].str.contains(search_term, na=False)
    ]
    if not filtered.empty:
        selected_display = st.selectbox("종목 선택", filtered['Name'] + " (" + filtered['Code'] + ")")
        target_code = selected_display.split("(")[-1].replace(")", "")
        target_name = selected_display.split(" (")[0]
    else:
        st.warning("검색 결과가 없습니다.")
        target_code = None

if target_code:
    with st.sidebar:
        st.header("⚙️ 투자 설정")
        initial_shares = st.number_input("현재 보유 수량 (주)", min_value=0, value=8418)
        monthly_invest = st.number_input("매월 추가 적립금 (원)", min_value=0, value=500000, step=100000)
        dist_rate_input = st.number_input("예상 월 분배율 (%)", min_value=0.0, max_value=5.0, value=1.25, step=0.1)
        reinvest_dist = st.checkbox("월 분배금 재투자 여부", value=True)
        
        st.divider()
        growth_option = st.radio(
            "미래 주가 성장률 설정",
            ["반영 안함 (0%)", "최근 3년 CAGR 반영", "연 3% 고정 성장 반영"]
        )
        
        start_date = st.date_input("투자 시작일", value=datetime.now().date())
        end_date = st.date_input("예상 종료일", value=datetime(2032, 6, 30))

    if st.button("🚀 시뮬레이션 실행"):
        df_history = fdr.DataReader(target_code)
        if df_history.empty:
            st.error("데이터 로드 실패")
        else:
            # 성장률 결정
            if growth_option == "반영 안함 (0%)":
                applied_cagr = 0.0
            elif growth_option == "최근 3년 CAGR 반영":
                applied_cagr = calculate_cagr(df_history)
            else: # 연 3% 고정 성장
                applied_cagr = 0.03
            
            monthly_growth = (1 + applied_cagr) ** (1/12) - 1
            monthly_dist_rate = dist_rate_input / 100
            
            st.info(f"📊 **선택된 시나리오**: 연평균 성장률 **{applied_cagr*100:.2f}%** 적용")

            # 초기값 설정
            total_shares = float(initial_shares)
            current_price = df_history['Close'].iloc[-1]
            initial_price = current_price
            initial_asset = total_shares * initial_price
            initial_monthly_dist = total_shares * (initial_price * monthly_dist_rate)
            
            total_invested = initial_asset
            history = []
            sim_months = pd.date_range(start=start_date, end=end_date, freq='MS')
            
            for i, date in enumerate(sim_months):
                if i > 0: current_price *= (1 + monthly_growth)
                dist_income = total_shares * (current_price * monthly_dist_rate)
                if reinvest_dist:
                    total_shares += dist_income / current_price
                total_shares += monthly_invest / current_price
                total_invested += monthly_invest
                history.append({
                    '회차': f"{i+1}회차", '날짜': date.strftime('%Y-%m'), '현재주가': current_price, 
                    '투자원금': total_invested, '평가금액': total_shares * current_price, 
                    '보유수량': total_shares, '월분배금': total_shares * (current_price * monthly_dist_rate)
                })

            res_df = pd.DataFrame(history)
            f_row = res_df.iloc[-1]
            
            st.divider()
            st.subheader(f"🏁 {target_name} ({target_code}) 결과 요약")
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("💰 최종 자산", f"{int(f_row['평가금액']):,}원", delta=f"{int(f_row['평가금액'] - total_invested):,}원 수익")
            col_b.metric("📦 최종 수량", f"{int(f_row['보유수량']):,}주", delta=f"{int(f_row['보유수량'] - initial_shares):,}주 증량")
            col_c.metric("💵 최종 월 분배금", f"{int(f_row['월분배금']):,}원", delta=f"{int(f_row['월분배금'] - initial_monthly_dist):,}원 증액")
            col_d.metric("📈 누적 수익률", f"{((f_row['평가금액'] - total_invested) / total_invested * 100):.2f}%")

            st.dataframe(res_df.style.format({
                '현재주가': '{:,.0f}원', '투자원금': '{:,.0f}원', '평가금액': '{:,.0f}원', 
                '보유수량': '{:,.0f}주', '월분배금': '{:,.0f}원'
            }), width="stretch", height=500)

            # 저장 기능
            st.divider()
            st.subheader("📁 데이터 저장")
            file_name_input = st.text_input("저장할 파일명 입력", value=f"시뮬레이션_{target_name}")
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                res_df.to_excel(writer, sheet_name='상세내역', index=False)
                summary_data = {
                    "항목": ["종목명", "투자코드", "성장률시나리오", "최종자산", "최종수량", "최종 예상 월 분배금", "누적수익률"],
                    "내용": [target_name, target_code, growth_option, f"{int(f_row['평가금액']):,}원", f"{int(f_row['보유수량']):,}주", f"{int(f_row['월분배금']):,}원", f"{((f_row['평가금액'] - total_invested) / total_invested * 100):.2f}%"]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='요약', index=False)
            
            st.download_button(
                label="📁 엑셀 파일 다운로드",
                data=buffer.getvalue(), file_name=f"{file_name_input}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
