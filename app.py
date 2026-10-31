"""
Aplikasi Web AI Struk & Faktur Parser (Versi SaaS Enterprise Komersial - Gemini 3.8 Flash)
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
# FUNGSI PEMANGGILAN GEMINI 3.8 FLASH DENGAN AUTO-FALLBACK
# -------------------------------------------------------------
def generate_with_fallback(api_key, contents, is_json=False):
    genai.configure(api_key=api_key)
    
    # Prioritas pertama sesuai instruksi resmi API: models/gemini-3.8-flash
    candidate_models = [
        "models/gemini-3.8-flash",
        "gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest"
    ]
    
    # Tambahkan model lain dari list_models() yang bukan 1.5 atau 2.5 sebagai cadangan
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if m.name not in candidate_models and "1.5" not in m.name and "2.5" not in m.name:
                    candidate_models.append(m.name)
    except Exception:
        pass

    config = {"response_mime_type": "application/json"} if is_json else None
    last_error = None

    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name=model_name, generation_config=config)
            return model.generate_content(contents)
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            # Jika error karena model tidak ditemukan/tidak tersedia (404), coba kandidat berikutnya
            if "404" in err_msg or "not found" in err_msg or "no longer available" in err_msg:
                continue
            else:
                raise e

    raise last_error

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
        st.info(f"✨ **Mode
