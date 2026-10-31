from datetime import datetime
import io
import json
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image
import google.generativeai as genai

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

if "itemized_data" not in st.session_state:
    st.session_state["itemized_data"] = []

if "trial_count" not in st.session_state:
    st.session_state["trial_count"] = 0

if "cs_messages" not in st.session_state:
    st.session_state["cs_messages"] = [
        {"role": "assistant", "content": "Halo! Ada yang bisa saya bantu seputar BizReceipt AI atau pembayaran via QRIS?"}
    ]

MAX_TRIAL = 10
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

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


def process_batch_files(uploaded_files, api_key):
    if st.session_state["trial_count"] >= MAX_TRIAL:
        st.error("🚫 Kuota 10x trial gratis telah habis. Silakan buka menu Kelola Langganan & QRIS.")
        return
    if not api_key:
        st.error("⚠️ API Key belum dikonfigurasi di Secrets.")
        return

    success_count = 0
    for u_file in uploaded_files:
        if st.session_state["trial_count"] >= MAX_TRIAL:
            st.warning("⚠️ Batas kuota trial tercapai.")
            break
        try:
            new_rows = parse_single_file(u_file, api_key)
            st.session_state["itemized_data"].extend(new_rows)
            st.session_state["trial_count"] += 1
            success_count += 1
        except Exception as e:
            st.warning(f"Gagal memproses {u_file.name}: {e}")

    if success_count > 0:
        sisa_now = MAX_TRIAL - st.session_state["trial_count"]
        st.success(f"✨ Berhasil mengekstrak {success_count} dokumen! Sisa trial: {sisa_now} kali.")


def get_cs_reply(user_query, api_key):
    if not api_key:
        return "Maaf, API Key belum dikonfigurasi di Secrets."
    try:
        full_p = f"{SYS_CTX_CS}\n\nUser: {user_query}"
        resp = call_gemini_api(api_key, full_p, is_json=False)
        return resp.text
    except Exception as e:
        return f"Maaf, kendala koneksi CS AI: {e}"


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


# Sidebar Navigasi
st.sidebar.markdown("### 🏢 BizReceipt AI")
st.sidebar.caption("Solusi Ekstraksi Dokumen Finansial Otomatis")
st.sidebar.markdown("---")

sisa_trial = max(0, MAX_TRIAL - st.session_state["trial_count"])
st.sidebar.markdown("#### Status Akun Anda")
if sisa_trial > 0:
    st.sidebar.info(f"✨ **Mode Trial Aktif**\n\nSisa Kuota Gratis: **{sisa_trial} dari {MAX_TRIAL} dokumen**")
else:
    st.sidebar.warning("⚠️ **Kuota Trial Habis!**\n\nSilakan bayar via QRIS untuk memperpanjang akses.")

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

    sisa = max(0, MAX_TRIAL - st.session_state["trial_count"])
    col_info.info(
        f"💡 **Info Trial & Kualitas**\n\n"
        f"🎁 Sisa Gratis: **{sisa} kali**\n"
        "1. Foto struk harus terang & jelas.\n"
        "2. Mendukung struk cetak & tulisan tangan.\n"
        "3. Edit hasil langsung di tabel sebelum unduh."
    )

    if uploaded_files:
        if st.button("🚀 Proses Dokumen", type="primary"):
            with st.spinner("🤖 AI sedang memindai dokumen..."):
                process_batch_files(uploaded_files, GEMINI_API_KEY)

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
        st.write("Sudah transfer via QRIS? Klik tombol di bawah untuk mengirim bukti pembayaran ke Telegram Admin.")
        tg_user = "MasterGenerative_bot"
        tg_msg = "Halo Admin, saya sudah bayar langganan BizReceipt AI via QRIS."
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
                reply = get_cs_reply(user_query, GEMINI_API_KEY)
                st.markdown(reply)
                st.session_state["cs_messages"].append({"role": "assistant", "content": reply})
