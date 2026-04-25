import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr

st.set_page_config(page_title="Test App")
st.title("✅ 앱 작동 확인")

# 1. 라이브러리 로드 확인
st.write("라이브러리 로드 성공!")

# 2. 환율 데이터 간단 테스트
try:
    rate_df = fdr.DataReader('USD/KRW', '2024-01-01')
    current_rate = rate_df['Close'].iloc[-1]
    st.success(f"데이터 통신 성공! 현재 환율: {current_rate}")
except Exception as e:
    st.error(f"데이터 호출 에러: {e}")

# 3. 입력 테스트
name = st.text_input("이름을 입력하세요", "홍길동")
st.write(f"{name}님, 환영합니다. 이 화면이 보인다면 앱은 정상입니다.")
