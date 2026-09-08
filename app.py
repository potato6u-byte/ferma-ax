# Step 3 완료 처리: 선택 탱크별 실측 및 설정 요약 문자열 생성
        st.session_state.tank_summary_str = " | ".join(summary_list)
        st.session_state.step_entry_times["Step_4"] = get_kst_now()
        st.session_state.process_step = 4
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 4: A400 시럽 배합
# =============================================================
elif st.session_state.process_step == 4:
    st.subheader("[Step 4: A400] 시럽 배합 (T401~T402)")
    syrup_temp = st.number_input("시럽 배합 탱크 실측 온도 (℃)", 10.0, 90.0, 65.0, 0.1)
    syrup_status = st.selectbox("시럽 배합 및 투입 상태", ["정상 배합 완료 (원료 용해 양호)", "원료 용해 중", "투입 대기"])
    
    if st.button("A400 완료 [다음 A500 시럽 살균 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_4", kst_now)).total_seconds())
        st.session_state.step_durations["Step_4"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A400", "시럽 배합", step_dur_str, "T401~T402", 65.0, 65.0, syrup_temp, syrup_status)
        st.session_state.step_entry_times["Step_5"] = get_kst_now()
        st.session_state.process_step = 5
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 5: A500 시럽 살균
# =============================================================
elif st.session_state.process_step == 5:
    st.subheader("[Step 5: A500] 시럽 살균 (P201TC02)")
    syrup_steril_set = st.number_input("시럽 살균 HMI 설정 온도 (℃)", 80.0, 100.0, 92.0, 0.1)
    syrup_steril_meas = st.number_input("시럽 살균 토출 실측 온도 (℃)", 80.0, 100.0, 92.3, 0.1)
    
    if st.button("A500 완료 [다음 A600 급속 칠링 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_5", kst_now)).total_seconds())
        st.session_state.step_durations["Step_5"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A500", "시럽 살균", step_dur_str, "P201TC02", 92.0, syrup_steril_set, syrup_steril_meas, "정상 살균 완료")
        st.session_state.step_entry_times["Step_6"] = get_kst_now()
        st.session_state.process_step = 6
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 6: A600 급속 칠링
# =============================================================
elif st.session_state.process_step == 6:
    st.subheader("[Step 6: A600] 급속 칠링 (PHE301)")
    c_res = st.session_state.calc_res
    st.info(f"**AI 추천 급속 칠링 목표 온도:** **`{c_res['target_chilling']} ℃`** (원료 물성 프로파일 적용)")
    
    chilling_set = st.number_input("칠링 HMI 설정값 (℃)", 3.0, 15.0, float(c_res['target_chilling']), 0.1)
    chilling_meas = st.number_input("PHE301 토출 실측 품온 (℃)", 3.0, 15.0, float(c_res['target_chilling']), 0.1)
    
    if st.button("A600 완료 [다음 A700 MQI 충전/최종 검사 이동]", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_6", kst_now)).total_seconds())
        st.session_state.step_durations["Step_6"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A600", "급속 칠링", step_dur_str, "PHE301", c_res['target_chilling'], chilling_set, chilling_meas, "정상 칠링 완료")
        st.session_state.step_entry_times["Step_7"] = get_kst_now()
        st.session_state.process_step = 7
        st.session_state.temp_locked = False
        st.session_state.show_temp_popup = True
        st.rerun()

# =============================================================
# STEP 7: A700 MQI 충전 및 최종 품질 평가
# =============================================================
elif st.session_state.process_step == 7:
    st.subheader("[Step 7: A700] MQI 품질 검사 및 배치 최종 완료")
    
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        f_acidity = st.number_input("최종 산도 (%)", 0.700, 1.200, 0.965, 0.005, format="%.3f")
        f_ph = st.number_input("최종 pH", 3.80, 5.00, 4.25, 0.01)
        f_visc = st.number_input("점도 (cP)", 1000, 8000, 3200, 50)
    with col_q2:
        f_syn = st.number_input("유청분리율/Syneresis (%)", 0.0, 10.0, 1.1, 0.1)
        f_taste = st.number_input("관능 평가 점수 (1~5점)", 1.0, 5.0, 5.0, 0.5)
        worker_memo = st.text_input("작업자 최종 메모", "전 탱크 정상 충전 완료 및 이상 없음")

    # MQI (Master Quality Index) 동적 연산
    mqi_score = round(100.0 - abs(f_acidity - 0.960)*50 - abs(f_ph - 4.25)*20 - (f_syn * 2.0), 1)
    mqi_score = max(0.0, min(100.0, mqi_score))
    
    st.markdown(
        f"""
        <div style="text-align: center; padding: 12px; background: #064e3b; border-radius: 10px; border: 1.5px solid #10b981; margin: 10px 0;">
            <div style="font-size: 13px; color: #a7f3d0; font-weight: bold;">최종 종합 MQI (Master Quality Index)</div>
            <div style="font-size: 28px; font-weight: 900; color: #34d399; font-family: monospace;">{mqi_score} / 100 점</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("최종 배치 완료 및 DB/엑셀/구글시트 동시 기록", type="primary", use_container_width=True):
        step_dur_str = format_time_delta((kst_now - st.session_state.step_entry_times.get("Step_7", kst_now)).total_seconds())
        st.session_state.step_durations["Step_7"] = step_dur_str
        log_step_temp_multi(st.session_state.run_id, "A700", "MQI 충전", step_dur_str, "서지/충전기", 0.0, 0.0, 0.0, "충전 완료")

        total_sec = (kst_now - st.session_state.batch_start_dt).total_seconds() if st.session_state.batch_start_dt else 0
        total_min = int(total_sec // 60)
        tanks_str = ", ".join(st.session_state.selected_tanks)

        # 1. SQLite 마스터 DB 저장
        save_final_mqi_multi(
            st.session_state.run_id, total_min, f_acidity, f_ph, f_visc, f_syn, f_taste,
            mqi_score, st.session_state.get("tank_summary_str", ""), worker_memo
        )

        # 2. 로컬 엑셀(.xlsx) 누적 저장
        excel_data = {
            "배치ID": st.session_state.run_id,
            "투입탱크": tanks_str,
            "원료": st.session_state.raw_material,
            "생산용량(L)": st.session_state.batch_volume,
            "착수시각": st.session_state.start_time_korean,
            "총소요시간(분)": total_min,
            "최종산도": f_acidity,
            "최종pH": f_ph,
            "점도(cP)": f_visc,
            "유청분리율(%)": f_syn,
            "관능점수": f_taste,
            "MQI점수": mqi_score,
            "탱크별품온요약": st.session_state.get("tank_summary_str", ""),
            "작업자메모": worker_memo
        }
        ok_xl, msg_xl = append_to_local_excel(excel_data)

        # 3. 구글 스프레드시트 Webhook 전송
        gsheet_payload = {
            "tanks_list": tanks_str,
            "raw_material": st.session_state.raw_material,
            "batch_volume": st.session_state.batch_volume,
            "start_time": st.session_state.start_time_korean,
            "cooling_temp": st.session_state.calc_res.get("rec_cooling", 0.0),
            "hotwater_temp": st.session_state.calc_res.get("tanks", {}).get(st.session_state.selected_tanks[0], {}).get("rec_hotwater", 0.0),
            "phe_temp": st.session_state.calc_res.get("target_chilling", 0.0),
            "duration": total_min,
            "acidity": f_acidity,
            "ph": f_ph,
            "viscosity": f_visc,
            "syneresis": f_syn,
            "taste": f_taste,
            "mqi_score": mqi_score,
            "memo": worker_memo
        }
        ok_gs, msg_gs = send_to_google_sheet(gsheet_payload)

        st.success(f"🎉 배치 완수 완료! ({msg_xl} | {msg_gs})")
        st.session_state.process_step = 8
        st.rerun()

# =============================================================
# STEP 8: 완료 보고 및 생산 이력 테이블 조회
# =============================================================
elif st.session_state.process_step == 8:
    st.balloons()
    st.success("✅ **모든 공정이 성공적으로 종료되었으며 3중 분산 데이터 로깅이 완료되었음.**")
    
    if st.button("🔄 신규 생산 배치 등록 (Step 0 이동)", type="primary", use_container_width=True):
        st.session_state.process_step = 0
        st.session_state.run_id = ""
        st.session_state.batch_start_dt = None
        st.session_state.step_durations = {}
        st.session_state.step_entry_times = {}
        st.rerun()

    st.markdown("### 📋 완료된 생산 배치 이력 (SQLite DB)")
    completed_df = get_all_completed_batches_multi()
    if not completed_df.empty:
        st.dataframe(completed_df, use_container_width=True)
    else:
        st.info("기록된 완료 배치 데이터가 없음.")
