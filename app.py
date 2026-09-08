import streamlit as st

# 1. 로트번호 및 원재료/균주 슬롯 입력 UI (1, 2, 3 칸 생성)
st.sidebar.subheader("📦 이력 추적 및 균주 설정 (Lot & Strain)")
raw_lot_no = st.sidebar.text_input("원유/베이스 Lot 번호", value="LOT-202607-001")
strain_lot_no = st.sidebar.text_input("균주 Lot 번호", value="ST-LOT-7701")

col1, col2, col3 = st.sidebar.columns(3)
# 추후 exact strain list가 정의되면 st.selectbox로 전환 가능하도록 설계
strain_options = ["미선택", "Strain_A (7월 표준)", "Strain_B", "Strain_C", "직접입력"]

with col1:
    strain_1 = st.selectbox("균주 1", strain_options, index=1)
with col2:
    strain_2 = st.selectbox("균주 2", strain_options, index=0)
with col3:
    strain_3 = st.selectbox("균주 3", strain_options, index=0)

# 2. 7월 베이스라인 데이터 기반 목표 제어값 튜닝 로직
JULY_BENCHMARK = {
    "a200_paster_temp": 88.5,  # A200 살균 목표 (℃)
    "a300_ferment_temp": 41.8, # A300 발효 목표 (℃)
    "a300_target_ph": 4.22,    # 발효 완료 target pH
    "a600_chilling_temp": 3.8  # A600 PHE301 칠링 목표 (℃)
}

# 제어 목표 산출 함수 (7월 데이터 추종)
def get_july_tuned_controls(current_inputs):
    # 7월 베이스라인과의 편차를 최소화하도록 보정 제어값 계산
    control_settings = {
        "target_paster_temp": JULY_BENCHMARK["a200_paster_temp"],
        "target_ferment_temp": JULY_BENCHMARK["a300_ferment_temp"],
        "target_chilling_temp": JULY_BENCHMARK["a600_chilling_temp"],
        "strain_composition": [strain_1, strain_2, strain_3]
    }
    return control_settings
