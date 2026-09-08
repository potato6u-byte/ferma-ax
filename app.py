import streamlit as st
import pandas as pd
import datetime
import io

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 스타일
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="신앙촌 SCADA SOP & 7월 데이터 추종 제어 시스템",
    page_icon="🥛",
    layout="wide"
)

st.title("🥛 신앙촌 유가공 SCADA SOP & 7월 데이터 추종 제어 시스템")
st.caption("A100~A700 전체 공정 제어 | 균주 3슬롯 및 Lot 이력 관리 | 엑셀 데이터 익스포트 연동")

# -----------------------------------------------------------------------------
# 2. 7월 베이스라인 데이터 (July Benchmark Target)
# -----------------------------------------------------------------------------
JULY_BENCHMARK = {
    "a200_paster_temp": 88.5,       # A200 베이스 살균 목표 온도 (℃)
    "a300_ferment_temp": 41.8,      # A300 발효 목표 품온 (℃)
    "a300_target_ph": 4.22,         # A300 발효 완료 목표 pH
    "a500_syrup_paster_temp": 95.0, # A500 시럽 살균 목표 온도 (℃)
    "a600_chilling_temp": 3.8,      # A600 PHE301 급속 칠링 목표 온도 (℃)
    "f_acidity": 0.85,              # 최종 산도 목표 (%)
    "f_viscosity": 1850             # 최종 점도 목표 (cP)
}

# -----------------------------------------------------------------------------
# 3. 사이드바: 배치 정보, Lot 번호 및 균주 3슬롯 가변 설정
# -----------------------------------------------------------------------------
st.sidebar.header("📋 배치 및 원료/균주 이력 입력")

run_id = st.sidebar.text_input("배치 번호 (Run ID)", value="BATCH-202607-001")
batch_volume = st.sidebar.number_input("생산 용량 (L)", value=10000, step=500)
raw_material = st.sidebar.selectbox("원료 구분", ["원유 (Base Milk)", "탈지분유 혼합유", "저지방 원유"])

st.sidebar.markdown("---")
st.sidebar.subheader("📦 Lot 이력 및 균주 선택 (1, 2, 3 슬롯)")

raw_lot_no = st.sidebar.text_input("원유/베이스 Lot 번호", value="LOT-RAW-20260701")
strain_lot_no = st.sidebar.text_input("균주 통합 Lot 번호", value="LOT-STR-20260701")

# 정확한 균주명이 확정되면 리스트 항목 수정하여 드롭다운 선택 가능하도록 설계
STRAIN_MASTER_LIST = [
    "미선택 (None)",
    "Strain_A (7월 표준 유산균 A)",
    "Strain_B (7월 표준 유산균 B)",
    "Strain_C (보조 균주 C)",
    "Lactobacillus bulgaricus",
    "Streptococcus thermophilus",
    "Bifidobacterium lactis",
    "직접 입력 (Custom)"
]

col_s1, col_s2, col_s3 = st.sidebar.columns(3)
with col_s1:
    strain_1 = st.selectbox("균주 1", STRAIN_MASTER_LIST, index=1)
with col_s2:
    strain_2 = st.selectbox("균주 2", STRAIN_MASTER_LIST, index=2)
with col_s3:
    strain_3 = st.selectbox("균주 3", STRAIN_MASTER_LIST, index=0)

# 직접 입력 선택 시 텍스트 입력창 활성화
if strain_1 == "직접 입력 (Custom)":
    strain_1 = st.sidebar.text_input("균주 1 직접 입력", value="Custom_Strain_1")
if strain_2 == "직접 입력 (Custom)":
    strain_2 = st.sidebar.text_input("균주 2 직접 입력", value="Custom_Strain_2")
if strain_3 == "직접 입력 (Custom)":
    strain_3 = st.sidebar.text_input("균주 3 직접 입력", value="Custom_Strain_3")

# -----------------------------------------------------------------------------
# 4. 공정 단계별 제어 입력 (A100 ~ A700) 및 7월 데이터 추종 분석
# -----------------------------------------------------------------------------
st.subheader("⚙️ 공정 제어값 입력 및 7월 데이터 추종 편차 분석")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. 베이스/살균 (A100/A200)",
    "2. 발효 공정 (A300)",
    "3. 시럽 배합/살균 (A400/A500)",
    "4. 칠링/혼합 (A600/A700)",
    "5. 최종 품질/MQI (QC)"
])

