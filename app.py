from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode

import db
import pdf_parser
import workdays

st.set_page_config(page_title="Joinery Production Tracker", layout="wide")
db.init_db()

BOOL_TOGGLE_FIELDS = {"urgent", "paperwork"}
STAGE_DONE_MAP = {"Make": "make_done", "Press": "press_done", "CNC": "cnc_done"}
STAGE_LABELS = {"make": "Make", "press": "Press", "cnc": "CNC"}


def _get_holiday_dates():
    return {date.fromisoformat(h["date"]) for h in db.get_holidays()}


st.title("Joinery Production Tracker")

tab_dash, tab_schedule, tab_upload, tab_holidays = st.tabs(
    ["Dashboard", "Schedule", "Upload SOs", "Public Holidays"]
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

    palette = [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    ]
    company_colors = {}

    def _color_for(company):
        if company not in company_colors:
            company_colors[company] = palette[len(company_colors) % len(palette)]
        return company_colors[company]

    fig = go.Figure()
    day_ms = 24 * 60 * 60 * 1000
    for d in sorted(day_jobs):
        for o in day_jobs[d]:
            fig.add_trace(
                go.Bar(
                    x=[d],
                    y=[o["qty"] or 0],
                    width=day_ms * 0.8,
                    name=f"{o['so']} / {o['pro']}",
                    marker_color=_color_for(o["company"]),
                    text=o["pro"],
                    textposition="inside",
                    insidetextanchor="middle",
                    hovertemplate=(
                        f"<b>{o['so']} / {o['pro']}</b><br>"
                        f"{o['company']}<br>Qty: {o['qty']}<br>Date: {d.isoformat()}<extra></extra>"
                    ),
                    showlegend=False,
                )
            )

    fig.add_hline(
        y=capacity,
        line_dash="dot",
        line_color="#cc0000",
        annotation_text=f"Capacity: {capacity}/day",
        annotation_position="top left",
    )
    fig.update_layout(
        barmode="stack",
        xaxis=dict(type="date", range=[range_start.isoformat(), range_end.isoformat()], title="Day"),
        yaxis=dict(title=f"{stage_label} qty scheduled"),
        height=450,
        margin=dict(t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Reschedule a job")
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
                    "make_done": bool(o["make_done"]),
                    "press_done": bool(o["press_done"]),
                    "cnc_done": bool(o["cnc_done"]),
                    "Posted": o["posted"] or "",
                    "Start Date": o["start_date"] or "",
                    "Comments": o["comments"] or "",
                }
            )
        df = pd.DataFrame(rows)

        on_cell_clicked = JsCode(
            """
            function(params) {
                const stageMap = {'Make': 'make_done', 'Press': 'press_done', 'CNC': 'cnc_done'};
                const field = params.colDef.field;
                if (field === 'Urgent' || field === 'Paperwork') {
                    params.node.setDataValue(field, !params.value);
                } else if (stageMap[field]) {
                    const flagField = stageMap[field];
                    params.node.setDataValue(flagField, !params.data[flagField]);
                    params.api.refreshCells({rowNodes: [params.node], columns: ['Make', 'Press', 'CNC'], force: true});
                }
            }
            """
        )

        stage_cell_style = JsCode(
            """
            function(params) {
                const doneMap = {'Make': 'make_done', 'Press': 'press_done', 'CNC': 'cnc_done'};
                const flagField = doneMap[params.colDef.field];
                if (params.data[flagField]) {
                    return {backgroundColor: '#93c47d', color: '#000000', cursor: 'pointer'};
                }
                return {cursor: 'pointer'};
            }
            """
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
            {"field": "make_done", "hide": True},
            {"field": "press_done", "hide": True},
            {"field": "cnc_done", "hide": True},
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
                "onCellClicked": on_cell_clicked,
            },
            {
                "field": "Press",
                "width": 110,
                "editable": False,
                "cellStyle": stage_cell_style,
                "onCellClicked": on_cell_clicked,
            },
            {
                "field": "CNC",
                "width": 110,
                "editable": False,
                "cellStyle": stage_cell_style,
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
            "Click a Make / Press / CNC date, or the Urgent / Paperwork boxes, to toggle them done. "
            "Movement, Posted, Start Date and Comments are editable text — double-click to edit. "
            "Tick the checkboxes on the left to select rows to delete. "
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
        editable_fields = {
            "urgent": "Urgent",
            "paperwork": "Paperwork",
            "movement": "Movement",
            "posted": "Posted",
            "start_date": "Start Date",
            "comments": "Comments",
            "make_done": "make_done",
            "press_done": "press_done",
            "cnc_done": "cnc_done",
        }

        orders_by_id = {o["id"]: o for o in orders}
        for _, row in updated_df.iterrows():
            so_id = int(row["id"])
            original = orders_by_id.get(so_id)
            if original is None:
                continue
            changed = {}
            for db_field, grid_field in editable_fields.items():
                new_val = row[grid_field]
                if db_field in ("urgent", "paperwork", "make_done", "press_done", "cnc_done"):
                    new_val = bool(new_val) if not isinstance(new_val, bool) else new_val
                    old_val = bool(original[db_field])
                    new_val = int(new_val)
                    old_val = int(old_val)
                else:
                    new_val = "" if pd.isna(new_val) else str(new_val)
                    old_val = original[db_field] or ""
                if new_val != old_val:
                    changed[db_field] = new_val
            if changed:
                db.update_order_row(so_id, changed)
