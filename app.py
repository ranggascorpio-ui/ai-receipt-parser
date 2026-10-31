"""
Aplikasi Web AI Struk & Faktur Parser (Versi SaaS Enterprise Komersial)
Framework: Streamlit
File: app.py
"""

from datetime import datetime
import io
import json
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

# Kustomisasi CSS Tingkat Lanjut untuk Estetika SaaS Komersial Premium
st.markdown("""
    <style>
    /* Mengatur latar belakang utama agar tidak terlalu polos */
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    }
    
    /* Header Utama */
    .main-header {
        font-size: 2.25rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.2rem;
        letter-spacing: -0.025em;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    
    /* Kartu & Container kustom */
    div.stContainer {
        border-radius: 12px;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }
    
    /* Tombol Utama */
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
    
    /* Styling Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# SIDEBAR: Navigasi & Info Akun / Langganan (SaaS Ready)
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏢 BizReceipt AI")
    st.caption("Solusi Ekstraksi Dokumen Finansial Otomatis")
    st.markdown("---")
    
    # Status Akun Pengguna (Simulasi SaaS Tier)
    st.markdown("#### Status Langganan")
    st.info("⭐ **Paket: Enterprise Pro**\n\nStatus: Aktif\nSisa Kuota: **Unlimited / Sesuai API**")
    
    st.markdown("---")
    st.markdown("#### Navigasi Menu")
    app_mode = st.radio(
        "Pilih Menu",
        ["🚀 Parser Utama", "📚 Riwayat & Panduan", "💳 Kelola Langganan"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("<p style='font-size: 0.8rem; color: #94a3b8;'>© 2026 BizReceipt Intelligence. All rights reserved.</p>", unsafe_allow_html=True)

# Mengambil API Key secara aman dari Streamlit Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

# Inisialisasi Session State
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

# -------------------------------------------------------------
# HALAMAN 1: PARSER UTAMA
# -------------------------------------------------------------
if app_mode == "🚀 Parser Utama":
    # Header Utama Platform
    st.markdown('<p class="main-header">💼 AI Receipt & Invoice Intelligence</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Ubah dokumen struk, nota, atau faktur fisik/digital menjadi laporan tabel akuntansi terstruktur secara instan.</p>', unsafe_allow_html=True)
    st.markdown("")

    # Layout Kolom dengan Kontainer Profesional
    col_upload, col_info = st.columns([2, 1], gap="large")

    with col_upload:
        with st.container(border=True):
            st.subheader("📤 Unggah Dokumen Transaksi")
            st.caption("Mendukung multi-file sekaligus (Format: PNG, JPG, JPEG)")
            
            uploaded_files = st.file_uploader(
                "Seret & letakkan file foto di sini", 
                type=["png", "jpg", "jpeg"], 
                accept_multiple_files=True,
                label_visibility="collapsed"
            )

    with col_info:
        with st.container(border=True):
            st.subheader("💡 Standar Kualitas")
            st.markdown(
                "1. **Kejelasan:** Pastikan foto struk terang & tidak blur.\n"
                "2. **Fleksibel:** Mendukung cetakan termal POS & **tulisan tangan**.\n"
                "3. **Audit Data:** Validasi ulang langsung di tabel sebelum diekspor."
            )

    # Tombol Proses & Logika AI
    if uploaded_files:
        st.markdown("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            process_btn = st.button("🚀 Proses Dokumen", type="primary", use_container_width=True)
        
        if process_btn:
            if not GEMINI_API_KEY:
                st.error("⚠️ Sistem API Key belum terkonfigurasi dengan benar di server.")
            else:
                with st.spinner("🤖 AI sedang memindai rincian transaksi, pajak, dan item belanja..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        model = genai.GenerativeModel(
                            model_name='gemini-1.5-flash',
                            generation_config={"response_mime_type": "application/json"}
                        )
                        
                        prompt = """
                        Ekstrak data dari struk atau bon ini menjadi format JSON dengan struktur persis berikut:
                        {
                          "nama_vendor": "Nama toko atau vendor",
                          "no_struk": "Nomor struk atau referensi",
                          "tanggal": "YYYY-MM-DD",
                          "items": [
                            {
                              "Nama Barang": "Nama produk",
                              "Kuantitas": "Jumlah dan satuan (contoh: 4 Kg / 2 Pcs)",
                              "Harga Satuan": 12500,
                              "Total Harga": 50000
                            }
                          ]
                        }
                        Pastikan Harga Satuan dan Total Harga berupa angka bulat (integer/float) tanpa titik atau simbol mata uang.
                        """
                        
                        success_count = 0
                        for uploaded_file in uploaded_files:
                            try:
                                image = Image.open(uploaded_file)
                                response = model.generate_content([image, prompt])
                                data = json.loads(response.text)
                                
                                vendor = data.get("nama_vendor") or "-"
                                no_struk = data.get("no_struk") or "-"
                                tanggal = data.get("tanggal") or "-"
                                
                                for item in data.get("items", []):
                                    harga_satuan = pd.to_numeric(item.get("Harga Satuan", 0), errors="coerce") or 0
                                    total_harga = pd.to_numeric(item.get("Total Harga", 0), errors="coerce") or 0
                                    
                                    row_item = {
                                        "File Sumber": uploaded_file.name,
                                        "Tanggal": tanggal,
                                        "Nama Vendor": vendor,
                                        "No. Struk": no_struk,
                                        "Nama Barang": item.get("Nama Barang", "-"),
                                        "Kuantitas": item.get("Kuantitas", "1"),
                                        "Harga Satuan": int(harga_satuan),
                                        "Total Harga": int(total_harga)
                                    }
                                    st.session_state["itemized_data"].append(row_item)
                                success_count += 1
                            except Exception as e:
                                st.warning(f"Gagal memproses file {uploaded_file.name}: {str(e)}")
                        
                        if success_count > 0:
                            st.success(f"✨ Berhasil mengekstrak {success_count} dokumen secara presisi!")
                    except Exception as ex:
                        st.error(f"Gagal terhubung ke layanan AI: {str(ex)}")

    # Tampilan Tabel Hasil & Ekspor
    if len(st.session_state["itemized_data"]) > 0:
        st.markdown("---")
        st.subheader("📊 Hasil Rekapitulasi & Validasi Data")
        
        df_preview = pd.DataFrame(st.session_state["itemized_data"])
        
        st.info("💡 Klik sel mana saja pada tabel di bawah untuk melakukan koreksi manual sebelum diunduh.")
        
        edited_df = st.data_editor(
            df_preview,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Harga Satuan": st.column_config.NumberColumn("Harga Satuan (Rp)", format="Rp %d"),
                "Total Harga": st.column_config.NumberColumn("Total Harga (Rp)", format="Rp %d")
            }
        )
        
        # Metrik Ringkasan Profesional
        total_items = len(edited_df)
        total_vendors = edited_df["Nama Vendor"].nunique() if not edited_df.empty else 0
        grand_total = pd.to_numeric(edited_df["Total Harga"], errors="coerce").fillna(0).sum() if not edited_df.empty else 0

        m1, m2, m3 = st.columns(3)
        m1.metric(label="Total Item Terbaca", value=f"{total_items} Item")
        m2.metric(label="Total Vendor / Toko", value=f"{total_vendors} Vendor")
        m3.metric(label="Total Nilai Transaksi", value=f"Rp {int(grand_total):,}".replace(",", "."))
        
        st.markdown("---")
        st.subheader("📥 Ekspor Laporan Keuangan")
        
        col_dl1, col_dl2, col_reset = st.columns([1, 1, 2])
        
        with col_dl1:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='Rekapitulasi Belanja')
            excel_data = output.getvalue()
            
            st.download_button(
                label="📊 Unduh Format Excel (.xlsx)",
                data=excel_data,
                file_name=f"laporan_rekap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        with col_dl2:
            csv_data = edited_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Unduh Format CSV (.csv)",
                data=csv_data,
                file_name=f"laporan_rekap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_reset:
            if st.button("🗑️ Bersihkan Semua Sesi Data", use_container_width=True):
                st.session_state["itemized_data"] = []
                st.rerun()

# -------------------------------------------------------------
# HALAMAN 2: RIWAYAT & PANDUAN
# -------------------------------------------------------------
elif app_mode == "📚 Riwayat & Panduan":
    st.markdown('<p class="main-header">📚 Panduan & Dokumentasi Pengguna</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Pelajari cara memaksimalkan akurasi pemindaian dokumen dan integrasi data.</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    with st.container(border=True):
        st.subheader("🎯 Tips Mendapatkan Hasil Akurat 99%")
        st.markdown("""
        * **Pencahayaan Cukup:** Hindari bayangan tangan atau benda menutupi teks penting pada struk.
        * **Fokus Kamera:** Pastikan angka total dan rincian item tidak buram (*blurry*).
        * **Format Dukungan:** Sistem mendukung gambar beresolusi tinggi (PNG, JPG, JPEG) hasil foto kamera ponsel maupun tangkapan layar digital (*e-receipt*).
        """)
        
    with st.container(border=True):
        st.subheader("🔒 Keamanan & Privasi Data Korporat")
        st.markdown("""
        * Data transaksi Anda diproses secara aman menggunakan enkripsi standar industri.
        * File gambar yang diunggah tidak digunakan untuk melatih model publik tanpa izin.
        """)

# -------------------------------------------------------------
# HALAMAN 3: KELOLA LANGGANAN (Monetisasi SaaS)
# -------------------------------------------------------------
elif app_mode == "💳 Kelola Langganan":
    st.markdown('<p class="main-header">💳 Paket & Langganan Layanan</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Pilih skema berlangganan yang sesuai dengan skala bisnis atau perusahaan Anda.</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    col_plan1, col_plan2, col_plan3 = st.columns(3)
    
    with col_plan1:
        with st.container(border=True):
            st.markdown("### 🥉 Starter Plan")
            st.markdown("#### **Rp 99.000** / bulan")
            st.caption("Cocok untuk UMKM dan pencatatan pribadi.")
            st.markdown("---")
            st.markdown("✅ 150 Struk / bulan\n✅ Ekspor Excel & CSV\n✅ Support Standar")
            st.markdown("")
            st.button("Pilih Paket Starter", use_container_width=True, key="p1")
            
    with col_plan2:
        with st.container(border=True):
            st.markdown("### 🥈 Business Pro")
            st.markdown("#### **Rp 249.000** / bulan")
            st.caption("Solusi optimal untuk toko retail & agensi.")
            st.markdown("---")
            st.markdown("⭐ **Terlaris**\n✅ 600 Struk / bulan\n✅ Multi-user / Tim\n✅ Prioritas Pemrosesan AI")
            st.markdown("")
            st.button("Pilih Paket Pro", type="primary", use_container_width=True, key="p2")
            
    with col_plan3:
        with st.container(border=True):
            st.markdown("### 🥇 Enterprise")
            st.markdown("#### **Rp 599.000** / bulan")
            st.caption("Untuk kebutuhan korporat skala besar.")
            st.markdown("---")
            st.markdown("✅ **Unlimited** Struk\n✅ Custom API Integration\n✅ Dedicated Account Manager")
            st.markdown("")
            st.button("Hubungi Sales", use_container_width=True, key="p3")
