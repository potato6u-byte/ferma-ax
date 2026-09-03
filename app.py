# -*- coding: utf-8 -*-
"""
FermaAX™ Mobile-Optimized SCADA SOP & AI Temperature Controller v7.6
• 단일 공정 다중 탱크(Multi-Tank) 분입 시스템 완벽 지원
• Step 0: 이번 배치에 투입할 발효탱크 다중 선택 (Multi-Select)
• Step 2: 투입 탱크 중 최대 열손실 탱크 기준 살균냉각 안전온도 연산
• Step 3 (핵심): 선택된 탱크별 개별 단열계수(kappa) 기반 동적 핫워터 AI 추천 및 실측 개별 제어판 제공
• 구글 스프레드시트 웹훅 및 로컬 엑셀(.xlsx) 통합 분산 로깅 완비
"""
import os
import io
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import requests
import sqlite3
from datetime import datetime, date, timedelta, timezone

# 1. 구글 스프레드시트 웹 앱 URL
GSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzMcyBZL5mhYVfP5ShDhixvlm50tqvsoDu99VmrFbGivDegWjiFRCTZ7r4Eqam7mYga/exec"

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone(timedelta(hours=9))

def get_kst_now():
    return datetime.now(KST)

def format_korean_ampm(dt_obj):
    if not dt_obj:
        return ""
    ampm = "오전" if dt_obj.hour < 12 else "오후"
    return f"{ampm} {dt_obj.strftime('%H:%M:%S')}"

def format_time_delta(seconds_total):
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