# ----- Tab 1: A100 / A200 -----
with tab1:
    st.markdown("#### A100 Base Mix & A200 Base Pasteurizer")
    c1, c2 = st.columns(2)
    with c1:
        selected_tanks = st.multiselect("투입 베이스 탱크", ["T101", "T102", "T103", "T104"], default=["T101", "T102"])
        a100_mix_temp = st.number_input("A100 혼합 온도 (℃)", value=37.7, step=0.1)
    with c2:
        a200_paster_meas = st.number_input("A200 베이스 살균 실측 온도 (℃)", value=88.3, step=0.1)
        a200_holding_sec = st.number_input("A200 살균 보류관 유지시간 (초)", value=15, step=1)
    
    # 7월 베이스라인 비교
    dev_a200 = a200_paster_meas - JULY_BENCHMARK["a200_paster_temp"]
    if abs(dev_a200) <= 0.5:
        st.success(f"✅ A200 살균 온도: 7월 표준({JULY_BENCHMARK['a200_paster_temp']}℃)과 일치함 (편차: {dev_a200:+.1f}℃)")
    else:
        st.warning(f"⚠️ A200 살균 온도: 7월 표준({JULY_BENCHMARK['a200_paster_temp']}℃) 대비 {dev_a200:+.1f}℃ 편차 발생. 스팀 밸브 보정 필요함.")

# ----- Tab 2: A300 Fermentation -----
with tab2:
    st.markdown("#### A300 Fermentation (발효 탱크 T301~T307)")
    c1, c2, c3 = st.columns(3)
    with c1:
        ferment_tank = st.selectbox("발효 탱크 선택", ["T301", "T302", "T303", "T304", "T305", "T306", "T307"], index=1)
        a300_ferment_temp = st.number_input("A300 발효 실측 품온 (℃)", value=41.9, step=0.1)
    with c2:
        a300_agitator_rpm = st.number_input("A300 교반기 속도 (RPM)", value=40, step=5)
        a300_meas_ph = st.number_input("현재 실측 pH", value=4.24, step=0.01)
    with c3:
        a300_meas_acidity = st.number_input("현재 실측 산도 (%)", value=0.84, step=0.01)
        ferment_hours = st.number_input("발효 경과 시간 (시간)", value=7.5, step=0.5)

    # 7월 목표 pH 도달 가이드
    ph_dev = a300_meas_ph - JULY_BENCHMARK["a300_target_ph"]
    if a300_meas_ph <= JULY_BENCHMARK["a300_target_ph"]:
        st.info("🎯 7월 목표 pH(4.22) 도달함. 발효 종료 및 A600 급속 칠링 전환 권장함.")
    else:
        st.write(f"⌛ 7월 목표 pH까지 {ph_dev:+.2f} 남음. (예상 잔여시간: 약 {int(ph_dev*100)}분)")

# ----- Tab 3: A400 / A500 Syrup -----
with tab3:
    st.markdown("#### A400 Syrup Mix & A500 Syrup Pasteurizer")
    c1, c2 = st.columns(2)
    with c1:
        syrup_tank = st.selectbox("시럽 배합 탱크", ["T401", "T402"], index=0)
        a400_syrup_temp = st.number_input("A400 시럽 배합 온도 (℃)", value=24.5, step=0.1)
        a400_brix = st.number_input("시럽 Brix (%)", value=65.0, step=0.5)
    with c2:
        a500_paster_meas = st.number_input("A500 시럽 살균 실측 온도 (℃)", value=95.1, step=0.1)
        a500_holding_sec = st.number_input("A500 살균 보류관 유지시간 (초)", value=30, step=1)

