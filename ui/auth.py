from __future__ import annotations

import streamlit as st

from repositories.users_repo import create_user, authenticate
from db.migrations import seed_defaults_for_user


def get_current_user_id() -> int | None:
    """Return current user_id from session or None if not logged in."""
    return st.session_state.get("user_id")


def render_auth():
    """Render login/register form. Returns True if user is authenticated."""
    if "user_id" in st.session_state:
        return True

    tab_login, tab_register = st.tabs(["Вход", "Регистрация"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Логин", key="login_user")
            password = st.text_input("Пароль", type="password", key="login_pass")
            submitted = st.form_submit_button("Войти", type="primary")

        if submitted:
            if not username or not password:
                st.error("Введи логин и пароль.")
            else:
                user = authenticate(username, password)
                if user:
                    st.session_state["user_id"] = user["id"]
                    st.session_state["display_name"] = user["display_name"]
                    st.session_state["username"] = user["username"]
                    st.rerun()
                else:
                    st.error("Неверный логин или пароль.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Логин", key="reg_user")
            new_display = st.text_input("Имя (отображаемое)", key="reg_display")
            new_password = st.text_input("Пароль", type="password", key="reg_pass")
            new_password2 = st.text_input("Пароль ещё раз", type="password", key="reg_pass2")
            reg_submitted = st.form_submit_button("Зарегистрироваться")

        if reg_submitted:
            if not new_username or not new_password:
                st.error("Логин и пароль обязательны.")
            elif len(new_password) < 4:
                st.error("Пароль слишком короткий (минимум 4 символа).")
            elif new_password != new_password2:
                st.error("Пароли не совпадают.")
            else:
                user_id = create_user(new_username, new_password, new_display)
                if user_id:
                    seed_defaults_for_user(user_id)
                    st.session_state["user_id"] = user_id
                    st.session_state["display_name"] = new_display or new_username
                    st.session_state["username"] = new_username
                    st.success("Регистрация успешна!")
                    st.rerun()
                else:
                    st.error("Такой логин уже занят.")

    return False


def render_user_sidebar():
    """Show user info and logout button in sidebar."""
    with st.sidebar:
        display = st.session_state.get("display_name", "")
        st.caption(f"Пользователь: **{display}**")
        if st.button("Выйти"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        st.divider()