st.set_page_config(page_title="런 발효유 SCADA", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    header[data-testid="stHeader"] { display: none !important; height: 0px !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    html, body, [class*="css"] { font-size: 16px !important; }
    div[data-testid="stForm"] {
        border: 1.5px solid #38bdf8 !important;
        border-radius: 12px !important;
        background: #0f172a !important;
        padding: 10px !important;
        box-sizing: border-box !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        margin-bottom: 8px !important;
    }
    div[data-testid="stForm"] .stNumberInput { margin-bottom: 0px !important; }
    div[data-testid="stForm"] .stNumberInput input {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
        border: 1.5px solid #0284c7 !important;
        font-size: 1.35rem !important;
        font-weight: 900 !important;
        text-align: center !important;
        border-radius: 8px !important;
    }
    div[data-testid="stForm"] button {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #38bdf8 !important;
        font-size: 1.15rem !important;
        font-weight: 900 !important;
        border-radius: 8px !important;
        height: 46px !important;
        margin-top: 2px !important;
    }
    .stTextInput label, .stNumberInput label, .stSelectbox label, .stMultiSelect label {
        font-size: 1.1rem !important; font-weight: 700 !important; color: #0f172a !important;
    }
    .stButton button {
        font-size: 1.15rem !important; font-weight: 800 !important;
        padding: 0.6rem 1rem !important; border-radius: 8px !important;
    }
    h1 { font-size: 1.9rem !important; }
    h2 { font-size: 1.6rem !important; }
    h3 { font-size: 1.35rem !important; }
</style>
""", unsafe_allow_html=True)

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

def append_to_local_excel(data_dict):
    excel_path = "ferma_history.xlsx"
    new_df = pd.DataFrame([data_dict])
    try:
        if os.path.exists(excel_path):
            old_df = pd.read_excel(excel_path, engine='openpyxl')
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            combined_df.to_excel(excel_path, index=False, engine='openpyxl')
        else:
            new_df.to_excel(excel_path, index=False, engine='openpyxl')
        return True, "서버 엑셀 누적 완료"
    except Exception as e:
        return False, f"엑셀 오류: {str(e)[:25]}"

def send_to_google_sheet(payload):
    if not GSHEET_WEBHOOK_URL or "여기에" in GSHEET_WEBHOOK_URL:
        return False, "구글 시트 URL 미설정"
    try:
        headers = {"Content-Type": "application/json"}
        res = requests.post(
            GSHEET_WEBHOOK_URL,
            data=json.dumps(payload),
            headers=headers,
            timeout=12,
            allow_redirects=True
        )
        if res.status_code in [200, 302]:
            return True, "구글 스프레드시트 기록 성공"
        else:
            return False, f"구글 서버 거부 (HTTP {res.status_code})"
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_gijang_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=35.297&longitude=129.200&"
        "current=temperature_2m&"
        "daily=temperature_2m_max,temperature_2m_min&"
        "timezone=Asia%2FSeoul"
    )
    try:
        res = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
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

# 탱크별 단열 계수 및 원료 물성 프로파일
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
    t_swing = (max_t - min_t) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)
    t_in_traj = indoor_t + 0.622 * (t_out_traj - out_t) * (1.0 - np.exp(-dt / 2.5))

    early_mask = dt <= 1.5
    late_mask = dt > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    m_prof = RAW_SPECS.get(raw_mat, {"cp": 3930.0, "offset": 0.0, "cooling_target": 7.3})
    c_p = m_prof["cp"]
    mat_offset = m_prof["offset"]
    delta_t_pipe = round((1.85 * 8.35 * max(0.0, 38.4 - indoor_t)) / (2.083 * c_p), 2)

    # 1. A200 살균기 토출 냉각 추천 (선택 탱크 중 최대 방열 단열계수 기준)
    kappas = [TANK_SPECS[t]["kappa"] for t in tank_list if t in TANK_SPECS]
    max_kappa = max(kappas) if kappas else 1.00
    base_cool = 38.4 + max(0.0, (32.0 - t_eff_early) * 0.050 * max_kappa) + delta_t_pipe + mat_offset
    rec_cooling = min(39.3, round(base_cool, 1))

    # 2. A300 발효/보온 추천 (탱크별 개별 산출)
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

# 세션 상태 초기화
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
    (7, "A700", "MQI 충전", "서지/충전")
]
cur_step = st.session_state.process_step

if hasattr(st, "dialog"):
    @st.dialog("공정 단계별 실내온도 재설정", dismissible=False)
    def step_indoor_temp_modal(s_code, s_name):
        st.markdown(f"#### [{s_code} {s_name}] 단계 진입")
        st.markdown(f"**투입 탱크:** `{', '.join(st.session_state.selected_tanks)}`")
        st.markdown("현재 작업장 실내온도를 입력바람. 확정 즉시 각 탱크별 추천온도가 재계산됨.")
        pop_in_val = st.number_input(
            "현재 실내온도 (℃)", 10.0, 40.0, float(st.session_state.indoor_t), 0.1, format="%.1f", key=f"modal_in_t_{cur_step}"
        )
        if st.button("온도 확정 및 공정 시작", type="primary", use_container_width=True):
            st.session_state.indoor_t = pop_in_val
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            calc_h = st.session_state.get("start_hour", round(float(kst_now.hour + kst_now.minute / 60.0), 1))
            st.session_state.calc_res = calculate_multi_tank_temperatures(
                calc_h, pop_in_val, curr_t, min_t, max_t,
                st.session_state.selected_tanks, st.session_state.raw_material
            )
            st.rerun()

if st.session_state.show_temp_popup and (1 <= cur_step <= 7):
    if hasattr(st, "dialog"):
        step_indoor_temp_modal(step_defs[cur_step - 1][1], step_defs[cur_step - 1][2])

# 상단 헤더
col_weather, col_indoor, col_clock = st.columns([1.0, 1.1, 1.2])

with col_weather:
    st.markdown(
        f"""
        <div style="text-align: center; padding: 10px; background: #0f172a; border-radius: 12px; border: 1.5px solid #38bdf8; margin-bottom: 8px;">
            <div style="font-size: 11px; color: #94a3b8; font-weight: bold;">기장군 외기 ({weather_status})</div>
            <div style="font-size: 26px; font-weight: 900; color: #f43f5e; font-family: monospace; line-height: 1.2; margin: 2px 0;">{curr_t} ℃</div>
            <div style="font-size: 11px; color: #38bdf8; font-weight: 700;">최저 {min_t}℃ ~ 최고 {max_t}℃</div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_indoor:
    curr_step_name_label = step_defs[cur_step - 1][1] if (1 <= cur_step <= 7) else "Step 0"
    if st.session_state.temp_locked:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 10px; background: #0f172a; border-radius: 12px; border: 1.5px solid #10b981; margin-bottom: 4px;">
                <div style="font-size: 11px; color: #a7f3d0; font-weight: bold;">[{curr_step_name_label}] 실내온도 확정 고정</div>
                <div style="font-size: 24px; font-weight: 900; color: #34d399; font-family: monospace; line-height: 1.2; margin: 2px 0;">{st.session_state.indoor_t} ℃</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("온도 수정 (재입력)", use_container_width=True, key="unlock_temp_btn"):
            st.session_state.temp_locked = False
            st.rerun()
    else:
        with st.form("quick_indoor_temp_form", clear_on_submit=False):
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="font-size: 11px; color: #94a3b8; font-weight: bold;">[{curr_step_name_label}] 실내온도</span>
                    <span style="font-size: 11px; color: #facc15; font-weight: 800;">입력 대기</span>
                </div>
                """,
                unsafe_allow_html=True
            )
            c_in_val, c_in_btn = st.columns([1.5, 1.0])
            with c_in_val:
                typed_in_temp = st.number_input(
                    "실내온도입력", 10.0, 40.0, float(st.session_state.indoor_t), 0.1, format="%.1f",
                    label_visibility="collapsed", key="header_indoor_input_field"
                )
            with c_in_btn:
                submitted_lock = st.form_submit_button("입력", use_container_width=True)
                if submitted_lock:
                    st.session_state.indoor_t = typed_in_temp
                    st.session_state.temp_locked = True
                    calc_h = st.session_state.get("start_hour", round(float(kst_now.hour + kst_now.minute / 60.0), 1))
                    st.session_state.calc_res = calculate_multi_tank_temperatures(
                        calc_h, typed_in_temp, curr_t, min_t, max_t,
                        st.session_state.selected_tanks, st.session_state.raw_material
                    )
                    st.rerun()

batch_start_epoch = int(st.session_state.batch_start_dt.timestamp() * 1000) if (cur_step > 0 and st.session_state.batch_start_dt) else 0
active_step_code = step_defs[cur_step - 1][1] if 1 <= cur_step <= 7 else ""
active_step_epoch = int(st.session_state.step_entry_times.get(f"Step_{cur_step}", kst_now).timestamp() * 1000) if 1 <= cur_step <= 7 else 0

with col_clock:
    clock_html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
        body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif; }}
        .clock-card {{ text-align: center; padding: 10px; background: #0f172a; border-radius: 12px; border: 1.5px solid #38bdf8; display: flex; flex-direction: column; justify-content: center; }}
        .clock-title {{ font-size: 11px; color: #94a3b8; font-weight: bold; }}
        .clock-time {{ font-size: 22px; font-weight: 900; color: #38bdf8; font-family: monospace; line-height: 1.2; margin: 2px 0; }}
        .ampm {{ font-size: 12px; color: #a5f3fc; margin-right: 4px; }}
        .elapsed-box {{ font-size: 11px; color: #4ade80; font-weight: 800; }}
        .step-elapsed-box {{ font-size: 11px; color: #facc15; font-weight: 800; }}
    </style></head><body>
    <div class="clock-card">
        <div class="clock-title">대한민국 표준시 (KST)</div>
        <div class="clock-time" id="live-clock">--:--:--</div>
        <div class="elapsed-box" id="live-elapsed"></div>
        <div class="step-elapsed-box" id="live-step-elapsed"></div>
    </div>
    <script>
        function updateClock() {{
            const now = new Date();
            const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
            const kst = new Date(utc + (9 * 3600000));
            let hrs = kst.getHours();
            const mins = String(kst.getMinutes()).padStart(2, '0');
            const secs = String(kst.getSeconds()).padStart(2, '0');
            const ampm = hrs < 12 ? '오전' : '오후';
            document.getElementById('live-clock').innerHTML = `<span class="ampm">${{ampm}}</span> ${{String(hrs).padStart(2,'0')}}:${{mins}}:${{secs}}`;
            const startEpoch = {batch_start_epoch};
            if (startEpoch > 0) {{
                const diffSec = Math.max(0, Math.floor((now.getTime() - startEpoch) / 1000));
                const h = Math.floor(diffSec / 3600);
                const m = Math.floor((diffSec % 3600) / 60);
                const s = diffSec % 60;
                document.getElementById('live-elapsed').innerHTML = '총 경과: ' + (h > 0 ? `${{h}}시간 ${{m}}분` : `${{m}}분 ${{s}}초`);
            }}
            const stepEpoch = {active_step_epoch};
            if (stepEpoch > 0) {{
                const sDiff = Math.max(0, Math.floor((now.getTime() - stepEpoch) / 1000));
                const sm = Math.floor(sDiff / 60);
                const ss = sDiff % 60;
                document.getElementById('live-step-elapsed').innerHTML = '현재 {active_step_code}: ' + (sm > 0 ? `${{sm}}분 ${{ss}}초` : `${{ss}}초`);
            }}
        }}
        updateClock(); setInterval(updateClock, 1000);
    </script></body></html>
    """
    components.html(clock_html, height=105)

st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)

steps_data = []
for s_idx, s_code, s_label, s_tag in step_defs:
    s_state = "waiting" if cur_step == 0 or cur_step < s_idx else ("completed" if cur_step > s_idx else "active")
    s_dur = "대기" if cur_step == 0 or cur_step < s_idx else (st.session_state.step_durations.get(f"Step_{s_idx}", "완료") if cur_step > s_idx else "진행")
    steps_data.append({"index": s_idx, "code": s_code, "label": s_label, "state": s_state, "duration": s_dur})

stage_bar_html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
    body {{ margin: 0; padding: 0; background: transparent; overflow-x: auto; overflow-y: hidden; font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif; -webkit-overflow-scrolling: touch; }}
    .swipe-container {{ display: flex; gap: 8px; padding: 4px 2px; width: max-content; }}
    .step-card {{ flex: 0 0 100px; border-radius: 10px; padding: 6px 4px; text-align: center; border-width: 1.5px; border-style: solid; box-sizing: border-box; }}
    .state-waiting {{ background: #f8fafc; border-color: #cbd5e1; color: #64748b; }}
    .state-completed {{ background: #f0fdf4; border-color: #86efac; color: #15803d; }}
    .state-active {{ background: #eff6ff; border-color: #3b82f6; color: #1d4ed8; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3); }}
    .badge {{ font-size: 10px; font-weight: 800; }}
    .duration-text {{ font-size: 13px; font-weight: 900; margin: 2px 0; color: #0f172a; white-space: nowrap; }}
    .label {{ font-size: 10px; color: #64748b; font-weight: 600; }}
</style></head><body>
<div class="swipe-container" id="stage-swipe"></div>
<script>
    const steps = {json.dumps(steps_data, ensure_ascii=False)};
    const container = document.getElementById('stage-swipe');
    steps.forEach(s => {{
        const card = document.createElement('div');
        card.className = `step-card state-${{s.state}}`;
        let bTxt = s.state === 'completed' ? '완료' : (s.state === 'active' ? '진행 중' : '대기');
        card.innerHTML = `<div class="badge">${{bTxt}} | ${{s.code}}</div><div class="duration-text" id="dur-${{s.index}}">${{s.code}} ${{s.duration}}</div><div class="label">${{s.label}}</div>`;
        container.appendChild(card);
    }});
    const activeStepEpoch = {active_step_epoch};
    function updateDur() {{
        if (activeStepEpoch > 0) {{
            const diff = Math.max(0, Math.floor((Date.now() - activeStepEpoch) / 1000));
            const m = Math.floor(diff / 60);
            const s = diff % 60;
            const el = document.getElementById('dur-{cur_step}');
            if (el) el.innerText = '{active_step_code} ' + (m > 0 ? `${{m}}분 ${{s}}초` : `${{s}}초`);
        }}
    }}
    if (activeStepEpoch > 0) {{ updateDur(); setInterval(updateDur, 1000); }}
</script></body></html>
"""
components.html(stage_bar_html, height=80)
st.divider()

# =============================================================
# STEP 0: 생산 배치 착수 등록 (다중 탱크 선택)
# =============================================================
if st.session_state.process_step == 0:
    st.subheader("[Step 0] 생산 배치 착수 등록 (다중 탱크 분입)")
    
    with st.expander("구글 스프레드시트 연동 상태 검증 (테스트 전송)", expanded=False):
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

    # 선택된 각 탱크별로 독립적인 제어 카드 동적 생성
    for idx, tank_name in enumerate(st.session_state.selected_tanks):
        t_info = c_res["tanks"].get(tank_name, {"rec_hotwater": 38.3, "rec_tank_tt": 38.5, "kappa": 1.00})
        st.markdown(f"#### 🏷️ **{tank_name}** (단열계수 $\kappa$={t_info['kappa']})")
        
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

        # 개별 탱크 로그 기록
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
        st.session_state.show_temp_popup = True
        st.rerun()

elif st.session_state.process_step == 4:
    st.subheader("[Step 4: A400] 시럽 배합 및 용해")
    syrup_mix_t = st.number_input("시럽 배합탱크 액온 (℃)", 15.0, 35.0, 24.5, 0.1)
    syrup_brix = st.number_input("시럽 실측 당도 (Brix)", 10.0, 65.0, 45.0, 0.5)
    if st.button("A400 완료 [다음 A500 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_4", kst_now)).total_seconds())
        st.session_state.step_durations["Step_4"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A400", "시럽배합용해", step_dur_str, "T401~T402", 24.5, 24.5, syrup_mix_t, f"{syrup_brix} Brix")
        st.session_state.step_entry_times["Step_5"] = get_kst_now()
        st.session_state.process_step = 5
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

elif st.session_state.process_step == 5:
    st.subheader("[Step 5: A500] 시럽 살균/냉각")
    syrup_pasteur_t = st.number_input("살균 유지온도 (℃)", 75.0, 95.0, 85.0, 0.5)
    syrup_cool_t = st.number_input("냉각 토출온도 (℃)", 15.0, 30.0, 24.7, 0.1)
    if st.button("A500 완료 [다음 A600 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_5", kst_now)).total_seconds())
        st.session_state.step_durations["Step_5"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A500", "시럽살균냉각", step_dur_str, "P201TC02", 85.0, syrup_pasteur_t, syrup_cool_t, f"냉각 {syrup_cool_t}℃")
        st.session_state.step_entry_times["Step_6"] = get_kst_now()
        st.session_state.process_step = 6
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

elif st.session_state.process_step == 6:
    st.subheader(f"[Step 6: A600] 블렌딩 및 급속 냉각 ({st.session_state.raw_material})")
    rem_acid = 0.930 - getattr(st.session_state, 'acid_5h', 0.910)
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
    st.subheader(f"[Step 7: A700] MQI 품질 검증 및 최종 자동 저장")
    f_acid = st.number_input("최종 산도 [골든: 0.965]", 0.800, 1.200, 0.965, 0.001, format="%.3f")
    f_ph = st.number_input("최종 pH [골든: 4.70]", 4.00, 5.50, 4.70, 0.01)
    f_total_dur = st.number_input("총 소요 발효시간 (분)", 300, 450, 378, 1)
    f_visc = st.number_input("점도계 측정치 (cP)", 1500.0, 4500.0, 3200.0, 50.0)
    f_syn = st.number_input("유청 분리율 (%)", 0.0, 15.0, 1.1, 0.1)
    f_taste = st.slider("관능 평가 점수 (5점 만점)", 1.0, 5.0, 4.8, 0.1)
    f_memo = st.text_input("특이사항 메모", placeholder="특이사항 입력")

    mqi_total = round(min(100.0, max(0.0, (30.0 - abs(f_acid - 0.965) * 500.0) + (40.0 - abs(f_visc - 3200.0) * 0.02 - (f_syn * 2.0)) + (f_taste / 5.0 * 30.0))), 1)
    st.markdown(f"### MQI 종합 품질점수: **`{mqi_total} / 100 점`**")

    if st.button("전체 공정 최종 종결 [엑셀 자동 누적 & 구글 시트 전송]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_7", kst_now)).total_seconds())
        st.session_state.step_durations["Step_7"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A700", "서지충전&MQI", step_dur_str, "701~705호", 7.3, 7.3, 7.3, f"MQI {mqi_total}점")

        t_summary = getattr(st.session_state, 'tank_summary_str', "탱크 개별입력 완료")
        save_final_mqi_multi(st.session_state.run_id, f_total_dur, f_acid, f_ph, f_visc, f_syn, f_taste, mqi_total, t_summary, f_memo)

        final_record = {
            "발효탱크목록": ", ".join(st.session_state.selected_tanks),
            "생산원료": st.session_state.raw_material,
            "생산용량(L)": st.session_state.batch_volume,
            "착수시각": st.session_state.start_time_korean,
            "살균냉각(℃)": st.session_state.calc_res.get('rec_cooling', 39.1),
            "탱크별품온요약": t_summary,
            "급속칠링(℃)": getattr(st.session_state, 'phe_out_t', 7.3),
            "소요시간(분)": f_total_dur,
            "산도": f_acid,
            "pH": f_ph,
            "점도(cP)": f_visc,
            "유청분리(%)": f_syn,
            "맛점수": f_taste,
            "MQI점수": mqi_total,
            "특이사항": f_memo,
            "기록일시": get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        }

        excel_ok, excel_msg = append_to_local_excel(final_record)
        st.session_state.excel_status = excel_msg

        gsheet_payload = {
            "tank_no": final_record["발효탱크목록"],
            "raw_material": final_record["생산원료"],
            "batch_volume": final_record["생산용량(L)"],
            "start_time": final_record["착수시각"],
            "cooling_temp": final_record["살균냉각(℃)"],
            "hotwater_temp": t_summary,
            "phe_temp": final_record["급속칠링(℃)"],
            "duration": final_record["소요시간(분)"],
            "acidity": final_record["산도"],
            "ph": final_record["pH"],
            "viscosity": final_record["점도(cP)"],
            "syneresis": final_record["유청분리(%)"],
            "taste": final_record["맛점수"],
            "mqi_score": final_record["MQI점수"],
            "memo": final_record["특이사항"]
        }
        g_ok, g_msg = send_to_google_sheet(gsheet_payload)
        st.session_state.gsheet_status = g_msg
        st.session_state.gsheet_ok = g_ok

        st.session_state.process_step = 8
        st.rerun()

elif st.session_state.process_step == 8:
    st.success(f"[{', '.join(st.session_state.selected_tanks)}] 공정 종결 및 저장 완료")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.info(f"**서버 엑셀 상태:** {getattr(st.session_state, 'excel_status', '저장 완료')}")
    with col_s2:
        g_msg = getattr(st.session_state, 'gsheet_status', '미설정')
        if getattr(st.session_state, 'gsheet_ok', False):
            st.success(f"**구글 시트:** {g_msg}")
        else:
            st.error(f"**구글 시트:** {g_msg}")

    all_df = get_all_completed_batches_multi()
    if not all_df.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            all_df.to_excel(writer, index=False, sheet_name='다중탱크공정이력')
        excel_data = buffer.getvalue()

        st.download_button(
            label="누적 공정기록 엑셀(.xlsx) 내 기기로 다운로드",
            data=excel_data,
            file_name=f"FermaAX_MultiTankLog_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("#### 이번 배치 단계별 온도/시간 이력")
    cur_logs = get_step_logs_multi(st.session_state.run_id)
    st.dataframe(cur_logs, use_container_width=True)

    if st.button("새로운 배치 작업 시작하기", use_container_width=True):
        st.session_state.process_step = 0
        st.session_state.run_id = ""
        st.session_state.batch_start_dt = None
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = False
        st.rerun()
