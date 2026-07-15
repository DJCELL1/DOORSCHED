import streamlit as st
import streamlit.components.v1 as components

import db

_q = st.query_params
if "scanned_pro" in _q:
    st.session_state["scan_pro_input"] = _q["scanned_pro"]
    st.session_state["show_scanner"] = False
    st.query_params.clear()
    st.rerun()

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
