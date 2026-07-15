import hashlib
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode

import db
import pdf_parser
import workdays

st.set_page_config(page_title="Joinery Production Tracker", layout="wide")
db.init_db()

STAGE_LABELS = {"make": "Make", "press": "Press", "cnc": "CNC"}

JOB_COLOR_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#86bcb6", "#d37295",
]


def _get_holiday_dates():
    return {date.fromisoformat(h["date"]) for h in db.get_holidays()}


def _color_for_pro(pro: str) -> str:
    idx = int(hashlib.md5(pro.encode()).hexdigest(), 16) % len(JOB_COLOR_PALETTE)
    return JOB_COLOR_PALETTE[idx]


# A drag-drop in the Schedule board below navigates the top window with
# ?resched_id=&resched_stage=&resched_date= to get the move back to Python
# (components.v1.html has no return channel of its own). Apply and clear it
# before anything else renders so it can't be re-applied on the next rerun.
_q = st.query_params
if {"resched_id", "resched_stage", "resched_date"} <= set(_q.keys()):
    db.reschedule_stage(int(_q["resched_id"]), _q["resched_stage"], _q["resched_date"])
    st.query_params.clear()
    st.rerun()
elif "scanned_pro" in _q:
    st.session_state["scan_pro_input"] = _q["scanned_pro"]
    st.session_state["show_scanner"] = False
    st.query_params.clear()
    st.rerun()

st.title("Joinery Production Tracker")

tab_dash, tab_scan, tab_schedule, tab_upload, tab_holidays = st.tabs(
    ["Dashboard", "Scan", "Schedule", "Upload SOs", "Public Holidays"]
)

# ---------------------------------------------------------------- Upload tab
with tab_upload:
    st.subheader("Bulk upload Sales Order PDFs")
    st.caption(
        "Drop in as many SO PDFs as you like — a single PDF can hold one order or "
        "several combined together (even multiple PROs under the same SO), each is "
        "picked out and tracked as its own row. Re-uploading a PDF for a PRO already "
        "in the tracker updates its extracted fields (SO/Company/Qty/Type/Shipping "
        "Date) without touching anything you've entered by hand (Urgent, Movement, "
        "Comments, etc.)."
    )
    files = st.file_uploader("SO PDFs", type="pdf", accept_multiple_files=True, label_visibility="collapsed")
    if files:
        holiday_dates = _get_holiday_dates()
        results = []
        for f in files:
            try:
                records = pdf_parser.extract_all_records(f)
            except pdf_parser.PdfExtractionError as e:
                results.append((f.name, None, "error", str(e)))
                continue
            for fields in records:
                stage = workdays.compute_stage_dates(fields["shipping_date"], holiday_dates)
                fields["make_date"] = stage["make"].isoformat() if stage["make"] else None
                fields["press_date"] = stage["press"].isoformat() if stage["press"] else None
                fields["cnc_date"] = stage["cnc"].isoformat() if stage["cnc"] else None
                _, action = db.upsert_so(fields)
                results.append((f.name, fields["so"], action, None))
        for fname, so, action, err in results:
            if err:
                st.error(f"**{fname}**: {err}")
            else:
                st.success(f"**{fname}** → {so} ({action})")

