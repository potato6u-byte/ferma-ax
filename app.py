# -*- coding: utf-8 -*-
"""
FermaAX™ Full-Process SCADA SOP & AI Temperature Controller v5.7
• A400(시럽 배합) & A500(시럽 살균) 개별 공정 분리
• 작업자 성명 디폴트: '공장장'
• 대한민국 표준시(KST) 대형 디지털 시계 & 실시간 총 경과/단계별 소요시간 연산
• 상단 7단계(A100~A700) 가로형 실시간 소요시간 카드 바 및 이전 단계 되돌리기 완비
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
from datetime import datetime, date, timedelta, timezone

# 0. 대한민국 표준시(KST) 타임존 및 시각 함수
try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone(timedelta(hours=9))

def get_kst_now():
    """대한민국 표준시(KST) 현재 시각 반환"""
    return datetime.now(KST)

def format_korean_ampm(dt_obj):
    """오전/오후 HH:MM:SS 한국어 시각 포맷 변환"""
    if not dt_obj:
        return ""
    ampm = "오전" if dt_obj.hour < 12 else "오후"
    return f"{ampm} {dt_obj.strftime('%H:%M:%S')}"

def format_time_delta(seconds_total):
    """소요 시간을 'X분' 또는 'X시간 Y분' 형태로 간결 변환"""
    if seconds_total < 0:
        seconds_total = 0
    mins = int(seconds_total // 60)
    hrs = int(mins // 60)
    rem_mins = int(mins % 60)
    if hrs > 0:
        return f"{hrs}시간 {rem_mins}분"
    elif mins > 0:
        return f"{mins}분"
    else:
        return f"{int(seconds_total)}초"

# 1. 반응형 페이지 설정
st.set_page_config(
    page_title="FermaAX - SCADA 공정 제어기",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. SQLite 데이터베이스 초기화
DB_FILE = "ferma_scada_v57.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_master (
            batch_id TEXT PRIMARY KEY,
            product_name TEXT,
            target_tank TEXT,
            worker_name TEXT,
            start_datetime TEXT,
            start_time_korean TEXT,
            outdoor_temp REAL,
            indoor_temp REAL,
            status TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS step_temperature_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            step_code TEXT,
            step_name TEXT,
            log_time TEXT,
            step_duration_str TEXT,
            scada_tag TEXT,
            ai_recommended_temp REAL,
            operator_set_temp REAL,
            actual_measured_temp REAL,
            action_status TEXT,
            FOREIGN KEY (batch_id) REFERENCES batch_master (batch_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_mqi_final (
            batch_id TEXT PRIMARY KEY,
            completed_at TEXT,
            actual_duration INTEGER,
            final_acidity REAL,
            final_ph REAL,
            viscosity_cp REAL,
            syneresis_rate REAL,
            taste_score REAL,
            mqi_total_score REAL,
            worker_memo TEXT,
            FOREIGN KEY (batch_id) REFERENCES batch_master (batch_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# DB 헬퍼 함수
def save_batch_start(batch_id, p_name, tank, worker, s_dt, s_korean, out_t, in_t):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO batch_master 
        (batch_id, product_name, target_tank, worker_name, start_datetime, start_time_korean, outdoor_temp, indoor_temp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
    ''', (batch_id, p_name, tank, worker, s_dt, s_korean, out_t, in_t))
    conn.commit()
    conn.close()

def log_step_temp(batch_id, step_code, step_name, step_dur_str, scada_tag, ai_rec, op_set, act_meas, status_txt):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO step_temperature_logs 
        (batch_id, step_code, step_name, log_time, step_duration_str, scada_tag, ai_recommended_temp, operator_set_temp, actual_measured_temp, action_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (batch_id, step_code, step_name, now_str, step_dur_str, scada_tag, ai_rec, op_set, act_meas, status_txt))
    conn.commit()
    conn.close()

def save_final_mqi(batch_id, duration, acidity, ph, visc, syn, taste, mqi, memo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO batch_mqi_final VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (batch_id, now_str, duration, acidity, ph, visc, syn, taste, mqi, memo))
    c.execute("UPDATE batch_master SET status = 'COMPLETED' WHERE batch_id = ?", (batch_id,))
    conn.commit()
    conn.close()

def get_step_logs(batch_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM step_temperature_logs WHERE batch_id = ? ORDER BY id ASC", conn, params=(batch_id,))
    conn.close()
    return df

def get_all_completed_batches():
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT b.batch_id, b.product_name, b.worker_name, b.start_time_korean,
               q.completed_at, q.actual_duration, q.final_acidity, q.final_ph,
               q.viscosity_cp, q.taste_score, q.mqi_total_score
        FROM batch_master b
        JOIN batch_mqi_final q ON b.batch_id = q.batch_id
        ORDER BY q.completed_at DESC
    '''
    df = pd.read_sql_query(query, conn)
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
        return 12.0, 5.0, 18.0, "오프라인 기본 안전모드"

# 4. 4D 동적 최적화 및 배관 열손실 연산 엔진
def calculate_optimal_temperatures(start_h, indoor_t, out_t, min_t, max_t):
    time_steps = np.linspace(start_h, start_h + 6.3, 25)
    dt = time_steps - start_h

    t_mean = (max_t + min_t) / 2.0
    t_swing = (max_t - min_t) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)
    t_in_traj = indoor_t + 0.622 * (t_out_traj - out_t) * (1.0 - np.exp(-dt / 2.5))

    early_mask = dt <= 1.5
    late_mask = dt > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    delta_t_pipe = round((1.85 * 8.35 * max(0.0, 38.4 - indoor_t)) / (2.083 * 3930), 2)

    rec_cooling = min(39.3, round(38.4 + max(0.0, (32.0 - t_eff_early) * 0.050) + delta_t_pipe, 1))
    rec_hotwater = min(38.8, round(38.3 + max(0.0, (32.0 - t_eff_late) * 0.040), 1))
    rec_tank_tt = min(39.2, round(38.5 + max(0.0, (32.0 - t_eff_late) * 0.035), 1))

    return {
        "rec_cooling": rec_cooling,
        "rec_hotwater": rec_hotwater,
        "rec_tank_tt": rec_tank_tt,
        "delta_t_pipe": delta_t_pipe,
        "t_eff_early": round(t_eff_early, 1),
        "t_eff_late": round(t_eff_late, 1)
    }

# 5. 세션 상태 관리
if "process_step" not in st.session_state:
    st.session_state.process_step = 0

if "batch_id" not in st.session_state:
    st.session_state.batch_id = ""

if "batch_start_dt" not in st.session_state:
    st.session_state.batch_start_dt = None

if "step_durations" not in st.session_state:
    st.session_state.step_durations = {}

if "step_entry_times" not in st.session_state:
    st.session_state.step_entry_times = {}

# 6. 상단 헤더 및 대한민국 표준시 디지털 시계
curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
kst_now = get_kst_now()

col_head_left, col_head_right = st.columns([1.8, 1.4])

with col_head_left:
    p_name_display = st.session_state.get("product_name", "런 발효유")
    st.title("🧪 FermaAX™ SCADA 단계별 공정 제어기")
    st.caption(f"생산품목: **{p_name_display}** | 기장군 외기 {curr_t}℃ ({min_t}℃~{max_t}℃) | {weather_status}")

with col_head_right:
    clock_time_str = kst_now.strftime("%H:%M:%S")
    ampm_kor = "오전" if kst_now.hour < 12 else "오후"
    
    total_elapsed_txt = ""
    if st.session_state.process_step > 0 and st.session_state.batch_start_dt:
        total_sec = (kst_now - st.session_state.batch_start_dt).total_seconds()
        total_elapsed_txt = f"<div style='font-size: 13px; color: #4ade80; font-weight: bold; margin-top: 4px;'>⏱️ 총 경과: {format_time_delta(total_sec)}</div>"

    st.markdown(
        f"""
        <div style="text-align: right; padding: 10px 14px; background: #0f172a; border-radius: 10px; border: 1.5px solid #38bdf8; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="font-size: 11px; color: #94a3b8; font-weight: bold;">대한민국 표준시 (KST)</div>
            <div style="font-size: 22px; font-weight: 900; color: #38bdf8; font-family: monospace; letter-spacing: 1px;">
                <span style="font-size: 13px; color: #a5f3fc;">{ampm_kor}</span> {clock_time_str}
            </div>
            {total_elapsed_txt}
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 상단 7단계 가로형 소요시간 카드 바 (A100 ➔ A200 ➔ A300 ➔ A400 ➔ A500 ➔ A600 ➔ A700)
# -------------------------------------------------------------
step_cols = st.columns(7)
step_defs = [
    (1, "A100", "Base 배합", "T101~104"),
    (2, "A200", "살균/냉각", "P101TC02"),
    (3, "A300", "발효/보온", "재킷 온수"),
    (4, "A400", "시럽 배합", "T401~402"),
    (5, "A500", "시럽 살균", "P201TC02"),
    (6, "A600", "급속 칠링", "PHE301"),
    (7, "A700", "MQI 충전", "서지/충전")
]

