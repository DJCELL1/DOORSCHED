import streamlit as st

import db
import helpers
import pdf_parser
import workdays

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
    holiday_dates = helpers.get_holiday_dates()
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