# ----------------------------------------------------------------- Scan tab
with tab_scan:
    st.subheader("Scan / Log Production Progress")
    st.caption(
        "Scan a PRO barcode or type it in, then log how many have been "
        "completed for Make, Press or CNC. Updates show up immediately on "
        "the Dashboard."
    )

    col_pro, col_scan_btn = st.columns([2, 1])
    with col_pro:
        pro_input = st.text_input(
            "PRO number", key="scan_pro_input", placeholder="e.g. PRO-315238"
        )
    with col_scan_btn:
        st.markdown("&nbsp;")
        if st.button("📷 Scan barcode", key="open_scanner", use_container_width=True):
            st.session_state["show_scanner"] = True
            st.rerun()

    if st.session_state.get("show_scanner"):
        scanner_html = """
        <div id="reader" style="width:100%;"></div>
        <p style="font-family:sans-serif;font-size:12px;color:#666;">
            Point the camera at the PRO barcode. Needs HTTPS (or localhost) to access the camera.
        </p>
        <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
        <script>
            function onScanSuccess(decodedText) {
                var url = new URL(window.top.location.href);
                url.searchParams.set('scanned_pro', decodedText);
                window.top.location.href = url.toString();
            }
            var html5QrCode = new Html5Qrcode("reader");
            html5QrCode.start(
                { facingMode: "environment" },
                {
                    fps: 10,
                    qrbox: { width: 260, height: 160 },
                    formatsToSupport: [
                        Html5QrcodeSupportedFormats.CODE_39,
                        Html5QrcodeSupportedFormats.CODE_128,
                        Html5QrcodeSupportedFormats.EAN_13,
                        Html5QrcodeSupportedFormats.QR_CODE
                    ]
                },
                onScanSuccess
            ).catch(function(err) {
                document.getElementById("reader").innerHTML =
                    "<p style='color:#cc0000;font-family:sans-serif;'>Camera error: " + err +
                    "</p><p style='font-family:sans-serif;'>Type the PRO number above instead.</p>";
            });
        </script>
        """
        components.html(scanner_html, height=340)
        if st.button("Close scanner", key="close_scanner"):
            st.session_state["show_scanner"] = False
            st.rerun()

    pro_value = (pro_input or "").strip().upper()
    if pro_value:
        order = db.get_order_by_pro(pro_value)
        if order is None:
            st.error(f"No job found with PRO '{pro_value}'.")
        else:
            total_qty = order["qty"] or 0
            st.markdown(f"### {order['so']} / {order['pro']} — {order['company']}")
            st.caption(f"{order['type']} · Qty {total_qty} · Shipping {order['shipping_date']}")

            for label, key in (("Make", "make"), ("Press", "press"), ("CNC", "cnc")):
                done = order[f"{key}_progress"] or 0
                st.markdown(f"**{label}** — {done}/{total_qty}")
                st.progress(min(1.0, done / total_qty) if total_qty else 0.0)

            st.markdown("#### Log progress")
            stage_pick = st.radio("Stage", ["Make", "Press", "CNC"], horizontal=True, key="scan_stage_pick")
            stage_key2 = stage_pick.lower()
            current_done = order[f"{stage_key2}_progress"] or 0

            new_done = st.number_input(
                f"Total {stage_pick} completed so far (out of {total_qty})",
                min_value=0,
                max_value=total_qty,
                value=min(current_done, total_qty),
                step=1,
                key=f"scan_qty_{order['id']}_{stage_key2}",
            )

            quick_cols = st.columns(4)
            for col, frac in zip(quick_cols, [0.25, 0.5, 0.75, 1.0]):
                with col:
                    label = "All done" if frac == 1.0 else f"{int(frac * 100)}%"
                    if st.button(label, key=f"quick_{frac}_{order['id']}_{stage_key2}"):
                        db.update_progress(order["id"], stage_key2, round(total_qty * frac))
                        st.rerun()

            if st.button("Save progress", type="primary", key=f"save_{order['id']}_{stage_key2}"):
                db.update_progress(order["id"], stage_key2, int(new_done))
                st.success(f"{stage_pick} updated: {int(new_done)}/{total_qty}")
                st.rerun()

# ------------------------------------------------------------ Schedule tab
with tab_schedule:
    st.subheader("Production Schedule")

    stage_label = st.radio("Stage", ["Make", "Press", "CNC"], horizontal=True, key="schedule_stage")
    stage_key = stage_label.lower()
    date_col = f"{stage_key}_date"

    holiday_dates = _get_holiday_dates()
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

    st.caption("Drag a job's box onto another day to reschedule it — box height is its door quantity.")

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
            color = _color_for_pro(j["pro"])
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
                db.reschedule_stage(selected_order["id"], stage_key, new_date.isoformat())
                st.rerun()
        with col_pick:
            picked_date = st.date_input("Move to date", value=current_date, key=f"pick_date_{stage_key}")
        with col_set:
            if st.button("Set date", key=f"set_date_{stage_key}"):
                db.reschedule_stage(selected_order["id"], stage_key, picked_date.isoformat())
                st.rerun()
        with col_later:
            if st.button("Move later ▶", key=f"later_{stage_key}"):
                new_date = workdays.workday(current_date, 1, holiday_dates)
                db.reschedule_stage(selected_order["id"], stage_key, new_date.isoformat())
                st.rerun()

# ------------------------------------------------------------- Holidays tab
with tab_holidays:
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

