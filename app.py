import streamlit as st

import db

st.set_page_config(page_title="Joinery Production Tracker", layout="wide")
db.init_db()

st.title("Joinery Production Tracker")

pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("views/scan.py", title="Scan", icon="📷"),
    st.Page("views/schedule.py", title="Schedule", icon="📅"),
    st.Page("views/upload.py", title="Upload SOs", icon="📤"),
    st.Page("views/holidays.py", title="Public Holidays", icon="🗓️"),
]

st.navigation(pages).run()
