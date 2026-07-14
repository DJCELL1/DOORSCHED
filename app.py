from datetime import date

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode

import db
import pdf_parser
import workdays

st.set_page_config(page_title="Joinery Production Tracker", layout="wide")
db.init_db()

BOOL_TOGGLE_FIELDS = {"urgent", "paperwork"}
STAGE_DONE_MAP = {"Make": "make_done", "Press": "press_done", "CNC": "cnc_done"}

st.title("Joinery Production Tracker")

tab_dash, tab_upload, tab_holidays = st.tabs(["Dashboard", "Upload SOs", "Public Holidays"])

# ---------------------------------------------------------------- Upload tab
with tab_upload:
    st.subheader("Bulk upload Sales Order PDFs")
    st.caption(
        "Drop in as many SO PDFs as you like — a single PDF can hold one order or "
        "several combined together, each is picked out and tracked separately. "
        "Re-uploading a PDF for an SO already in the tracker updates its extracted "
        "fields (Company/Qty/Type/Shipping Date) without touching anything you've "
        "entered by hand (Urgent, Movement, Comments, etc.)."
    )
    files = st.file_uploader("SO PDFs", type="pdf", accept_multiple_files=True, label_visibility="collapsed")
    if files:
        results = []
        for f in files:
            try:
                records = pdf_parser.extract_all_records(f)
            except pdf_parser.PdfExtractionError as e:
                results.append((f.name, None, "error", str(e)))
                continue
            for fields in records:
                _, action = db.upsert_so(fields)
                results.append((f.name, fields["so"], action, None))
        for fname, so, action, err in results:
            if err:
                st.error(f"**{fname}**: {err}")
            else:
                st.success(f"**{fname}** → {so} ({action})")

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
    holiday_dates = {date.fromisoformat(h["date"]) for h in db.get_holidays()}

    if not orders:
        st.info("No sales orders yet. Upload some PDFs in the 'Upload SOs' tab to get started.")
    else:
        rows = []
        for o in orders:
            stage = workdays.compute_stage_dates(o["shipping_date"], holiday_dates)
            rows.append(
                {
                    "id": o["id"],
                    "SO": o["so"],
                    "PRO": o["pro"],
                    "Company": o["company"],
                    "Qty": o["qty"],
                    "Type": o["type"],
                    "Shipping Date": o["shipping_date"],
                    "Week Due": stage["week_due"],
                    "Urgent": bool(o["urgent"]),
                    "Paperwork": bool(o["paperwork"]),
                    "Movement": o["movement"] or "",
                    "Make": stage["make"].isoformat() if stage["make"] else "",
                    "Press": stage["press"].isoformat() if stage["press"] else "",
                    "CNC": stage["cnc"].isoformat() if stage["cnc"] else "",
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
            "Click a Make / Press / CNC date, or the Urgent / Paperwork boxes, to toggle them. "
            "Movement, Posted, Start Date and Comments are editable text — double-click to edit. "
            "Tick the checkboxes on the left to select rows to delete."
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
