"""
Aplikasi Web AI Struk & Faktur Parser (Versi SaaS Enterprise Modern)
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

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="AI Receipt & Invoice Intelligence",
    page_icon="💼",
    layout="wide"
)

# Kustomisasi CSS Tambahan untuk Estetika SaaS Modern
st.markdown("""
    <style>
    .main-header {
        font-size: 2.25rem;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #4b5563;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# Header Utama
st.markdown('<p class="main-header">💼 AI Receipt & Invoice Intelligence Platform</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Ubah dokumen struk, nota, atau bon belanja fisik/digital menjadi laporan tabel terstruktur secara instan menggunakan kecerdasan buatan.</p>', unsafe_allow_html=True)
st.markdown("---")

# Mengambil API Key secara aman dari Streamlit Secrets atau Input Sidebar
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

if not GEMINI_API_KEY:
    with st.sidebar:
        st.header("🔑 Konfigurasi API")
        GEMINI_API_KEY = st.text_input("Masukkan Gemini API Key:", type="password")
        st.caption("Untuk produksi, simpan API Key di `.streamlit/secrets.toml`.")

# Inisialisasi Session State
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

# Layout Kolom dengan Kontainer Profesional
col_upload, col_info = st.columns([2, 1], gap="large")

with col_upload:
    with st.container(border=True):
        st.subheader("📤 Unggah Dokumen Transaksi")
        st.caption("Mendukung banyak file sekaligus (Format: PNG, JPG, JPEG)")
        
        uploaded_files = st.file_uploader(
            "Seret & letakkan file foto di sini", 
            type=["png", "jpg", "jpeg"], 
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

with col_info:
    with st.container(border=True):
        st.subheader("💡 Panduan Penggunaan")
        st.markdown(
            "1. **Unggah Foto:** Pastikan foto struk atau bon terlihat jelas.\n"
            "2. **Dukungan Teks:** Bisa membaca cetakan printer maupun **tulisan tangan**.\n"
            "3. **Validasi:** Anda dapat langsung mengedit hasil tabel sebelum diunduh."
        )

# Tombol Proses & Logika AI
if uploaded_files:
    st.markdown("")
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        process_btn = st.button("🚀 Proses Dokumen", type="primary", use_container_width=True)
    
    if process_btn:
        if not GEMINI_API_KEY:
            st.error("⚠️ Gemini API Key belum dikonfigurasi. Silakan masukkan di Sidebar atau menu Secrets.")
        else:
            with st.spinner("🤖 AI sedang memindai rincian transaksi dan item belanja..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    # Menggunakan response_mime_type agar output dijamin berupa JSON valid
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
    
    st.info("💡 Anda dapat langsung mengedit sel data pada tabel di bawah ini jika ada koreksi nilai.")
    
    edited_df = st.data_editor(
        df_preview,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Harga Satuan": st.column_config.NumberColumn("Harga Satuan (Rp)", format="Rp %d"),
            "Total Harga": st.column_config.NumberColumn("Total Harga (Rp)", format="Rp %d")
        }
    )
    
    # sinkronisasi hasil edit ke metrik
    total_items = len(edited_df)
    total_vendors = edited_df["Nama Vendor"].nunique() if not edited_df.empty else 0
    grand_total = pd.to_numeric(edited_df["Total Harga"], errors="coerce").fillna(0).sum() if not edited_df.empty else 0

    # Metrik Ringkasan
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Item Terbaca", value=f"{total_items} Item")
    m2.metric(label="Total Vendor / Toko", value=f"{total_vendors} Vendor")
    m3.metric(label="Total Nilai Transaksi", value=f"Rp {int(grand_total):,}".replace(",", "."))
    
    st.markdown("---")
    st.subheader("📥 Unduh Laporan")
    
    col_dl1, col_dl2, col_reset = st.columns([1, 1, 2])
    
    with col_dl1:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='Rekapitulasi Belanja')
        excel_data = output.getvalue()
        
        st.download_button(
            label="📊 Unduh Excel (.xlsx)",
            data=excel_data,
            file_name=f"laporan_rekap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
    with col_dl2:
        csv_data = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Unduh CSV (.csv)",
            data=csv_data,
            file_name=f"laporan_rekap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col_reset:
        if st.button("🗑️ Kosongkan Data", use_container_width=True):
            st.session_state["itemized_data"] = []
            st.rerun()
