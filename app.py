# -*- coding: utf-8 -*-
"""
FermaAX™ Step-by-Step Smart Process Optimizer v4.0
공정별(A100~A400) 순차 진행 및 시·분·초 실시간 연동 제어 시스템
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, time, date

# 1. 페이지 설정
st.set_page_config(
    page_title="FermaAX - 공정별 단계식 AI 제어 시스템",
    page_icon="🧪",
    layout="wide"
)

# 2. 로컬 SQLite DB 초기화
DB_FILE = "ferma_process_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS process_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_date TEXT,
            tank_no TEXT,
            start_time_str TEXT,
            outdoor_temp REAL,
            indoor_temp REAL,
            cooling_target REAL,
            hotwater_target REAL,
            tank_tt_target REAL,
            actual_5h_temp REAL,
            final_duration INTEGER,
            final_acidity REAL,
            completed_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 3. 부산 기장군 실시간 기상 데이터 수집 함수
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
        return 12.0, 5.0, 18.0, "오프라인 기본값"

# 4. 4D 동적 최적화 연산 엔진
def calculate_ferma_recipe(start_hour_float, t_in_curr, t_out_curr, t_min, t_max):
    time_steps = np.linspace(start_hour_float, start_hour_float + 6.3, 20)
    dt = time_steps - start_hour_float

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

# 5. 세션 상태(Session State) 관리
if "process_step" not in st.session_state:
    st.session_state.process_step = 0  # 0: 대기, 1: A100, 2: A200, 3: A300, 4: A400, 5: 완료

if "captured_start_time" not in st.session_state:
    st.session_state.captured_start_time = datetime.now()

if "edit_time_mode" not in st.session_state:
    st.session_state.edit_time_mode = False

if "tank_no" not in st.session_state:
    st.session_state.tank_no = "301호"

# 6. 상단 헤더 및 기상 현황
curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
st.title("🧪 FermaAX™ 스마트 발효공정 단계별 제어기")
st.caption(f"부산 기장군 외기: **{curr_t}℃** (최저 {min_t}℃ / 최고 {max_t}℃) | {weather_status}")
st.divider()

# 7. 기본 공정 환경 및 착수 시각 관리 바
col_top1, col_top2, col_top3 = st.columns([2, 2, 3])

with col_top1:
    st.session_state.tank_no = st.selectbox("발효탱크 선택", ["301호", "302호", "303호"], index=0)

with col_top2:
    indoor_temp = st.number_input("발효실 실내온도 (℃)", min_value=10.0, max_value=40.0, value=24.5, step=0.1)

with col_top3:
    # 시간 인식 및 수정 인터페이스
    cap_time = st.session_state.captured_start_time
    time_display = cap_time.strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(f"**현재 작업 인식 시각:** `{time_display}`")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("✏️ 시간 수정하기", use_container_width=True):
            st.session_state.edit_time_mode = not st.session_state.edit_time_mode
    with col_btn2:
        if st.button("🔄 현재 시간으로 재동기화", use_container_width=True):
            st.session_state.captured_start_time = datetime.now()
            st.session_state.edit_time_mode = False
            st.rerun()

    if st.session_state.edit_time_mode:
        st.info("수정할 시·분·초를 입력하고 [수정 완료]를 누름.")
        c_h, c_m, c_s = st.columns(3)
        new_h = c_h.number_input("시 (Hour)", 0, 23, cap_time.hour)
        new_m = c_m.number_input("분 (Minute)", 0, 59, cap_time.minute)
        new_s = c_s.number_input("초 (Second)", 0, 59, cap_time.second)
        if st.button("💾 시간 수정 확정", use_container_width=True):
            st.session_state.captured_start_time = cap_time.replace(hour=new_h, minute=new_m, second=new_s)
            st.session_state.edit_time_mode = False
            st.success("작업 시각이 수정되었음.")
            st.rerun()

# 8. AI 처방값 연산 (인식된 시각 기준)
start_hour_float = cap_time.hour + cap_time.minute / 60.0 + cap_time.second / 3600.0
recipe = calculate_ferma_recipe(start_hour_float, indoor_temp, curr_t, min_t, max_t)

st.divider()

# 9. 공정 단계별 UI 렌더링

steps_name = ["대기", "A100 (원유 살균/준비)", "A200 (살균냉각/접종)", "A300 (발효/핫워터)", "A400 (냉각/이송)", "공정 완료"]
st.progress(st.session_state.process_step / 5.0, text=f"현재 진행 공정: **{steps_name[st.session_state.process_step]}**")

# -------------------------------------------------------------
# STEP 0: 작업 대기 상태
# -------------------------------------------------------------
if st.session_state.process_step == 0:
    st.info("💡 모든 준비가 완료되면 아래 [▶ 공정 시작 (A100 착수)] 버튼을 누름.")
    if st.button("▶ 공정 시작 (A100 착수)", type="primary", use_container_width=True):
        st.session_state.process_step = 1
        st.rerun()

# -------------------------------------------------------------
# STEP 1: A100 공정 (원유 살균 및 준비)
# -------------------------------------------------------------
elif st.session_state.process_step == 1:
    st.subheader("📍 [A100 공정] 원유 살균 및 설비 라인 준비 단계")
    st.write("• **작업 내용:** 원유 계량, 살균기 가동(95℃ 살균), 발효탱크 SIP 살균 점검")
    st.write("• **현재 단계 제어 특이사항:** 별도 외기 보상 온도 설정 없음 (표준 살균 가동)")
    
    st.divider()
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("◀ 작업 취소 (대기로 복귀)", use_container_width=True):
            st.session_state.process_step = 0
            st.rerun()
    with col_nav2:
        if st.button("A100 완료 ➔ 다음 공정 [A200 살균냉각] 이동", type="primary", use_container_width=True):
            st.session_state.process_step = 2
            st.rerun()

# -------------------------------------------------------------
# STEP 2: A200 공정 (살균냉각 및 균주 접종) - ★ 온도설정 필요
# -------------------------------------------------------------
elif st.session_state.process_step == 2:
    st.subheader("📍 [A200 공정] 살균냉각 및 원유 투입 / 종균 접종 단계")
    st.warning("⚠️ **[온도 설정 필수]** 당일 기상 및 실내외 편차에 맞춘 AI 살균냉각온도를 확인하고 HMI에 입력바람.")

    st.markdown("### 🎯 A200 AI 권장 설정값")
    c_box1, c_box2 = st.columns([1, 2])
    with c_box1:
        st.markdown("#### 1. 살균냉각온도 (투입)")
        st.markdown(f"<h1 style='color:#1f77b4; font-size:48px;'>{recipe['cooling_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("초반 급속 과발효 및 산도 폭주 방지 셋포인트")
    with c_box2:
        st.info(f"""
        • **착수 시각 기준 유효 초기환경:** {recipe['t_eff_early']} ℃
        • **작업 지침:** 살균기 냉각 밸브를 **{recipe['cooling_target']} ℃**로 맞추고 원유를 탱크에 투입함.
        • 과거 동절기처럼 41℃ 이상으로 과열 투입하지 않도록 주의함.
        """)

    st.divider()
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("◀ 이전 공정 (A100)", use_container_width=True):
            st.session_state.process_step = 1
            st.rerun()
    with col_nav2:
        if st.button("A200 접종 완료 ➔ 다음 공정 [A300 발효] 이동", type="primary", use_container_width=True):
            st.session_state.process_step = 3
            st.rerun()

# -------------------------------------------------------------
# STEP 3: A300 공정 (발효 유지 및 모니터링) - ★ 온도설정 필요
# -------------------------------------------------------------
elif st.session_state.process_step == 3:
    st.subheader("📍 [A300 공정] 발효 유지 및 핫워터(재킷) 보온 제어 단계")
    st.warning("⚠️ **[온도 설정 필수]** 중후반 방열 손실을 방지하기 위한 핫워터 및 탱크 목표 TT를 HMI에 입력바람.")

    col_val1, col_val2 = st.columns(2)
    with col_val1:
        st.markdown("#### 2. 핫워터 설정온도 (재킷)")
        st.markdown(f"<h1 style='color:#2ca02c; font-size:44px;'>{recipe['hotwater_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("중기(3~5H) 방열 손실 보상용 재킷 순환수 온도")
    with col_val2:
        st.markdown("#### 3. 발효탱크 목표 TT")
        st.markdown(f"<h1 style='color:#ff7f0e; font-size:44px;'>{recipe['tank_tt_target']} ℃</h1>", unsafe_allow_html=True)
        st.caption("발효조 내부 유지 목표 온도")

    st.markdown("---")
    st.markdown("##### ⏱️ 5시간(300분) 경과 시점 중간 점검")
    actual_5h_t = st.number_input("5시간 경과 실측 액온 (℃) [골든 기준: 39.5℃]", min_value=35.0, max_value=42.0, value=39.5, step=0.1)

    st.divider()
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("◀ 이전 공정 (A200)", use_container_width=True):
            st.session_state.process_step = 2
            st.rerun()
    with col_nav2:
        if st.button("5H 점검 완료 ➔ 다음 공정 [A400 냉각/종결] 이동", type="primary", use_container_width=True):
            st.session_state.actual_5h_t = actual_5h_t
            st.session_state.process_step = 4
            st.rerun()

# -------------------------------------------------------------
# STEP 4: A400 공정 (선행 냉각 및 종결/이송) - ★ 냉각 시점 판단
# -------------------------------------------------------------
elif st.session_state.process_step == 4:
    st.subheader("📍 [A400 공정] 선행 냉각 개시 및 발효 종결/이송 단계")
    st.info("💡 최종 목표 산도(0.965)에 도달하기 전, 후산도(+0.035)를 감안한 **선행 냉각 트리거**를 준수바람.")

    c_cool1, c_cool2 = st.columns(2)
    with c_cool1:
        st.markdown("### ❄️ 냉각 개시 산도 기준")
        st.markdown("<h2 style='color:#0284c7;'>산도 0.925 ~ 0.930 도달 시</h2>", unsafe_allow_html=True)
        st.caption("도달 즉시 1차 예냉(39.5℃ ➔ 25℃) 밸브 OPEN")
    with c_cool2:
        st.markdown("### ⏱️ 예상 냉각 개시 시점")
        st.markdown("<h2 style='color:#0284c7;'>접종 후 약 345~355분 시점</h2>", unsafe_allow_html=True)
        st.caption("예상 총 발효 종결시간: 378~380분")

    st.markdown("---")
    st.markdown("##### 📝 최종 결과 입력 및 DB 저장")
    f_c1, f_c2 = st.columns(2)
    with f_c1:
        final_dur = st.number_input("실제 총 종결시간 (분)", min_value=300, max_value=450, value=378, step=1)
    with f_c2:
        final_acid = st.number_input("최종 완제품 산도", min_value=0.800, max_value=1.200, value=0.965, step=0.001, format="%.3f")

    st.divider()
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("◀ 이전 공정 (A300)", use_container_width=True):
            st.session_state.process_step = 3
            st.rerun()
    with col_nav2:
        if st.button("💾 배치 완료 및 결과 DB 저장", type="primary", use_container_width=True):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO process_logs (
                    batch_date, tank_no, start_time_str, outdoor_temp,
                    indoor_temp, cooling_target, hotwater_target,
                    tank_tt_target, actual_5h_temp, final_duration,
                    final_acidity, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(date.today()), st.session_state.tank_no,
                st.session_state.captured_start_time.strftime("%H:%M:%S"),
                curr_t, indoor_temp, recipe['cooling_target'],
                recipe['hotwater_target'], recipe['tank_tt_target'],
                getattr(st.session_state, 'actual_5h_t', 39.5),
                int(final_dur), float(final_acid),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
            st.session_state.process_step = 5
            st.rerun()

# -------------------------------------------------------------
# STEP 5: 공정 완료 및 요약
# -------------------------------------------------------------
elif st.session_state.process_step == 5:
    st.success("🎉 배치가 성공적으로 완료되었으며 모든 공정 데이터가 데이터베이스에 안전하게 기록되었음!")
    
    conn = sqlite3.connect(DB_FILE)
    df_logs = pd.read_sql_query("SELECT * FROM process_logs ORDER BY id DESC LIMIT 5", conn)
    conn.close()
    
    st.markdown("##### 📊 최근 완료 배치 이력")
    st.dataframe(df_logs, use_container_width=True)
    
    if st.button("🔄 새로운 배치 시작하기", type="primary", use_container_width=True):
        st.session_state.process_step = 0
        st.session_state.captured_start_time = datetime.now()
        st.rerun()
