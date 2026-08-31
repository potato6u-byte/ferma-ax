# -*- coding: utf-8 -*-
"""
FermaAX™ Real-Time Dynamic Optimizer v3.5
7~8월 골든배치 수렴형 4D 처방 + 시간대별 적정 액온 궤적 실시간 비교 모니터링
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, date

# 1. 페이지 설정
st.set_page_config(
    page_title="FermaAX - 발효 AI 처방 및 실시간 적정온도 추적",
    page_icon="🧪",
    layout="wide"
)

# 2. SQLite 데이터베이스 초기화
DB_FILE = "ferma_tracking.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 배치 메타 정보 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_meta (
            batch_id TEXT PRIMARY KEY,
            start_datetime TEXT,
            tank_no TEXT,
            indoor_temp REAL,
            outdoor_temp REAL,
            rec_cooling REAL,
            rec_hotwater REAL,
            rec_tank_tt REAL,
            status TEXT
        )
    ''')
    # 시간대별 실측 액온 로그 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS temp_tracking_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            elapsed_hours REAL,
            target_temp REAL,
            actual_temp REAL,
            log_time TEXT,
            FOREIGN KEY (batch_id) REFERENCES batch_meta (batch_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# DB 헬퍼 함수
def save_batch_meta(batch_id, start_dt, tank_no, in_t, out_t, cool_t, hw_t, tt_t):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO batch_meta 
        (batch_id, start_datetime, tank_no, indoor_temp, outdoor_temp, rec_cooling, rec_hotwater, rec_tank_tt, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
    ''', (batch_id, start_dt, tank_no, in_t, out_t, cool_t, hw_t, tt_t))
    conn.commit()
    conn.close()

def log_actual_temp(batch_id, elapsed_h, target_t, actual_t):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO temp_tracking_logs (batch_id, elapsed_hours, target_temp, actual_temp, log_time)
        VALUES (?, ?, ?, ?, ?)
    ''', (batch_id, elapsed_h, target_t, actual_t, now_str))
    conn.commit()
    conn.close()

def get_tracking_logs(batch_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM temp_tracking_logs WHERE batch_id = ? ORDER BY elapsed_hours ASC", conn, params=(batch_id,))
    conn.close()
    return df

def get_active_batches():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM batch_meta WHERE status = 'RUNNING' ORDER BY start_datetime DESC", conn)
    conn.close()
    return df

# 3. 기상청 API 연동 (부산 기장군 AWS 923)
@st.cache_data(ttl=600)
def fetch_gijang_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=35.297&longitude=129.200&current_weather=true&"
            "daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FSeoul"
        )
        res = requests.get(url, timeout=5).json()
        curr_t = res["current_weather"]["temperature"]
        min_t = res["daily"]["temperature_2m_min"][0]
        max_t = res["daily"]["temperature_2m_max"][0]
        return curr_t, min_t, max_t, "기상청 정상 연동"
    except Exception:
        return 12.0, 5.0, 18.0, "오프라인 기본값 모드"

# 4. 7~8월 골든배치 수렴형 4D 최적 처방 및 이상적 액온 궤적 엔진
def calculate_golden_trajectory(start_hour, t_in_curr, t_out_curr, t_min, t_max):
    time_steps = np.linspace(start_hour, start_hour + 6.3, 25) # 약 15분 단위
    elapsed_hours = time_steps - start_hour

    # 외기/내기 열역학 궤적 계산
    t_mean = (t_max + t_min) / 2.0
    t_swing = (t_max - t_min) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)
    t_in_traj = t_in_curr + 0.622 * (t_out_traj - t_out_curr) * (1.0 - np.exp(-elapsed_hours / 2.5))

    # 구간 분리 유효온도
    early_mask = elapsed_hours <= 1.5
    late_mask = elapsed_hours > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    # 7~8월 골든 수렴 처방 (상한선 클램핑)
    cooling_target = min(39.3, round(38.4 + max(0.0, (32.0 - t_eff_early) * 0.050), 1))
    hotwater_target = min(38.8, round(38.3 + max(0.0, (32.0 - t_eff_late) * 0.040), 1))
    tank_tt_target = min(39.2, round(38.5 + max(0.0, (32.0 - t_eff_late) * 0.035), 1))

    # 7~8월 실측 기반 시간대별 이상적 발효액온(Golden Curve) 생성
    # 0H(투입온도) -> 1.5H(미세 발열) -> 3.5H(피크 39.8℃) -> 5.0H(유지 39.5℃) -> 6.3H(선행 냉각 전 39.2℃)
    golden_temps = []
    for h in elapsed_hours:
        if h <= 1.5:
            # 투입 직후 발효열 발생 시작
            temp = cooling_target + (0.5 * (h / 1.5))
        elif h <= 3.5:
            # 주 발효기: 균주 대사열로 액온 상승 피크 도달
            temp = (cooling_target + 0.5) + (0.7 * ((h - 1.5) / 2.0))
        elif h <= 5.0:
            # 정상 발효 유지기: 골든 기준 39.5℃ 수렴
            temp = 39.7 - (0.2 * ((h - 3.5) / 1.5))
        else:
            # 종결 냉각 준비기
            temp = 39.5 - (0.3 * ((h - 5.0) / 1.3))
        golden_temps.append(round(temp, 2))

    return {
        "time_steps": time_steps,
        "elapsed_hours": elapsed_hours,
        "golden_temps": np.array(golden_temps),
        "upper_bound": np.array(golden_temps) + 0.3, # 허용 상한 (+0.3℃)
        "lower_bound": np.array(golden_temps) - 0.3, # 허용 하한 (-0.3℃)
        "cooling_target": cooling_target,
        "hotwater_target": hotwater_target,
        "tank_tt_target": tank_tt_target,
        "t_out_traj": t_out_traj,
        "t_in_traj": t_in_traj
    }

# 5. UI 헤더 구성
st.title("🧪 FermaAX™ 실시간 발효 적정온도 추적 & AI 처방 시스템")
curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
st.caption(f"부산 기장군 기상 연동 (외기 {curr_t}℃ | 일교차 {min_t}℃ ~ {max_t}℃) | 7~8월 골든배치 수렴형 트래커")
st.divider()

# 6. 상단 탭 메뉴 구성
tab1, tab2 = st.tabs(["🚀 1. 배치 착수 & 실시간 적정온도 추적 모니터링", "📋 2. 전체 진행 배치 관리"])

with tab1:
    col_ctrl1, col_ctrl2 = st.columns([1, 2])

    with col_ctrl1:
        st.subheader("⚙️ 공정 제어 및 착수 설정")
        selected_tank = st.selectbox("발효탱크 선택", ["301호 탱크", "302호 탱크", "303호 탱크"])
        indoor_temp = st.slider("현재 발효실 실내온도 (℃)", 15.0, 38.0, 24.5, 0.1)

        now = datetime.now()
        default_start_hour = float(now.hour + now.minute / 60.0)
        start_hour = st.slider("작업 착수 시각", 0.0, 23.5, round(default_start_hour, 1), 0.5, format="%.1f시")

        # 연산 실행
        calc_res = calculate_golden_trajectory(start_hour, indoor_temp, curr_t, min_t, max_t)

        st.markdown("---")
        st.markdown("##### 🎯 HMI 권장 입력 셋포인트")
        st.metric("1. 살균냉각설정 (투입)", f"{calc_res['cooling_target']} ℃", help="초반 과열 억제")
        st.metric("2. 핫워터설정 (재킷)", f"{calc_res['hotwater_target']} ℃", help="5H 보온 보상")
        st.metric("3. 발효탱크 TT", f"{calc_res['tank_tt_target']} ℃")

        batch_id_candidate = f"{date.today().strftime('%Y%m%d')}_{selected_tank[:3]}_{int(start_hour):02d}H"
        
        if st.button("🚀 이 설정으로 [배치 작업 시작]", use_container_width=True, type="primary"):
            start_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_batch_meta(
                batch_id_candidate, start_dt_str, selected_tank,
                indoor_temp, curr_t, calc_res['cooling_target'],
                calc_res['hotwater_target'], calc_res['tank_tt_target']
            )
            # 0H 초기값 자동 기록
            log_actual_temp(batch_id_candidate, 0.0, calc_res['cooling_target'], calc_res['cooling_target'])
            st.success(f"✅ [{batch_id_candidate}] 배치가 시작되었음!")

    with col_ctrl2:
        st.subheader("📈 시간대별 적정온도 궤적 vs 실측 액온 실시간 비교")
        
        # 현재 선택된 배치의 실제 기록 조회
        active_df = get_tracking_logs(batch_id_candidate)

        # Plotly 비교 차트 생성
        fig = go.Figure()
        time_labels = [f"{int(t%24):02d}:{int((t%1)*60):02d}" for t in calc_res["time_steps"]]

        # 1. 허용 적정 온도 밴드 (±0.3℃ Shading)
        fig.add_trace(go.Scatter(
            x=time_labels + time_labels[::-1],
            y=np.concatenate([calc_res["upper_bound"], calc_res["lower_bound"][::-1]]),
            fill='toself',
            fillcolor='rgba(46, 204, 113, 0.15)',
            line=dict(color='rgba(255,255,255,0)'),
            name='7~8월 적정 허용 밴드 (±0.3℃)',
            hoverinfo="skip"
        ))

        # 2. 7~8월 표준 골든 액온 커브
        fig.add_trace(go.Scatter(
            x=time_labels, y=calc_res["golden_temps"],
            mode='lines',
            name='7~8월 표준 적정 액온 (Golden Curve)',
            line=dict(color='#27ae60', width=2.5, dash='dash')
        ))

        # 3. 작업자 실측 액온 데이터 플롯
        if not active_df.empty:
            actual_time_labels = []
            for eh in active_df["elapsed_hours"]:
                t_val = start_hour + eh
                actual_time_labels.append(f"{int(t_val%24):02d}:{int((t_val%1)*60):02d}")

            fig.add_trace(go.Scatter(
                x=actual_time_labels, y=active_df["actual_temp"],
                mode='lines+markers',
                name='★ 현재 실제 액온 (Real)',
                marker=dict(size=9, color='#e74c3c', symbol='circle'),
                line=dict(color='#e74c3c', width=3)
            ))

        fig.update_layout(
            xaxis_title="발효 공정 진행 시각 (타임라인)",
            yaxis_title="발효조 내부 액온 (℃)",
            hovermode="x unified",
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 실측 액온 현장 입력 폼
        st.markdown("#### 📝 경과 시간대별 실측 액온 현장 입력")
        with st.form("input_temp_form"):
            i_col1, i_col2, i_col3 = st.columns(3)
            with i_col1:
                cur_elapsed = st.selectbox("경과 시간대 선택", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], format_func=lambda x: f"{x}시간 경과 시점")
            
            # 해당 시간대의 적정 목표온도 자동 조회
            idx_match = np.argmin(np.abs(calc_res["elapsed_hours"] - cur_elapsed))
            target_at_elapsed = calc_res["golden_temps"][idx_match]

            with i_col2:
                st.metric("해당 시점 적정 목표액온", f"{target_at_elapsed} ℃")

            with i_col3:
                input_act_temp = st.number_input("실측 액온(℃) 입력", min_value=35.0, max_value=43.0, value=float(target_at_elapsed), step=0.1)

            btn_log = st.form_submit_button("💾 실측 액온 기록 및 판정", use_container_width=True)
            if btn_log:
                log_actual_temp(batch_id_candidate, cur_elapsed, target_at_elapsed, input_act_temp)
                diff = input_act_temp - target_at_elapsed
                if abs(diff) <= 0.3:
                    st.success(f"✅ 정상 유지 중: 7~8월 골든 기준 대비 편차 {diff:+.2f}℃ (적정 범위 내)")
                elif diff < -0.3:
                    st.warning(f"⚠️ 저온 이탈 ({diff:+.2f}℃): 외기 냉각 손실 발생. 핫워터 설정을 0.2℃ 상향 조정 바람.")
                else:
                    st.error(f"🚨 과열 이탈 ({diff:+.2f}℃): 초반 과발효 위험. 재킷 냉각 확인 필요.")
                st.rerun()

with tab2:
    st.subheader("📋 실시간 가동 중인 배치 목록 및 상태")
    all_batches = get_active_batches()
    if all_batches.empty:
        st.info("현재 진행 중인 배치가 없음. [탭 1]에서 배치를 시작바람.")
    else:
        st.dataframe(all_batches, use_container_width=True)
