from datetime import datetime
import io
import json
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image
import google.generativeai as genai

# Konfigurasi Halaman
st.set_page_config(
    page_title="BizReceipt AI | Invoice Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Kustomisasi CSS
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
}
.main-header {
    font-size: 2.6rem !important;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0.2rem;
    line-height: 1.2;
}
.sub-header {
    font-size: 1.1rem;
    color: #475569;
    margin-bottom: 1.8rem;
}
div.stContainer {
    border-radius: 12px;
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
}
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
    border: none;
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
    welcome_msg = (
        "Halo! Ada yang bisa saya bantu seputar "
        "penggunaan BizReceipt AI atau cara pembayaran via QRIS?"
    )
    st.session_state["cs_messages"] = [
        {"role": "assistant", "content": welcome_msg}
    ]

MAX_TRIAL = 10
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)


# Fungsi Pemanggilan Gemini 3.8 Flash dengan Fallback
def generate_with_fallback(api_key, contents, is_json=False):
    genai.configure(api_key=api_key)
    candidates = [
        "models/gemini-3.8-flash",
        "gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest"
    ]
    try:
        for m in genai.list_models():
            methods = m.supported_generation_methods
            if "generateContent" in methods:
                if (
                    m.name not in candidates
                    and "1.5" not in m.name
                    and "2.5" not in m.name
                ):
                    candidates.append(m.name)
    except Exception:
        pass

    cfg = {"response_mime_type": "application/json"} if is_json else None
    last_err = None

    for model_name in candidates:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=cfg
            )
            return model.generate_content(contents)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if (
                "404" in msg
                or "not found" in msg
                or "no longer available" in msg
            ):
                continue
            raise e
    raise last_err


# Sidebar Navigasi
with st.sidebar:
    st.markdown("### 🏢 BizReceipt AI")
    st.caption("Solusi Ekstraksi Dokumen Finansial Otomatis")
    st.markdown("---")

    sisa_trial = max(0, MAX_TRIAL - st.session_state["trial_count"])
    st.markdown("#### Status Akun Anda")
    if sisa_trial > 0:
        msg_trial = (
            f"✨ **Mode Trial Aktif**\n\n"
            f"Sisa Kuota Gratis: **{sisa_trial} dari {MAX_TRIAL} dokumen**"
        )
        st.info(msg_trial)
    else:
        msg_habis = (
            "⚠️ **Kuota Trial Habis!**\n\n"
            "Silakan bayar via QRIS untuk memperpanjang akses."
        )
        st.warning(msg_habis)

    st.markdown("---")
    st.markdown("#### Navigasi Menu")
    menu_options = [
        "🚀 Parser Utama",
        "📚 Riwayat & Panduan",
        "💳 Kelola Langganan & QRIS",
        "💬 Tanya CS AI"
    ]
    app_mode = st.radio(
        "Pilih Menu",
        menu_options,
        label_visibility="collapsed"
    )
    st.markdown("---")
    st.caption("© 2026 BizReceipt Intelligence.")

