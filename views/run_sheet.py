from datetime import date

import streamlit as st

import db

st.subheader("Daily Run Sheet")
st.caption(
    "What's due today for Make/Press (same person, same day) and what's due for CNC "
    "(next working day after Make/Press). Update progress here and it syncs straight "
    "to the Dashboard."
)

selected_date = st.date_input("Date", value=date.today(), key="run_sheet_date")
date_str = selected_date.isoformat()
day_label = selected_date.strftime("%a %d %b %Y")

orders = db.get_all_orders()
capacities = db.get_capacities()

make_press_jobs = sorted(
    (o for o in orders if o["make_date"] == date_str or o["press_date"] == date_str),
    key=lambda o: o["pro"],
)
cnc_jobs = sorted((o for o in orders if o["cnc_date"] == date_str), key=lambda o: o["pro"])


def _job_label(o):
    return f"**{o['so']} / {o['pro']}** — {o['company']} ({o['type']}, Qty {o['qty']})"


st.markdown(f"### Make & Press — due {day_label}")
make_total = sum(o["qty"] or 0 for o in make_press_jobs)
st.caption(f"{make_total} doors queued — Make capacity {capacities['make']}/day, Press capacity {capacities['press']}/day")

if not make_press_jobs:
    st.info("Nothing due for Make/Press on this date.")
else:
    header = st.columns([3, 1, 1])
    header[1].markdown("**Make done**")
    header[2].markdown("**Press done**")
    for o in make_press_jobs:
        qty = o["qty"] or 0
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(_job_label(o))
        with cols[1]:
            new_make = st.number_input(
                "Make done",
                min_value=0,
                max_value=qty,
                value=min(o["make_progress"] or 0, qty),
                step=1,
                key=f"rs_make_{o['id']}",
                label_visibility="collapsed",
            )
            if int(new_make) != (o["make_progress"] or 0):
                db.update_progress(o["id"], "make", int(new_make))
        with cols[2]:
            new_press = st.number_input(
                "Press done",
                min_value=0,
                max_value=qty,
                value=min(o["press_progress"] or 0, qty),
                step=1,
                key=f"rs_press_{o['id']}",
                label_visibility="collapsed",
            )
            if int(new_press) != (o["press_progress"] or 0):
                db.update_progress(o["id"], "press", int(new_press))

st.divider()

st.markdown(f"### CNC — due {day_label}")
cnc_total = sum(o["qty"] or 0 for o in cnc_jobs)
st.caption(f"{cnc_total} doors queued — CNC capacity {capacities['cnc']}/day")

if not cnc_jobs:
    st.info("Nothing due for CNC on this date.")
else:
    header = st.columns([3, 1])
    header[1].markdown("**CNC done**")
    for o in cnc_jobs:
        qty = o["qty"] or 0
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(_job_label(o))
        with cols[1]:
            new_cnc = st.number_input(
                "CNC done",
                min_value=0,
                max_value=qty,
                value=min(o["cnc_progress"] or 0, qty),
                step=1,
                key=f"rs_cnc_{o['id']}",
                label_visibility="collapsed",
            )
            if int(new_cnc) != (o["cnc_progress"] or 0):
                db.update_progress(o["id"], "cnc", int(new_cnc))
