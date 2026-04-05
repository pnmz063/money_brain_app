from datetime import date
import streamlit as st

from db.migrations import init_db
from repositories.settings_repo import get_setting
from ui.onboarding_wizard import render_onboarding_wizard
from ui.dashboard import render_dashboard

st.set_page_config(
    page_title="Семейный бюджет MVP",
    page_icon="💸",
    layout="wide",
)

init_db()

st.title("💸 Семейный бюджет MVP")
st.caption("Бюджет, долги, остаток месяца и рекомендации по досрочному погашению.")

onboarding_completed = get_setting("onboarding_completed", "false").lower() == "true"

if not onboarding_completed:
    render_onboarding_wizard()
else:
    render_dashboard(selected_month=date.today().replace(day=1))
