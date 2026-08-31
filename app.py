# -*- coding: utf-8 -*-
"""
FermaAX™ On-Site Operator SOP & QC Manager v4.0
공정도 P&ID 매핑 기반 신입직원용 발효 공정 제어 가이드 & 시간대별 실시간 온도 판정/로깅 시스템
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, date

# 1. 반응형 모바일/웹 UI 설정
st.set_page_config(
    page_title="FermaAX - 발효제어 가이드 & 실시간 QC",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. SQLite 데이터베이스 초기화
DB_FILE = "ferma_sop_db.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 1) 활성 배치 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            created_at TEXT,
            tank_no TEXT,
            product_code TEXT,
            worker_name TEXT,
            start_hour REAL,
            indoor_temp REAL,
            outdoor_temp REAL,
            rec_cooling REAL,
            rec_hotwater REAL,
            rec_tank_tt REAL,
            status TEXT
        )
    ''')
    # 2) 시간대별 액온 추적 로그 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS temp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            log_time TEXT,
            elapsed_hour REAL,
            golden_target REAL,
            actual_temp REAL,
            status_eval TEXT,
            action_guide TEXT
        )
    ''')
    # 3) 최종 종결 QC 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS qc_final (
            batch_id TEXT PRIMARY KEY,
            end_time TEXT,
            actual_cooling REAL,
            actual_duration INTEGER,
            final_acidity REAL,
            final_ph REAL,
            cooling_trigger_min INTEGER,
            overall_result TEXT,
            worker_memo TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# DB 헬퍼 함수
def save_new_batch(b_id, tank, p_code, worker, s_hour, in_t, out_t, cool_t, hw_t, tt_t):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO batches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
    ''', (b_id, datetime.now().strftime("%Y-%m-%d %H:%M"), tank, p_code, worker, s_hour, in_t, out_t, cool_t, hw_t, tt_t))
    conn.commit()
    conn.close()

def log_temp_check(b_id, elapsed_h, golden_t, actual_t, eval_text, guide_text):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO temp_logs (batch_id, log_time, elapsed_hour, golden_target, actual_temp, status_eval, action_guide)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (b_id, datetime.now().strftime("%H:%M:%S"), elapsed_h, golden_t, actual_t, eval_text, guide_text))
    conn.commit()
    conn.close()

def save_final_qc(b_id, act_cool, duration, acid, ph, cool_min, result, memo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO qc_final VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (b_id, datetime.now().strftime("%Y-%m-%d %H:%M"), act_cool, duration, acid, ph, cool_min, result, memo))
    c.execute("UPDATE batches SET status = 'COMPLETED' WHERE batch_id = ?", (b_id,))
    conn.commit()
    conn.close()

def load_temp_logs(b_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM temp_logs WHERE batch_id = ? ORDER BY elapsed_hour ASC", conn, params=(b_id,))
    conn.close()
    return df

def load_all_completed_qc():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('''
        SELECT b.batch_id, b.created_at, b.tank_no, b.product_code, b.worker_name,
               b.outdoor_temp, b.rec_cooling, q.actual_cooling, b.rec_hotwater,
               q.actual_duration, q.final_acidity, q.final_ph, q.overall_result, q.worker_memo
        FROM batches b JOIN qc_final q ON b.batch_id = q.batch_id
        ORDER BY b.created_at DESC
    ''', conn)
    conn.close()
    return df

# 3. 기상청 실시간 API 연동 (부산 기장군 AWS 923)
@st.cache_data(ttl=600)
def fetch_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=35.297&longitude=129.200&current_weather=true&"
            "daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FSeoul"
        )
        res = requests.get(url, timeout=5).json()
        return (
            res["current_weather"]["temperature"],
            res["daily"]["temperature_2m_min"][0],
            res["daily"]["temperature_2m_max"][0],
            "기상청 정상 연동"
        )
    except Exception:
        return 12.0, 5.0, 18.0, "오프라인 기본 안전모드"

# 4. 7~8월 골든배치 수렴형 궤적 계산 엔진
def calculate_ferma_sop(start_hour, t_in, t_out, t_min, t_max):
    time_steps = np.linspace(start_hour, start_hour + 6.3, 25)
    elapsed = time_steps - start_hour

    t_mean = (t_max + t_min) / 2.0
    t_swing = (t_max - t_min) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)
    t_in_traj = t_in + 0.622 * (t_out_traj - t_out) * (1.0 - np.exp(-elapsed / 2.5))

    early_mask = elapsed <= 1.5
    late_mask = elapsed > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    # 3대 HMI 셋포인트 (과열 방지 클램핑)
    cooling_sp = min(39.3, round(38.4 + max(0.0, (32.0 - t_eff_early) * 0.050), 1))
    hotwater_sp = min(38.8, round(38.3 + max(0.0, (32.0 - t_eff_late) * 0.040), 1))
    tank_tt_sp = min(39.2, round(38.5 + max(0.0, (32.0 - t_eff_late) * 0.035), 1))

    # 시간대별 이상적 골든 액온 커브
    golden_temps = []
    for h in elapsed:
        if h <= 1.5:
            temp = cooling_sp + (0.5 * (h / 1.5))
        elif h <= 3.5:
            temp = (cooling_sp + 0.5) + (0.7 * ((h - 1.5) / 2.0))
        elif h <= 5.0:
            temp = 39.7 - (0.2 * ((h - 3.5) / 1.5))
        else:
            temp = 39.5 - (0.3 * ((h - 5.0) / 1.3))
        golden_temps.append(round(temp, 2))

    return {
        "time_steps": time_steps,
        "elapsed": elapsed,
        "golden_temps": np.array(golden_temps),
        "upper": np.array(golden_temps) + 0.3,
        "lower": np.array(golden_temps) - 0.3,
        "cooling_sp": cooling_sp,
        "hotwater_sp": hotwater_sp,
        "tank_tt_sp": tank_tt_sp,
        "t_eff_early": round(t_eff_early, 1),
        "t_eff_late": round(t_eff_late, 1)
    }

# ==========================================================
# 5. UI 메인 화면 구성
# ==========================================================
curr_out, min_out, max_out, w_status = fetch_weather()

st.title("🧪 FermaAX™ 스마트 발효 공정 가이드 & 실시간 QC")
st.caption(f"부산 기장군 날씨 연동 (현재 외기: {curr_out}℃ | 일교차: {min_out}℃~{max_out}℃) | 초보자용 표준작업가이드(SOP)")

main_tab1, main_tab2, main_tab3 = st.tabs([
    "🚀 1. 배치 착수 & HMI 셋포인트 가이드",
    "📈 2. 시간대별 액온 비교 점검 & 실시간 판정",
    "📋 3. 공정 종결 QC & 전체 이력 관리"
])

# ----------------------------------------------------------
# 탭 1: 배치 착수 & HMI 셋포인트 가이드
# ----------------------------------------------------------
with main_tab1:
    st.markdown("### 📌 [Step 1] 배치 착수 정보 입력 및 SCADA 설정 확인")
    
    col_in1, col_in2, col_in3 = st.columns(3)
    with col_in1:
        tank_select = st.selectbox("발효탱크 선택 (A300)", ["301호", "302호", "303호", "304호", "305호", "306호", "307호"])
        p_code = st.selectbox("생산 품목 코드", ["P.Code: 101 (플레인)", "P.Code: 102 (딸기)", "P.Code: 103 (블루베리)"])
    with col_in2:
        worker = st.text_input("작업자 성명", placeholder="홍길동")
        in_temp = st.number_input("발효실 현재 실내온도 (℃)", 15.0, 38.0, 24.5, 0.1)
    with col_in3:
        now_h = float(datetime.now().hour + datetime.now().minute / 60.0)
        s_hour = st.slider("작업 착수 시각", 0.0, 23.5, round(now_h, 1), 0.5, format="%.1f시")

    # 계산 실행
    sop_data = calculate_ferma_sop(s_hour, in_temp, curr_out, min_out, max_out)
    batch_id_cur = f"{date.today().strftime('%Y%m%d')}_{tank_select[:3]}_{int(s_hour):02d}H"

    st.divider()
    st.markdown("#### 🎯 SCADA/HMI 제어반 입력 지침 (신입직원 필독)")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("💧 **A200 베이스 살균기 토출 (P101TC02)**")
        st.markdown(f"<h1 style='color:#1f77b4; font-size:38px;'>{sop_data['cooling_sp']} ℃</h1>", unsafe_allow_html=True)
        st.caption("초반 급속 과발효 및 산도 폭주 방지 셋포인트")

    with c2:
        st.success("🔥 **A300 재킷 온수 순환 (PHE301WCV)**")
        st.markdown(f"<h1 style='color:#2ca02c; font-size:38px;'>{sop_data['hotwater_sp']} ℃</h1>", unsafe_allow_html=True)
        st.caption("중후반 외기 방열 손실 보상용 재킷 보온 셋포인트")

    with c3:
        st.warning(f"🏷️ **A300 {tank_select} 목표 품온 (TT)**")
        st.markdown(f"<h1 style='color:#ff7f0e; font-size:38px;'>{sop_data['tank_tt_sp']} ℃</h1>", unsafe_allow_html=True)
        st.caption("발효조 내부 유지 목표 품온")

    if st.button("🚀 이 설정값으로 [배치 작업 시작 및 DB 등록]", use_container_width=True, type="primary"):
        if not worker:
            st.error("작업자 성명을 입력바람.")
        else:
            save_new_batch(
                batch_id_cur, tank_select, p_code, worker, s_hour, in_temp,
                curr_out, sop_data['cooling_sp'], sop_data['hotwater_sp'], sop_data['tank_tt_sp']
            )
            # 0H 초기값 자동 로깅
            log_temp_check(batch_id_cur, 0.0, sop_data['cooling_sp'], sop_data['cooling_sp'], "정상 투입", "HMI 설정값 일치 확인")
            st.success(f"✅ 배치 [{batch_id_cur}] 등록 완료! [탭 2]로 이동하여 시간대별 온도를 점검바람.")

# ----------------------------------------------------------
# 탭 2: 시간대별 액온 비교 점검 & 실시간 판정
# ----------------------------------------------------------
with main_tab2:
    st.markdown("### 📌 [Step 2] 시간대별 발효액온 실측치 비교 & 정상여부 판정")
    
    col_chk1, col_chk2 = st.columns([1, 2])

    with col_chk1:
        st.markdown("#### 📝 현장 온도 점검 입력")
        check_batch = st.text_input("현재 진행 배치 ID", value=batch_id_cur)
        elapsed_sel = st.selectbox("경과 시간 선택", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], format_func=lambda x: f"{x}시간 경과 시점 ({int(x*60)}분)")

        # 해당 시점 골든 타깃 온도 추출
        idx_t = np.argmin(np.abs(sop_data["elapsed"] - elapsed_sel))
        target_t = sop_data["golden_temps"][idx_t]

        st.metric("7~8월 표준 적정 액온", f"{target_t} ℃", delta="허용범위 ±0.3℃")

        act_temp_input = st.number_input("실제 탱크 실측 액온 (℃)", 35.0, 43.0, float(target_t), 0.1)

        # 판정 및 작업 지침 자동 도출
        diff_t = act_temp_input - target_t
        if abs(diff_t) <= 0.3:
            eval_res = "✅ 정상 유지"
            guide_res = "7~8월 골든배치 궤적과 일치함. 현재 설정 유지."
        elif diff_t < -0.3:
            eval_res = "⚠️ 저온 이탈"
            guide_res = f"외기 냉기 유입으로 품온 저하({diff_t:+.2f}℃). HMI 핫워터 설정을 +0.2℃ 상향 조정바람."
        else:
            eval_res = "🚨 과열 이탈"
            guide_res = f"발효열 과다 축적({diff_t:+.2f}℃). 초반 급속 과발효 위험. 재킷 순환 점검 바람."

        if st.button("💾 점검 결과 기록 및 판정", use_container_width=True):
            log_temp_check(check_batch, elapsed_sel, target_t, act_temp_input, eval_res, guide_res)
            st.success("점검 데이터가 기록되었음!")

        # 판정 결과 카드 표시
        if "정상" in eval_res:
            st.success(f"**판정 결과:** {eval_res}\n\n**조치 지침:** {guide_res}")
        elif "저온" in eval_res:
            st.warning(f"**판정 결과:** {eval_res}\n\n**조치 지침:** {guide_res}")
        else:
            st.error(f"**판정 결과:** {eval_res}\n\n**조치 지침:** {guide_res}")

    with col_chk2:
        st.markdown("#### 📈 7~8월 골든 궤적(녹색 밴드) vs 실측 액온(빨간 점)")
        
        t_logs = load_temp_logs(check_batch)
        time_labels = [f"{int(t%24):02d}:{int((t%1)*60):02d}" for t in sop_data["time_steps"]]

        fig_track = go.Figure()
        
        # 골든 허용 밴드 (±0.3℃)
        fig_track.add_trace(go.Scatter(
            x=time_labels + time_labels[::-1],
            y=np.concatenate([sop_data["upper"], sop_data["lower"][::-1]]),
            fill='toself',
            fillcolor='rgba(46, 204, 113, 0.15)',
            line=dict(color='rgba(255,255,255,0)'),
            name='7~8월 적정 허용 밴드 (±0.3℃)',
            hoverinfo="skip"
        ))

        # 골든 커브
        fig_track.add_trace(go.Scatter(
            x=time_labels, y=sop_data["golden_temps"],
            mode='lines', name='7~8월 표준 적정 액온',
            line=dict(color='#27ae60', width=2.5, dash='dash')
        ))

        # 실측치
        if not t_logs.empty:
            act_labels = []
            for eh in t_logs["elapsed_hour"]:
                t_val = s_hour + eh
                act_labels.append(f"{int(t_val%24):02d}:{int((t_val%1)*60):02d}")

            fig_track.add_trace(go.Scatter(
                x=act_labels, y=t_logs["actual_temp"],
                mode='lines+markers', name='★ 현장 실측 액온',
                marker=dict(size=10, color='#e74c3c'),
                line=dict(color='#e74c3c', width=3)
            ))

        fig_track.update_layout(
            xaxis_title="진행 시각 (타임라인)",
            yaxis_title="탱크 내부 액온 (℃)",
            hovermode="x unified",
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_track, use_container_width=True)

        # 누적 점검 이력 표
        if not t_logs.empty:
            st.dataframe(t_logs[["log_time", "elapsed_hour", "golden_target", "actual_temp", "status_eval", "action_guide"]], use_container_width=True)

# ----------------------------------------------------------
# 탭 3: 공정 종결 QC & 전체 이력 관리
# ----------------------------------------------------------
with main_tab3:
    st.markdown("### 📌 [Step 3] 선행 냉각 타이머 & 최종 발효 QC 데이터 저장")
    
    qc_c1, qc_c2 = st.columns(2)
    
    with qc_c1:
        st.markdown("#### ❄️ 5H 산도 기반 선행 냉각(Chilling) 시점 계산")
        acid_5h_val = st.number_input("5시간(300분) 경과 시점 실측 산도", 0.700, 0.960, 0.910, 0.005, format="%.3f")
        
        # 선행 산도 0.930 도달 시점 계산
        rem_acid = 0.930 - acid_5h_val
        if rem_acid <= 0:
            cool_trig_min = 300
            cool_msg = "🚨 즉시 PHE301 냉각 밸브를 열어 급속 칠링을 시작바람! (선행산도 0.930 도달)"
        else:
            add_min = int(rem_acid / 0.0015)
            cool_trig_min = 300 + add_min
            cool_msg = f"⏱️ 접종 후 **{cool_trig_min}분 시점 (앞으로 약 {add_min}분 뒤)**에 PHE301 냉각을 개시바람."

        st.info(cool_msg)

    with qc_c2:
        st.markdown("#### 🏁 최종 공정 실적 입력 및 종결 처리")
        with st.form("final_qc_form"):
            f_cooling = st.number_input("실제 살균냉각 투입온도 (℃)", 35.0, 42.0, float(sop_data['cooling_sp']), 0.1)
            f_dur = st.number_input("실제 총 발효시간 (분)", 300, 450, int(cool_trig_min + 30), 1)
            f_acid = st.number_input("최종 안착 완제품 산도", 0.800, 1.200, 0.965, 0.001, format="%.3f")
            f_ph = st.number_input("최종 안착 완제품 pH", 4.00, 5.20, 4.70, 0.01)
            f_memo = st.text_area("작업자 특이사항 메모", placeholder="예: 4H 시점 저온 경보로 핫워터 0.2도 상향 후 정상 수렴 완료.")
            
            btn_final = st.form_submit_button("💾 공정 최종 종결 및 DB 영구 저장", use_container_width=True, type="primary")
            if btn_final:
                # 합격 여부 자동 판정
                is_pass = (0.955 <= f_acid <= 0.975) and (370 <= f_dur <= 390)
                overall = "합격 (골든 수렴)" if is_pass else "품질 편차 주의"
                
                save_final_qc(check_batch, f_cooling, f_dur, f_acid, f_ph, cool_trig_min, overall, f_memo)
                st.success(f"🎉 배치 [{check_batch}] 공정이 정상 종결 및 저장되었음! (판정: {overall})")

    st.divider()
    st.markdown("#### 📊 공장 전체 누적 QC 이력 데이터베이스")
    completed_df = load_all_completed_qc()
    
    if not completed_df.empty:
        st.dataframe(completed_df, use_container_width=True)
        csv_data = completed_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 누적 공정 이력 CSV 엑셀 다운로드",
            data=csv_data,
            file_name=f"Ferma_QC_History_{date.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.caption("아직 완료된 배치 이력이 없음.")
