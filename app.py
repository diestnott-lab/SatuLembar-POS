import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import plotly.express as px
import hashlib
import json
import os

# --- KONFIGURASI HALAMAN STREAMLIT ---
st.set_page_config(
    page_title="SatuLembar POS",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- FUNGSI KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def init_gsheet_connection():
    """Menghubungkan Python ke Google Sheets menggunakan credentials.json"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Mendukung pembacaan credentials lokal atau dari Streamlit Secrets (untuk cloud)
    if os.path.exists("credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    elif "gcp_service_account" in st.secrets:
        # Untuk deployment cloud aman, bisa simpan JSON di streamlit secrets
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        st.error("File 'credentials.json' tidak ditemukan! Pastikan file berada di folder yang sama dengan app.py.")
        st.stop()
        
    client = gspread.authorize(creds)
    # Ganti dengan nama Google Sheet Anda yang sudah dibagikan ke email robot
    try:
        sheet = client.open("SatuLembar_POS_Database")
        return sheet
    except Exception as e:
        st.error(f"Gagal membuka Google Sheet. Pastikan sheet bernama 'SatuLembar_POS_Database' dan sudah di-share ke email service account. Error: {e}")
        st.stop()

# Membuka koneksi ke database
sh = init_gsheet_connection()

# --- FUNGSI BANTU MEMBACA & MENULIS DATA ---
def get_data(sheet_name):
    worksheet = sh.worksheet(sheet_name)
    data = worksheet.get_all_records()
    if not data:
        # Jika kosong, buat DataFrame kosong sesuai kolom awal
        headers = worksheet.row_values(1)
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(data)

def append_data(sheet_name, row_list):
    worksheet = sh.worksheet(sheet_name)
    worksheet.append_row(row_list)

def update_cell_by_id(sheet_name, id_col_name, id_val, target_col_name, new_val):
    worksheet = sh.worksheet(sheet_name)
    df = get_data(sheet_name)
    # Cari nomor baris (ditambah 2 karena index dataframe mulai 0, dan baris 1 adalah header)
    row_idx = df[df[id_col_name].astype(str) == str(id_val)].index
    if not row_idx.empty:
        col_idx = df.columns.get_loc(target_col_name) + 1
        worksheet.update_cell(int(row_idx[0]) + 2, col_idx, str(new_val))

def delete_row_by_condition(sheet_name, id_col_name, id_val):
    worksheet = sh.worksheet(sheet_name)
    df = get_data(sheet_name)
    row_idx = df[df[id_col_name].astype(str) == str(id_val)].index
    if not row_idx.empty:
        # Hapus baris di Google Sheets (ingat pergeseran baris jika menghapus banyak, di sini satu-satu)
        worksheet.delete_rows(int(row_idx[0]) + 2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- INSTANSIASI STATE GLOBAL ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'discount_selected' not in st.session_state:
    st.session_state.discount_selected = {"nama": "Tidak Ada", "tipe": "Persen", "nilai": 0}

# --- HALAMAN LOGIN ---
def login_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Login SatuLembar POS</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            btn_login = st.form_submit_button("Masuk", use_container_width=True)
            
            if btn_login:
                df_users = get_data("tb_users")
                # Cari user
                user_match = df_users[df_users["Username"] == username]
                if not user_match.empty:
                    saved_pw = str(user_match.iloc[0]["Password"])
                    # Validasi password (bisa teks biasa atau hash, demi kemudahan kita cek dua-duanya)
                    if saved_pw == password or saved_pw == hash_password(password):
                        st.session_state.logged_in = True
                        st.session_state.user_role = user_match.iloc[0]["Role"]
                        st.session_state.username = user_match.iloc[0]["Nama_Lengkap"]
                        st.success(f"Selamat Datang, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Password salah!")
                else:
                    st.error("Username tidak terdaftar!")

# --- HALAMAN KASIR (POS) ---
def cash_register_page():
    st.markdown("### 🛒 Layar Kasir (Point of Sale)")
    
    # Ambil data terbaru dari sheet
    df_produk = get_data("tb_produk")
    df_diskon = get_data("tb_diskon")
    df_diskon_aktif = df_diskon[df_diskon["Status"] == "Aktif"]
    
    # Header Info Toko
    df_toko = get_data("tb_setting_toko")
    nama_toko = df_toko.iloc[0]["Nama_Toko"] if not df_toko.empty else "SatuLembar POS"
    st.caption(f"Toko: {nama_toko} | Kasir: {st.session_state.username} ({st.session_state.user_role})")
    
    col_kiri, col_kanan = st.columns([3, 2])
    
    # --- KOLOM KIRI: PILIH PRODUK ---
    with col_kiri:
        st.subheader("Pilih Menu / Produk")
        
        # Filter & Cari
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            search_query = st.text_input("🔍 Cari nama produk...", value="")
        with col_f2:
            categories = ["Semua"] + list(df_produk["Kategori"].unique())
            category_filter = st.selectbox("Kategori", categories)
            
        # Saring produk
        filtered_df = df_produk.copy()
        if category_filter != "Semua":
            filtered_df = filtered_df[filtered_df["Kategori"] == category_filter]
        if search_query:
            filtered_df = filtered_df[filtered_df["Nama_Produk"].str.contains(search_query, case=False)]
            
        # Menampilkan Grid Produk
        if filtered_df.empty:
            st.warning("Produk tidak ditemukan atau stok kosong.")
        else:
            # Gunakan grid kolom untuk layout produk
            grid_cols = st.columns(3)
            for idx, row in filtered_df.iterrows():
                with grid_cols[idx % 3]:
                    st.markdown(
                        f"""
                        <div style='border:1px solid #ddd; padding:10px; border-radius:5px; margin-bottom:10px; background-color:#f9f9f9;'>
                            <strong>{row['Nama_Produk']}</strong><br>
                            <span style='color:green; font-weight:bold;'>Rp {row['Harga_Jual']:,}</span><br>
                            <small>Stok: {row['Stok_Sistem']}</small>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    
                    # Cek jika stok masih ada
                    if int(row["Stok_Sistem"]) > 0:
                        if st.button(f"Tambah", key=f"add_{row['ID_Produk']}"):
                            # Tambah ke keranjang belanja
                            # Cari apakah barang sudah ada di keranjang
                            found = False
                            for item in st.session_state.cart:
                                if item["id"] == row["ID_Produk"]:
                                    if item["qty"] < int(row["Stok_Sistem"]):
                                        item["qty"] += 1
                                    else:
                                        st.warning("Jumlah pembelian melebihi stok yang tersedia!")
                                    found = True
                                    break
                            if not found:
                                st.session_state.cart.append({
                                    "id": row["ID_Produk"],
                                    "nama": row["Nama_Produk"],
                                    "harga": int(row["Harga_Jual"]),
                                    "hpp": int(row["Harga_Beli"]),
                                    "qty": 1,
                                    "stok_max": int(row["Stok_Sistem"])
                                })
                            st.rerun()
                    else:
                        st.button("Habis", key=f"add_{row['ID_Produk']}", disabled=True)

    # --- KOLOM KANAN: KERANJANG & PEMBAYARAN ---
    with col_kanan:
        st.subheader("🛒 Keranjang Belanja")
        
        # Fitur Table Hold / Recall
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hold_name = st.text_input("Label Meja/Nama", key="hold_label_input", placeholder="Meja 1 / Pak Budi")
            if st.button("📌 Hold Order", use_container_width=True):
                if not st.session_state.cart:
                    st.error("Keranjang kosong!")
                elif not hold_name:
                    st.error("Masukkan label meja/nama dulu!")
                else:
                    # Simpan isi keranjang ke tb_hold
                    # Buat ID Hold unik
                    hold_id = f"HLD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    for item in st.session_state.cart:
                        append_data("tb_hold", [
                            hold_id,
                            hold_name,
                            item["id"],
                            item["qty"],
                            "" # Catatan kosong
                        ])
                    st.session_state.cart = []
                    st.success(f"Order untuk {hold_name} berhasil disimpan sementara!")
                    st.rerun()
                    
        with col_h2:
            df_hold = get_data("tb_hold")
            if not df_hold.empty:
                list_meja = df_hold["Label_Meja"].unique()
                meja_pilihan = st.selectbox("Panggil Hold", ["Pilih Meja..."] + list(list_meja))
                if meja_pilihan != "Pilih Meja...":
                    if st.button("🚀 Buka Order", use_container_width=True):
                        # Ambil barang dari tb_hold
                        items_hold = df_hold[df_hold["Label_Meja"] == meja_pilihan]
                        st.session_state.cart = []
                        # Cari data produk asli untuk melengkapi data keranjang
                        for _, h_row in items_hold.iterrows():
                            p_info = df_produk[df_produk["ID_Produk"] == h_row["ID_Produk"]]
                            if not p_info.empty:
                                st.session_state.cart.append({
                                    "id": h_row["ID_Produk"],
                                    "nama": p_info.iloc[0]["Nama_Produk"],
                                    "harga": int(p_info.iloc[0]["Harga_Jual"]),
                                    "hpp": int(p_info.iloc[0]["Harga_Beli"]),
                                    "qty": int(h_row["Jumlah"]),
                                    "stok_max": int(p_info.iloc[0]["Stok_Sistem"])
                                })
                        # Hapus data hold tersebut dari tb_hold agar tidak dobel
                        delete_row_by_condition("tb_hold", "Label_Meja", meja_pilihan)
                        st.success(f"Order {meja_pilihan} dikembalikan ke keranjang!")
                        st.rerun()

        st.write("---")
        
        # Detail Keranjang
        if not st.session_state.cart:
            st.info("Keranjang belanja masih kosong.")
            total_belanja = 0
        else:
            total_belanja = 0
            for i, item in enumerate(st.session_state.cart):
                col_item1, col_item2, col_item3 = st.columns([3, 2, 1])
                with col_item1:
                    st.write(f"**{item['nama']}**")
                    st.caption(f"Rp {item['harga']:,} x {item['qty']}")
                with col_item2:
                    # Edit Qty langsung
                    new_qty = st.number_input(
                        "Qty", min_value=0, max_value=item["stok_max"], 
                        value=item["qty"], key=f"qty_{item['id']}_{i}", label_visibility="collapsed"
                    )
                    if new_qty != item["qty"]:
                        if new_qty == 0:
                            st.session_state.cart.pop(i)
                        else:
                            item["qty"] = new_qty
                        st.rerun()
                with col_item3:
                    if st.button("🗑️", key=f"del_{item['id']}_{i}"):
                        st.session_state.cart.pop(i)
                        st.rerun()
                total_belanja += item["harga"] * item["qty"]
                st.write("---")

        # Perhitungan Diskon
        diskon_opsi = ["Tidak Ada"] + [row["Nama_Diskon"] for _, row in df_diskon_aktif.iterrows()]
        diskon_terpilih_nama = st.selectbox("Diskon / Promo", diskon_opsi)
        
        nilai_diskon = 0
        tipe_diskon = "Persen"
        
        if diskon_terpilih_nama != "Tidak Ada":
            diskon_row = df_diskon_aktif[df_diskon_aktif["Nama_Diskon"] == diskon_terpilih_nama].iloc[0]
            tipe_diskon = diskon_row["Tipe"]
            nilai_diskon_raw = int(diskon_row["Nilai"])
            
            if tipe_diskon == "Persen":
                nilai_diskon = int(total_belanja * (nilai_diskon_raw / 100))
            else:
                nilai_diskon = nilai_diskon_raw
                
        total_akhir = max(0, total_belanja - nilai_diskon)
        
        # Tampilan Ringkasan Biaya
        st.write(f"Subtotal: **Rp {total_belanja:,,}**")
        if nilai_diskon > 0:
            st.write(f"Potongan Diskon: <span style='color:red;'>- Rp {nilai_diskon:,,}</span>", unsafe_allow_html=True)
        st.markdown(f"### Total Tagihan: <span style='color:green;'>Rp {total_akhir:,,}</span>", unsafe_allow_html=True)
        
        # Pilihan Metode Bayar
        metode_pembayaran = st.radio("Metode Pembayaran", ["Tunai", "QRIS"], horizontal=True)
        
        input_bayar = 0
        kembalian = 0
        
        if metode_pembayaran == "Tunai":
            input_bayar = st.number_input("Uang Diterima (Rp)", min_value=0, step=1000, value=int(total_akhir))
            kembalian = input_bayar - total_akhir
            if kembalian >= 0:
                st.write(f"Kembalian: **Rp {kembalian:,,}**")
            else:
                st.error("Uang kurang!")
        else:
            # Metode QRIS: Lampirkan gambar barcode QRIS
            st.info("Pindai Barcode QRIS di bawah ini untuk membayar:")
            # Tampilkan placeholder image yang aman jika file qris.png belum diunggah
            if os.path.exists("qris.png"):
                st.image("qris.png", width=250, caption="Scan QRIS Toko")
            else:
                # Membuat visual QRIS tiruan menggunakan HTML agar aplikasi tetap cantik saat baru pertama kali coba
                st.markdown(
                    """
                    <div style="border: 2px dashed #333; width:220px; height:220px; display:flex; align-items:center; justify-content:center; text-align:center; background-color:#eee; border-radius:10px;">
                        <div style="font-size:12px; color:#555;">
                            <b>[ BARCODE QRIS ]</b><br>
                            Letakkan gambar <b>qris.png</b> Anda di folder program untuk mengganti visual ini.
                        </div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
        # Tombol Proses Transaksi Selesai
        bisa_bayar = True
        if metode_pembayaran == "Tunai" and kembalian < 0:
            bisa_bayar = False
        if not st.session_state.cart:
            bisa_bayar = False
            
        if st.button("🚀 SELESAIKAN & BAYAR", type="primary", use_container_width=True, disabled=not bisa_bayar):
            # 1. Update Stok di tb_produk & Tulis Log ke tb_penjualan
            trx_id = f"TRX-{datetime.datetime.now().strftime('%Y%m%d')}-{idx}"
            tgl_now = datetime.datetime.now().strftime('%Y-%m-%d')
            jam_now = datetime.datetime.now().strftime('%H:%M:%S')
            
            # Catat setiap barang di keranjang
            for item in st.session_state.cart:
                # Cari stok lama
                p_row = df_produk[df_produk["ID_Produk"] == item["id"]].iloc[0]
                stok_baru = int(p_row["Stok_Sistem"]) - item["qty"]
                
                # Update stok di Google Sheets
                update_cell_by_id("tb_produk", "ID_Produk", item["id"], "Stok_Sistem", stok_baru)
                
                # Masukkan log penjualan
                item_total = item["harga"] * item["qty"]
                append_data("tb_penjualan", [
                    trx_id,
                    tgl_now,
                    jam_now,
                    item["id"],
                    item["qty"],
                    item["harga"],
                    item_total,
                    metode_pembayaran,
                    st.session_state.username
                ])
                
            # Cetak Struk Preview
            st.session_state["struk_cetak"] = {
                "id": trx_id,
                "tgl": tgl_now,
                "jam": jam_now,
                "items": st.session_state.cart.copy(),
                "total": total_belanja,
                "diskon": nilai_diskon,
                "grand_total": total_akhir,
                "bayar": input_bayar if metode_pembayaran == "Tunai" else total_akhir,
                "kembalian": kembalian if metode_pembayaran == "Tunai" else 0,
                "metode": metode_pembayaran
            }
            
            # Kosongkan keranjang
            st.session_state.cart = []
            st.success("Transaksi Sukses disimpan ke Google Sheets!")
            st.rerun()

    # --- POP-UP PREVIEW STRUK (JIKA ADA) ---
    if "struk_cetak" in st.session_state:
        st.markdown("---")
        st.subheader("🧾 Struk Transaksi Terakhir")
        st_data = st.session_state["struk_cetak"]
        
        # Ambil Format Header Footer Struk dari Setting Toko
        df_toko = get_data("tb_setting_toko")
        store_name = df_toko.iloc[0]["Nama_Toko"] if not df_toko.empty else "SatuLembar POS"
        store_address = df_toko.iloc[0]["Alamat"] if not df_toko.empty else "-"
        store_phone = df_toko.iloc[0]["Telepon"] if not df_toko.empty else "-"
        store_footer = df_toko.iloc[0]["Footer_Struk"] if not df_toko.empty else "Terima Kasih!"
        paper_size = df_toko.iloc[0]["Ukuran_Kertas"] if not df_toko.empty else "58mm"
        
        width_px = "280px" if paper_size == "58mm" else "380px"
        
        # HTML & CSS Struk Thermal
        struk_html = f"""
        <div style="width: {width_px}; font-family: 'Courier New', Courier, monospace; font-size: 12px; border: 1px solid #ccc; padding: 15px; margin: auto; background-color: #fff; color: #000; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 10px;">
                <h3 style="margin: 0; font-size: 16px;">{store_name}</h3>
                <p style="margin: 3px 0; font-size: 11px;">{store
