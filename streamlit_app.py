"""Streamlit Community Cloud entry point; retains the C++ calculation engine."""
import runpy
import streamlit as st

from scripts.cloud_backend import ensure_backend

try:
    ensure_backend()
except Exception as exc:
    st.error("云端 C++ 后端启动失败，请查看下方信息及部署日志。")
    st.exception(exc)
    st.stop()

runpy.run_module("frontend.app", run_name="__main__")
