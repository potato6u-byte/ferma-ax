# -*- coding: utf-8 -*-
"""
FermaAX™ Dynamic Hybrid Optimizer v2.0
기상청 부산 기장군 실시간 날씨, 일교차 궤적, 착수 시각 연동형 발효 최적화 대시보드
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime

# 1. 웹 대시보드 페이지 기본 설정
st.set_page_config(
    page_title="FermaAX - 발효공정 4D 동적 최적화 시스템",
    page_icon="🧪",
    layout="wide"
)

# 2. 기상청 부산 기장군 실시간 기상 데이터 수집 함수 (위도 35.297, 경도 129.200)
@st.cache_data(ttl=600)  # 10분 캐싱
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
        return curr_temp, min_temp, max_temp, "정상 연동 (기상청/Open-Meteo)"
    except Exception:
        # 오프라인/통신 장애 시 기본 안전값
        return 12.0, 5.0, 18.0, "오프라인 기본값 모드"

# 3. 4D 시계열 궤적 적분 및 최적 셋포인트 역최적화 엔진
def calculate_dynamic_ferma_recipe(start_hour, t_in_curr, t_out_curr, t_min, t_max):
    # 6.3시간 발효 진행 시간 스텝 (20개 구간 생성)
    time_steps = np.linspace(start_hour, start_hour + 6.3, 20)
    dt = time_steps - start_hour

    # (1) 24시간 외기 일주기 궤적 모델링 (최저 06시, 최고 14시 정현파)
    t_mean = (t_max + t_min) / 2.0
    t_swing = (t_max - t_min) / 2.0
    t_out_traj = t_mean + t_swing * np.sin(2 * np.pi * (time_steps - 10.0) / 24.0)

    # (2) 공장 건물 열관성 지연 모델링 (감쇠율 0.622, 시정수 tau=2.5h)
    t_in_traj = t_in_curr + 0.622 * (t_out_traj - t_out_curr) * (1.0 - np.exp(-dt / 2.5))

    # (3) 구간별 유효 환경온도 분리 적분
    early_mask = dt <= 1.5
    late_mask = dt > 1.5
    t_eff_early = np.mean(0.70 * t_in_traj[early_mask] + 0.30 * t_out_traj[early_mask])
    t_eff_late = np.mean(0.60 * t_in_traj[late_mask] + 0.40 * t_out_traj[late_mask])

    # (4) 3대 제어 파라미터 역최적화 처방
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
        "tank_tt_target": tank_tt,
        "expected_duration": 378,
        "expected_acidity": 0.965
    }

# 4. 헤더 및 상태 표시
st.title("🧪 FermaAX™ 4D 스마트 발효공정 동적 최적 처방 시스템")
st.caption(f"부산 기장군 기상 데이터 연동 | 건물 열관성(τ=2.5h) 및 일교차 궤적 적분 제어 | 기준시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
st.divider()

# 5. 사이드바 제어 패널
curr_t, min_t, max_t, api_status = fetch_gijang_weather()

st.sidebar.header("⚙️ 실시간 제어 파라미터 입력")
auto_weather = st.sidebar.checkbox("기상청 API 실시간 자동 연동", value=True)

if auto_weather:
    outdoor_t = curr_t
    outdoor_min = min_t
    outdoor_max = max_t
    st.sidebar.success(f"{api_status}\n- 현재 기온: {curr_t}℃\n- 최저/최고: {min_t}℃ / {max_t}℃")
else:
    outdoor_t = st.sidebar.slider("현재 외기온도 (℃)", -10.0, 40.0, float(curr_t), 0.5)
    outdoor_min = st.sidebar.slider("당일 최저기온 (℃)", -10.0, 30.0, float(min_t), 0.5)
    outdoor_max = st.sidebar.slider("당일 최고기온 (℃)", 0.0, 40.0, float(max_t), 0.5)

st.sidebar.subheader("🏭 현장 공정 상태 입력")
indoor_t = st.sidebar.slider("발효실 내부 실측온도 (℃)", 15.0, 40.0, 24.5, 0.1)

# 작업 착수 시각 선택 (기본값 현재 시각)
now = datetime.now()
default_start_hour = float(now.hour + now.minute / 60.0)
start_hour = st.sidebar.slider("작업 착수 시각 (시)", 0.0, 23.5, round(default_start_hour, 1), 0.5, format="%.1f시")

# 6. 알고리즘 연산 실행
res = calculate_dynamic_ferma_recipe(start_hour, indoor_t, outdoor_t, outdoor_min, outdoor_max)

# 7. 상단 메트릭 요약 표시
m1, m2, m3, m4 = st.columns(4)
start_time_str = f"{int(start_hour):02d}:{int((start_hour%1)*60):02d}"
m1.metric("착수 시각", start_time_str, help="배치 투입 시작 시각")
m2.metric("외기 현황 (일교차)", f"{outdoor_t} ℃", delta=f"일교차 {outdoor_max - outdoor_min:.1f} ℃")
m3.metric("실내외 편차 (ΔT)", f"{indoor_t - outdoor_t:.1f} ℃", delta="내기 감쇠 반영됨")
m4.metric("목표 품질 (골든배치)", "종결 378분 / 산도 0.965", delta="사계절 균일")

# 8. 3대 핵심 AI 처방 셋포인트 카드
st.subheader("🎯 공정 제어 최적 권장 셋포인트 (HMI 입력값)")
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("### 1. 살균냉각온도 (투입)")
    st.markdown(f"<h1 style='color:#1f77b4; font-size:42px;'>{res['cooling_target']} ℃</h1>", unsafe_allow_html=True)
    st.caption(f"초기 1.5H 환경(T_eff={res['t_eff_early']}℃) 반영 / 초반 과발효 억제")

with c2:
    st.markdown("### 2. 핫워터 설정온도 (재킷)")
    st.markdown(f"<h1 style='color:#2ca02c; font-size:42px;'>{res['hotwater_target']} ℃</h1>", unsafe_allow_html=True)
    st.caption(f"중후반 4.8H 환경(T_eff={res['t_eff_late']}℃) 반영 / 5H 액온 보온")

with c3:
    st.markdown("### 3. 발효탱크 목표 TT")
    st.markdown(f"<h1 style='color:#ff7f0e; font-size:42px;'>{res['tank_tt_target']} ℃</h1>", unsafe_allow_html=True)
    st.caption("발효조 내부 유지 목표 온도")

st.divider()

# 9. 향후 6.3시간 발효 진행 중 열환경 궤적 Plotly 차트 (오류 완벽 수정 영역)
st.subheader("📈 향후 6.3시간 발효 진행 중 환경 궤적 예측 및 제어 시점")

fig = go.Figure()
time_labels = [f"{int(t%24):02d}:{int((t%1)*60):02d}" for t in res["time_steps"]]

# 외기 궤적 선
fig.add_trace(go.Scatter(
    x=time_labels, y=res["t_out_traj"],
    mode='lines+markers', name='예상 외기온도 궤적 (기상청)',
    line=dict(color='#3b82f6', width=2, dash='dash')
))

# 내기 궤적 선
fig.add_trace(go.Scatter(
    x=time_labels, y=res["t_in_traj"],
    mode='lines+markers', name='예상 실내온도 궤적 (건물 열관성 지연)',
    line=dict(color='#10b981', width=3)
))

# 1.5시간 초기/후반 분기선 표시 (add_shape 방식으로 변경하여 타입 에러 원천 해결)
split_idx = int(len(time_labels) * (1.5 / 6.3))
split_time_label = time_labels[split_idx]

fig.add_shape(
    type="line",
    x0=split_time_label, x1=split_time_label,
    y0=0, y1=1, yref="paper",
    line=dict(color="gray", width=1.5, dash="dot")
)

fig.add_annotation(
    x=split_time_label, y=1, yref="paper",
    text="초기 투입기 / 후반 유지기 분기",
    showarrow=False,
    xanchor="left", yanchor="top",
    font=dict(size=11, color="gray")
)

fig.update_layout(
    xaxis_title="발효 공정 진행 시각 (Timeline)",
    yaxis_title="환경 온도 (℃)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=30, b=20),
    height=420,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)