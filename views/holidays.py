from datetime import date

import pandas as pd
import streamlit as st

import db

st.subheader("Public Holidays")
st.caption("Used to skip non-working days when calculating Make/Press/CNC dates.")
holidays_list = db.get_holidays()
col_list, col_add = st.columns([2, 1])
with col_list:
    if holidays_list:
        hdf = pd.DataFrame(holidays_list)
        st.dataframe(hdf, use_container_width=True, hide_index=True, height=350)
    else:
        st.info("No holidays yet.")
with col_add:
    st.markdown("**Add a holiday**")
    new_date = st.date_input("Date", value=date.today(), key="new_holiday_date")
    new_name = st.text_input("Name", key="new_holiday_name")
    if st.button("Add"):
        db.add_holiday(new_date.isoformat(), new_name or "")
        st.rerun()
    st.markdown("**Remove a holiday**")
    if holidays_list:
        del_date = st.selectbox(
            "Date to remove", [h["date"] for h in holidays_list], key="del_holiday_date"
        )
        if st.button("Remove"):
            db.delete_holiday(del_date)
            st.rerun()
