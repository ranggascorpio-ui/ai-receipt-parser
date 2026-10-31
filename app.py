"""
Aplikasi Web AI Struk & Faktur Parser (Versi SaaS Enterprise Komersial + Trial + AI CS + QRIS & Telegram)
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

# Kustomisasi CSS Tingkat Lanjut (Header Besar & Estetika SaaS)
st.markdown("""
    <style>
    /* Latar belakang modern */
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    }
    
    /* Header Utama */
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

# Inisialisasi Session State
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

if "trial_count" not in st.session_state:
    st.session_state["trial_count"] = 0  # Mulai dari 0 penggunaan

if "cs_messages" not in st.session_state:
    st.session_state["cs_messages"] = [
        {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu seputar penggunaan BizReceipt AI atau cara pembayaran berlangganan via QRIS?"}
    ]

MAX_TRIAL = 10  # Batas maksimal uji coba gratis

# Mengambil API Key secara aman dari Streamlit Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

# -------------------------------------------------------------
# SIDEBAR: Navigasi, Status Trial, & AI CS Bot Pintar
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏢 BizReceipt AI")
    st.caption("Solusi Ekstraksi Dokumen Finansial Otomatis")
    st.markdown("---")
    
    # Widget Status Kuota Trial
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
    
    st.markdown("---")
    st.markdown("<p style='font-size: 0.8rem; color: #94a3b8;'>© 2026 BizReceipt Intelligence. All rights reserved.</p>", unsafe_allow_html=True)

# -------------------------------------------------------------
# HALAMAN 1: PARSER UTAMA
# -------------------------------------------------------------
if app_mode == "🚀 Parser Utama":
    st.markdown('<p class="main-header">💼 AI Receipt & Invoice Intelligence</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Ubah dokumen struk, nota, atau faktur fisik/digital menjadi laporan tabel akuntansi terstruktur secara instan menggunakan kecerdasan buatan.</p>', unsafe_allow_html=True)
    st.markdown("")

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
            st.subheader("💡 Informasi Trial & Kualitas")
            st.markdown(
                f"🎁 **Uji Coba Gratis:** Anda memiliki sisa **{max(0, MAX_TRIAL - st.session_state['trial_count'])} kali** pemrosesan gratis.\n\n"
                "1. **Kejelasan:** Pastikan foto struk terang & tidak blur.\n"
                "2. **Fleksibel:** Mendukung cetakan termal POS & **tulisan tangan**.\n"
                "3. **Audit Data:** Validasi ulang langsung di tabel sebelum diekspor."
            )

    if uploaded_files:
        st.markdown("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            process_btn = st.button("🚀 Proses Dokumen", type="primary", use_container_width=True)
        
        if process_btn:
            if st.session_state["trial_count"] >= MAX_TRIAL:
                st.error("🚫 Maaf, jatah 10x uji coba gratis Anda telah habis. Silakan lakukan pembayaran paket di menu **Kelola Langganan & QRIS**.")
            elif not GEMINI_API_KEY:
                st.error("⚠️ Sistem API Key belum terkonfigurasi di server.")
            else:
                with st.spinner("🤖 AI sedang memindai rincian transaksi, pajak, dan item belanja..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        # Menggunakan gemini-1.5-flash yang kompatibel dan cepat
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
                            if st.session_state["trial_count"] >= MAX_TRIAL:
                                st.warning("⚠️ Batas kuota trial tercapai di tengah proses.")
                                break

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
                                
                                st.session_state["trial_count"] += 1
                                success_count += 1
                            except Exception as e:
                                st.warning(f"Gagal memproses file {uploaded_file.name}: {str(e)}")
                        
                        if success_count > 0:
                            st.success(f"✨ Berhasil mengekstrak {success_count} dokumen! Sisa kuota trial: {MAX_TRIAL - st.session_state['trial_count']} kali.")
                    except Exception as ex:
                        st.error(f"Gagal terhubung ke layanan AI: {str(ex)}")

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
        * **Fokus Kamera:** Pastikan angka total dan rincian item tidak blur.
        * **Format Dukungan:** Sistem mendukung gambar beresolusi tinggi (PNG, JPG, JPEG).
        """)
        
    with st.container(border=True):
        st.subheader("🔒 Keamanan & Privasi Data Korporat")
        st.markdown("""
        * Data transaksi Anda diproses secara aman menggunakan enkripsi standar industri.
        * File gambar yang diunggah tidak digunakan untuk melatih model publik tanpa izin.
        """)

# -------------------------------------------------------------
# HALAMAN 3: KELOLA LANGGANAN & PEMBAYARAN QRIS
# -------------------------------------------------------------
elif app_mode == "💳 Kelola Langganan & QRIS":
    st.markdown('<p class="main-header">💳 Paket Berlangganan & Pembayaran QRIS</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Pilih paket layanan Anda, lakukan pembayaran via QRIS GoPay Merchant, dan konfirmasikan secara instan via Telegram.</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    col_plan1, col_plan2, col_plan3 = st.columns(3)
    
    with col_plan1:
        with st.container(border=True):
            st.markdown("### 🥉 Starter Plan")
            st.markdown("#### **Rp 99.000** / bulan")
            st.caption("Cocok untuk UMKM dan pencatatan pribadi.")
            st.markdown("---")
            st.markdown("✅ 150 Struk / bulan\n✅ Ekspor Excel & CSV\n✅ Support Standar")
            
    with col_plan2:
        with st.container(border=True):
            st.markdown("### 🥈 Business Pro")
            st.markdown("#### **Rp 249.000** / bulan")
            st.caption("Solusi optimal untuk toko retail & agensi.")
            st.markdown("---")
            st.markdown("⭐ **Terlaris**\n✅ 600 Struk / bulan\n✅ Multi-user / Tim\n✅ Prioritas Pemrosesan AI")
            
    with col_plan3:
        with st.container(border=True):
            st.markdown("### 🥇 Enterprise")
            st.markdown("#### **Rp 599.000** / bulan")
            st.caption("Untuk kebutuhan korporat skala besar.")
            st.markdown("---")
            st.markdown("✅ **Unlimited** Struk\n✅ Custom API Integration\n✅ Dedicated Account Manager")

    st.markdown("---")
    
    # Bagian Instruksi Pembayaran QRIS GoPay Merchant & Telegram
    with st.container(border=True):
        st.subheader("📲 Cara Pembayaran via QRIS (GoPay Merchant)")
        st.markdown("""
        1. Pilih paket langganan yang Anda inginkan di atas (Starter, Pro, atau Enterprise).
        2. Buka aplikasi M-Banking (BCA, Mandiri, BSI, BRI, dll) atau E-Wallet (GoPay, OVO, DANA, ShopeePay) Anda.
        3. Scan QRIS resmi merchant kami di bawah ini, atau transfer sesuai nominal paket.
        4. Setelah transfer berhasil, klik tombol konfirmasi di bawah untuk mengirimkan bukti transfer via Telegram admin.
        """)
        
        col_qris1, col_qris2 = st.columns([1, 1], gap="large")
        with col_qris1:
            st.info("📌 **QRIS Resmi BizReceipt AI / GoPay Merchant**")
            try:
                # Menggunakan qris.png.jpeg sesuai file unggahan Anda
                st.image("qris.png.jpeg", caption="Scan pakai aplikasi apa saja (BCA, Livin, GoPay, OVO, DANA, dll)", use_container_width=True)
            except Exception:
                st.warning("⚠️ File gambar QRIS belum ditemukan. Pastikan file terunggah dengan benar.")
                
        with col_qris2:
            st.markdown("### 💬 Konfirmasi Pembayaran Instan")
            st.markdown("Sudah melakukan pembayaran? Klik tombol di bawah untuk mengirimkan bukti transfer (*screenshot*) beserta username akun Anda ke Telegram admin.")
            
            telegram_username = "UsernameTelegramAnda" 
            tg_message = "Halo Admin, saya sudah melakukan pembayaran berlangganan BizReceipt AI via QRIS. Berikut bukti transfernya:"
            encoded_msg = urllib.parse.quote(tg_message)
            tg_link = f"https://t.me/{telegram_username}?text={encoded_msg}"
            
            st.markdown(f"""
                <a href="{tg_link}" target="_blank">
                    <button style="background-color: #0088cc; color: white; padding: 12px 20px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%;">
                        ✈️ Konfirmasi Pembayaran via Telegram
                    </button>
                </a>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------
# HALAMAN 4: TANYA CS AI (Asisten Virtual Pintar)
# -------------------------------------------------------------
elif app_mode == "💬 Tanya CS AI":
    st.markdown('<p class="main-header">💬 Pusat Bantuan & CS AI</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Tanyakan apa saja seputar cara penggunaan aplikasi, kendala scan, atau info paket berlangganan kepada asisten virtual kami.</p>', unsafe_allow_html=True)
    st.markdown("---")

    for message in st.session_state["cs_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Ketik pertanyaan Anda di sini... (Contoh: Bagaimana cara bayar via QRIS?)"):
        st.session_state["cs_messages"].append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Asisten CS sedang mengetik..."):
                try:
                    if not GEMINI_API_KEY:
                        reply = "Maaf, sistem API Key belum terkonfigurasi dengan benar."
                    else:
                        genai.configure(api_key=GEMINI_API_KEY)
                        # Menggunakan gemini-1.5-flash untuk CS Bot
                        cs_model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        system_context = """
                        Anda adalah Customer Service Virtual yang ramah, profesional, dan membantu untuk aplikasi SaaS bernama 'BizReceipt AI'. 
                        Aplikasi ini adalah platform berbasis AI untuk mengekstrak struk dan faktur belanja menjadi laporan Excel/CSV.
                        Informasi Layanan & Harga:
                        - Ada mode trial gratis 10x pemrosesan.
                        - Paket Starter: Rp 99.000/bulan (150 struk).
                        - Paket Business Pro: Rp 249.000/bulan (600 struk).
                        - Paket Enterprise: Rp 599.000/bulan (Unlimited).
                        - Pembayaran via QRIS GoPay Merchant yang tertera di menu Kelola Langganan & QRIS, lalu konfirmasi pembayaran via Telegram admin.
                        Jawablah dengan bahasa Indonesia yang sopan, ramah, dan membantu.
                        """
                        
                        full_prompt = f"{system_context}\n\nPertanyaan Pengguna: {user_query}"
                        response = cs_model.generate_content(full_prompt)
                        reply = response.text
                except Exception as e:
                    reply = f"Maaf, terjadi kendala saat menghubungkan ke layanan CS AI: {str(e)}"

                st.markdown(reply)
                st.session_state["cs_messages"].append({"role": "assistant", "content": reply})
