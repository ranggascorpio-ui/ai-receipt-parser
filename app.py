"""
Aplikasi Web AI Struk & Faktur Parser (Versi Enterprise / Profesional)
Framework: Streamlit
File: app.py
"""

from datetime import datetime
import io
import json
import pandas as pd
import streamlit as st
import openpyxl
from PIL import Image
import google.generativeai as genai

# ==============================================================================
# KONFIGURASI API KEY AMAN (MENGGUNAKAN STREAMLIT SECRETS)
# ==============================================================================
# Baris ini mengambil API Key secara aman dari sistem cloud Streamlit (bukan ditulis mentah)
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="SaaS AI Struk & Faktur Parser",
    page_icon="💼",
    layout="wide"
)

# Kustomisasi CSS untuk Tampilan Lebih Profesional
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stDownloadButton>button {
        background-color: #0d6efd;
        color: white;
        border-radius: 6px;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# Header Utama Aplikasi
st.title("💼 AI Receipt & Invoice Intelligence Platform")
st.markdown(
    "Unggah dokumen struk atau nota belanja Anda. Sistem cerdas kami akan mengekstrak "
    "seluruh rincian transaksi, kuantitas, dan harga secara otomatis ke dalam format laporan siap unduh."
)
st.markdown("---")

# Inisialisasi Session State untuk Menyimpan Data
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

# Layout Kolom: Area Unggah & Panel Informasi
col_upload, col_info = st.columns([2, 1], gap="large")

with col_upload:
    st.subheader("📤 Unggah Dokumen")
    uploaded_files = st.file_uploader(
        "Seret & letakkan foto struk / nota (Mendukung banyak file sekaligus)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True,
        help="Format yang didukung: PNG, JPG, JPEG"
    )

with col_info:
    st.subheader("💡 Panduan Singkat")
    st.markdown(
        "- Pastikan foto struk / bon terbaca jelas.\n"
        "- Mendukung ketikan komputer maupun **tulisan tangan**.\n"
        "- Data dapat langsung diedit di tabel sebelum diunduh."
    )

# Proses Ekstraksi Ketika Tombol Ditekan
if uploaded_files:
    st.markdown("---")
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        process_btn = st.button("🚀 Proses Data", type="primary", use_container_width=True)
    
    if process_btn:
        with st.spinner("🤖 AI sedang memindai rincian dan item belanja dari dokumen..."):
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-3.8-flash')
                
                success_count = 0
                for uploaded_file in uploaded_files:
                    try:
                        image = Image.open(uploaded_file)
                        
                        prompt = """
                        Ekstrak data dari struk atau bon ini menjadi format JSON murni dengan struktur persis berikut:
                        {
                          "nama_vendor": "Nama toko",
                          "no_struk": "Nomor struk",
                          "tanggal": "YYYY-MM-DD",
                          "items": [
                            {
                              "Nama Barang": "Nama produk",
                              "Kuantitas": "Jumlah dan satuan (contoh: 4.000 Kg / 8.000 Pcs / 2 Lbr)",
                              "Harga Satuan": 12500,
                              "Total Harga": 50000000
                            }
                          ]
                        }
                        Pastikan hanya mengembalikan format JSON valid tanpa teks pengantar atau markdown tambahan lainnya.
                        """
                        
                        response = model.generate_content([image, prompt])
                        clean_text = response.text.strip().replace("```json", "").replace("```", "")
                        data = json.loads(clean_text)
                        
                        vendor = data.get("nama_vendor", "-")
                        no_struk = data.get("no_struk", "-")
                        tanggal = data.get("tanggal", "-")
                        
                        for item in data.get("items", []):
                            row_item = {
                                "File Sumber": uploaded_file.name,
                                "Tanggal": tanggal,
                                "Nama Vendor": vendor,
                                "No. Struk": no_struk,
                                "Nama Barang": item.get("Nama Barang"),
                                "Kuantitas": item.get("Kuantitas"),
                                "Harga Satuan": item.get("Harga Satuan"),
                                "Total Harga": item.get("Total Harga")
                            }
                            st.session_state["itemized_data"].append(row_item)
                        success_count += 1
                    except Exception as e:
                        st.warning(f"Gagal memproses file {uploaded_file.name}: {str(e)}")
                
                if success_count > 0:
                    st.success(f"✨ Berhasil mengekstrak {success_count} dokumen secara presisi!")
            except Exception as ex:
                st.error(f"Gagal terhubung ke layanan AI: {str(ex)}")

# Tampilan Hasil Rekapitulasi & Tabel Interaktif
if len(st.session_state["itemized_data"]) > 0:
    st.markdown("---")
    st.subheader("📊 Hasil Rekapitulasi & Validasi Data")
    
    df_preview = pd.DataFrame(st.session_state["itemized_data"])
    total_items = len(df_preview)
    total_vendors = df_preview["Nama Vendor"].nunique()
    
    m1, m2 = st.columns(2)
    m1.metric(label="Total Item Barang Terbaca", value=f"{total_items} Item")
    m2.metric(label="Jumlah Toko / Vendor", value=f"{total_vendors} Vendor")
    
    st.markdown("")
    st.caption("💡 *Anda dapat langsung mengedit sel tabel di bawah ini jika ada data yang perlu dikoreksi.*")
    
    edited_df = st.data_editor(df_preview, num_rows="dynamic", use_container_width=True)
    
    st.markdown("---")
    st.subheader("📥 Ekspor Laporan")
    
    col_dl1, col_dl2, col_reset = st.columns([1, 1, 2])
    
    with col_dl1:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='Rekapitulasi Belanja')
        excel_data = output.getvalue()
        
        st.download_button(
            label="📊 Unduh Excel (.xlsx)",
            data=excel_data,
            file_name=f"laporan_rekap_belanja_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
    with col_dl2:
        csv_data = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Unduh CSV (.csv)",
            data=csv_data,
            file_name=f"laporan_rekap_belanja_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col_reset:
        if st.button("🗑️ Kosongkan Data / Mulai Baru", use_container_width=True):
            st.session_state["itemized_data"] = []
            st.rerun()