# Halaman 1: Parser Utama
if app_mode == "🚀 Parser Utama":
    st.markdown(
        '<p class="main-header">💼 AI Receipt & Invoice Intelligence</p>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<p class="sub-header">'
        'Ubah struk, nota, atau faktur menjadi laporan tabel '
        'akuntansi terstruktur secara instan.'
        '</p>',
        unsafe_allow_html=True
    )

    col_upload, col_info = st.columns([2, 1], gap="large")

    with col_upload:
        with st.container(border=True):
            st.subheader("📤 Unggah Dokumen Transaksi")
            st.caption("Mendukung multi-file (Format: PNG, JPG, JPEG)")
            uploaded_files = st.file_uploader(
                "Seret & letakkan file foto di sini",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
                label_visibility="collapsed"
            )

    with col_info:
        with st.container(border=True):
            st.subheader("💡 Informasi Trial & Kualitas")
            sisa = max(0, MAX_TRIAL - st.session_state["trial_count"])
            panduan_teks = (
                f"🎁 **Uji Coba Gratis:** Sisa **{sisa} kali** proses.\n\n"
                "1. **Kejelasan:** Pastikan foto struk terang & jelas.\n"
                "2. **Fleksibel:** Bisa baca struk cetak & tulisan tangan.\n"
                "3. **Audit Data:** Edit langsung di tabel sebelum unduh."
            )
            st.markdown(panduan_teks)

    if uploaded_files:
        st.markdown("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            process_btn = st.button(
                "🚀 Proses Dokumen",
                type="primary",
                use_container_width=True
            )

        if process_btn:
            if st.session_state["trial_count"] >= MAX_TRIAL:
                st.error(
                    "🚫 Kuota 10x trial gratis telah habis. "
                    "Silakan buka menu Kelola Langganan & QRIS."
                )
            elif not GEMINI_API_KEY:
                st.error("⚠️ API Key belum dikonfigurasi di Secrets.")
            else:
                with st.spinner("🤖 AI sedang memindai dokumen..."):
                    try:
                        prompt = """
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
                        Harga Satuan dan Total Harga wajib angka bulat.
                        """
                        success_count = 0
                        for u_file in uploaded_files:
                            if st.session_state["trial_count"] >= MAX_TRIAL:
                                st.warning("⚠️ Batas kuota trial tercapai.")
                                break
                            try:
                                img = Image.open(u_file)
                                resp = generate_with_fallback(
                                    GEMINI_API_KEY,
                                    [img, prompt],
                                    is_json=True
                                )
                                raw = resp.text.strip()
                                raw = raw.removeprefix("```json")
                                raw = raw.removesuffix("```").strip()
                                data = json.loads(raw)

                                vendor = data.get("nama_vendor") or "-"
                                no_struk = data.get("no_struk") or "-"
                                tgl = data.get("tanggal") or "-"

                                for item in data.get("items", []):
                                    hs = pd.to_numeric(
                                        item.get("Harga Satuan", 0),
                                        errors="coerce"
                                    ) or 0
                                    th = pd.to_numeric(
                                        item.get("Total Harga", 0),
                                        errors="coerce"
                                    ) or 0

                                    row_item = {
                                        "File Sumber": u_file.name,
                                        "Tanggal": tgl,
                                        "Nama Vendor": vendor,
                                        "No. Struk": no_struk,
                                        "Nama Barang": item.get("Nama Barang", "-"),
                                        "Kuantitas": item.get("Kuantitas", "1"),
                                        "Harga Satuan": int(hs),
                                        "Total Harga": int(th)
                                    }
                                    st.session_state["itemized_data"].append(row_item)

                                st.session_state["trial_count"] += 1
                                success_count += 1
                            except Exception as e:
                                st.warning(f"Gagal memproses {u_file.name}: {e}")

                        if success_count > 0:
                            sisa_now = MAX_TRIAL - st.session_state["trial_count"]
                            st.success(
                                f"✨ Berhasil mengekstrak {success_count} dokumen! "
                                f"Sisa trial: {sisa_now} kali."
                            )
                    except Exception as ex:
                        st.error(f"Gagal terhubung ke AI: {ex}")

    if len(st.session_state["itemized_data"]) > 0:
        st.markdown("---")
        st.subheader("📊 Hasil Rekapitulasi & Validasi Data")

        df_preview = pd.DataFrame(st.session_state["itemized_data"])
        st.info("💡 Klik sel tabel di bawah untuk mengedit data sebelum diunduh.")

        edited_df = st.data_editor(
            df_preview,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Harga Satuan": st.column_config.NumberColumn(
                    "Harga Satuan (Rp)", format="Rp %d"
                ),
                "Total Harga": st.column_config.NumberColumn(
                    "Total Harga (Rp)", format="Rp %d"
                )
            }
        )

        total_items = len(edited_df)
        total_vendors = edited_df["Nama Vendor"].nunique() if not edited_df.empty else 0
        grand_total = (
            pd.to_numeric(edited_df["Total Harga"], errors="coerce")
            .fillna(0)
            .sum()
            if not edited_df.empty else 0
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Item Terbaca", f"{total_items} Item")
        m2.metric("Total Vendor / Toko", f"{total_vendors} Vendor")
        fmt_total = f"Rp {int(grand_total):,}".replace(",", ".")
        m3.metric("Total Nilai Transaksi", fmt_total)

        st.markdown("---")
        st.subheader("📥 Ekspor Laporan Keuangan")

        col_dl1, col_dl2, col_reset = st.columns([1, 1, 2])
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        with col_dl1:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                edited_df.to_excel(
                    writer, index=False, sheet_name="Rekapitulasi"
                )
            st.download_button(
                label="📊 Unduh Excel (.xlsx)",
                data=output.getvalue(),
                file_name=f"laporan_rekap_{now_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with col_dl2:
            csv_data = edited_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📄 Unduh CSV (.csv)",
                data=csv_data,
                file_name=f"laporan_rekap_{now_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_reset:
            if st.button("🗑️ Bersihkan Data", use_container_width=True):
                st.session_state["itemized_data"] = []
                st.rerun()

# Halaman 2: Riwayat & Panduan
elif app_mode == "📚 Riwayat & Panduan":
    st.markdown(
        '<p class="main-header">📚 Panduan & Dokumentasi</p>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    with st.container(border=True):
        st.subheader("🎯 Tips Akurasi 99%")
        st.markdown(
            "* **Pencahayaan Cukup:** Hindari bayangan pada struk.\n"
            "* **Fokus Kamera:** Pastikan angka tidak buram.\n"
            "* **Format:** Mendukung PNG, JPG, dan JPEG."
        )

# Halaman 3: Kelola Langganan & QRIS
elif app_mode == "💳 Kelola Langganan & QRIS":
    st.markdown(
        '<p class="main-header">💳 Paket Langganan & QRIS</p>',
        unsafe_allow_html=True
    )
    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("### 🥉 Starter Plan")
            st.markdown("#### **Rp 99.000** / bln")
            st.markdown("✅ 150 Struk / bulan\n\n✅ Ekspor Excel & CSV")
    with c2:
        with st.container(border=True):
            st.markdown("### 🥈 Business Pro")
            st.markdown("#### **Rp 249.000** / bln")
            st.markdown("⭐ **Terlaris**\n\n✅ 600 Struk / bulan\n\n✅ Prioritas AI")
    with c3:
        with st.container(border=True):
            st.markdown("### 🥇 Enterprise")
            st.markdown("#### **Rp 599.000** / bln")
            st.markdown("✅ **Unlimited** Struk\n\n✅ Custom Integrasi")

    st.markdown("---")
    with st.container(border=True):
        st.subheader("📲 Pembayaran via QRIS GoPay Merchant")
        col_q1, col_q2 = st.columns([1, 1], gap="large")
        with col_q1:
            st.info("📌 **Scan QRIS Resmi Kami**")
            try:
                st.image("qris.png.jpeg", use_container_width=True)
            except Exception:
                try:
                    st.image("qris.png", use_container_width=True)
                except Exception:
                    st.warning("⚠️ Gambar QRIS belum ditemukan di GitHub.")

        with col_q2:
            st.markdown("### 💬 Konfirmasi Pembayaran")
            st.write(
                "Sudah transfer via QRIS? Klik tombol di bawah untuk "
                "mengirimkan bukti pembayaran ke Telegram Admin."
            )
            tg_user = "MasterGenerative_bot"
            tg_msg = "Halo Admin, saya sudah bayar langganan BizReceipt AI via QRIS."
            enc_msg = urllib.parse.quote(tg_msg)
            tg_url = f"https://t.me/{tg_user}?text={enc_msg}"
            st.link_button(
                "✈️ Konfirmasi via Telegram",
                url=tg_url,
                type="primary",
                use_container_width=True
            )

# Halaman 4: Tanya CS AI
elif app_mode == "💬 Tanya CS AI":
    st.markdown(
        '<p class="main-header">💬 Pusat Bantuan & CS AI</p>',
        unsafe_allow_html=True
    )
    st.markdown("---")

    for message in st.session_state["cs_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_query = st.chat_input("Tanyakan cara pakai atau cara bayar...")
    if user_query:
        st.session_state["cs_messages"].append(
            {"role": "user", "content": user_query}
        )
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Asisten CS sedang mengetik..."):
                try:
