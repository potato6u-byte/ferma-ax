# -*- coding: utf-8 -*-
"""
FermaAX™ Mobile-Optimized SCADA SOP & AI Temperature Controller v7.6
• 단일 공정 다중 탱크(Multi-Tank) 분입 시스템 완벽 지원
• Step 0: 이번 배치에 투입할 발효탱크 다중 선택 (Multi-Select)
• Step 2: 투입 탱크 중 최대 열손실 탱크 기준 살균냉각 안전온도 연산
• Step 3 (핵심): 선택된 탱크별 개별 단열계수(kappa) 기반 동적 핫워터 AI 추천 및 실측 개별 제어판 제공
• 구글 스프레드시트 웹훅 및 로컬 엑셀(.xlsx) 통합 분산 로깅 완비
• [UI v7.6-P] 퍼플 테마 + 상단 고정(Sticky) 공정 흐름바 적용
"""
import os
import io
import json
import sqlite3
import requests
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta, timezone

# =============================================================
# 1. 구글 스프레드시트 웹 앱 URL 및 기본 설정
# =============================================================
GSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzMcyBZL5mhYVfP5ShDhixvlm50tqvsoDu99VmrFbGivDegWjiFRCTZ7r4Eqam7mYga/exec"

# 대한민국 표준시(KST) 타임존 설정
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
KST = ZoneInfo("Asia/Seoul")

def get_kst_now():
    return datetime.now(KST)

def format_korean_ampm(dt):
    ampm = "오전" if dt.hour < 12 else "오후"
    h12 = dt.hour if dt.hour <= 12 else dt.hour - 12
    if h12 == 0: h12 = 12
    return f"{ampm} {h12}:{dt.strftime('%M:%S')}"

def format_time_delta(seconds_total):
    mins = int(seconds_total // 60)
    secs = int(seconds_total % 60)
    if mins > 0:
        return f"{mins}분 {secs}초"
    else:
        return f"{secs}초"

st.set_page_config(page_title="런 발효유 SCADA", layout="wide", initial_sidebar_state="collapsed")

# =============================================================
# 1-1. 퍼플 테마 글로벌 CSS
# =============================================================
st.markdown("""
<style>
    /* ---------- 퍼플 팔레트 변수 ---------- */
    :root {
        --fp-900: #4c1d95;
        --fp-700: #6d28d9;
        --fp-600: #7c3aed;
        --fp-500: #8b5cf6;
        --fp-300: #c4b5fd;
        --fp-200: #ddd6fe;
        --fp-100: #ede9fe;
        --fp-50:  #f5f3ff;
    }

    /* ---------- 전체 배경 & 타이포 ---------- */
    .stApp { background: #fbfaff; }
    h1, h2, h3 { color: var(--fp-900) !important; }

    .stTextInput label, .stNumberInput label, .stSelectbox label, .stMultiSelect label {
        font-size: 1.1rem !important; font-weight: 700 !important; color: var(--fp-900) !important;
    }

    /* ---------- 버튼 (기본/프라이머리) ---------- */
    .stButton button {
        font-size: 1.1rem !important; font-weight: 700 !important;
        border-radius: 10px !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(90deg, var(--fp-700), var(--fp-500)) !important;
        border: none !important; color: #ffffff !important;
        box-shadow: 0 3px 10px rgba(124, 58, 237, 0.35) !important;
    }
    .stButton button[kind="primary"]:hover {
        background: linear-gradient(90deg, var(--fp-900), var(--fp-600)) !important;
    }
    .stDownloadButton button {
        background: var(--fp-100) !important; color: var(--fp-900) !important;
        border: 1.5px solid var(--fp-500) !important; border-radius: 10px !important;
        font-weight: 700 !important;
    }

    /* ---------- 입력 위젯 포커스 컬러 ---------- */
    .stNumberInput input:focus, .stTextInput input:focus {
        border-color: var(--fp-600) !important;
        box-shadow: 0 0 0 2px var(--fp-200) !important;
    }
    span[data-baseweb="tag"] { background-color: var(--fp-100) !important; }
    span[data-baseweb="tag"] span { color: var(--fp-900) !important; }

    /* ---------- 정보/성공/경고 박스 퍼플 톤 ---------- */
    div[data-testid="stInfo"] {
        background-color: var(--fp-100) !important;
        border-left: 5px solid var(--fp-600) !important;
        border-radius: 10px !important;
    }
    div[data-testid="stSuccess"] {
        background-color: #f0fdf4 !important;
        border-left: 5px solid #22c55e !important;
        border-radius: 10px !important;
    }

    /* ---------- 구분선 ---------- */
    hr { border-color: var(--fp-200) !important; }

    /* =========================================================
       상단 고정(Sticky) 공정 흐름바
       ========================================================= */
    .fs-sticky {
        position: sticky;
        top: 2.875rem;              /* Streamlit 헤더 바로 아래 고정 */
        z-index: 999;
        background: linear-gradient(135deg, var(--fp-100), #ffffff 70%);
        border: 1px solid var(--fp-200);
        border-radius: 14px;
        padding: 10px 14px 12px 14px;
        box-shadow: 0 4px 16px rgba(109, 40, 217, 0.18);
        margin-bottom: 14px;
    }
    .fs-head {
        display: flex; flex-wrap: wrap; align-items: baseline;
        justify-content: space-between; gap: 4px 14px;
        margin-bottom: 8px;
    }
    .fs-title {
        font-size: 1.25rem; font-weight: 800; color: var(--fp-900);
        letter-spacing: -0.3px;
    }
    .fs-title small { font-size: 0.8rem; font-weight: 600; color: var(--fp-600); }
    .fs-weather { font-size: 0.85rem; font-weight: 600; color: var(--fp-700); }
    .fs-now {
        font-size: 0.85rem; font-weight: 800; color: #ffffff;
        background: var(--fp-600); border-radius: 999px; padding: 3px 12px;
    }

    /* 공정 칩 (가로 스크롤 - 모바일에서 세로로 밀리지 않음) */
    .fs-bar {
        display: flex; flex-wrap: nowrap; align-items: stretch;
        gap: 6px; overflow-x: auto; padding-bottom: 2px;
        -webkit-overflow-scrolling: touch;
    }
    .fs-bar::-webkit-scrollbar { height: 4px; }
    .fs-bar::-webkit-scrollbar-thumb { background: var(--fp-300); border-radius: 4px; }

    .fs-chip {
        flex: 0 0 auto;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        min-width: 82px; padding: 6px 10px; border-radius: 11px;
        line-height: 1.25;
    }
    .fs-icon { font-size: 0.95rem; }
    .fs-code { font-size: 0.95rem; font-weight: 800; }
    .fs-label { font-size: 0.72rem; font-weight: 600; opacity: 0.9; }

    .fs-active {
        background: linear-gradient(135deg, var(--fp-700), var(--fp-500));
        color: #ffffff;
        box-shadow: 0 3px 10px rgba(124, 58, 237, 0.45);
        animation: fsPulse 1.6s ease-in-out infinite;
    }
    .fs-done  { background: var(--fp-200); color: var(--fp-900); }
    .fs-wait  { background: #ffffff; color: #94a3b8; border: 1.5px dashed #cbd5e1; }

    .fs-arrow {
        flex: 0 0 auto; align-self: center;
        color: var(--fp-300); font-weight: 800; font-size: 1.05rem;
    }

    @keyframes fsPulse {
        0%, 100% { box-shadow: 0 3px 10px rgba(124, 58, 237, 0.45); }
        50%      { box-shadow: 0 3px 18px rgba(124, 58, 237, 0.75); }
    }

    /* 진행률 바 */
    .fs-progress-wrap {
        height: 6px; background: var(--fp-100);
        border-radius: 999px; margin-top: 8px; overflow: hidden;
    }
    .fs-progress {
        height: 100%;
        background: linear-gradient(90deg, var(--fp-600), var(--fp-500));
        border-radius: 999px; transition: width .4s ease;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================
# 2. SQLite 데이터베이스 초기화 (다중 탱크 v7.6)
# =============================================================
DB_FILE = "ferma_master_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_multi_tank (
            run_id TEXT PRIMARY KEY,
            tanks_list TEXT,
            raw_material TEXT,
            batch_volume INTEGER,
            start_datetime TEXT,
            start_time_korean TEXT,
            outdoor_temp REAL,
            indoor_temp REAL,
            status TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS step_logs_multi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            step_code TEXT,
            step_name TEXT,
            log_time TEXT,
            step_duration_str TEXT,
            scada_tag TEXT,
            ai_recommended_temp REAL,
            operator_set_temp REAL,
            actual_measured_temp REAL,
            action_status TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_mqi_multi (
            run_id TEXT PRIMARY KEY,
            completed_at TEXT,
            actual_duration INTEGER,
            final_acidity REAL,
            final_ph REAL,
            viscosity_cp REAL,
            syneresis_rate REAL,
            taste_score REAL,
            mqi_total_score REAL,
            tank_temp_summary TEXT,
            worker_memo TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_batch_start_multi(run_id, tanks_str, raw_mat, vol, s_dt, s_korean, out_t, in_t):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO batch_multi_tank 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
    ''', (run_id, tanks_str, raw_mat, vol, s_dt, s_korean, out_t, in_t))
    conn.commit()
    conn.close()

def log_step_temp_multi(run_id, step_code, step_name, step_dur_str, scada_tag, ai_rec, op_set, act_meas, status_txt):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO step_logs_multi 
        (run_id, step_code, step_name, log_time, step_duration_str, scada_tag, ai_recommended_temp, operator_set_temp, actual_measured_temp, action_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (run_id, step_code, step_name, now_str, step_dur_str, scada_tag, ai_rec, op_set, act_meas, status_txt))
    conn.commit()
    conn.close()

def save_final_mqi_multi(run_id, duration, acidity, ph, visc, syn, taste, mqi, tank_summary, memo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO batch_mqi_multi VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (run_id, now_str, duration, acidity, ph, visc, syn, taste, mqi, tank_summary, memo))
    c.execute("UPDATE batch_multi_tank SET status = 'COMPLETED' WHERE run_id = ?", (run_id,))
    conn.commit()
    conn.close()

def send_to_google_sheet(payload):
    try:
        res = requests.post(GSHEET_WEBHOOK_URL, json=payload, timeout=5)
        if res.status_code == 200:
            return True, "성공"
        return False, f"응답 코드: {res.status_code}"
    except Exception as e:
        return False, f"네트워크 지연 ({str(e)[:20]})"

def get_step_logs_multi(run_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM step_logs_multi WHERE run_id = ? ORDER BY id ASC", conn, params=(run_id,))
    conn.close()
    return df

def get_all_completed_batches_multi():
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT b.run_id, b.tanks_list, b.raw_material, b.batch_volume, b.start_time_korean,
               q.completed_at, q.actual_duration, q.final_acidity, q.final_ph,
               q.viscosity_cp, q.syneresis_rate, q.taste_score, q.mqi_total_score, q.tank_temp_summary, q.worker_memo
        FROM batch_multi_tank b
        JOIN batch_mqi_multi q ON b.run_id = q.run_id
        ORDER BY q.completed_at DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def create_excel_download(df_master, df_logs):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_master.to_excel(writer, sheet_name='배치종합역사', index=False)
        df_logs.to_excel(writer, sheet_name='단계별세부로그', index=False)
    return output.getvalue()

# 기장군 기상청 API 연동
@st.cache_data(ttl=300, show_spinner=False)
def fetch_gijang_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=35.2447&longitude=129.2226&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            curr_t = float(data["current"]["temperature_2m"])
            min_t = float(data["daily"]["temperature_2m_min"][0])
            max_t = float(data["daily"]["temperature_2m_max"][0])
            return curr_t, min_t, max_t, "기상청 정상 연동"
        else:
            return 24.5, 20.0, 29.0, "기상 서버 지연"
    except Exception:
        return 24.5, 20.0, 29.0, "네트워크 지연 모드"

# =============================================================
# 3. 탱크 단열계수 및 원료 비열 기반 4D AI 제어 연산 엔진
# =============================================================
TANK_SPECS = {
    "301호 탱크": {"kappa": 1.00, "desc": "표준형 단열 탱크 (중앙 구역)"},
    "302호 탱크": {"kappa": 1.15, "desc": "외벽 밀접 탱크 (방열 손실 15% 큼)"},
    "303호 탱크": {"kappa": 0.90, "desc": "고단열 보온 자켓 탱크 (방열 손실 10% 적음)"},
    "304호 탱크": {"kappa": 0.95, "desc": "대용량 5000L 탱크 (열용량 큼)"},
    "305호 탱크": {"kappa": 1.10, "desc": "소용량 3000L 탱크 (방열 빠름)"}
}

RAW_SPECS = {
    "국산 1등급A 원유 (표준)": {"cp": 3930.0, "offset": 0.0, "cooling_target": 7.3},
    "무항생제/유기농 원유 (고단백)": {"cp": 3890.0, "offset": +0.2, "cooling_target": 7.5},
    "저지방 배합원유 (고수분)": {"cp": 4020.0, "offset": -0.1, "cooling_target": 7.1},
    "고형분 농축/환원 배합유": {"cp": 3820.0, "offset": +0.1, "cooling_target": 7.3}
}

def calculate_multi_tank_temperatures(start_h, indoor_t, out_t, min_t, max_t, tank_list, raw_mat):
    time_steps = np.linspace(start_h, start_h + 6.3, 25)
    dt = time_steps - start_h
    t_mean = (max_t + min_t) / 2.0
    t_amp = (max_t - min_t) / 2.0
    t_out_traj = t_mean + t_amp * np.sin((2 * np.pi / 24.0) * (time_steps - 9.0))
    t_in_traj = indoor_t + 0.15 * (t_out_traj - out_t)

    early_mask = (dt >= 0.5) & (dt <= 2.0)
    late_mask = (dt >= 2.0) & (dt <= 6.3)
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask]) if np.any(early_mask) else indoor_t
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask]) if np.any(late_mask) else indoor_t

    m_prof = RAW_SPECS.get(raw_mat, {"cp": 3930.0, "offset": 0.0, "cooling_target": 7.3})
    c_p = m_prof["cp"]
    mat_offset = m_prof["offset"]

    delta_t_pipe = round((1.85 * 8.35 * max(0.0, 38.4 - indoor_t)) / (2.083 * c_p), 2)

    kappas = [TANK_SPECS[t]["kappa"] for t in tank_list if t in TANK_SPECS]
    max_kappa = max(kappas) if kappas else 1.00
    base_cool = 38.4 + max(0.0, (32.0 - t_eff_early) * 0.050 * max_kappa) + delta_t_pipe + mat_offset
    rec_cooling = min(39.3, round(base_cool, 1))

    tank_recommendations = {}
    for t in tank_list:
        k_val = TANK_SPECS.get(t, {}).get("kappa", 1.00)
        base_hw = 38.3 + max(0.0, (32.0 - t_eff_late) * 0.040 * k_val) + (mat_offset * 0.5)
        rec_hw = min(38.8, round(base_hw, 1))
        base_tt = 38.5 + max(0.0, (32.0 - t_eff_late) * 0.035 * k_val)
        rec_tt = min(39.2, round(base_tt, 1))
        tank_recommendations[t] = {
            "kappa": k_val,
            "rec_hotwater": rec_hw,
            "rec_tank_tt": rec_tt
        }

    return {
        "rec_cooling": rec_cooling,
        "delta_t_pipe": delta_t_pipe,
        "target_chilling": m_prof["cooling_target"],
        "tanks": tank_recommendations
    }

# =============================================================
# 세션 상태 초기화 및 공정 가이드
# =============================================================
if "process_step" not in st.session_state: st.session_state.process_step = 0
if "run_id" not in st.session_state: st.session_state.run_id = ""
if "selected_tanks" not in st.session_state: st.session_state.selected_tanks = ["301호 탱크", "302호 탱크"]
if "raw_material" not in st.session_state: st.session_state.raw_material = "국산 1등급A 원유 (표준)"
if "batch_volume" not in st.session_state: st.session_state.batch_volume = 4000
if "batch_start_dt" not in st.session_state: st.session_state.batch_start_dt = None
if "step_durations" not in st.session_state: st.session_state.step_durations = {}
if "step_entry_times" not in st.session_state: st.session_state.step_entry_times = {}
if "indoor_t" not in st.session_state: st.session_state.indoor_t = 24.5
if "temp_locked" not in st.session_state: st.session_state.temp_locked = False
if "show_temp_popup" not in st.session_state: st.session_state.show_temp_popup = False
if "tank_measurements" not in st.session_state: st.session_state.tank_measurements = {}

curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
kst_now = get_kst_now()

if "calc_res" not in st.session_state:
    st.session_state.calc_res = calculate_multi_tank_temperatures(
        round(float(kst_now.hour + kst_now.minute / 60.0), 1),
        st.session_state.indoor_t, curr_t, min_t, max_t,
        st.session_state.selected_tanks, st.session_state.raw_material
    )

step_defs = [
    (1, "A100", "Base 배합", "T101~104"),
    (2, "A200", "살균/냉각", "P101TC02"),
    (3, "A300", "발효/보온", "탱크별 재킷 온수"),
    (4, "A400", "시럽 배합", "T401~402"),
    (5, "A500", "시럽 살균", "P201TC02"),
    (6, "A600", "급속 칠링", "PHE301"),
    (7, "A700", "서지/MQI", "701~705호")
]
cur_step = st.session_state.process_step

@st.dialog("공정 단계별 실내온도 재설정", dismissible=False)
def step_indoor_temp_modal(s_code, s_name):
    st.markdown(f"#### [{s_code} {s_name}] 단계 진입")
    st.markdown(f"**투입 탱크:** `{', '.join(st.session_state.selected_tanks)}`")
    st.markdown("현재 작업장 실내온도를 입력바람. 확정 즉시 각 탱크별 추천온도가 재계산됨.")
    pop_in_val = st.number_input(
        "현재 실내온도 (℃)", 10.0, 40.0, float(st.session_state.indoor_t), 0.1, format="%.1f", key=f"modal_in_t_{cur_step}"
    )
    if st.button("실내온도 적용 및 확정", type="primary", use_container_width=True):
        st.session_state.indoor_t = pop_in_val
        st.session_state.temp_locked = True
        st.session_state.show_temp_popup = False
        calc_h = st.session_state.get("start_hour", round(float(kst_now.hour + kst_now.minute / 60.0), 1))
        st.session_state.calc_res = calculate_multi_tank_temperatures(
            calc_h, pop_in_val, curr_t, min_t, max_t,
            st.session_state.selected_tanks, st.session_state.raw_material
        )
        st.rerun()

if st.session_state.show_temp_popup and cur_step in [2, 3, 6, 7]:
    s_info = step_defs[cur_step - 1]
    step_indoor_temp_modal(s_info[1], s_info[2])

# =============================================================
# 3-1. 상단 고정(Sticky) 퍼플 공정 흐름바 렌더링
#      - 스크롤해도 항상 상단에 고정
#      - 모바일에서는 가로 스크롤 칩(세로로 길게 밀리지 않음)
# =============================================================
def render_sticky_stepper(cur_step, step_defs, curr_t, min_t, max_t, weather_status):
    # 현재 단계 표시 텍스트
    if cur_step == 0:
        now_badge = "STEP 0 · 배치 착수 등록"
    elif cur_step >= 8:
        now_badge = "✔ 전 공정 종결"
    else:
        _s = step_defs[cur_step - 1]
        now_badge = f"진행중 · {_s[1]} {_s[2]}"

    chips_html = ""
    for (s_idx, s_code, s_label, s_tag) in step_defs:
        if cur_step == 0 or cur_step < s_idx:
            state, icon = "wait", "⏱"
        elif cur_step > s_idx:
            state, icon = "done", "✔"
        else:
            state, icon = "active", "▶"
        chips_html += (
            f'<div class="fs-chip fs-{state}">'
            f'<span class="fs-icon">{icon}</span>'
            f'<span class="fs-code">{s_code}</span>'
            f'<span class="fs-label">{s_label}</span>'
            f'</div>'
        )
        if s_idx < len(step_defs):
            chips_html += '<div class="fs-arrow">›</div>'

    # 진행률 (Step 0=0%, 종결=100%)
    progress_pct = int(min(max(cur_step, 0), 7) / 7 * 100)

    st.markdown(f"""
    <div class="fs-sticky">
        <div class="fs-head">
            <div class="fs-title">FermaAX™ SCADA <small>v7.6</small></div>
            <div class="fs-weather">기장군 기상: {curr_t}℃ ({min_t}℃~{max_t}℃) · {weather_status}</div>
            <div class="fs-now">{now_badge}</div>
        </div>
        <div class="fs-bar">{chips_html}</div>
        <div class="fs-progress-wrap"><div class="fs-progress" style="width:{progress_pct}%"></div></div>
    </div>
    """, unsafe_allow_html=True)

render_sticky_stepper(cur_step, step_defs, curr_t, min_t, max_t, weather_status)

# =============================================================
# STEP 0: 생산 배치 착수 등록 (다중 탱크 선택)
# =============================================================
if st.session_state.process_step == 0:
    st.subheader("[Step 0] 생산 배치 착수 등록 (다중 탱크 분입)")

    with st.expander("구글 스프레드시트 연동 상태 검증 (테스트 전송)", expanded=False):
        st.caption(f"연동 URL: `{GSHEET_WEBHOOK_URL[:55]}...`")
        if st.button("구글 시트 1줄 테스트 전송하기", use_container_width=True):
            test_payload = {
                "tanks_list": "301호 탱크, 302호 탱크", "raw_material": "국산 1등급A 원유 (표준)", "batch_volume": 4000,
                "start_time": format_korean_ampm(get_kst_now()), "cooling_temp": 39.1, "hotwater_temp": 38.4,
                "phe_temp": 7.3, "duration": 360, "acidity": 0.965, "ph": 4.70, "viscosity": 3200,
                "syneresis": 1.1, "taste": 5.0, "mqi_score": 100.0, "memo": "다중탱크 통신 검증"
            }
            ok, msg = send_to_google_sheet(test_payload)
            if ok: st.success("구글 시트 기록 성공!")
            else: st.error(f"전송 실패: {msg}")

    sel_tanks = st.multiselect(
        "이번 배치 투입 발효탱크 (복수 선택 가능)",
        list(TANK_SPECS.keys()),
        default=st.session_state.selected_tanks
    )
    if not sel_tanks:
        st.warning("최소 1개 이상의 발효탱크를 선택해야 함.")

    c_p1, c_p2 = st.columns(2)
    with c_p1:
        sel_raw = st.selectbox("투입 원유/배합원료", list(RAW_SPECS.keys()), index=0)
    with c_p2:
        sel_vol = st.number_input("배치 총 생산용량 (L)", min_value=1000, max_value=12000, value=st.session_state.batch_volume, step=500)

    auto_run_id = f"RUN_{kst_now.strftime('%Y%m%d_%H%M')}"
    st.info(f"내부 자동 생성 고유 코드: **`{auto_run_id}`** | 선택 탱크 수: **{len(sel_tanks)}개 탱크**")

    if st.button("이 설정으로 [배치 작업 시작 (A100 착수)]", type="primary", use_container_width=True):
        if not sel_tanks:
            st.error("투입할 발효탱크를 선택바람.")
        else:
            exact_kst_dt = get_kst_now()
            start_korean_val = format_korean_ampm(exact_kst_dt)
            start_hour_val = round(float(exact_kst_dt.hour + exact_kst_dt.minute / 60.0), 1)

            st.session_state.run_id = auto_run_id
            st.session_state.selected_tanks = sel_tanks
            st.session_state.raw_material = sel_raw
            st.session_state.batch_volume = sel_vol
            st.session_state.start_hour = start_hour_val
            st.session_state.batch_start_dt = exact_kst_dt
            st.session_state.start_time_korean = start_korean_val
            st.session_state.temp_locked = True
            st.session_state.step_entry_times["Step_1"] = exact_kst_dt

            st.session_state.calc_res = calculate_multi_tank_temperatures(
                start_hour_val, st.session_state.indoor_t, curr_t, min_t, max_t,
                sel_tanks, sel_raw
            )

            tanks_str = ", ".join(sel_tanks)
            save_batch_start_multi(
                auto_run_id, tanks_str, sel_raw, sel_vol,
                exact_kst_dt.strftime("%Y-%m-%d %H:%M:%S"), start_korean_val, curr_t, st.session_state.indoor_t
            )
            st.session_state.process_step = 1
            st.rerun()

# =============================================================
# STEP 1: A100 Base Mix 배합
# =============================================================
elif st.session_state.process_step == 1:
    st.subheader(f"[Step 1: A100] Base Mix 배합 (투입: {', '.join(st.session_state.selected_tanks)})")
    mix_temp = st.number_input("배합탱크 실측 원유온도 (℃)", 4.0, 25.0, 10.5, 0.1)
    mix_status = st.selectbox("배합 상태 점검", ["정상 배합 완료 (균질 양호)", "원료 투입 중"])
    if st.button("A100 완료 [다음 A200 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_1", kst_now)).total_seconds())
        st.session_state.step_durations["Step_1"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A100", "Base Mix 배합", step_dur_str, "T101~T104", 0.0, 0.0, mix_temp, mix_status)
        st.session_state.step_entry_times["Step_2"] = get_kst_now()
        st.session_state.process_step = 2
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 2: A200 살균 및 냉각 분입
# =============================================================
elif st.session_state.process_step == 2:
    st.subheader("[Step 2: A200] 살균 및 냉각 분입")
    c_res = st.session_state.calc_res
    st.info(f"""
    * **살균기 공통 토출 최적화 (선택 {len(st.session_state.selected_tanks)}개 탱크 중 최대 방열 단열계수 기준)**
    * **AI 추천 살균냉각온도:** **{c_res['rec_cooling']} ℃** (배관손실 +{c_res['delta_t_pipe']}℃ 반영)
    * 살균 토출액은 배관을 거쳐 각 발효탱크로 동시 분입됨.
    """)
    op_set_cool = st.number_input("HMI 실제 살균냉각 설정값 (P101TC02.SP, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)
    act_meas_cool = st.number_input("살균기 토출 실측 액온 (P101TT02, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)
    if st.button("A200 확인 [다음 A300 발효보온 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_2", kst_now)).total_seconds())
        st.session_state.step_durations["Step_2"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A200", "살균냉각분입", step_dur_str, "P101TC02", c_res['rec_cooling'], op_set_cool, act_meas_cool, "정상 설정")
        st.session_state.step_entry_times["Step_3"] = get_kst_now()
        st.session_state.process_step = 3
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 3: A300 발효 및 재킷 보온 (탱크별 개별 온도 제어판)
# =============================================================
elif st.session_state.process_step == 3:
    st.subheader("[Step 3: A300] 발효 및 재킷 보온 제어 (탱크별 개별 관리)")
    st.caption("각 탱크의 단열계수에 따라 AI 추천 핫워터 순환온도가 개별 산출됨.")

    c_res = st.session_state.calc_res
    tank_data_inputs = {}

    for idx, tank_name in enumerate(st.session_state.selected_tanks):
        t_info = c_res["tanks"].get(tank_name, {"rec_hotwater": 38.3, "rec_tank_tt": 38.5, "kappa": 1.00})
        st.markdown(f"#### 🏷️ **{tank_name}** (단열계수 $\\kappa$={t_info['kappa']})")

        col_t_rec, col_t_in1, col_t_in2 = st.columns([1.2, 1.0, 1.0])
        with col_t_rec:
            st.info(f"**AI 추천 핫워터:** **`{t_info['rec_hotwater']} ℃`**\n\n**목표 품온:** `{t_info['rec_tank_tt']} ℃`")
        with col_t_in1:
            set_hw = st.number_input(
                f"{tank_name} 핫워터 설정값 (℃)",
                35.0, 42.0, float(t_info['rec_hotwater']), 0.1, key=f"hw_{tank_name}"
            )
        with col_t_in2:
            meas_5h = st.number_input(
                f"{tank_name} 5H 실측품온 (℃)",
                35.0, 43.0, 39.5, 0.1, key=f"meas_{tank_name}"
            )
        tank_data_inputs[tank_name] = {"set_hw": set_hw, "meas_5h": meas_5h, "rec_hw": t_info['rec_hotwater']}
        st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)

    acid_5h = st.number_input("발효 5H 공통 실측 산도", 0.700, 0.950, 0.910, 0.005, format="%.3f")

    if st.button("5H 전 탱크 점검 완료 [다음 A400 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_3", kst_now)).total_seconds())
        st.session_state.step_durations["Step_3"] = step_dur_str
        st.session_state.tank_measurements = tank_data_inputs
        st.session_state.acid_5h = acid_5h

        summary_list = []
        for t_name, d_vals in tank_data_inputs.items():
            summary_list.append(f"{t_name}:{d_vals['meas_5h']}℃(HW:{d_vals['set_hw']}℃)")
            log_step_temp_multi(
                st.session_state.run_id, "A300", f"발효보온_{t_name}", step_dur_str,
                f"{t_name}_Jacket", d_vals["rec_hw"], d_vals["set_hw"], d_vals["meas_5h"], "정상 유지"
            )
        st.session_state.tank_summary_str = " | ".join(summary_list)

        st.session_state.step_entry_times["Step_4"] = get_kst_now()
        st.session_state.process_step = 4
        st.session_state.temp_locked = False
        st.rerun()

# =============================================================
# STEP 4: A400 시럽 배합 및 용해
# =============================================================
elif st.session_state.process_step == 4:
    st.subheader("[Step 4: A400] 시럽 배합 및 용해")
    syrup_mix_t = st.number_input("시럽 배합 실측 온도 (℃)", 15.0, 40.0, 24.5, 0.1)
    syrup_brix = st.number_input("시럽 실측 Brix", 50.0, 75.0, 65.0, 0.1)
    if st.button("A400 완료 [다음 A500 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_4", kst_now)).total_seconds())
        st.session_state.step_durations["Step_4"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A400", "시럽배합용해", step_dur_str, "T401~T402", 24.5, 24.5, syrup_mix_t, f"{syrup_brix} Brix")
        st.session_state.step_entry_times["Step_5"] = get_kst_now()
        st.session_state.process_step = 5
        st.session_state.temp_locked = False
        st.rerun()

# =============================================================
# STEP 5: A500 시럽 살균 및 냉각
# =============================================================
elif st.session_state.process_step == 5:
    st.subheader("[Step 5: A500] 시럽 살균 및 냉각")
    syrup_pasteur_t = st.number_input("시럽 살균 실측 온도 (℃)", 80.0, 95.0, 85.0, 0.1)
    syrup_cool_t = st.number_input("시럽 냉각 실측 온도 (℃)", 15.0, 35.0, 25.0, 0.1)
    if st.button("A500 완료 [다음 A600 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_5", kst_now)).total_seconds())
        st.session_state.step_durations["Step_5"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A500", "시럽살균냉각", step_dur_str, "P201TC02", 85.0, syrup_pasteur_t, syrup_cool_t, f"냉각 {syrup_cool_t}℃")
        st.session_state.step_entry_times["Step_6"] = get_kst_now()
        st.session_state.process_step = 6
        st.session_state.temp_locked = False
        st.rerun()

# =============================================================
# STEP 6: A600 급속 칠링
# =============================================================
elif st.session_state.process_step == 6:
    st.subheader("[Step 6: A600] 급속 칠링 (PHE301)")
    acid_curr = getattr(st.session_state, 'acid_5h', 0.910)
    rem_acid = max(0.0, 0.965 - acid_curr)
    trig_min = 300 if rem_acid <= 0 else int(300 + (rem_acid / 0.0015))
    chilling_target = st.session_state.calc_res.get("target_chilling", 7.3)

    st.info(f"**목표 칠링온도:** **{chilling_target} ℃** (권장 선행냉각: 접종 후 {trig_min}분)")
    act_dur_min = st.number_input("실제 냉각 개시 분(Time)", 300, 420, int(trig_min), 1)
    phe_out_t = st.number_input("PHE301 토출온도 (℃)", 4.0, 15.0, float(chilling_target), 0.1)
    if st.button("A600 확인 [다음 A700 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_6", kst_now)).total_seconds())
        st.session_state.step_durations["Step_6"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A600", "PHE301급속냉각", step_dur_str, "PHE301STT02", chilling_target, chilling_target, phe_out_t, f"{act_dur_min}분 개시")
        st.session_state.phe_out_t = phe_out_t
        st.session_state.step_entry_times["Step_7"] = get_kst_now()
        st.session_state.process_step = 7
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 7: MQI 품질 검증 및 전 탱크 통합 로깅
# =============================================================
elif st.session_state.process_step == 7:
    st.subheader("[Step 7: A700] MQI 품질 검증 및 최종 자동 저장")
    f_acid = st.number_input("최종 산도 [골든: 0.965]", 0.800, 1.200, 0.965, 0.001, format="%.3f")
    f_ph = st.number_input("최종 pH [골든: 4.70]", 4.00, 5.50, 4.70, 0.01)
    f_total_dur = st.number_input("총 소요 발효시간 (분)", 300, 450, 378, 1)
    f_visc = st.number_input("점도 (cPs)", 1000, 5000, 3200, 50)
    f_syn = st.number_input("離乳率 (Syneresis %)", 0.0, 5.0, 1.1, 0.1)
    f_taste = st.number_input("관능 점수 (5.0 만점)", 1.0, 5.0, 5.0, 0.1)
    f_memo = st.text_input("작업자 특이사항 메모", "특이사항 없음 (정상 제어)")

    mqi_total = round(100.0 - (abs(f_acid - 0.965) * 200) - (abs(f_ph - 4.70) * 30), 1)
    mqi_total = max(0.0, min(100.0, mqi_total))

    st.markdown(f"### **최종 MQI 점수: `{mqi_total} / 100 점`**")

    if st.button("전체 공정 최종 종결 [엑셀 자동 누적 & 구글 시트 전송]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_7", kst_now)).total_seconds())
        st.session_state.step_durations["Step_7"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A700", "서지충전&MQI", step_dur_str, "701~705호", 7.3, 7.3, 7.3, f"MQI {mqi_total}점")

        t_summary = getattr(st.session_state, 'tank_summary_str', "탱크 개별입력 완료")
        save_final_mqi_multi(st.session_state.run_id, f_total_dur, f_acid, f_ph, f_visc, f_syn, f_taste, mqi_total, t_summary, f_memo)

        final_record = {
            "tanks_list": ", ".join(st.session_state.selected_tanks),
            "raw_material": st.session_state.raw_material,
            "batch_volume": st.session_state.batch_volume,
            "start_time": st.session_state.start_time_korean,
            "cooling_temp": st.session_state.calc_res.get('rec_cooling', 39.1),
            "hotwater_temp": t_summary,
            "phe_temp": getattr(st.session_state, 'phe_out_t', 7.3),
            "duration": f_total_dur,
            "acidity": f_acid,
            "ph": f_ph,
            "viscosity": f_visc,
            "syneresis": f_syn,
            "taste": f_taste,
            "mqi_score": mqi_total,
            "memo": f_memo
        }

        gsheet_ok, gsheet_msg = send_to_google_sheet(final_record)
        st.session_state.gsheet_status = gsheet_msg if gsheet_ok else f"실패 ({gsheet_msg})"

        st.success("배치 공정 저장이 성공적으로 완료되었음!")
        st.session_state.process_step = 8
        st.rerun()

elif st.session_state.process_step == 8:
    st.success("🎉 모든 공정이 정상 종결 및 누적 저장되었음.")
    df_completed = get_all_completed_batches_multi()
    df_logs = get_step_logs_multi(st.session_state.run_id)

    st.dataframe(df_completed)

    excel_bytes = create_excel_download(df_completed, df_logs)
    st.download_button(
        label="📥 전체 데이터 (.xlsx) 다운로드",
        data=excel_bytes,
        file_name=f"FermaAX_History_{kst_now.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    if st.button("새로운 생산 배치 시작하기", type="primary", use_container_width=True):
        st.session_state.process_step = 0
        st.rerun()