for idx, (s_idx, s_code, s_label, s_tag) in enumerate(step_defs):
    with step_cols[idx]:
        if st.session_state.process_step == 0:
            status_color = "#64748b"
            bg_color = "#f8fafc"
            border_color = "#cbd5e1"
            dur_display = "대기"
            badge = "대기"
        elif st.session_state.process_step > s_idx:
            status_color = "#15803d"
            bg_color = "#f0fdf4"
            border_color = "#86efac"
            dur_display = st.session_state.step_durations.get(f"Step_{s_idx}", "완료")
            badge = "✓ 완료"
        elif st.session_state.process_step == s_idx:
            status_color = "#0284c7"
            bg_color = "#f0f9ff"
            border_color = "#38bdf8"
            s_start = st.session_state.step_entry_times.get(f"Step_{s_idx}", kst_now)
            elapsed_sec = (kst_now - s_start).total_seconds()
            dur_display = format_time_delta(elapsed_sec)
            badge = "● 진행 중"
        else:
            status_color = "#94a3b8"
            bg_color = "#f8fafc"
            border_color = "#e2e8f0"
            dur_display = "대기"
            badge = "예정"

        st.markdown(
            f"""
            <div style="padding: 8px; border-radius: 8px; background: {bg_color}; border: 1.5px solid {border_color}; text-align: center;">
                <div style="font-size: 10px; font-weight: bold; color: {status_color};">{badge} | {s_code}</div>
                <div style="font-size: 14px; font-weight: 900; color: #0f172a; margin: 2px 0;">{s_code} {dur_display}</div>
                <div style="font-size: 10px; color: #64748b;">{s_label}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

st.divider()

# =============================================================
# STEP 0: 배치 착수 등록 (작업자 디폴트: 공장장)
# =============================================================
if st.session_state.process_step == 0:
    st.subheader("📋 [Step 0] 런 발효유 생산 배치 착수 등록")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        product_name_input = st.text_input("생산 품목명", value="런 발효유", help="필요 시 다른 품목명을 직접 입력하여 변경할 수 있음.")
        target_tank = "A300 발효탱크"
    with col2:
        worker_name = st.text_input("작업자 성명", value="공장장", placeholder="작업자명 입력")
        indoor_t = st.number_input("현재 발효실 실내온도 (℃)", 10.0, 40.0, 24.5, 0.1)
    with col3:
        st.markdown(f"**현재 착수 시각 (KST):** `{format_korean_ampm(kst_now)}`")
        start_hour_val = round(float(kst_now.hour + kst_now.minute / 60.0), 1)
        clean_pname = "".join(filter(str.isalnum, product_name_input))
        batch_id_gen = f"{kst_now.strftime('%Y%m%d')}_{clean_pname}_{kst_now.strftime('%H%M')}"
        st.info(f"생성될 배치 ID: **{batch_id_gen}**")

    st.divider()
    if st.button("🚀 이 설정으로 [배치 작업 시작 (A100 착수)]", type="primary", use_container_width=True):
        if not worker_name.strip():
            st.error("작업자 성명을 입력바람.")
        elif not product_name_input.strip():
            st.error("생산 품목명을 입력바람.")
        else:
            exact_kst_dt = get_kst_now()
            start_korean_val = format_korean_ampm(exact_kst_dt)
            
            st.session_state.batch_id = batch_id_gen
            st.session_state.product_name = product_name_input.strip()
            st.session_state.target_tank = target_tank
            st.session_state.worker_name = worker_name.strip()
            st.session_state.indoor_t = indoor_t
            st.session_state.start_hour = start_hour_val
            st.session_state.batch_start_dt = exact_kst_dt
            st.session_state.start_time_korean = start_korean_val
            
            st.session_state.step_entry_times["Step_1"] = exact_kst_dt
            
            calc_res = calculate_optimal_temperatures(start_hour_val, indoor_t, curr_t, min_t, max_t)
            st.session_state.calc_res = calc_res
            
            save_batch_start(
                batch_id_gen, product_name_input.strip(), target_tank, worker_name.strip(),
                exact_kst_dt.strftime("%Y-%m-%d %H:%M:%S"), start_korean_val, curr_t, indoor_t
            )
            st.session_state.process_step = 1
            st.rerun()

# =============================================================
# STEP 1: A100 공정 (Base Mix 배합 및 준비)
# =============================================================
elif st.session_state.process_step == 1:
    st.subheader(f"📍 [Step 1: A100] {st.session_state.product_name} Base Mix 배합 단계 (배치: {st.session_state.batch_id})")
    
    st.markdown(f"""
    * **담당 구역:** 101~104호 베이스 배합탱크 및 분말 믹서 (`MX101`, 45.0 Hz)
    * **주요 작업:** **{st.session_state.product_name}** 원유 및 배합원료 계량 투입, 배합 탱크 교반 가동, 살균 라인 이송 밸브 점검
    * **제어 지침:** 원유 초기 온도 확인 후 A200 살균기 이송 준비 완료 확인
    """)
    
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        mix_temp = st.number_input("배합탱크 실측 원유온도 (℃)", 4.0, 25.0, 10.5, 0.1)
    with col_a2:
        mix_status = st.selectbox("배합 상태 점검", ["정상 배합 완료 (균질 양호)", "원료 투입 중"])

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 작업 취소 (Step 0으로 복귀)", use_container_width=True):
            st.session_state.process_step = 0
            st.session_state.batch_start_dt = None
            st.session_state.step_entry_times = {}
            st.session_state.step_durations = {}
            st.rerun()
    with c2:
        if st.button("A100 완료 ➔ 다음 단계 [A200 살균/냉각] 이동", type="primary", use_container_width=True):
            s1_start = st.session_state.step_entry_times.get("Step_1", kst_now)
            step_sec = (kst_now - s1_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_1"] = step_dur_str
            
            log_step_temp(st.session_state.batch_id, "A100", "Base Mix 배합", step_dur_str, "T101~T104", 0.0, 0.0, mix_temp, mix_status)
            
            st.session_state.step_entry_times["Step_2"] = get_kst_now()
            st.session_state.process_step = 2
            st.rerun()

# =============================================================
# STEP 2: A200 공정 (살균냉각 및 투입) - ★ AI 추천온도 제어점 1
# =============================================================
elif st.session_state.process_step == 2:
    st.subheader(f"📍 [Step 2: A200] {st.session_state.product_name} 살균 및 냉각 투입 단계 (배치: {st.session_state.batch_id})")
    st.warning("⚠️ **[핵심 제어점 1: 살균냉각온도]** AI 추천온도를 확인하고 HMI 제어반에 설정한 뒤 확인 값을 입력바람.")
    
    c_res = st.session_state.calc_res
    
    c_rec1, c_rec2 = st.columns([1, 2])
    with c_rec1:
        st.markdown("#### 🎯 AI 추천 살균냉각온도")
        st.markdown(f"<h1 style='color:#1f77b4; font-size:48px;'>{c_res['rec_cooling']} ℃</h1>", unsafe_allow_html=True)
        st.caption("SCADA 태그: **P101TC02.SP** (A200 구역)")
    with c_rec2:
        st.info(f"""
        * **외적 환경 분석:** 실시간 외기 {curr_t}℃ / 실내 {st.session_state.indoor_t}℃ (유효환경 {c_res['t_eff_early']}℃)
        * **배관 이송 열손실:** 35m SUS 배관 통과 중 **+{c_res['delta_t_pipe']}℃** 손실 보정 반영됨.
        * **작업 지침:** 살균기 냉각 제어반(`P101TC02`)을 **{c_res['rec_cooling']}℃**로 설정하여 발효조로 투입바람. (동절기 41℃ 이상 과열 금지)
        """)

    st.markdown("---")
    st.markdown("#### 📝 작업자 HMI 설정 및 실측 확인 입력")
    f1, f2 = st.columns(2)
    with f1:
        op_set_cool = st.number_input("HMI 실제 설정값 (`P101TC02.SP`, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)
    with f2:
        act_meas_cool = st.number_input("살균기 토출 실측 액온 (`P101TT02`, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A100 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 1
            st.rerun()
    with c2:
        if st.button("💾 A200 확인 기록 ➔ [A300 발효] 이동", type="primary", use_container_width=True):
            s2_start = st.session_state.step_entry_times.get("Step_2", kst_now)
            step_sec = (kst_now - s2_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_2"] = step_dur_str
            
            status_eval = "정상 설정" if abs(op_set_cool - c_res['rec_cooling']) <= 0.2 else "권장치 편차 설정"
            log_step_temp(st.session_state.batch_id, "A200", "살균냉각투입", step_dur_str, "P101TC02", c_res['rec_cooling'], op_set_cool, act_meas_cool, status_eval)
            
            st.session_state.step_entry_times["Step_3"] = get_kst_now()
            st.session_state.process_step = 3
            st.rerun()

# =============================================================
# STEP 3: A300 공정 (발효 및 재킷 보온) - ★ AI 추천온도 제어점 2
# =============================================================
elif st.session_state.process_step == 3:
    st.subheader(f"📍 [Step 3: A300] {st.session_state.product_name} 발효 및 재킷 보온 제어 (배치: {st.session_state.batch_id})")
    st.warning("⚠️ **[핵심 제어점 2: 재킷 핫워터 & 발효조 TT]** 중후반 방열 손실을 방지하기 위한 AI 추천값을 HMI에 입력바람.")
    
    c_res = st.session_state.calc_res
    
    c_hw1, c_hw2 = st.columns(2)
    with c_hw1:
        st.markdown("#### 🔥 AI 추천 핫워터 순환온도")
        st.markdown(f"<h1 style='color:#2ca02c; font-size:42px;'>{c_res['rec_hotwater']} ℃</h1>", unsafe_allow_html=True)
        st.caption("SCADA 태그: **PHE301WCV01** (재킷 온수 순환밸브)")
    with c_hw2:
        st.markdown("#### 🏷️ AI 추천 발효조 목표 품온 (TT)")
        st.markdown(f"<h1 style='color:#ff7f0e; font-size:42px;'>{c_res['rec_tank_tt']} ℃</h1>", unsafe_allow_html=True)
        st.caption("발효조 내부 유지 목표 품온")

    st.markdown("---")
    st.markdown("#### ⏱️ 5시간(300분) 경과 시점 골든 액온 점검")
    h1, h2, h3 = st.columns(3)
    with h1:
        op_set_hw = st.number_input("HMI 핫워터 설정값 (℃)", 35.0, 42.0, float(c_res['rec_hotwater']), 0.1)
    with h2:
        act_meas_5h = st.number_input("5H 경과 실측 액온 (℃) [골든기준: 39.5℃]", 35.0, 43.0, 39.5, 0.1)
    with h3:
        acid_5h = st.number_input("5H 경과 실측 산도", 0.700, 0.950, 0.910, 0.005, format="%.3f")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A200 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 2
            st.rerun()
    with c2:
        if st.button("💾 5H 점검 기록 ➔ [A400 시럽 배합] 이동", type="primary", use_container_width=True):
            s3_start = st.session_state.step_entry_times.get("Step_3", kst_now)
            step_sec = (kst_now - s3_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_3"] = step_dur_str
            
            diff_5h = act_meas_5h - 39.5
            eval_5h = "골든 궤적 정상 유지" if abs(diff_5h) <= 0.3 else f"편차 발생 ({diff_5h:+.2f}℃)"
            log_step_temp(st.session_state.batch_id, "A300", "발효재킷보온", step_dur_str, "PHE301WCV01", c_res['rec_hotwater'], op_set_hw, act_meas_5h, eval_5h)
            
            st.session_state.acid_5h = acid_5h
            st.session_state.act_meas_5h = act_meas_5h
            st.session_state.step_entry_times["Step_4"] = get_kst_now()
            st.session_state.process_step = 4
            st.rerun()

# =============================================================
# STEP 4: A400 공정 (시럽 배합 및 용해) - ★ 독립 분리
# =============================================================
elif st.session_state.process_step == 4:
    st.subheader(f"📍 [Step 4: A400] {st.session_state.product_name} 시럽 배합 및 용해 단계 (배치: {st.session_state.batch_id})")
    
    st.markdown(f"""
    * **담당 구역:** 401~402호 시럽 배합탱크 (`T401`, `T402`) 및 파우더 믹서 펌프 (`P401`, `P402` 45.0 Hz)
    * **주요 작업:** **{st.session_state.product_name}** 전용 당류/과일 원료 투입, 고속 용해 교반, 배합액 균질성 및 당도(Brix) 점검
    * **제어 지침:** 시럽 완전 용해 확인 후 A500 시럽 전용 살균기로 이송 개시
    """)
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        syrup_mix_t = st.number_input("시럽 배합탱크 내부 액온 (℃)", 15.0, 35.0, 24.5, 0.1)
    with col_s2:
        syrup_brix = st.number_input("시럽 실측 배합 당도 (Brix)", 10.0, 65.0, 45.0, 0.5)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A300 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 3
            st.rerun()
    with c2:
        if st.button("A400 완료 ➔ 다음 단계 [A500 시럽 살균] 이동", type="primary", use_container_width=True):
            s4_start = st.session_state.step_entry_times.get("Step_4", kst_now)
            step_sec = (kst_now - s4_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_4"] = step_dur_str
            
            log_step_temp(st.session_state.batch_id, "A400", "시럽배합용해", step_dur_str, "T401~T402", 24.5, 24.5, syrup_mix_t, f"당도 {syrup_brix} Brix")
            
            st.session_state.step_entry_times["Step_5"] = get_kst_now()
            st.session_state.process_step = 5
            st.rerun()

# =============================================================
# STEP 5: A500 공정 (시럽 살균 및 냉각) - ★ 독립 분리
# =============================================================
elif st.session_state.process_step == 5:
    st.subheader(f"📍 [Step 5: A500] {st.session_state.product_name} 시럽 전용 살균 및 냉각 단계 (배치: {st.session_state.batch_id})")
    
    st.markdown(f"""
    * **담당 구역:** 시럽 전용 판형 살균기 (`P201TC02`, `P2X2TC01`) 및 전도도 센서 (`P2B1CT02`)
    * **주요 작업:** 85℃ 살균 유지 확인, 살균 후 급속 냉각(`P2X4TT71`, 목표 24.7℃), 이송 배관 세니타이제이션 점검
    * **제어 지침:** 냉각 완료 시럽을 A600 블렌딩 라인으로 공급 대기
    """)
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        syrup_pasteur_t = st.number_input("시럽 살균 유지온도 (`P201TT02`, ℃)", 75.0, 95.0, 85.0, 0.5)
    with col_p2:
        syrup_cool_t = st.number_input("시럽 살균 후 최종 냉각온도 (`P2X4TT71`, ℃)", 15.0, 30.0, 24.7, 0.1)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A400 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 4
            st.rerun()
    with c2:
        if st.button("A500 완료 ➔ 다음 단계 [A600 블렌딩/칠링] 이동", type="primary", use_container_width=True):
            s5_start = st.session_state.step_entry_times.get("Step_5", kst_now)
            step_sec = (kst_now - s5_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_5"] = step_dur_str
            
            log_step_temp(st.session_state.batch_id, "A500", "시럽살균냉각", step_dur_str, "P201TC02", 85.0, syrup_pasteur_t, syrup_cool_t, f"냉각 {syrup_cool_t}℃ 완료")
            
            st.session_state.step_entry_times["Step_6"] = get_kst_now()
            st.session_state.process_step = 6
            st.rerun()

# =============================================================
# STEP 6: A600 공정 (블렌딩 및 선행 급속 냉각) - ★ AI 추천온도 제어점 3
# =============================================================
elif st.session_state.process_step == 6:
    st.subheader(f"📍 [Step 6: A600] {st.session_state.product_name} 블렌딩 및 PHE301 급속 냉각 (배치: {st.session_state.batch_id})")
    st.warning("⚠️ **[핵심 제어점 3: 선행 냉각 트리거]** 후산도(+0.035)를 고려한 AI 선행 냉각 시점을 준수바람.")
    
    acid_5h_saved = getattr(st.session_state, 'acid_5h', 0.910)
    rem_acid = 0.930 - acid_5h_saved
    
    if rem_acid <= 0:
        trig_min = 300
        trig_msg = "🚨 즉시 PHE301 냉각 밸브를 OPEN하여 급속 칠링을 시작바람! (선행산도 0.930 도달)"
    else:
        add_min = int(rem_acid / 0.0015)
        trig_min = 300 + add_min
        trig_msg = f"⏱️ 접종 후 **{trig_min}분 시점 (앞으로 약 {add_min}분 뒤)**에 PHE301 냉각 밸브를 개방바람."

    c_c1, c_c2 = st.columns(2)
    with c_c1:
        st.markdown("#### ❄️ AI 냉각 개시 선행 산도")
        st.markdown("<h1 style='color:#0284c7; font-size:40px;'>산도 0.925 ~ 0.930</h1>", unsafe_allow_html=True)
        st.caption("PHE301 통과 토출 목표온도: **7.3 ℃**")
    with c_c2:
        st.info(f"**[냉각 카운트다운]**\n\n{trig_msg}")

    st.markdown("---")
    st.markdown("#### 📝 PHE301 냉각 가동 및 실측 입력")
    cl1, cl2 = st.columns(2)
    with cl1:
        act_dur_min = st.number_input("실제 냉각 개시 분(Time)", 300, 420, int(trig_min), 1)
    with cl2:
        phe_out_t = st.number_input("PHE301 토출 냉각온도 (`PHE301STT02`, ℃)", 4.0, 15.0, 7.3, 0.1)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A500 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 5
            st.rerun()
    with c2:
        if st.button("💾 A600 냉각 확인 ➔ [A700 충전/MQI QC] 이동", type="primary", use_container_width=True):
            s6_start = st.session_state.step_entry_times.get("Step_6", kst_now)
            step_sec = (kst_now - s6_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_6"] = step_dur_str
            
            log_step_temp(st.session_state.batch_id, "A600", "PHE301급속냉각", step_dur_str, "PHE301STT02", 7.3, 7.3, phe_out_t, f"{act_dur_min}분 시점 냉각 개시")
            
            st.session_state.act_dur_min = act_dur_min
            st.session_state.step_entry_times["Step_7"] = get_kst_now()
            st.session_state.process_step = 7
            st.rerun()

# =============================================================
# STEP 7: A700 공정 (서지탱크/충전 & 다차원 MQI 품질 검증)
# =============================================================
elif st.session_state.process_step == 7:
    st.subheader(f"📍 [Step 7: A700] {st.session_state.product_name} 서지탱크 충전 & 다차원 품질검증 (배치: {st.session_state.batch_id})")
    st.info(f"💡 {st.session_state.product_name} 완제품의 이화학(산도·pH), 물성(점도·유청분리), 관능(맛) 점수를 종합 평가하여 DB에 영구 기록함.")
    
    st.markdown("##### 1. 이화학 지표 (Chemical)")
    q1, q2, q3 = st.columns(3)
    with q1:
        f_acid = st.number_input("최종 완제품 산도 [골든: 0.965]", 0.800, 1.200, 0.965, 0.001, format="%.3f")
    with q2:
        f_ph = st.number_input("최종 완제품 pH [골든: 4.70]", 4.00, 5.50, 4.70, 0.01)
    with q3:
        f_total_dur = st.number_input("총 소요 발효시간 (분)", 300, 450, 378, 1)

    st.markdown("##### 2. 물성/텍스처 지표 (Texture)")
    t1, t2 = st.columns(2)
    with t1:
        f_visc = st.number_input("회전식 점도계 측정치 (cP) [골든: 3,200 cP]", 1500.0, 4500.0, 3200.0, 50.0)
    with t2:
        f_syn = st.number_input("유청 분리율 (Syneresis, %) [골든: 1.5% 이하]", 0.0, 15.0, 1.1, 0.1)

    st.markdown("##### 3. 관능/맛 지표 (Taste & Flavor)")
    g1, g2 = st.columns(2)
    with g1:
        f_taste = st.slider(f"관능 평가 점수 ({st.session_state.product_name} 맛 밸런스, 5점 만점)", 1.0, 5.0, 4.8, 0.1)
    with g2:
        f_memo = st.text_input("작업 특이사항 메모", placeholder=f"예: {st.session_state.product_name} 골든 기준 완벽 수렴, 풍미 및 바디감 우수.")

    score_chem = max(0.0, 30.0 - abs(f_acid - 0.965) * 500.0)
    score_tex = max(0.0, 40.0 - abs(f_visc - 3200.0) * 0.02 - (f_syn * 2.0))
    score_taste = (f_taste / 5.0) * 30.0
    mqi_total = round(min(100.0, max(0.0, score_chem + score_tex + score_taste)), 1)

    st.markdown(f"### 🏆 {st.session_state.product_name} 종합 품질점수 (MQI Score): **`{mqi_total} / 100 점`**")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("◀ 이전 단계로 되돌리기 (A600 복귀 / 잘못 누름 취소)", use_container_width=True):
            st.session_state.process_step = 6
            st.rerun()
    with c2:
        if st.button("💾 전체 공정 최종 종결 및 DB 영구 저장", type="primary", use_container_width=True):
            s7_start = st.session_state.step_entry_times.get("Step_7", kst_now)
            step_sec = (kst_now - s7_start).total_seconds()
            step_dur_str = format_time_delta(step_sec)
            st.session_state.step_durations["Step_7"] = step_dur_str
            
            log_step_temp(st.session_state.batch_id, "A700", "서지충전&MQI", step_dur_str, "701~705호", 7.3, 7.3, 7.3, f"MQI {mqi_total}점")
            save_final_mqi(
                st.session_state.batch_id, f_total_dur, f_acid, f_ph,
                f_visc, f_syn, f_taste, mqi_total, f_memo
            )
            st.session_state.process_step = 8
            st.rerun()

# =============================================================
# STEP 8: 공정 완료 리포트 및 이력 조회
# =============================================================
elif st.session_state.process_step == 8:
    st.success(f"🎉 [{st.session_state.product_name}] 배치 [{st.session_state.batch_id}] 공정이 성공적으로 종결되었으며 모든 단계별 온도 및 소요시간 이력이 기록되었음!")
    
    tab_r1, tab_r2 = st.tabs(["📊 이번 배치 공정 단계별 온도 및 소요시간 이력", "📋 누적 완료 배치 관리"])
    
    with tab_r1:
        cur_logs = get_step_logs(st.session_state.batch_id)
        st.dataframe(cur_logs, use_container_width=True)
    
    with tab_r2:
        all_df = get_all_completed_batches()
        st.dataframe(all_df, use_container_width=True)
        if not all_df.empty:
            csv_export = all_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 누적 MQI 품질 이력 CSV 다운로드",
                data=csv_export,
                file_name=f"FermaAX_MQI_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

    st.divider()
    if st.button("🔄 새로운 배치 작업 시작하기", type="primary", use_container_width=True):
        st.session_state.process_step = 0
        st.session_state.batch_id = ""
        st.session_state.batch_start_dt = None
        st.session_state.step_entry_times = {}
        st.session_state.step_durations = {}
        st.session_state.start_time_korean = ""
        st.rerun()
