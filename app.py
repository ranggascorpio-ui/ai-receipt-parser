from datetime import datetime
import io
import json
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image
import google.generativeai as genai
from supabase import create_client

# Konfigurasi Halaman
st.set_page_config(
    page_title="BizReceipt AI | Invoice Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

CSS_STYLE = """
<style>
.stApp { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); }
.main-header { font-size: 2.5rem !important; font-weight: 800; color: #0f172a; margin-bottom: 0.2rem; }
.sub-header { font-size: 1.05rem; color: #475569; margin-bottom: 1.5rem; }
div.stContainer { border-radius: 12px; background-color: #ffffff; border: 1px solid #e2e8f0; }
.stButton > button { border-radius: 8px; font-weight: 600; }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); border: none; }
section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
</style>
"""
st.markdown(CSS_STYLE, unsafe_allow_html=True)

# Inisialisasi Kredensial & Supabase Client
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", None)
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", None)

@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

supabase = init_supabase()

# Inisialisasi Session State untuk Login & Data
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_email" not in st.session_state:
    st.session_state["user_email"] = ""
if "user_tier" not in st.session_state:
    st.session_state["user_tier"] = "trial"
if "quota_left" not in st.session_state:
    st.session_state["quota_left"] = 10
if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []
if "cs_messages" not in st.session_state:
    st.session_state["cs_messages"] = [
        {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu seputar BizReceipt AI atau pembayaran via QRIS?"}
    ]

PROMPT_RECEIPT = """
Ekstrak data struk ini ke format JSON murni:
{
  "nama_vendor": "Nama toko",
  "no_struk": "Nomor struk",
  "tanggal": "YYYY-MM-DD",
  "items": [
    {
      "Nama Barang": "Nama produk",
      "Kuantitas": "1 Pcs",
      "Harga Satuan": 10000,
      "Total Harga": 10000
    }
  ]
}
Harga Satuan dan Total Harga wajib berupa angka bulat.
"""

SYS_CTX_CS = (
    "Anda adalah CS Virtual aplikasi 'BizReceipt AI' (platform ekstraksi struk belanja ke Excel/CSV).\n"
    "- Trial gratis: 10x proses.\n"
    "- Paket Starter: Rp 99.000/bln (150 struk).\n"
    "- Paket Business Pro: Rp 249.000/bln (600 struk).\n"
    "- Paket Enterprise: Rp 599.000/bln (Unlimited).\n"
    "- Cara Bayar: Buka menu 'Kelola Langganan & QRIS', scan QRIS GoPay Merchant, "
    "lalu klik tombol Konfirmasi via Telegram.\n"
    "Jawab dengan ramah, sopan, dan ringkas."
)

# --- FUNGSI DATABASE & AUTH ---
def fetch_user_data(email):
    if not supabase:
        return None
    try:
        res = supabase.table("users").select("*").eq("email", email).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None

def update_user_quota_in_db(email, new_quota):
    if not supabase:
        return
    try:
        supabase.table("users").update({"quota_left": new_quota}).eq("email", email).execute()
    except Exception:
        pass

# --- FUNGSI PEMANGGILAN AI ---
def call_gemini_api(api_key, contents, is_json=False):
    genai.configure(api_key=api_key)
    candidates = [
        "models/gemini-3.8-flash",
        "gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest"
    ]
    try:
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                if m.name not in candidates and "1.5" not in m.name and "2.5" not in m.name:
                    candidates.append(m.name)
    except Exception:
        pass

    cfg = {"response_mime_type": "application/json"} if is_json else None
    last_err = None

    for model_name in candidates:
        try:
            model = genai.GenerativeModel(model_name=model_name, generation_config=cfg)
            return model.generate_content(contents)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "404" in msg or "not found" in msg or "no longer available" in msg:
                continue
            raise e
    raise last_err

def parse_single_file(u_file, api_key):
    img = Image.open(u_file)
    resp = call_gemini_api(api_key, [img, PROMPT_RECEIPT], is_json=True)
    raw = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
    data = json.loads(raw)
    vendor = data.get("nama_vendor") or "-"
    no_struk = data.get("no_struk") or "-"
    tgl = data.get("tanggal") or "-"
    rows = []
    for item in data.get("items", []):
        hs = pd.to_numeric(item.get("Harga Satuan", 0), errors="coerce") or 0
        th = pd.to_numeric(item.get("Total Harga", 0), errors="coerce") or 0
        rows.append({
            "File Sumber": u_file.name,
            "Tanggal": tgl,
            "Nama Vendor": vendor,
            "No. Struk": no_struk,
            "Nama Barang": item.get("Nama Barang", "-"),
            "Kuantitas": item.get("Kuantitas", "1"),
            "Harga Satuan": int(hs),
            "Total Harga": int(th)
        })
    return rows

def show_qris_image():
    try:
        st.image("qris.png.jpeg", use_container_width=True)
        return
    except Exception:
        pass
    try:
        st.image("qris.png", use_container_width=True)
        return
    except Exception:
        st.warning("⚠️ Gambar QRIS belum ditemukan di GitHub.")

# --- HALAMAN AUTENTIKASI (JIKA BELUM LOGIN) ---
if not st.session_state["logged_in"]:
    st.markdown('<p class="main-header">💼 BizReceipt AI | Portal Akun</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Silakan masuk atau daftar akun untuk mulai menggunakan kecerdasan buatan ekstraksi struk.</p>', unsafe_allow_html=True)
    
    tab_login, tab_register = st.tabs(["🔑 Masuk (Login)", "📝 Daftar Akun Baru (Register)"])
    
    with tab_login:
        st.subheader("Masuk ke Akun Anda")
        with st.form("login_form"):
            email_in = st.text_input("Email")
            pass_in = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Masuk", type="primary")
            
            if submit_login:
                if not email_in or not pass_in:
                    st.error("Email dan Password wajib diisi.")
                elif not supabase:
                    st.error("Koneksi Database Supabase belum dikonfigurasi di Secrets.")
                else:
                    try:
                        # Cek auth supabase
                        auth_res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                        if auth_res.user:
                            user_data = fetch_user_data(email_in)
                            if user_data:
                                st.session_state["logged_in"] = True
                                st.session_state["user_email"] = email_in
                                st.session_state["user_tier"] = user_data.get("tier", "trial")
                                st.session_state["quota_left"] = user_data.get("quota_left", 10)
                                st.success("Login berhasil!")
                                st.rerun()
                            else:
                                st.error("Data profil pengguna tidak ditemukan di database.")
                    except Exception as e:
                        st.error(f"Login gagal: Periksa kembali email dan password Anda. ({e})")

    with tab_register:
        st.subheader("Daftar Akun Baru (Bonus 10x Kuota Trial)")
        with st.form("register_form"):
            email_reg = st.text_input("Email Aktif")
            pass_reg = st.text_input("Buat Password", type="password")
            submit_reg = st.form_submit_button("Daftar Sekarang", type="primary")
            
            if submit_reg:
                if not email_reg or not pass_reg:
                    st.error("Email dan Password wajib diisi.")
                elif not supabase:
                    st.error("Koneksi Database Supabase belum dikonfigurasi di Secrets.")
                else:
                    try:
                        # Buat akun di Supabase Auth
                        auth_res = supabase.auth.sign_up({"email": email_reg, "password": pass_reg})
                        if auth_res.user:
                            # Masukkan ke tabel public.users
                            supabase.table("users").insert({
                                "email": email_reg,
                                "tier": "trial",
                                "quota_left": 10
                            }).execute()
                            st.success("Pendaftaran berhasil! Silakan pindah ke tab 'Masuk (Login)' untuk masuk.")
                    except Exception as e:
                        st.error(f"Pendaftaran gagal (Email mungkin sudah terdaftar): {e}")
    st.stop()

# --- SETELAH LOGIN BERHASIL ---
# Sinkronisasi sisa kuota terbaru dari database
db_profile = fetch_user_data(st.session_state["user_email"])
if db_profile:
    st.session_state["quota_left"] = db_profile.get("quota_left", 0)
    st.session_state["user_tier"] = db_profile.get("tier", "trial")

# Sidebar Navigasi & Profil
st.sidebar.markdown("### 🏢 BizReceipt AI")
st.sidebar.caption(f"Akun: **{st.session_state['user_email']}**")
st.sidebar.markdown("---")

sisa_kuota = st.session_state["quota_left"]
st.sidebar.markdown("#### Status Akun Anda")
st.sidebar.info(f"✨ **Paket: {st.session_state['user_tier'].upper()}**\n\nSisa Kuota: **{sisa_kuota} dokumen**")

if st.sidebar.button("🚪 Keluar (Logout)", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = ""
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("#### Navigasi Menu")
app_mode = st.sidebar.radio(
    "Pilih Menu",
    ["🚀 Parser Utama", "📚 Riwayat & Panduan", "💳 Kelola Langganan & QRIS", "💬 Tanya CS AI"],
    label_visibility="collapsed"
)
st.sidebar.markdown("---")
st.sidebar.caption("© 2026 BizReceipt Intelligence.")

# Halaman 1: Parser Utama
if app_mode == "🚀 Parser Utama":
    st.markdown('<p class="main-header">💼 AI Receipt & Invoice Intelligence</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Ubah struk, nota, atau faktur menjadi laporan tabel akuntansi terstruktur secara instan.</p>', unsafe_allow_html=True)

    col_upload, col_info = st.columns([2, 1], gap="large")
    uploaded_files = col_upload.file_uploader(
        "📤 Unggah Dokumen Transaksi (PNG, JPG, JPEG)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    col_info.info(
        f"💡 **Info Kuota & Kualitas**\n\n"
        f"🎁 Sisa Kuota Anda: **{st.session_state['quota_left']} kali**\n"
        "1. Foto struk harus terang & jelas.\n"
        "2. Mendukung struk cetak & tulisan tangan.\n"
        "3. Edit hasil langsung di tabel sebelum unduh."
    )

    if uploaded_files:
        if st.button("🚀 Proses Dokumen", type="primary"):
            if st.session_state["quota_left"] <= 0:
                st.error("🚫 Kuota Anda telah habis. Silakan lakukan perpanjangan paket di menu **Kelola Langganan & QRIS**.")
            elif not GEMINI_API_KEY:
                st.error("⚠️ API Key belum dikonfigurasi di Secrets.")
            else:
                with st.spinner("🤖 AI sedang memindai dokumen..."):
                    success_count = 0
                    for u_file in uploaded_files:
                        if st.session_state["quota_left"] <= 0:
                            st.warning("⚠️ Batas kuota Anda tercapai di tengah proses.")
                            break
                        try:
                            new_rows = parse_single_file(u_file, GEMINI_API_KEY)
                            st.session_state["itemized_data"].extend(new_rows)
                            
                            # Kurangi kuota di database Supabase
                            st.session_state["quota_left"] -= 1
                            update_user_quota_in_db(st.session_state["user_email"], st.session_state["quota_left"])
                            
                            success_count += 1
                        except Exception as e:
                            st.warning(f"Gagal memproses {u_file.name}: {e}")

                    if success_count > 0:
                        st.success(f"✨ Berhasil mengekstrak {success_count} dokumen! Sisa kuota Anda: {st.session_state['quota_left']} kali.")

    if len(st.session_state["itemized_data"]) > 0:
        st.markdown("---")
        st.subheader("📊 Hasil Rekapitulasi & Validasi Data")
        df_preview = pd.DataFrame(st.session_state["itemized_data"])

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
        m1.metric("Total Item Terbaca", f"{total_items} Item")
        m2.metric("Total Vendor / Toko", f"{total_vendors} Vendor")
        m3.metric("Total Nilai Transaksi", f"Rp {int(grand_total):,}".replace(",", "."))

        st.markdown("---")
        col_dl1, col_dl2, col_reset = st.columns([1, 1, 2])
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Rekapitulasi")

        col_dl1.download_button(
            label="📊 Unduh Excel (.xlsx)",
            data=output.getvalue(),
            file_name=f"laporan_rekap_{now_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        csv_data = edited_df.to_csv(index=False).encode("utf-8")
        col_dl2.download_button(
            label="📄 Unduh CSV (.csv)",
            data=csv_data,
            file_name=f"laporan_rekap_{now_str}.csv",
            mime="text/csv",
            use_container_width=True
        )

        if col_reset.button("🗑️ Bersihkan Data", use_container_width=True):
            st.session_state["itemized_data"] = []
            st.rerun()

# Halaman 2: Riwayat & Panduan
elif app_mode == "📚 Riwayat & Panduan":
    st.markdown('<p class="main-header">📚 Panduan & Dokumentasi</p>', unsafe_allow_html=True)
    st.markdown("---")
    st.info(
        "🎯 **Tips Akurasi 99%**\n\n"
        "* **Pencahayaan Cukup:** Hindari bayangan pada struk.\n"
        "* **Fokus Kamera:** Pastikan angka tidak buram.\n"
        "* **Format:** Mendukung PNG, JPG, dan JPEG."
    )

# Halaman 3: Kelola Langganan & QRIS
elif app_mode == "💳 Kelola Langganan & QRIS":
    st.markdown('<p class="main-header">💳 Paket Langganan & QRIS</p>', unsafe_allow_html=True)
    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    c1.info("### 🥉 Starter Plan\n#### **Rp 99.000** / bln\n* ✅ 150 Struk / bulan\n* ✅ Ekspor Excel & CSV")
    c2.success("### 🥈 Business Pro\n#### **Rp 249.000** / bln\n* ⭐ **Terlaris**\n* ✅ 600 Struk / bulan\n* ✅ Prioritas AI")
    c3.warning("### 🥇 Enterprise\n#### **Rp 599.000** / bln\n* ✅ **Unlimited** Struk\n* ✅ Custom Integrasi")

    st.markdown("---")
    st.subheader("📲 Pembayaran via QRIS GoPay Merchant")
    col_q1, col_q2 = st.columns([1, 1], gap="large")

    with col_q1:
        st.info("📌 **Scan QRIS Resmi Kami**")
        show_qris_image()

    with col_q2:
        st.markdown("### 💬 Konfirmasi Pembayaran")
        st.write("Sudah transfer via QRIS? Klik tombol di bawah untuk mengirim bukti pembayaran ke Telegram Admin beserta email akun Anda.")
        tg_user = "MasterGenerative_bot"
        tg_msg = f"Halo Admin, saya sudah bayar langganan BizReceipt AI via QRIS. Email akun saya: {st.session_state['user_email']}"
        tg_url = f"https://t.me/{tg_user}?text={urllib.parse.quote(tg_msg)}"
        st.link_button("✈️ Konfirmasi via Telegram", url=tg_url, type="primary", use_container_width=True)

# Halaman 4: Tanya CS AI
elif app_mode == "💬 Tanya CS AI":
    st.markdown('<p class="main-header">💬 Pusat Bantuan & CS AI</p>', unsafe_allow_html=True)
    st.markdown("---")

    for message in st.session_state["cs_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_query = st.chat_input("Tanyakan cara pakai atau cara bayar...")
    if user_query:
        st.session_state["cs_messages"].append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Asisten CS sedang mengetik..."):
                try:
                    if not GEMINI_API_KEY:
                        reply = "Maaf, API Key belum dikonfigurasi."
                    else:
                        sys_ctx = (
                            f"Anda adalah CS Virtual aplikasi 'BizReceipt AI'. "
                            f"Email user saat ini: {st.session_state['user_email']}.\n"
                            "- Trial gratis: 10x proses.\n"
                            "- Paket Starter: Rp 99.000/bln (150 struk).\n"
                            "- Paket Business Pro: Rp 249.000/bln (600 struk).\n"
                            "- Paket Enterprise: Rp 599.000/bln (Unlimited).\n"
                            "- Cara Bayar: Buka menu 'Kelola Langganan & QRIS', scan QRIS GoPay Merchant, "
                            "lalu klik tombol Konfirmasi via Telegram dengan menyertakan email akun.\n"
                            "Jawab dengan ramah, sopan, dan ringkas."
                        )
                        full_p = f"{sys_ctx}\n\nUser: {user_query}"
                        resp = call_gemini_api(GEMINI_API_KEY, full_p, is_json=False)
                        reply = resp.text
                except Exception as e:
                    reply = f"Maaf, kendala koneksi CS AI: {e}"

                st.markdown(reply)
                st.session_state["cs_messages"].append({"role": "assistant", "content": reply})
