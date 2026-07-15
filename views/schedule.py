from datetime import date, timedelta

import streamlit as st
import streamlit.components.v1 as components

import db
import helpers
import workdays

holiday_dates = helpers.get_holiday_dates()

_q = st.query_params
if {"resched_id", "resched_stage", "resched_date"} <= set(_q.keys()):
    db.reschedule_stage(int(_q["resched_id"]), _q["resched_stage"], _q["resched_date"], holiday_dates)
    st.query_params.clear()
    st.rerun()

st.subheader("Production Schedule")

stage_label = st.radio("Stage", ["Make", "Press", "CNC"], horizontal=True, key="schedule_stage")
stage_key = stage_label.lower()
date_col = f"{stage_key}_date"

capacities = db.get_capacities()

col_cap, col_start, col_days = st.columns([1, 1, 1])
with col_cap:
    new_capacity = st.number_input(
        f"{stage_label} daily capacity",
        min_value=1,
        value=capacities[stage_key],
        key=f"cap_input_{stage_key}",
    )
    if int(new_capacity) != capacities[stage_key]:
        db.set_capacity(stage_key, int(new_capacity))
        st.rerun()
with col_start:
    range_start = st.date_input(
        "Show from", value=date.today() - timedelta(days=3), key=f"sched_start_{stage_key}"
    )
with col_days:
    num_days = st.slider("Days to show", min_value=7, max_value=60, value=21, key=f"sched_days_{stage_key}")

range_end = range_start + timedelta(days=num_days)
capacity = capacities[stage_key]

orders = db.get_all_orders()
scheduled = [o for o in orders if o[date_col]]

day_jobs = {}
for o in scheduled:
    d = date.fromisoformat(o[date_col])
    if range_start <= d < range_end:
        day_jobs.setdefault(d, []).append(o)

st.caption(
    "Drag a job's box onto another day to reschedule it — box height is its door quantity. "
    "Moving a Make date also carries Press to the same day and CNC to the next working day; "
    "moving Press or CNC on their own only moves that stage."
)

PX_PER_UNIT = 4
MIN_CARD_H = 30
MAX_CARD_H = 220
COLUMN_BODY_H = 260

day_cols_html = []
for i in range(num_days):
    d = range_start + timedelta(days=i)
    jobs = day_jobs.get(d, [])
    total_qty = sum(j["qty"] or 0 for j in jobs)
    is_over = total_qty > capacity
    cap_line_top = min(capacity * PX_PER_UNIT, COLUMN_BODY_H)

    cards_html = []
    for j in jobs:
        qty = j["qty"] or 0
        h = max(MIN_CARD_H, min(MAX_CARD_H, qty * PX_PER_UNIT))
        color = helpers.color_for_pro(j["pro"])
        cards_html.append(f"""
            <div class="job-card"
                 style="height:{h}px; background:{color};"
                 data-id="{j['id']}"
                 onmousedown="onCardMouseDown(event)"
                 title="{j['so']} / {j['pro']} — {j['company']} — Qty {qty}">
                <div class="job-pro">{j['pro']}</div>
                <div class="job-meta">{j['company']} · {qty}</div>
            </div>
        """)

    day_name = d.strftime("%a")
    day_label = d.strftime("%d %b")
    col_class = "day-col over" if is_over else "day-col"
    total_class = "day-total over" if is_over else "day-total"

    day_cols_html.append(f"""
        <div class="{col_class}">
            <div class="day-header">{day_name}<br>{day_label}</div>
            <div class="{total_class}">{total_qty} / {capacity}</div>
            <div class="drop-zone" data-date="{d.isoformat()}">
                <div class="capacity-line" style="top:{cap_line_top}px;"></div>
                {''.join(cards_html)}
            </div>
        </div>
    """)