# ----- Tab 4: A600 / A700 Chilling & Filler -----
with tab4:
    st.markdown("#### A600 Mix Blending (PHE301) & A700 Surge Tank / Filler")
    c1, c2 = st.columns(2)
    with c1:
        a600_chilling_meas = st.number_input("A600 PHE301 칠링 실측 토출온도 (℃)", value=3.9, step=0.1)
        a600_phe_diff_press = st.number_input("PHE301 열교환기 차압 (ΔP bar)", value=0.35, step=0.01)
    with c2:
        surge_tank = st.selectbox("A700 서지 탱크", ["T701", "T702", "T703", "T704", "T705"], index=0)
        filler_no = st.selectbox("충전기 선택", ["충전기 #1", "충전기 #2", "충전기 #3"])
        yield_rate = st.number_input("최종 공정 수율 (%)", value=98.5, step=0.1)

# ----- Tab 5: Final Quality / MQI -----
with tab5:
    st.markdown("#### 최종 품질 검사 (QC) & MQI 산출")
    c1, c2 = st.columns(2)
    with c1:
        f_ph = st.number_input("최종 제품 pH", value=4.23, step=0.01)
        f_acidity = st.number_input("최종 제품 산도 (%)", value=0.85, step=0.01)
        f_visc = st.number_input("최종 점도 (cP)", value=1840, step=10)
    with c2:
        f_syn = st.number_input("유청 분리율 (%)", value=0.8, step=0.1)
        f_taste = st.slider("관능 평가 점수 (1~10)", min_value=1, max_value=10, value=9)
        worker_memo = st.text_area("작업자 메모", value="7월 베이스라인 목표와 품질 지표 일치함. 정상 출고 가능함.")

    # 7월 데이터 기준 MQI 스코어 자동 산출
    ph_score = max(0, 100 - abs(f_ph - JULY_BENCHMARK["a300_target_ph"]) * 200)
    visc_score = max(0, 100 - abs(f_visc - JULY_BENCHMARK["f_viscosity"]) * 0.1)
    mqi_score = round((ph_score * 0.4) + (visc_score * 0.3) + (f_taste * 10 * 0.3), 1)

    st.metric(label="📊 7월 데이터 추종 품질 점수 (MQI Score)", value=f"{mqi_score} / 100 점")

# -----------------------------------------------------------------------------
# 5. 전체 데이터 요약 테이블 & 엑셀 익스포트 연동
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("💾 엑셀 데이터 저장 및 다운로드")

record_data = {
    "배치_ID": [run_id],
    "생산_용량_L": [batch_volume],
    "원료_구분": [raw_material],
    "원유_Lot_No": [raw_lot_no],
    "균주_Lot_No": [strain_lot_no],
    "균주_Slot_1": [strain_1],
    "균주_Slot_2": [strain_2],
    "균주_Slot_3": [strain_3],
    "A100_혼합온도_℃": [a100_mix_temp],
    "A200_베이스살균온도_℃": [a200_paster_meas],
    "A200_살균유지시간_초": [a200_holding_sec],
    "A300_발효탱크": [ferment_tank],
    "A300_발효실측온도_℃": [a300_ferment_temp],
    "A300_교반기_RPM": [a300_agitator_rpm],
    "A300_실측_pH": [a300_meas_ph],
    "A300_실측_산도_%": [a300_meas_acidity],
    "A400_시럽온도_℃": [a400_syrup_temp],
    "A400_시럽_Brix": [a400_brix],
    "A500_시럽살균온도_℃": [a500_paster_meas],
    "A600_칠링토출온도_℃": [a600_chilling_meas],
    "A600_PHE_차압_bar": [a600_phe_diff_press],
    "최종_pH": [f_ph],
    "최종_산도_%": [f_acidity],
    "최종_점도_cP": [f_visc],
    "수율_%": [yield_rate],
    "MQI_품질점수": [mqi_score],
    "작업자_메모": [worker_memo],
    "기록_일시": [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
}

df_record = pd.DataFrame(record_data)

# 데이터 전치 미리보기
st.dataframe(df_record.T, use_container_width=True)

# 엑셀 바이너리 생성 및 다운로드 버퍼
output = io.BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_record.to_excel(writer, sheet_name='SCADA_SOP_LOG', index=False)
excel_data = output.getvalue()

st.download_button(
    label="📥 입력 데이터 엑셀 파일(.xlsx) 다운로드",
    data=excel_data,
    file_name=f"SCADA_SOP_{run_id}_{datetime.date.today().strftime('%Y%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