# ------------------------------------------------------------- Dashboard tab
with tab_dash:
    orders = db.get_all_orders()

    if not orders:
        st.info("No sales orders yet. Upload some PDFs in the 'Upload SOs' tab to get started.")
    else:
        rows = []
        for o in orders:
            week_due = workdays.iso_week(o["shipping_date"])
            rows.append(
                {
                    "id": o["id"],
                    "SO": o["so"],
                    "PRO": o["pro"],
                    "Company": o["company"],
                    "Qty": o["qty"],
                    "Type": o["type"],
                    "Shipping Date": o["shipping_date"],
                    "Week Due": week_due,
                    "Urgent": bool(o["urgent"]),
                    "Paperwork": bool(o["paperwork"]),
                    "Movement": o["movement"] or "",
                    "Make": o["make_date"] or "",
                    "Press": o["press_date"] or "",
                    "CNC": o["cnc_date"] or "",
                    "make_progress": o["make_progress"] or 0,
                    "press_progress": o["press_progress"] or 0,
                    "cnc_progress": o["cnc_progress"] or 0,
                    "Posted": o["posted"] or "",
                    "Start Date": o["start_date"] or "",
                    "Comments": o["comments"] or "",
                }
            )
        df = pd.DataFrame(rows)

        on_cell_clicked = JsCode(
            """
            function(params) {
                const stageMap = {'Make': 'make_progress', 'Press': 'press_progress', 'CNC': 'cnc_progress'};
                const field = params.colDef.field;
                if (field === 'Urgent' || field === 'Paperwork') {
                    params.node.setDataValue(field, !params.value);
                } else if (stageMap[field]) {
                    const progField = stageMap[field];
                    const total = params.data.Qty || 0;
                    const current = params.data[progField] || 0;
                    const newVal = (total > 0 && current >= total) ? 0 : total;
                    params.node.setDataValue(progField, newVal);
                    params.api.refreshCells({rowNodes: [params.node], columns: ['Make', 'Press', 'CNC'], force: true});
                }
            }
            """
        )

        stage_cell_style = JsCode(
            """
            function(params) {
                const progMap = {'Make': 'make_progress', 'Press': 'press_progress', 'CNC': 'cnc_progress'};
                const progField = progMap[params.colDef.field];
                const total = params.data.Qty || 0;
                const done = params.data[progField] || 0;
                const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
                const fillColor = pct >= 100 ? '#6aa84f' : '#8fbc7a';
                return {
                    background: 'linear-gradient(to right, ' + fillColor + ' 0%, ' + fillColor + ' ' + pct + '%, #e3e3e3 ' + pct + '%, #e3e3e3 100%)',
                    textAlign: 'center',
                    cursor: 'pointer',
                    fontWeight: '600',
                };
            }
            """
        )

        stage_value_formatter = JsCode(
            """
            function(params) {
                const progMap = {'Make': 'make_progress', 'Press': 'press_progress', 'CNC': 'cnc_progress'};
                const progField = progMap[params.colDef.field];
                const total = params.data.Qty || 0;
                const done = params.data[progField] || 0;
                return done + ' / ' + total;
            }
            """
        )

        stage_tooltip = JsCode(
            "function(params) { return 'Scheduled: ' + (params.value || 'not scheduled'); }"
        )

        bool_cell_style = JsCode(
            """
            function(params) {
                if (params.value) {
                    return {backgroundColor: '#93c47d', color: '#000000', cursor: 'pointer', textAlign: 'center'};
                }
                return {cursor: 'pointer', textAlign: 'center'};
            }
            """
        )

        bool_value_formatter = JsCode(
            "function(params) { return params.value ? '\\u2713' : ''; }"
        )

        get_row_style = JsCode(
            """
            function(params) {
                if (params.data.Paperwork === false) {
                    return {color: '#cc0000'};
                }
                return null;
            }
            """
        )

        column_defs = [
            {"field": "id", "hide": True},
            {"field": "make_progress", "hide": True},
            {"field": "press_progress", "hide": True},
            {"field": "cnc_progress", "hide": True},
            {"field": "SO", "pinned": "left", "width": 110},
            {"field": "PRO", "width": 110},
            {"field": "Company", "width": 160},
            {"field": "Qty", "width": 80},
            {"field": "Type", "width": 100},
            {"field": "Shipping Date", "width": 120},
            {"field": "Week Due", "width": 100},
            {
                "field": "Urgent",
                "width": 90,
                "editable": False,
                "cellStyle": bool_cell_style,
                "valueFormatter": bool_value_formatter,
                "onCellClicked": on_cell_clicked,
            },
            {
                "field": "Paperwork",
                "width": 100,
                "editable": False,
                "cellStyle": bool_cell_style,
                "valueFormatter": bool_value_formatter,
                "onCellClicked": on_cell_clicked,
            },
            {"field": "Movement", "width": 120, "editable": True},
            {
                "field": "Make",
                "width": 110,
                "editable": False,
                "cellStyle": stage_cell_style,
                "valueFormatter": stage_value_formatter,
                "tooltipValueGetter": stage_tooltip,
                "onCellClicked": on_cell_clicked,
            },
            {
                "field": "Press",
                "width": 110,
                "editable": False,
                "cellStyle": stage_cell_style,
                "valueFormatter": stage_value_formatter,
                "tooltipValueGetter": stage_tooltip,
                "onCellClicked": on_cell_clicked,
            },
            {
                "field": "CNC",
                "width": 110,
                "editable": False,
                "cellStyle": stage_cell_style,
                "valueFormatter": stage_value_formatter,
                "tooltipValueGetter": stage_tooltip,
                "onCellClicked": on_cell_clicked,
            },
            {"field": "Posted", "width": 90, "editable": True},
            {"field": "Start Date", "width": 120, "editable": True},
            {"field": "Comments", "width": 260, "editable": True},
        ]

        grid_options = {
            "columnDefs": column_defs,
            "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
            "getRowStyle": get_row_style,
            "rowHeight": 32,
            "headerHeight": 34,
            "rowSelection": {
                "mode": "multiRow",
                "checkboxes": True,
                "headerCheckbox": True,
                "enableClickSelection": False,
            },
        }

        st.caption(
            "Make / Press / CNC show a progress bar (done/total) filled in from the Scan tab — "
            "click one to quick-toggle it fully done or back to 0. Click Urgent / Paperwork to "
            "toggle them. Movement, Posted, Start Date and Comments are editable text — "
            "double-click to edit. Tick the checkboxes on the left to select rows to delete. "
            "To move a job to a different day, use the Schedule tab."
        )

        grid_key_version = st.session_state.setdefault("grid_key_version", 0)

        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=False,
            height=min(80 + 32 * (len(df) + 1), 700),
            theme="balham",
            key=f"dashboard_grid_{grid_key_version}",
        )

        selected_df = grid_response.selected_rows
        if selected_df is not None and len(selected_df) > 0:
            selected_ids = [int(i) for i in selected_df["id"].tolist()]
            selected_sos = selected_df["SO"].tolist()
            st.warning(f"Selected {len(selected_ids)} row(s): {', '.join(selected_sos)}")
            if st.button(f"Delete {len(selected_ids)} selected row(s)", type="primary"):
                for so_id in selected_ids:
                    db.delete_order(so_id)
                st.session_state["grid_key_version"] += 1
                st.rerun()

        updated_df = pd.DataFrame(grid_response["data"])
        bool_fields = {"urgent": "Urgent", "paperwork": "Paperwork"}
        text_fields = {
            "movement": "Movement",
            "posted": "Posted",
            "start_date": "Start Date",
            "comments": "Comments",
        }
        progress_fields = {
            "make_progress": "make_progress",
            "press_progress": "press_progress",
            "cnc_progress": "cnc_progress",
        }
        done_columns = {"make_progress": "make_done", "press_progress": "press_done", "cnc_progress": "cnc_done"}

        orders_by_id = {o["id"]: o for o in orders}
        for _, row in updated_df.iterrows():
            so_id = int(row["id"])
            original = orders_by_id.get(so_id)
            if original is None:
                continue
            changed = {}
            for db_field, grid_field in bool_fields.items():
                new_val = int(bool(row[grid_field]))
                old_val = int(bool(original[db_field]))
                if new_val != old_val:
                    changed[db_field] = new_val
            for db_field, grid_field in text_fields.items():
                new_val = "" if pd.isna(row[grid_field]) else str(row[grid_field])
                old_val = original[db_field] or ""
                if new_val != old_val:
                    changed[db_field] = new_val
            total_qty = int(row["Qty"]) if not pd.isna(row["Qty"]) else 0
            for db_field, grid_field in progress_fields.items():
                new_val = max(0, min(int(row[grid_field]), total_qty))
                old_val = int(original[db_field] or 0)
                if new_val != old_val:
                    changed[db_field] = new_val
                    changed[done_columns[db_field]] = 1 if total_qty > 0 and new_val >= total_qty else 0
            if changed:
                db.update_order_row(so_id, changed)