board_html = f"""
<style>
    body {{ margin:0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; }}
    .board {{ display:flex; gap:8px; overflow-x:auto; padding:4px 2px 12px 2px; }}
    .day-col {{ min-width:120px; max-width:120px; background:#f4f5f7; border-radius:8px; padding:6px; flex-shrink:0; }}
    .day-col.over {{ background:#fbe7e7; }}
    .day-header {{ font-size:12px; font-weight:600; text-align:center; color:#333; line-height:1.3; }}
    .day-total {{ font-size:11px; text-align:center; color:#777; margin:2px 0 6px 0; }}
    .day-total.over {{ color:#cc0000; font-weight:700; }}
    .drop-zone {{ position:relative; min-height:{COLUMN_BODY_H}px; border:1px dashed #ccc; border-radius:6px; padding:4px; background:#fff; }}
    .drop-zone.drag-over {{ background:#eef3ff; border-color:#4e79a7; }}
    .capacity-line {{ position:absolute; left:0; right:0; border-top:2px dashed #cc0000; pointer-events:none; }}
    .job-card {{ position:relative; color:#fff; border-radius:5px; padding:4px 6px; margin-bottom:4px;
                 font-size:10px; cursor:grab; box-shadow:0 1px 2px rgba(0,0,0,.25); overflow:hidden; box-sizing:border-box; }}
    .job-card:active {{ cursor:grabbing; opacity:0.85; }}
    .job-pro {{ font-weight:700; }}
    .job-meta {{ opacity:0.9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
</style>
<div class="board">
    {''.join(day_cols_html)}
</div>
<script>
    var dragEl = null, dragGhost = null, offsetX = 0, offsetY = 0;

    function onCardMouseDown(ev) {{
        dragEl = ev.currentTarget;
        var rect = dragEl.getBoundingClientRect();
        offsetX = ev.clientX - rect.left;
        offsetY = ev.clientY - rect.top;

        dragGhost = dragEl.cloneNode(true);
        dragGhost.style.position = 'fixed';
        dragGhost.style.left = rect.left + 'px';
        dragGhost.style.top = rect.top + 'px';
        dragGhost.style.width = rect.width + 'px';
        dragGhost.style.height = rect.height + 'px';
        dragGhost.style.opacity = '0.9';
        dragGhost.style.pointerEvents = 'none';
        dragGhost.style.zIndex = '1000';
        dragGhost.style.transform = 'rotate(-2deg)';
        document.body.appendChild(dragGhost);
        dragEl.style.opacity = '0.25';

        document.addEventListener('mousemove', onDragMove);
        document.addEventListener('mouseup', onDragEnd);
        ev.preventDefault();
    }}

    function onDragMove(ev) {{
        if (!dragGhost) return;
        dragGhost.style.left = (ev.clientX - offsetX) + 'px';
        dragGhost.style.top = (ev.clientY - offsetY) + 'px';
        document.querySelectorAll('.drop-zone').forEach(function(z) {{ z.classList.remove('drag-over'); }});
        var under = document.elementFromPoint(ev.clientX, ev.clientY);
        var zone = under && under.closest ? under.closest('.drop-zone') : null;
        if (zone) zone.classList.add('drag-over');
    }}

    function onDragEnd(ev) {{
        document.removeEventListener('mousemove', onDragMove);
        document.removeEventListener('mouseup', onDragEnd);
        if (dragGhost) {{ dragGhost.remove(); dragGhost = null; }}

        var under = document.elementFromPoint(ev.clientX, ev.clientY);
        var zone = under && under.closest ? under.closest('.drop-zone') : null;
        if (zone && dragEl) {{
            var id = dragEl.dataset.id;
            var targetDate = zone.dataset.date;
            var url = new URL(window.top.location.href);
            url.searchParams.set('resched_id', id);
            url.searchParams.set('resched_stage', '{stage_key}');
            url.searchParams.set('resched_date', targetDate);
            window.top.location.href = url.toString();
        }} else if (dragEl) {{
            dragEl.style.opacity = '1';
        }}
        dragEl = null;
    }}
</script>
"""
components.html(board_html, height=380, scrolling=True)

st.markdown("#### Reschedule a job")
st.caption("Fallback controls if you'd rather not drag.")
if not scheduled:
    st.info("No scheduled jobs yet.")
else:
    job_options = {
        f"{o['so']} / {o['pro']} — {o['company']} (Qty {o['qty']}) — currently {o[date_col]}": o
        for o in sorted(scheduled, key=lambda o: o[date_col])
    }
    selected_label = st.selectbox("Job", list(job_options.keys()), key=f"resched_select_{stage_key}")
    selected_order = job_options[selected_label]
    current_date = date.fromisoformat(selected_order[date_col])

    col_earlier, col_pick, col_set, col_later = st.columns([1, 1.4, 1, 1])
    with col_earlier:
        if st.button("◀ Move earlier", key=f"earlier_{stage_key}"):
            new_date = workdays.workday(current_date, -1, holiday_dates)
            db.reschedule_stage(selected_order["id"], stage_key, new_date.isoformat(), holiday_dates)
            st.rerun()
    with col_pick:
        picked_date = st.date_input("Move to date", value=current_date, key=f"pick_date_{stage_key}")
    with col_set:
        if st.button("Set date", key=f"set_date_{stage_key}"):
            db.reschedule_stage(selected_order["id"], stage_key, picked_date.isoformat(), holiday_dates)
            st.rerun()
    with col_later:
        if st.button("Move later ▶", key=f"later_{stage_key}"):
            new_date = workdays.workday(current_date, 1, holiday_dates)
            db.reschedule_stage(selected_order["id"], stage_key, new_date.isoformat(), holiday_dates)
            st.rerun()
