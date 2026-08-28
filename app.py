# -*- coding: utf-8 -*-
"""
FermaAX™ Mobile QC Manager v3.0
기상 연동 AI 최적 처방 + 공정 결과 모바일 실시간 기록 시스템
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, date

# 1. 모바일 최적화 페이지 설정
st.set_page_config(
    page_title="FermaAX - 발효 AI 처방 & QC 기록",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed"  # 모바일 화면 공간 확보를 위해 사이드바 기본 접힘
)

# 2. SQLite 데이터베이스 초기화 함수
DB_FILE = "ferma_qc_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS qc_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_time TEXT,
            manufacture_date TEXT,
            tank_no TEXT,
            start_time TEXT,
            outdoor_temp REAL,
            indoor_temp REAL,
            rec_cooling REAL,
            actual_cooling REAL,
            rec_hotwater REAL,
            actual_5h_temp REAL,
            actual_duration INTEGER,
            final_acidity REAL,
            final_ph REAL,
            worker_name TEXT,
            memo TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# DB 데이터 저장 함수
def insert_qc_record(data_tuple):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO qc_records (
            record_time, manufacture_date, tank_no, start_time,
            outdoor_temp, indoor_temp, rec_cooling, actual_cooling,
            rec_hotwater, actual_5h_temp, actual_duration,
            final_acidity, final_ph, worker_name, memo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', data_tuple)
    conn.commit()
    conn.close()

# DB 데이터 조회 함수
def load_qc_records():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM qc_records ORDER BY id DESC", conn)
    conn.close()
    return df

# 3. 기상청 부산 기장군 실시간 기상 데이터 수집 함수
@st.cache_data(ttl=600)
def fetch_gijang_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=35.297&longitude=129.200&current_weather=true&"
            "daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FSeoul"
        )
        res = requests.get(url, timeout=5).json()
        curr_temp = res["current_weather"]["temperature"]
        min_temp = res["daily"]["temperature_2m_min"][0]
        max_temp = res["daily"]["temperature_2m_max"][0]
        return curr_temp, min_temp, max_temp, "기상청 정상 연동"
    except Exception:
        return 12.0, 5.0, 18.0, "오프라인 기본값 모드"

# 4. 4D 동적 최적화 연산 엔진
def calculate_dynamic_ferma_recipe(start_hour, t_in_curr, t_out_curr, t_min, t_max):
    time_steps = np.linspace(start_hour, start_hour + 6.3, 20)
    dt = time_steps - start_hour

    t_mean = (t_max + t_min) / 2.0
    t_swing = (t_max - t_min) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)
    t_in_traj = t_in_curr + 0.622 * (t_out_traj - t_out_curr) * (1.0 - np.exp(-dt / 2.5))

    early_mask = dt <= 1.5
    late_mask = dt > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    cooling = min(39.3, round(38.3 + max(0.0, (34.0 - t_eff_early) * 0.045), 1))
    hotwater = min(38.8, round(38.2 + max(0.0, (34.0 - t_eff_late) * 0.035), 1))
    tank_tt = min(39.2, round(38.5 + max(0.0, (34.0 - t_eff_late) * 0.030), 1))

    return {
        "time_steps": time_steps,
        "t_out_traj": t_out_traj,
        "t_in_traj": t_in_traj,
        "t_eff_early": round(t_eff_early, 1),
        "t_eff_late": round(t_eff_late, 1),
        "cooling_target": cooling,
        "hotwater_target": hotwater,
        "tank_tt_target": tank_tt
    }

# 5. 메인 앱 상단 헤더
st.title("🧪 FermaAX™ 모바일 QC 매니저")
curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
st.caption(f"부산 기장군 외기: **{curr_t}℃** (최저 {min_t}℃ / 최고 {max_t}℃) | {weather_status}")

# 6. 상단 탭 메뉴 구성
tab1, tab2, tab3 = st.tabs(["🎯 1. AI 최적 처방 조회", "📝 2. 당일 공정 실적 기록", "📊 3. 누적 이력 및 분석"])

# ==========================================
# 탭 1: AI 최적 처방 조회
# ==========================================
with tab1:
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        indoor_temp = st.slider("현재 발효실 실내온도 (℃)", 15.0, 40.0, 24.5, 0.1)
    with col_input2:
        now = datetime.now()
        default_start_hour = float(now.hour + now.minute / 60.0)
        start_hour = st.slider("작업 착수 예정 시각 (시)", 0.0, 23.5, round(default_start_hour, 1), 0.5, format="%.1f시")

    res = calculate_dynamic_ferma_recipe(start_hour, indoor_temp, curr_t, min_t, max_t)

    st.markdown("#### 🎯 HMI 설정 권장값")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### 1. 살균냉각 (투입)")
        st.markdown(f"<h1 style='color:#1f77b4; font-size:38px;'>{res['cooling_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("초반 과발효 억제")
    with c2:
        st.markdown("### 2. 핫워터 (재킷)")
        st.markdown(f"<h1 style='color:#2ca02c; font-size:38px;'>{res['hotwater_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("5H 액온 보온 유지")
    with c3:
        st.markdown("### 3. 발효탱크 TT")
        st.markdown(f"<h1 style='color:#ff7f0e; font-size:38px;'>{res['tank_tt_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("탱크 목표 온도")

    st.divider()

    # 열환경 궤적 차트
    fig = go.Figure()
    time_labels = [f"{int(t%24):02d}:{int((t%1)*60):02d}" for t in res["time_steps"]]
    fig.add_trace(go.Scatter(x=time_labels, y=res["t_out_traj"], mode='lines', name='예상 외기온도', line=dict(color='#3b82f6', dash='dash')))
    fig.add_trace(go.Scatter(x=time_labels, y=res["t_in_traj"], mode='lines', name='예상 실내온도', line=dict(color='#10b981', width=3)))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="진행 시각", yaxis_title="온도(℃)")
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 탭 2: 당일 공정 실적 기록 (입력 폼)
# ==========================================
with tab2:
    st.markdown("#### 📝 배치별 실제 공정 및 품질 결과 입력")
    with st.form("qc_record_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            f_date = st.date_input("제조일자", value=date.today())
            f_tank = st.selectbox("발효탱크 번호", ["301호", "302호", "303호"])
            f_start_time = st.time_input("실제 착수 시각", value=datetime.now().time())
            f_worker = st.text_input("작업자 성명", placeholder="홍길동")
        with f_col2:
            f_actual_cooling = st.number_input("실제 살균냉각 투입온도 (℃)", min_value=35.0, max_value=45.0, value=float(res['cooling_target']), step=0.1)
            f_5h_temp = st.number_input("5시간 경과 실측액온 (℃)", min_value=35.0, max_value=42.0, value=39.5, step=0.1)
            f_duration = st.number_input("실제 발효 종결시간 (분)", min_value=300, max_value=450, value=378, step=1)
            f_acidity = st.number_input("최종 종결 산도", min_value=0.800, max_value=1.200, value=0.965, step=0.001, format="%.3f")
            f_ph = st.number_input("최종 종결 pH", min_value=4.00, max_value=5.50, value=4.70, step=0.01)

        f_memo = st.text_area("작업 메모 및 특이사항", placeholder="예: 외기 급랭으로 핫워터 수동 0.2도 추가 상향 조정함")

        submit_btn = st.form_submit_button("💾 공정 결과 DB 저장하기", use_container_width=True)

        if submit_btn:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record_tuple = (
                now_str, str(f_date), f_tank, f_start_time.strftime("%H:%M"),
                curr_t, indoor_temp, res['cooling_target'], f_actual_cooling,
                res['hotwater_target'], f_5h_temp, int(f_duration),
                float(f_acidity), float(f_ph), f_worker, f_memo
            )
            insert_qc_record(record_tuple)
            st.success("✅ 공정 실적 데이터가 성공적으로 저장되었음!")

# ==========================================
# 탭 3: 누적 이력 및 분석
# ==========================================
with tab3:
    st.markdown("#### 📊 누적 공정 이력 데이터베이스")
    history_df = load_qc_records()

    if history_df.empty:
        st.info("현재 저장된 공정 이력 데이터가 없음. [탭 2]에서 실적을 입력바람.")
    else:
        # 데이터프레임 표시
        st.dataframe(history_df, use_container_width=True)

        # CSV 다운로드 버튼
        csv = history_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 전체 QC 이력 CSV 다운로드 (엑셀 호환)",
            data=csv,
            file_name=f"ferma_qc_history_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # 품질 지표 트렌드 미니 차트
        st.markdown("##### 📈 최근 종결 산도 추이 (목표: 0.965)")
        chart_df = history_df.sort_values(by="id")
        fig_qc = go.Figure()
        fig_qc.add_trace(go.Scatter(x=chart_df["manufacture_date"], y=chart_df["final_acidity"], mode='lines+markers', name='실제 종결산도'))
        fig_qc.add_hline(y=0.965, line_dash="dash", line_color="green", annotation_text="골든배치 기준 (0.965)")
        fig_qc.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_qc, use_container_width=True)
