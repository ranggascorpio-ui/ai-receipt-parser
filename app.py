from datetime import datetime
import io
import json
import urllib.parse
import urllib.request
import pandas as pd
import streamlit as st
from PIL import Image
import google.generativeai as genai
from supabase import create_client

# Konfigurasi Tampilan
st.set_page_config(
    page_title="BizReceipt AI | Enterprise Edition",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stApp { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); }
.main-header { font-size: 2.2rem !important; font-weight: 800; color: #0f172a; margin-bottom: 0.2rem; }
.sub-header { font-size: 1rem; color: #475569; margin-bottom: 1.2rem; }
div.stContainer { border-radius: 12px; background-color: #ffffff; border: 1px solid #e2e8f0; }
.stButton > button { border-radius: 8px; font-weight: 600; }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); border: none; }
section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# Kredensial Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", None)
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", None)
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", None)
TELEGRAM_ADMIN_CHAT_ID = st.secrets.get("TELEGRAM_ADMIN_CHAT_ID", None)

@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

supabase = init_supabase()

def notify_admin_error(error_msg, context=""):
    """Mengirim pesan error monitoring ke HP via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        return
    try:
        user_info = st.session_state.get("user_email", "Belum Login")
        pesan = (
            f"🚨 *BIZRECEIPT AI - ERROR ALERT*\n"
            f"• *Konteks:* {context}\n"
            f"• *Akun:* `{user_info}`\n"
            f"• *Error:* `{error_msg}`"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_ADMIN_CHAT_ID,
            "text": pesan,
            "parse_mode": "Markdown"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

# Inisialisasi State
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
        {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu seputar pemakaian fitur, multi-valuta, PPN, LPJ, atau pembayaran?"}
    ]

# Prompt Mutakhir: Kategori + Pajak + Deteksi Mata Uang & Konversi Kurs IDR
PROMPT_RECEIPT = """
Ekstrak data struk ini ke format JSON murni:
{
  "nama_vendor": "Nama toko/vendor",
  "no_struk": "Nomor struk/nota",
  "tanggal": "YYYY-MM-DD",
  "mata_uang": "IDR / USD / SGD / EUR / MYR / lainnya",
  "kurs_ke_idr": 1,
  "total_ppn_struk_idr": 0,
  "items": [
    {
      "Nama Barang": "Nama produk",
      "Kategori": "Pilih salah satu: Konsumsi / Transportasi / ATK & Operasional / Bahan Baku / Lainnya",
      "Kuantitas": "1 Pcs",
      "Harga Satuan Asli": 10.0,
      "Total Harga Asli": 10.0,
      "Total Harga IDR": 160000
    }
  ]
}

Aturan Ketat Konversi & Ekstraksi:
1. Deteksi simbol atau kode mata uang pada struk ($, S$, SGD, USD, RM, €, Rp).
2. Jika mata uang adalah IDR: set "mata_uang": "IDR", "kurs_ke_idr": 1.
3. Jika mata uang ASING (misal USD, SGD, MYR, EUR):
   - Isi "mata_uang" dengan kodenya (misal: "USD").
   - Tentukan estimasi kurs wajar ke IDR di "kurs_ke_idr" (misal: USD ~ 16000, SGD ~ 12000, EUR ~ 17500, MYR ~ 3600).
   - "Total Harga IDR" wajib hasil perkalian dari (Total Harga Asli * kurs_ke_idr) dibulatkan ke integer.
4. Jika struk mencantumkan pajak (PPN/PB1/Tax/GST), konversikan nominal total pajaknya ke IDR dan catat di "total_ppn_struk_idr".
5. Kelompokkan tiap barang ke salah satu dari 5 kategori yang tersedia.
"""

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

def call_gemini_api(api_key, contents, is_json=False):
    genai.configure(api_key=api_key)
    
    # Daftar model khusus Vision / Gambar yang stabil & mendukung dokumen
    candidates = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro"
    ]
    
    try:
        for m in genai.list_models():
            clean_name = m.name.replace("models/", "")
            # Hanya ambil model yang mendukung gambar, tolak model audio / TTS / embedding
            if (
                "generateContent" in m.supported_generation_methods
                and clean_name not in candidates
                and "flash" in clean_name.lower()
                and "tts" not in clean_name.lower()
                and "audio" not in clean_name.lower()
                and "embed" not in clean_name.lower()
            ):
                candidates.append(clean_name)
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
            # Abaikan model jika: kuota habis (429), model tidak ditemukan (404), atau tidak dukung gambar (modality error)
            skip_triggers = [
                "404", "not found", "no longer available",
                "429", "quota", "resource_exhausted", "exceeded",
                "modality", "image input", "not enabled"
            ]
            if any(term in msg for term in skip_triggers):
                continue
            raise e
            
    raise last_err
    for model_name in candidates:
        try:
            model = genai.GenerativeModel(model_name=model_name, generation_config=cfg)
            return model.generate_content(contents)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            # Jika model 404 (tidak ada) ATAU 429 (kuota harian habis), otomatis coba model alternatif berikutnya
            if any(term in msg for term in ["404", "not found", "no longer available", "429", "quota", "resource_exhausted", "exceeded"]):
                continue
            raise e
    raise last_err

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

def parse_single_file(u_file, api_key, label_klien_proyek):
    img = Image.open(u_file)
    resp = call_gemini_api(api_key, [img, PROMPT_RECEIPT], is_json=True)
    
    if not resp or not hasattr(resp, "text") or not resp.text:
        raise ValueError("AI tidak dapat membaca teks pada gambar ini.")
        
    raw = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
    data = json.loads(raw)

    # Antisipasi jika AI mengembalikan list langsung
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    elif not isinstance(data, dict):
        data = {}
try:
                            rows = parse_single_file(u_file, GEMINI_API_KEY, project_name)
                            if rows and isinstance(rows, list):
                                st.session_state["itemized_data"].extend(rows)
                                st.session_state["quota_left"] -= 1
                                update_user_quota_in_db(st.session_state["user_email"], st.session_state["quota_left"])
                                success_count += 1
                        except Exception as e:
                            notify_admin_error(str(e), context=f"Scan: {u_file.name}")
                            st.warning(f"Gagal memproses {u_file.name}: {e}")
                            
    vendor = data.get("nama_vendor") or "-"
    no_struk = data.get("no_struk") or "-"
    tgl = data.get("tanggal") or "-"
    mata_uang = str(data.get("mata_uang") or "IDR").upper()
    kurs = pd.to_numeric(data.get("kurs_ke_idr", 1), errors="coerce") or 1
    total_ppn_idr = pd.to_numeric(data.get("total_ppn_struk_idr", 0), errors="coerce") or 0
    
    # Amankan pengambilan items jika bernilai None atau bukan list
    items = data.get("items")
    if not items or not isinstance(items, list):
        # Fallback otomatis untuk struk tanpa rincian item (struk parkir, bensin, dll.)
        items = [{
            "Nama Barang": "Transaksi Nota / Umum",
            "Kategori": "Operasional",
            "Kuantitas": "1",
            "Total Harga Asli": data.get("total_harga_asli", 0) or 0,
            "Total Harga IDR": data.get("total_harga_idr", 0) or 0
        }]

    num_items = len(items) if len(items) > 0 else 1
    rows = []
    
    for item in items:
        if not isinstance(item, dict):
            continue
            
        tot_asli = pd.to_numeric(item.get("Total Harga Asli", 0), errors="coerce") or 0
        tot_idr = pd.to_numeric(item.get("Total Harga IDR", 0), errors="coerce")
        if pd.isna(tot_idr) or tot_idr == 0:
            tot_idr = int(round(tot_asli * kurs))

        kategori = item.get("Kategori") or "Lainnya"
        item_ppn_idr = int(round(total_ppn_idr / num_items)) if total_ppn_idr > 0 else 0
        dpp_idr = max(0, int(tot_idr) - item_ppn_idr) if item_ppn_idr > 0 else int(tot_idr)

        rows.append({
            "File Sumber": u_file.name,
            "Klien / Proyek": label_klien_proyek,
            "Tanggal": tgl,
            "Nama Vendor": vendor,
            "No. Struk": no_struk,
            "Kategori": kategori,
            "Nama Barang": item.get("Nama Barang", "-"),
            "Kuantitas": str(item.get("Kuantitas", "1")),
            "Valuta": mata_uang,
            "Nominal Asli": float(tot_asli),
            "Kurs (IDR)": int(kurs),
            "DPP (IDR)": int(dpp_idr),
            "PPN (IDR)": int(item_ppn_idr),
            "Total (IDR)": int(tot_idr),
            "Status Klaim": "Pending"
        })
        
    return rows
    for item in items:
        tot_asli = pd.to_numeric(item.get("Total Harga Asli", 0), errors="coerce") or 0
        tot_idr = pd.to_numeric(item.get("Total Harga IDR", 0), errors="coerce")
        if pd.isna(tot_idr) or tot_idr == 0:
            tot_idr = int(round(tot_asli * kurs))

        kategori = item.get("Kategori") or "Lainnya"
        item_ppn_idr = int(round(total_ppn_idr / num_items)) if total_ppn_idr > 0 else 0
        dpp_idr = max(0, int(tot_idr) - item_ppn_idr) if item_ppn_idr > 0 else int(tot_idr)

        rows.append({
            "File Sumber": u_file.name,
            "Klien / Proyek": label_klien_proyek,
            "Tanggal": tgl,
            "Nama Vendor": vendor,
            "No. Struk": no_struk,
            "Kategori": kategori,
            "Nama Barang": item.get("Nama Barang", "-"),
            "Kuantitas": item.get("Kuantitas", "1"),
            "Valuta": mata_uang,
            "Nominal Asli": float(tot_asli),
            "Kurs (IDR)": int(kurs),
            "DPP (IDR)": int(dpp_idr),
            "PPN (IDR)": int(item_ppn_idr),
            "Total (IDR)": int(tot_idr),
            "Status Klaim": "Pending"
        })
    return rows

def show_qris_image():
    for f in ["qris.png.jpeg", "qris.png"]:
        try:
            st.image(f, use_container_width=True)
            return
        except Exception:
            continue
    st.warning("⚠️ File QRIS belum terpasang.")

# --- GERBANG AUTENTIKASI ---
if not st.session_state["logged_in"]:
    st.markdown('<p class="main-header">💼 BizReceipt AI | Portal Akses</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Platform Manajemen Struk Multi-Valuta, Pajak, dan Reimbursement.</p>', unsafe_allow_html=True)
    
    tab_login, tab_register = st.tabs(["🔑 Masuk (Login)", "📝 Daftar Akun Baru (Register)"])
    
    with tab_login:
        st.subheader("Masuk ke Akun")
        with st.form("login_form"):
            email_in = st.text_input("Email")
            pass_in = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Masuk", type="primary")
            if submit_login:
                if not email_in or not pass_in:
                    st.error("Email dan Password wajib diisi.")
                elif not supabase:
                    st.error("Koneksi Supabase belum aktif.")
                else:
                    try:
                        auth_res = supabase.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                        if auth_res.user:
                            user_data = fetch_user_data(email_in)
                            st.session_state["logged_in"] = True
                            st.session_state["user_email"] = email_in
                            st.session_state["user_tier"] = user_data.get("tier", "trial") if user_data else "trial"
                            st.session_state["quota_left"] = user_data.get("quota_left", 10) if user_data else 10
                            st.success("Login berhasil!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Login gagal: {e}")

    with tab_register:
        st.subheader("Daftar Akun Baru (Gratis 10x Kuota)")
        with st.form("register_form"):
            email_reg = st.text_input("Email Aktif")
            pass_reg = st.text_input("Buat Password", type="password")
            submit_reg = st.form_submit_button("Daftar Sekarang", type="primary")
            if submit_reg:
                if not email_reg or not pass_reg:
                    st.error("Email dan Password wajib diisi.")
                elif not supabase:
                    st.error("Koneksi Supabase belum aktif.")
                else:
                    try:
                        auth_res = supabase.auth.sign_up({"email": email_reg, "password": pass_reg})
                        if auth_res.user:
                            supabase.table("users").insert({
                                "email": email_reg,
                                "tier": "trial",
                                "quota_left": 10
                            }).execute()
                            st.success("Pendaftaran berhasil! Silakan langsung login.")
                    except Exception as e:
                        st.error(f"Gagal mendaftar: {e}")
    st.stop()

# Sinkronisasi Kuota
db_profile = fetch_user_data(st.session_state["user_email"])
if db_profile:
    st.session_state["quota_left"] = db_profile.get("quota_left", 0)
    st.session_state["user_tier"] = db_profile.get("tier", "trial")

# Sidebar
st.sidebar.markdown("### 🏢 BizReceipt AI")
st.sidebar.caption(f"Akun: **{st.session_state['user_email']}**")
st.sidebar.markdown("---")
st.sidebar.info(f"✨ **Paket: {st.session_state['user_tier'].upper()}**\n\nSisa Kuota: **{st.session_state['quota_left']} dokumen**")

if st.sidebar.button("🚪 Keluar (Logout)", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = ""
    st.rerun()

st.sidebar.markdown("---")
app_mode = st.sidebar.radio(
    "Menu Navigasi",
    ["🚀 Parser & LPJ Proyek", "📚 Riwayat & Panduan", "💳 Kelola Langganan & QRIS", "💬 Tanya CS AI"],
    label_visibility="collapsed"
)
st.sidebar.caption("© 2026 BizReceipt AI Suite.")

# --- HALAMAN 1: PARSER, VALUTA, PAJAK & LPJ ---
if app_mode == "🚀 Parser & LPJ Proyek":
    st.markdown('<p class="main-header">💼 Ekstraksi Struk, Multi-Valuta & Kas Bon</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Mendukung struk domestik & internasional (USD, SGD, dll.) dengan konversi kurs IDR instan.</p>', unsafe_allow_html=True)

    # Panel Setup Proyek & Kas Bon
    with st.expander("📌 Pengaturan Klien, Proyek & Kas Bon (Klik untuk Buka/Tutup)", expanded=True):
        col_proj, col_bon = st.columns(2)
        project_name = col_proj.text_input(
            "🏷️ Nama Klien / Proyek / Divisi",
            value="Operasional Kantor",
            help="Contoh: Klien PT Abadi, Reimburse Perjalanan Singapore, atau Project Launching"
        )
        kas_bon_awal = col_bon.number_input(
            "💵 Kas Bon / Dana Diterima Lapangan (IDR)",
            min_value=0,
            step=50000,
            value=0,
            help="Nominal dana muka kas bon dalam IDR untuk menghitung sisa lebih/kurang pertanggungjawaban."
        )

    col_up, col_info = st.columns([2, 1], gap="medium")
    uploaded_files = col_up.file_uploader(
        "📤 Unggah Dokumen Transaksi (PNG, JPG, JPEG)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    col_info.info(
        f"🎯 **Status Operasional**\n\n"
        f"• Kuota Aktif: **{st.session_state['quota_left']} kali**\n"
        f"• Konversi Valuta: **Aktif (USD/SGD/EUR $\\rightarrow$ IDR)**\n"
        f"• Deteksi Pajak: **Aktif (PPN/Tax & DPP)**\n"
        f"• Tracking Kas Bon: **{'Aktif' if kas_bon_awal > 0 else 'Nonaktif'}**"
    )

    if uploaded_files:
        if st.button("🚀 Proses Semua Dokumen", type="primary"):
            if st.session_state["quota_left"] <= 0:
                st.error("🚫 Kuota habis. Silakan perpanjang paket di menu Kelola Langganan & QRIS.")
            elif not GEMINI_API_KEY:
                st.error("⚠️ API Key Gemini belum disetel di Secrets.")
            else:
                with st.spinner("🤖 AI sedang membaca teks, mata uang, kurs, dan rincian transaksi..."):
                    success_count = 0
                    for u_file in uploaded_files:
                        if st.session_state["quota_left"] <= 0:
                            st.warning("⚠️ Kuota Anda habis di tengah proses.")
                            break
                        try:
                            rows = parse_single_file(u_file, GEMINI_API_KEY, project_name)
                            if rows and isinstance(rows, list):
                                st.session_state["itemized_data"].extend(rows)
                                st.session_state["quota_left"] -= 1
                                update_user_quota_in_db(st.session_state["user_email"], st.session_state["quota_left"])
                                success_count += 1
                        except Exception as e:
                            notify_admin_error(str(e), context=f"Scan: {u_file.name}")
                            st.warning(f"Gagal memproses {u_file.name}: {e}")

                    if success_count > 0:
                        st.success(f"✨ Selesai memproses {success_count} struk! Sisa kuota: {st.session_state['quota_left']}.")
    # Tabel Rekapitulasi & Kalkulator Kas Bon
    if len(st.session_state["itemized_data"]) > 0:
        st.markdown("---")
        st.subheader("📊 Tabel Rekapitulasi Finansial & Valuta")

        df = pd.DataFrame(st.session_state["itemized_data"])

        # Editor Interaktif
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Kategori": st.column_config.SelectboxColumn(
                    "Kategori Biaya",
                    options=["Konsumsi", "Transportasi", "ATK & Operasional", "Bahan Baku", "Lainnya"],
                    required=True
                ),
                "Status Klaim": st.column_config.SelectboxColumn(
                    "Status Klaim",
                    options=["Pending", "Disetujui", "Sudah Cair"],
                    required=True
                ),
                "Valuta": st.column_config.TextColumn("Mata Uang", width="small"),
                "Nominal Asli": st.column_config.NumberColumn("Nominal Asli", format="%.2f"),
                "Kurs (IDR)": st.column_config.NumberColumn("Kurs (Rp)", format="Rp %d"),
                "DPP (IDR)": st.column_config.NumberColumn("DPP Netto (Rp)", format="Rp %d"),
                "PPN (IDR)": st.column_config.NumberColumn("PPN / Tax (Rp)", format="Rp %d"),
                "Total (IDR)": st.column_config.NumberColumn("Total Transaksi (IDR)", format="Rp %d"),
            }
        )

        # Metrik Finansial
        total_items = len(edited_df)
        grand_total_idr = pd.to_numeric(edited_df["Total (IDR)"], errors="coerce").fillna(0).sum() if not edited_df.empty else 0
        total_ppn_idr_sum = pd.to_numeric(edited_df["PPN (IDR)"], errors="coerce").fillna(0).sum() if not edited_df.empty else 0
        total_dpp_idr_sum = pd.to_numeric(edited_df["DPP (IDR)"], errors="coerce").fillna(0).sum() if not edited_df.empty else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Item", f"{total_items} Item")
        m2.metric("Total DPP Netto", f"Rp {int(total_dpp_idr_sum):,}".replace(",", "."))
        m3.metric("Total Pajak / PPN", f"Rp {int(total_ppn_idr_sum):,}".replace(",", "."))
        m4.metric("Total Belanja (IDR)", f"Rp {int(grand_total_idr):,}".replace(",", "."))

        # Panel Rekonsiliasi Kas Bon
        if kas_bon_awal > 0:
            st.markdown("#### ⚖️ Rekonsiliasi Kas Bon / LPJ")
            selisih = kas_bon_awal - grand_total_idr
            c_bon1, c_bon2, c_bon3 = st.columns(3)
            c_bon1.info(f"💵 **Dana Awal Kas Bon:**\n\nRp {int(kas_bon_awal):,}".replace(",", "."))
            c_bon2.warning(f"🧾 **Total Belanja (IDR):**\n\nRp {int(grand_total_idr):,}".replace(",", "."))
            if selisih >= 0:
                c_bon3.success(f"💰 **Sisa Lebih (Kembalikan):**\n\n**Rp {int(selisih):,}**".replace(",", "."))
            else:
                c_bon3.error(f"⚠️ **Nominal Kurang (Reimburse):**\n\n**Rp {int(abs(selisih)):,}**".replace(",", "."))

        # Ekspor File
        st.markdown("---")
        c_dl1, c_dl2, c_del = st.columns([1, 1, 2])
        now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        out_excel = io.BytesIO()
        with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Laporan_Keuangan_IDR")

        c_dl1.download_button(
            label="📊 Unduh Excel Multi-Valuta (.xlsx)",
            data=out_excel.getvalue(),
            file_name=f"laporan_finansial_{now_ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
        c_dl2.download_button(
            label="📄 Unduh CSV (.csv)",
            data=csv_bytes,
            file_name=f"laporan_finansial_{now_ts}.csv",
            mime="text/csv",
            use_container_width=True
        )

        if c_del.button("🗑️ Bersihkan Riwayat Data", use_container_width=True):
            st.session_state["itemized_data"] = []
            st.rerun()

# --- HALAMAN 2: RIWAYAT & PANDUAN ---
elif app_mode == "📚 Riwayat & Panduan":
    st.markdown('<p class="main-header">📚 Panduan Standar Operasional</p>', unsafe_allow_html=True)
    st.markdown("---")
    st.info(
        "💡 **Cara Memaksimalkan Fitur Finansial:**\n\n"
        "1. **Struk Asing (Multi-Currency):** Cukup unggah foto struk dalam valuta apa pun (USD, SGD, dsb.). AI otomatis membaca nominal asli dan mengalikan dengan kurs wajar ke IDR.\n"
        "2. **Administrasi Petty Cash:** Ubah status pada kolom *Status Klaim* menjadi *Disetujui* atau *Sudah Cair* setelah dana ditransfer ke staf.\n"
        "3. **Pencatatan Pajak:** Nilai PPN/GST otomatis dipisahkan dari nilai dasar (DPP) untuk kebutuhan rekonsiliasi akuntansi.\n"
        "4. **LPJ Lapangan:** Masukkan nominal kas bon di bagian atas sebelum mengunggah struk untuk melihat perhitungan sisa dana secara otomatis."
    )

# --- HALAMAN 3: LANGGANAN & QRIS ---
elif app_mode == "💳 Kelola Langganan & QRIS":
    st.markdown('<p class="main-header">💳 Paket Lisensi & QRIS</p>', unsafe_allow_html=True)
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.info("### 🥉 Starter\n#### **Rp 99.000** / bln\n* ✅ 150 Struk\n* ✅ Ekspor Excel & CSV")
    c2.success("### 🥈 Business Pro\n#### **Rp 249.000** / bln\n* ⭐ **Paling Diminati**\n* ✅ 600 Struk\n* ✅ Fitur Valuta Asing, Pajak & LPJ")
    c3.warning("### 🥇 Enterprise\n#### **Rp 599.000** / bln\n* ✅ **Unlimited** Struk\n* ✅ Prioritas Support")

    st.markdown("---")
    st.subheader("📲 Pembayaran QRIS GoPay Merchant")
    q_col1, q_col2 = st.columns([1, 1], gap="large")
    with q_col1:
        st.info("📌 **Scan Kode QRIS**")
        show_qris_image()
    with q_col2:
        st.markdown("### 💬 Konfirmasi Langganan")
        st.write("Setelah melakukan transfer, klik tombol di bawah untuk mengirim bukti transfer ke Telegram Admin.")
        tg_msg = f"Halo Admin, saya sudah transfer via QRIS untuk paket BizReceipt AI. Email: {st.session_state['user_email']}"
        tg_url = f"https://t.me/MasterGenerative_bot?text={urllib.parse.quote(tg_msg)}"
        st.link_button("✈️ Konfirmasi Pembayaran via Telegram", url=tg_url, type="primary", use_container_width=True)

# --- HALAMAN 4: CS VIRTUAL ---
elif app_mode == "💬 Tanya CS AI":
    st.markdown('<p class="main-header">💬 Pusat Layanan Pelanggan</p>', unsafe_allow_html=True)
    st.markdown("---")
    for msg in st.session_state["cs_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    q_user = st.chat_input("Tanyakan seputar fitur, multi-valuta, PPN, LPJ, atau aktivasi paket...")
    if q_user:
        st.session_state["cs_messages"].append({"role": "user", "content": q_user})
        with st.chat_message("user"):
            st.markdown(q_user)

        with st.chat_message("assistant"):
            with st.spinner("Mengetik jawaban..."):
                try:
                    sys_prompt = (
                        f"Anda adalah CS BizReceipt AI untuk user {st.session_state['user_email']}. "
                        "Bantu jawab pertanyaan seputar klaim kas kecil, pembukuan pajak PPN, konversi valuta asing ke IDR, "
                        "LPJ kas bon, dan pembayaran via QRIS ke Telegram @MasterGenerative_bot secara ramah dan ringkas."
                    )
                    full_in = f"{sys_prompt}\n\nPertanyaan: {q_user}"
                    resp = call_gemini_api(GEMINI_API_KEY, full_in, is_json=False)
                    ans = resp.text
                except Exception as e:
                    ans = f"Layanan CS sedang sibuk: {e}"
                st.markdown(ans)
                st.session_state["cs_messages"].append({"role": "assistant", "content": ans})
