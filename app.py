# -*- coding: utf-8 -*-
"""
FermaAX™ Mobile-Optimized SCADA SOP & AI Temperature Controller v7.0
• 모바일 화면 완벽 대응 반응형 CSS 탑재 (상단 카드 삐져나옴 및 겹침 원천 차단)
• 실내온도 카드: 인라인 플렉스 레이아웃으로 버튼 이탈 완전 방지
• 상단 7단계 공정 바: 모바일 터치 스와이프(가로 스크롤) 지원으로 카드 찌그러짐 방지
• 단계 전환 시 실내온도 재설정 모달 팝업 및 확정 잠금/수정 기능 유지
• AI 4D 최적화 엔진 실시간 연동 및 구글 시트 영구 누적 기록 완비
"""
import os
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import requests
import sqlite3
from datetime import datetime, date, timedelta, timezone

# =============================================================
# 구글 스프레드시트 웹 앱 URL 설정
# =============================================================
GSHEET_WEBHOOK_URL = "여기에_복사한_웹앱_URL을_붙여넣으세요"

# 0. 대한민국 표준시(KST) 타임존 및 시각 함수
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

# 1. 반응형 페이지 설정
st.set_page_config(
    page_title="런 발효유 SCADA",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# [모바일 완벽 대응 반응형 커스텀 CSS]
st.markdown("""
<style>
    /* 기본 여백 및 글자 크기 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    html, body, [class*="css"] {
        font-size: 16px !important;
    }
    
    /* 상단 실내온도 폼 카드 반응형 스타일 */
    div[data-testid="stForm"] {
        border: 1.5px solid #38bdf8 !important;
        border-radius: 12px !important;
        background: #0f172a !important;
        padding: 10px !important;
        box-sizing: border-box !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        margin-bottom: 8px !important;
    }
    div[data-testid="stForm"] .stNumberInput {
        margin-bottom: 0px !important;
    }
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
    
    /* 입력 위젯 및 버튼 스타일 */
    .stTextInput label, .stNumberInput label, .stSelectbox label {
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
    }
    .stButton button {
        font-size: 1.15rem !important;
        font-weight: 800 !important;
        padding: 0.6rem 1rem !important;
        border-radius: 8px !important;
    }
    h1 { font-size: 1.9rem !important; }
    h2 { font-size: 1.6rem !important; }
    h3 { font-size: 1.35rem !important; }
    h4 { font-size: 1.2rem !important; }
</style>
""", unsafe_allow_html=True)

# 2. SQLite 데이터베이스 초기화
DB_FILE = "ferma_master_history.db"

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

def send_to_google_sheet(payload):
    if not GSHEET_WEBHOOK_URL or "여기에" in GSHEET_WEBHOOK_URL:
        return False, "구글 시트 URL 미설정"
    try:
        res = requests.post(GSHEET_WEBHOOK_URL, json=payload, timeout=8)
        if res.status_code == 200:
            return True, "구글 시트 영구 저장 완료"
        else:
            return False, f"구글 응답 오류: {res.status_code}"
    except Exception as e:
        return False, f"네트워크 지연: {str(e)[:15]}"

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

# 3. 부산 기장군 실시간 기상 연동
@st.cache_data(ttl=300, show_spinner=False)
def fetch_gijang_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=35.297&longitude=129.200&"
        "current=temperature_2m&"
        "daily=temperature_2m_max,temperature_2m_min&"
        "timezone=Asia%2FSeoul"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            curr_t = float(data["current"]["temperature_2m"])
            min_t = float(data["daily"]["temperature_2m_min"][0])
            max_t = float(data["daily"]["temperature_2m_max"][0])
            return curr_t, min_t, max_t, "기상청 정상 연동"
        else:
            return 24.5, 20.0, 29.0, f"기상 서버 지연 ({res.status_code})"
    except Exception:
        return 24.5, 20.0, 29.0, "네트워크 지연 모드"

# 4. 4D 동적 최적화 연산 엔진
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
if "indoor_t" not in st.session_state:
    st.session_state.indoor_t = 24.5
if "temp_locked" not in st.session_state:
    st.session_state.temp_locked = False
if "show_temp_popup" not in st.session_state:
    st.session_state.show_temp_popup = False

curr_t, min_t, max_t, weather_status = fetch_gijang_weather()
kst_now = get_kst_now()

if "calc_res" not in st.session_state:
    default_start_h = round(float(kst_now.hour + kst_now.minute / 60.0), 1)
    st.session_state.calc_res = calculate_optimal_temperatures(
        default_start_h, st.session_state.indoor_t, curr_t, min_t, max_t
    )

step_defs = [
    (1, "A100", "Base 배합", "T101~104"),
    (2, "A200", "살균/냉각", "P101TC02"),
    (3, "A300", "발효/보온", "재킷 온수"),
    (4, "A400", "시럽 배합", "T401~402"),
    (5, "A500", "시럽 살균", "P201TC02"),
    (6, "A600", "급속 칠링", "PHE301"),
    (7, "A700", "MQI 충전", "서지/충전")
]

cur_step = st.session_state.process_step

# 6. 단계 전환 모달 팝업
if hasattr(st, "dialog"):
    @st.dialog("공정 단계별 실내온도 재설정", dismissible=False)
    def step_indoor_temp_modal(s_code, s_name):
        st.markdown(f"#### [{s_code} {s_name}] 단계 진입")
        st.markdown("현재 작업장 실내온도를 확인하여 입력바람. 확정 즉시 AI 추천온도가 재계산됨.")
        pop_in_val = st.number_input(
            "현재 실내온도 (℃)",
            min_value=10.0,
            max_value=40.0,
            value=float(st.session_state.indoor_t),
            step=0.1,
            format="%.1f",
            key=f"modal_in_t_{cur_step}"
        )
        if st.button("온도 확정 및 이번 공정 제어 시작", type="primary", use_container_width=True):
            st.session_state.indoor_t = pop_in_val
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            calc_h = st.session_state.get("start_hour", round(float(kst_now.hour + kst_now.minute / 60.0), 1))
            st.session_state.calc_res = calculate_optimal_temperatures(
                calc_h, pop_in_val, curr_t, min_t, max_t
            )
            st.rerun()

if st.session_state.show_temp_popup and (1 <= cur_step <= 7):
    code_now = step_defs[cur_step - 1][1]
    name_now = step_defs[cur_step - 1][2]
    if hasattr(st, "dialog"):
        step_indoor_temp_modal(code_now, name_now)

# -------------------------------------------------------------
# 7. 상단 헤더 3대 카드 (모바일 핏 반응형 재설계)
# -------------------------------------------------------------
col_weather, col_indoor, col_clock = st.columns([1.0, 1.1, 1.2])

# [1. 기장군 외기온도 카드]
with col_weather:
    st.markdown(
        f"""
        <div style="text-align: center; padding: 8px 10px; background: #0f172a; border-radius: 12px; border: 1.5px solid #38bdf8; margin-bottom: 8px;">
            <div style="font-size: 11px; color: #94a3b8; font-weight: bold;">부산 기장군 외기 ({weather_status})</div>
            <div style="font-size: 26px; font-weight: 900; color: #f43f5e; font-family: monospace; line-height: 1.2; margin: 2px 0;">{curr_t} ℃</div>
            <div style="font-size: 11px; color: #38bdf8; font-weight: 700;">최저 {min_t}℃ ~ 최고 {max_t}℃</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# [2. 실내온도 상태 및 인라인 입력 카드 (버튼 삐져나옴 방지)]
with col_indoor:
    curr_step_name_label = step_defs[cur_step - 1][1] if (1 <= cur_step <= 7) else "Step 0"
    if st.session_state.temp_locked:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 8px 10px; background: #0f172a; border-radius: 12px; border: 1.5px solid #10b981; margin-bottom: 4px;">
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
                    "실내온도입력",
                    min_value=10.0,
                    max_value=40.0,
                    value=float(st.session_state.indoor_t),
                    step=0.1,
                    format="%.1f",
                    label_visibility="collapsed",
                    key="header_indoor_input_field"
                )
            with c_in_btn:
                submitted_lock = st.form_submit_button("입력", use_container_width=True)
                if submitted_lock:
                    st.session_state.indoor_t = typed_in_temp
                    st.session_state.temp_locked = True
                    calc_h = st.session_state.get("start_hour", round(float(kst_now.hour + kst_now.minute / 60.0), 1))
                    st.session_state.calc_res = calculate_optimal_temperatures(
                        calc_h, typed_in_temp, curr_t, min_t, max_t
                    )
                    st.rerun()

# [3. KST 라이브 시계 카드]
batch_start_epoch = int(st.session_state.batch_start_dt.timestamp() * 1000) if (cur_step > 0 and st.session_state.batch_start_dt) else 0
active_step_code = ""
active_step_name = ""
active_step_epoch = 0
if 1 <= cur_step <= 7:
    active_step_code = step_defs[cur_step - 1][1]
    active_step_name = step_defs[cur_step - 1][2]
    cur_step_entry_dt = st.session_state.step_entry_times.get(f"Step_{cur_step}", kst_now)
    active_step_epoch = int(cur_step_entry_dt.timestamp() * 1000)

with col_clock:
    clock_component_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0; padding: 0; background: transparent; overflow: hidden;
                font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif;
            }}
            .clock-card {{
                text-align: center;
                padding: 8px 10px;
                background: #0f172a;
                border-radius: 12px;
                border: 1.5px solid #38bdf8;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            .clock-title {{ font-size: 11px; color: #94a3b8; font-weight: bold; }}
            .clock-time {{ font-size: 22px; font-weight: 900; color: #38bdf8; font-family: monospace; line-height: 1.2; margin: 2px 0; }}
            .ampm {{ font-size: 12px; color: #a5f3fc; margin-right: 4px; }}
            .elapsed-box {{ font-size: 11px; color: #4ade80; font-weight: 800; }}
            .step-elapsed-box {{ font-size: 11px; color: #facc15; font-weight: 800; }}
        </style>
    </head>
    <body>
        <div class="clock-card">
            <div class="clock-title">대한민국 표준시 (KST)</div>
            <div class="clock-time" id="live-kst-clock">--:--:--</div>
            <div class="elapsed-box" id="live-kst-elapsed"></div>
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
                document.getElementById('live-kst-clock').innerHTML = 
                    `<span class="ampm">${{ampm}}</span> ${{String(hrs).padStart(2,'0')}}:${{mins}}:${{secs}}`;

                const startEpoch = {batch_start_epoch};
                if (startEpoch > 0) {{
                    const diffSec = Math.max(0, Math.floor((now.getTime() - startEpoch) / 1000));
                    const h = Math.floor(diffSec / 3600);
                    const m = Math.floor((diffSec % 3600) / 60);
                    const s = diffSec % 60;
                    document.getElementById('live-kst-elapsed').innerHTML = 
                        '총 경과: ' + (h > 0 ? `${{h}}시간 ${{m}}분` : `${{m}}분 ${{s}}초`);
                }}
                const stepEpoch = {active_step_epoch};
                if (stepEpoch > 0) {{
                    const sDiff = Math.max(0, Math.floor((now.getTime() - stepEpoch) / 1000));
                    const sm = Math.floor(sDiff / 60);
                    const ss = sDiff % 60;
                    document.getElementById('live-step-elapsed').innerHTML = 
                        '현재 {active_step_code}: ' + (sm > 0 ? `${{sm}}분 ${{ss}}초` : `${{ss}}초`);
                }}
            }}
            updateClock();
            setInterval(updateClock, 1000);
        </script>
    </body>
    </html>
    """
    components.html(clock_component_html, height=105)

st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 8. 상단 7단계 가로형 터치 스와이프 공정 바 (카드 찌그러짐 방지)
# -------------------------------------------------------------
steps_data = []
for s_idx, s_code, s_label, s_tag in step_defs:
    if cur_step == 0:
        s_state = "waiting"
        s_dur = "대기"
    elif cur_step > s_idx:
        s_state = "completed"
        s_dur = st.session_state.step_durations.get(f"Step_{s_idx}", "완료")
    elif cur_step == s_idx:
        s_state = "active"
        s_dur = "진행"
    else:
        s_state = "waiting"
        s_dur = "예정"
    steps_data.append({
        "index": s_idx,
        "code": s_code,
        "label": s_label,
        "state": s_state,
        "duration": s_dur
    })

steps_json_str = json.dumps(steps_data, ensure_ascii=False)

stage_bar_component_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0; padding: 0; background: transparent; overflow-x: auto; overflow-y: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif;
            -webkit-overflow-scrolling: touch;
        }}
        .swipe-container {{
            display: flex;
            gap: 8px;
            padding: 4px 2px;
            box-sizing: border-box;
            width: max-content;
        }}
        .step-card {{
            flex: 0 0 100px;
            border-radius: 10px;
            padding: 6px 4px;
            text-align: center;
            border-width: 1.5px;
            border-style: solid;
            box-sizing: border-box;
        }}
        .state-waiting {{ background: #f8fafc; border-color: #cbd5e1; color: #64748b; }}
        .state-completed {{ background: #f0fdf4; border-color: #86efac; color: #15803d; }}
        .state-active {{
            background: #eff6ff; border-color: #3b82f6; color: #1d4ed8;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
        }}
        .badge {{ font-size: 10px; font-weight: 800; }}
        .duration-text {{ font-size: 13px; font-weight: 900; margin: 2px 0; color: #0f172a; white-space: nowrap; }}
        .label {{ font-size: 10px; color: #64748b; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="swipe-container" id="stage-swipe"></div>
    <script>
        const steps = {steps_json_str};
        const activeStepEpoch = {active_step_epoch};
        const container = document.getElementById('stage-swipe');

        steps.forEach(s => {{
            const card = document.createElement('div');
            card.className = `step-card state-${{s.state}}`;
            let bTxt = s.state === 'completed' ? '완료' : (s.state === 'active' ? '진행 중' : '대기');
            card.innerHTML = `
                <div class="badge">${{bTxt}} | ${{s.code}}</div>
                <div class="duration-text" id="dur-${{s.index}}">${{s.code}} ${{s.duration}}</div>
                <div class="label">${{s.label}}</div>
            `;
            container.appendChild(card);
        }});

        function updateDur() {{
            if (activeStepEpoch > 0) {{
                const diff = Math.max(0, Math.floor((Date.now() - activeStepEpoch) / 1000));
                const m = Math.floor(diff / 60);
                const s = diff % 60;
                const el = document.getElementById('dur-{cur_step}');
                if (el) el.innerText = '{active_step_code} ' + (m > 0 ? `${{m}}분 ${{s}}초` : `${{s}}초`);
            }}
        }}
        if (activeStepEpoch > 0) {{
            updateDur();
            setInterval(updateDur, 1000);
        }}
    </script>
</body>
</html>
"""
components.html(stage_bar_component_html, height=80)

st.divider()

# =============================================================
# STEP 0: 배치 착수 등록
# =============================================================
if st.session_state.process_step == 0:
    st.subheader("[Step 0] 생산 배치 착수 등록")
    product_name_input = st.text_input("생산 품목명", value="런 발효유")
    worker_name = st.text_input("작업자 성명", value="공장장")
    target_tank = "A300 발효탱크"
    
    clean_pname = "".join(filter(str.isalnum, product_name_input))
    batch_id_gen = f"{kst_now.strftime('%Y%m%d')}_{clean_pname}_{kst_now.strftime('%H%M')}"
    st.info(f"생성될 배치 ID: **{batch_id_gen}**")

    st.caption("착수 실내온도는 상단 [실내온도] 카드에서 입력 후 [입력] 버튼을 누르면 확정됨.")

    if st.button("이 설정으로 [배치 작업 시작 (A100 착수)]", type="primary", use_container_width=True):
        if not worker_name.strip():
            st.error("작업자 성명을 입력바람.")
        elif not product_name_input.strip():
            st.error("생산 품목명을 입력바람.")
        else:
            exact_kst_dt = get_kst_now()
            start_korean_val = format_korean_ampm(exact_kst_dt)
            start_hour_val = round(float(exact_kst_dt.hour + exact_kst_dt.minute / 60.0), 1)
            
            st.session_state.batch_id = batch_id_gen
            st.session_state.product_name = product_name_input.strip()
            st.session_state.target_tank = target_tank
            st.session_state.worker_name = worker_name.strip()
            st.session_state.start_hour = start_hour_val
            st.session_state.batch_start_dt = exact_kst_dt
            st.session_state.start_time_korean = start_korean_val
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.session_state.step_entry_times["Step_1"] = exact_kst_dt
            
            calc_res = calculate_optimal_temperatures(start_hour_val, st.session_state.indoor_t, curr_t, min_t, max_t)
            st.session_state.calc_res = calc_res
            
            save_batch_start(
                batch_id_gen, product_name_input.strip(), target_tank, worker_name.strip(),
                exact_kst_dt.strftime("%Y-%m-%d %H:%M:%S"), start_korean_val, curr_t, st.session_state.indoor_t
            )
            st.session_state.process_step = 1
            st.rerun()

# =============================================================
# STEP 1: A100 공정 (Base Mix 배합 및 준비)
# =============================================================
elif st.session_state.process_step == 1:
    st.subheader(f"[Step 1: A100] {st.session_state.product_name} Base Mix 배합")
    st.markdown(f"**배치 ID:** `{st.session_state.batch_id}` | **실내온도:** `{st.session_state.indoor_t}℃`")
    
    mix_temp = st.number_input("배합탱크 실측 원유온도 (℃)", 4.0, 25.0, 10.5, 0.1)
    mix_status = st.selectbox("배합 상태 점검", ["정상 배합 완료 (균질 양호)", "원료 투입 중"])

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("작업 취소 (복귀)", use_container_width=True):
            st.session_state.process_step = 0
            st.session_state.batch_start_dt = None
            st.session_state.step_entry_times = {}
            st.session_state.step_durations = {}
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("A100 완료 [다음 A200 이동]", type="primary", use_container_width=True):
            s1_start = st.session_state.step_entry_times.get("Step_1", kst_now)
            step_dur_str = format_time_delta((kst_now - s1_start).total_seconds())
            st.session_state.step_durations["Step_1"] = step_dur_str
            log_step_temp(st.session_state.batch_id, "A100", "Base Mix 배합", step_dur_str, "T101~T104", 0.0, 0.0, mix_temp, mix_status)
            
            st.session_state.step_entry_times["Step_2"] = get_kst_now()
            st.session_state.process_step = 2
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 2: A200 공정 (살균냉각 및 투입)
# =============================================================
elif st.session_state.process_step == 2:
    st.subheader(f"[Step 2: A200] {st.session_state.product_name} 살균 및 냉각 투입")
    c_res = st.session_state.calc_res
    
    st.info(f"**AI 추천 살균냉각온도:** **{c_res['rec_cooling']} ℃** (외기 {curr_t}℃ / 실내 {st.session_state.indoor_t}℃ 반영)")
    op_set_cool = st.number_input("HMI 실제 설정값 (P101TC02.SP, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)
    act_meas_cool = st.number_input("살균기 토출 실측 액온 (P101TT02, ℃)", 35.0, 42.0, float(c_res['rec_cooling']), 0.1)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A100)", use_container_width=True):
            st.session_state.process_step = 1
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("A200 확인 [다음 A300 이동]", type="primary", use_container_width=True):
            s2_start = st.session_state.step_entry_times.get("Step_2", kst_now)
            step_dur_str = format_time_delta((kst_now - s2_start).total_seconds())
            st.session_state.step_durations["Step_2"] = step_dur_str
            status_eval = "정상 설정" if abs(op_set_cool - c_res['rec_cooling']) <= 0.2 else "권장치 편차 설정"
            log_step_temp(st.session_state.batch_id, "A200", "살균냉각투입", step_dur_str, "P101TC02", c_res['rec_cooling'], op_set_cool, act_meas_cool, status_eval)
            
            st.session_state.step_entry_times["Step_3"] = get_kst_now()
            st.session_state.process_step = 3
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 3: A300 공정 (발효 및 재킷 보온)
# =============================================================
elif st.session_state.process_step == 3:
    st.subheader(f"[Step 3: A300] {st.session_state.product_name} 발효 및 재킷 보온 제어")
    c_res = st.session_state.calc_res
    
    st.info(f"**AI 추천 핫워터 순환:** **{c_res['rec_hotwater']} ℃** | **목표 품온:** **{c_res['rec_tank_tt']} ℃**")
    op_set_hw = st.number_input("HMI 핫워터 설정값 (℃)", 35.0, 42.0, float(c_res['rec_hotwater']), 0.1)
    act_meas_5h = st.number_input("5H 경과 실측 액온 (℃) [골든: 39.5℃]", 35.0, 43.0, 39.5, 0.1)
    acid_5h = st.number_input("5H 경과 실측 산도", 0.700, 0.950, 0.910, 0.005, format="%.3f")

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A200)", use_container_width=True):
            st.session_state.process_step = 2
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("5H 점검 기록 [다음 A400 이동]", type="primary", use_container_width=True):
            s3_start = st.session_state.step_entry_times.get("Step_3", kst_now)
            step_dur_str = format_time_delta((kst_now - s3_start).total_seconds())
            st.session_state.step_durations["Step_3"] = step_dur_str
            eval_5h = "골든 궤적 정상 유지" if abs(act_meas_5h - 39.5) <= 0.3 else "편차 발생"
            log_step_temp(st.session_state.batch_id, "A300", "발효재킷보온", step_dur_str, "PHE301WCV01", c_res['rec_hotwater'], op_set_hw, act_meas_5h, eval_5h)
            
            st.session_state.acid_5h = acid_5h
            st.session_state.act_meas_5h = act_meas_5h
            st.session_state.step_entry_times["Step_4"] = get_kst_now()
            st.session_state.process_step = 4
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 4: A400 공정 (시럽 배합 및 용해)
# =============================================================
elif st.session_state.process_step == 4:
    st.subheader(f"[Step 4: A400] {st.session_state.product_name} 시럽 배합 및 용해")
    syrup_mix_t = st.number_input("시럽 배합탱크 내부 액온 (℃)", 15.0, 35.0, 24.5, 0.1)
    syrup_brix = st.number_input("시럽 실측 당도 (Brix)", 10.0, 65.0, 45.0, 0.5)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A300)", use_container_width=True):
            st.session_state.process_step = 3
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("A400 완료 [다음 A500 이동]", type="primary", use_container_width=True):
            s4_start = st.session_state.step_entry_times.get("Step_4", kst_now)
            step_dur_str = format_time_delta((kst_now - s4_start).total_seconds())
            st.session_state.step_durations["Step_4"] = step_dur_str
            log_step_temp(st.session_state.batch_id, "A400", "시럽배합용해", step_dur_str, "T401~T402", 24.5, 24.5, syrup_mix_t, f"{syrup_brix} Brix")
            
            st.session_state.step_entry_times["Step_5"] = get_kst_now()
            st.session_state.process_step = 5
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 5: A500 공정 (시럽 살균 및 냉각)
# =============================================================
elif st.session_state.process_step == 5:
    st.subheader(f"[Step 5: A500] {st.session_state.product_name} 시럽 전용 살균/냉각")
    syrup_pasteur_t = st.number_input("시럽 살균 유지온도 (P201TT02, ℃)", 75.0, 95.0, 85.0, 0.5)
    syrup_cool_t = st.number_input("시럽 냉각 토출온도 (P2X4TT71, ℃)", 15.0, 30.0, 24.7, 0.1)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A400)", use_container_width=True):
            st.session_state.process_step = 4
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("A500 완료 [다음 A600 이동]", type="primary", use_container_width=True):
            s5_start = st.session_state.step_entry_times.get("Step_5", kst_now)
            step_dur_str = format_time_delta((kst_now - s5_start).total_seconds())
            st.session_state.step_durations["Step_5"] = step_dur_str
            log_step_temp(st.session_state.batch_id, "A500", "시럽살균냉각", step_dur_str, "P201TC02", 85.0, syrup_pasteur_t, syrup_cool_t, f"냉각 {syrup_cool_t}℃")
            
            st.session_state.step_entry_times["Step_6"] = get_kst_now()
            st.session_state.process_step = 6
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 6: A600 공정 (블렌딩 및 선행 급속 냉각)
# =============================================================
elif st.session_state.process_step == 6:
    st.subheader(f"[Step 6: A600] {st.session_state.product_name} 블렌딩 및 급속 냉각")
    acid_5h_saved = getattr(st.session_state, 'acid_5h', 0.910)
    rem_acid = 0.930 - acid_5h_saved
    trig_min = 300 if rem_acid <= 0 else int(300 + (rem_acid / 0.0015))
    
    st.info(f"**AI 선행 냉각 권장 시점:** 접종 후 **{trig_min}분** (목표 토출온도: 7.3℃)")
    act_dur_min = st.number_input("실제 냉각 개시 분(Time)", 300, 420, int(trig_min), 1)
    phe_out_t = st.number_input("PHE301 토출온도 (℃)", 4.0, 15.0, 7.3, 0.1)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A500)", use_container_width=True):
            st.session_state.process_step = 5
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("A600 확인 [다음 A700 이동]", type="primary", use_container_width=True):
            s6_start = st.session_state.step_entry_times.get("Step_6", kst_now)
            step_dur_str = format_time_delta((kst_now - s6_start).total_seconds())
            st.session_state.step_durations["Step_6"] = step_dur_str
            log_step_temp(st.session_state.batch_id, "A600", "PHE301급속냉각", step_dur_str, "PHE301STT02", 7.3, 7.3, phe_out_t, f"{act_dur_min}분 개시")
            
            st.session_state.act_dur_min = act_dur_min
            st.session_state.phe_out_t = phe_out_t
            st.session_state.step_entry_times["Step_7"] = get_kst_now()
            st.session_state.process_step = 7
            st.session_state.temp_locked = False
            st.session_state.show_temp_popup = True
            st.rerun()

# =============================================================
# STEP 7: A700 공정 (MQI 품질 검증 및 최종 저장)
# =============================================================
elif st.session_state.process_step == 7:
    st.subheader(f"[Step 7: A700] {st.session_state.product_name} 서지탱크 충전 & MQI 품질 검증")
    
    f_acid = st.number_input("최종 산도 [골든: 0.965]", 0.800, 1.200, 0.965, 0.001, format="%.3f")
    f_ph = st.number_input("최종 pH [골든: 4.70]", 4.00, 5.50, 4.70, 0.01)
    f_total_dur = st.number_input("총 소요 발효시간 (분)", 300, 450, 378, 1)
    f_visc = st.number_input("점도계 측정치 (cP)", 1500.0, 4500.0, 3200.0, 50.0)
    f_syn = st.number_input("유청 분리율 (%)", 0.0, 15.0, 1.1, 0.1)
    f_taste = st.slider("관능 평가 점수 (5점 만점)", 1.0, 5.0, 4.8, 0.1)
    f_memo = st.text_input("특이사항 메모", placeholder="특이사항 입력")

    score_chem = max(0.0, 30.0 - abs(f_acid - 0.965) * 500.0)
    score_tex = max(0.0, 40.0 - abs(f_visc - 3200.0) * 0.02 - (f_syn * 2.0))
    score_taste = (f_taste / 5.0) * 30.0
    mqi_total = round(min(100.0, max(0.0, score_chem + score_tex + score_taste)), 1)
    st.markdown(f"### MQI 종합 품질점수: **`{mqi_total} / 100 점`**")

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("이전 복귀 (A600)", use_container_width=True):
            st.session_state.process_step = 6
            st.session_state.temp_locked = True
            st.session_state.show_temp_popup = False
            st.rerun()
    with c2:
        if st.button("최종 종결 및 구글 시트 영구 저장", type="primary", use_container_width=True):
            s7_start = st.session_state.step_entry_times.get("Step_7", kst_now)
            step_dur_str = format_time_delta((kst_now - s7_start).total_seconds())
            st.session_state.step_durations["Step_7"] = step_dur_str
            log_step_temp(st.session_state.batch_id, "A700", "서지충전&MQI", step_dur_str, "701~705호", 7.3, 7.3, 7.3, f"MQI {mqi_total}점")
            
            save_final_mqi(st.session_state.batch_id, f_total_dur, f_acid, f_ph, f_visc, f_syn, f_taste, mqi_total, f_memo)
            
            gsheet_payload = {
                "batch_id": st.session_state.batch_id,
                "product_name": st.session_state.product_name,
                "worker_name": st.session_state.worker_name,
                "start_time": st.session_state.start_time_korean,
                "cooling_temp": st.session_state.calc_res.get('rec_cooling', 39.3),
                "hotwater_temp": st.session_state.calc_res.get('rec_hotwater', 38.3),
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
            g_success, g_msg = send_to_google_sheet(gsheet_payload)
            st.session_state.gsheet_status = g_msg
            
            st.session_state.process_step = 8
            st.rerun()

# =============================================================
# STEP 8: 공정 완료 리포트 및 이력 조회
# =============================================================
elif st.session_state.process_step == 8:
    st.success(f"[{st.session_state.product_name}] 배치 [{st.session_state.batch_id}] 공정 종결 및 저장 완료")
    st.info(f"구글 시트 연동: {getattr(st.session_state, 'gsheet_status', '완료')}")

    cur_logs = get_step_logs(st.session_state.batch_id)
    st.dataframe(cur_logs, use_container_width=True)

    if st.button("새로운 배치 작업 시작하기", type="primary", use_container_width=True):
        st.session_state.process_step = 0
        st.session_state.batch_id = ""
        st.session_state.batch_start_dt = None
        st.session_state.step_entry_times = {}
        st.session_state.step_durations = {}
        st.session_state.start_time_korean = ""
        st.session_state.gsheet_status = ""
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = False
        st.rerun()
