import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode
from streamlit_autorefresh import st_autorefresh

import db
import workdays

col_refresh, col_interval = st.columns([1, 2])
with col_refresh:
    auto_refresh = st.checkbox(
        "Auto-refresh",
        value=True,
        key="dash_auto_refresh",
        help="Keeps this page in sync with updates made on the Scan and Daily Run Sheet pages, "
        "even if this browser tab is just sitting open on a wall display.",
    )
with col_interval:
    refresh_seconds = st.number_input(
        "Every (seconds)", min_value=3, max_value=120, value=8, step=1, key="dash_auto_refresh_secs"
    )
if auto_refresh:
    st_autorefresh(interval=refresh_seconds * 1000, key="dashboard_autorefresh_timer")

orders = db.get_all_orders()

if not orders:
    st.info("No sales orders yet. Upload some PDFs in the 'Upload SOs' page to get started.")
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
        "Make / Press / CNC show a progress bar (done/total) filled in from the Scan page — "
        "click one to quick-toggle it fully done or back to 0. Click Urgent / Paperwork to "
        "toggle them. Movement, Posted, Start Date and Comments are editable text — "
        "double-click to edit. Tick the checkboxes on the left to select rows to delete. "
        "To move a job to a different day, use the Schedule page."
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
