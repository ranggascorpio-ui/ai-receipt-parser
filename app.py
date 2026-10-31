"""
Aplikasi Web AI Struk & Faktur Parser (Versi SaaS Enterprise Komersial + Auto-Detect Model)
Framework: Streamlit
File: app.py
"""

from datetime import datetime
import io
import json
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image
import google.generativeai as genai

# Konfigurasi Halaman Streamlit (Harus paling atas)
st.set_page_config(
    page_title="BizReceipt AI | Enterprise Invoice Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Kustomisasi CSS Tingkat Lanjut
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    }
    .main-header {
        font-size: 2.8rem !important;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.2rem;
        letter-spacing: -0.03em;
        line-height: 1.2;
    }
    .sub-header {
        font-size: 1.15rem;
        color: #475569;
        margin-bottom: 2rem;
    }
    div.stContainer {
        border-radius: 12px;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        border: none;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    </style>
""", unsafe_allow_html=True)

# Inisialisasi Session State
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

if "trial_count" not in st.session_state:
    st.session_state["trial_count"] = 0

if "cs_messages" not in st.session_state:
    st.session_state["cs_messages"] = [
        {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu seputar penggunaan BizReceipt AI atau cara pembayaran berlangganan via QRIS?"}
    ]

MAX_TRIAL = 10
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

# -------------------------------------------------------------
# FUNGSI AUTO-DETECT MODEL GEMINI (Mencegah Error 404 Selamanya)
# -------------------------------------------------------------
@st.cache_resource
def get_active_model_name(api_key):
    genai.configure(api_key=api_key)
    try:
        available_models = [
            m.name for m in genai.list_models()
            if 'generateContent' in m.supported_generation_methods
        ]
        # Prioritaskan model generasi terbaru yang stabil dan cepat
        preferred_order = [
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash",
            "models/gemini-2.0-flash-lite",
            "models/gemini-2.5-pro",
            "models/gemini-pro-latest"
        ]
        for pref in preferred_order:
            if pref in available_models:
                return pref
        # Jika tidak ada di daftar prioritas, ambil model flash apa saja yang tersedia
        for m in available_models:
            if "flash" in m:
                return m
        # Fallback terakhir ke model pertama yang mendukung generateContent
        if available_models:
            return available_models[0]
    except Exception:
        pass
    return "gemini-2.5-flash"

# -------------------------------------------------------------
# SIDEBAR: Navigasi & Status Trial
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏢 BizReceipt AI")
    st.caption("Solusi Ekstraksi Dokumen Finansial Otomatis")
    st.markdown("---")
    
    sisa_trial = max(0, MAX_TRIAL - st.session_state["trial_count"])
    st.markdown("#### Status Akun Anda")
    if sisa_trial > 0:
        st.info(f"✨ **Mode Trial Aktif**\n\nSisa Kuota Gratis: **{sisa_trial} dari {MAX_TRIAL} dokumen**")
    else:
        st.warning("⚠️ **Kuota Trial Habis!**\n\nSilakan lakukan pembayaran via QRIS untuk memperpanjang akses.")
    
    st.markdown("---")
    st.markdown("#### Navigasi Menu")
    app_mode = st.radio(
        "Pilih Menu",
        ["🚀 Parser Utama", "📚 Riwayat & Panduan", "💳 Kelola Langganan & QRIS", "💬 Tanya CS AI"],
        label_visibility="collapsed"
    )
    
    st
