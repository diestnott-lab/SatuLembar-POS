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
    
        # 1. Cek konfigurasi database dari Streamlit Secrets (Cloud) dahulu
    # Hubungkan ke Google Sheets dengan metode modern (Tanpa oauth2client)
    try:
        if "gcp_service_account" in st.secrets:
            # Membaca data TOML dari Secrets Streamlit
            creds_dict = dict(st.secrets["gcp_service_account"])
            client = gspread.service_account_from_dict(creds_dict)
        elif os.path.exists("credentials.json"):
            # Membaca data dari file lokal jika di Pydroid/Tablet
            client = gspread.service_account(filename="credentials.json")
        else:
            st.error("Kunci database tidak ditemukan di Secrets maupun lokal!")
            st.stop()
            
        # METODE TEMBAK LANGSUNG: Ganti teks di bawah dengan URL yang Anda salin di Langkah 1
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/12ieWVopfzzjMcqEYW2nqqJm4LD3VNKi0CIwIRjNUOoc/edit?usp=drivesdk")
        return sheet
        
    except Exception as e:
        st.error(f"Gagal koneksi ke database. Pastikan URL benar & email robot sudah di-share. Error: {e}")
        st.stop()
    
    # Membuka database Google Sheets
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
    worksheet = sh.worksheet(work_sheet)
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
                    # 1. Hitung stoknya terlebih dahulu di baris pertama (Gunakan sistem pengaman .get)
                    stok_tampil = row.get('Stock_Sistem', row.get('Stock', 0))
                    
                    # 2. Cetak seluruh komponen kartu produk dalam SATU perintah markdown yang rapi
                    st.markdown(
                        f"""
                        <div style='border:1px solid #ddd; padding:10px; border-radius:5px; margin-bottom:10px; background-color:#f9f9f9; color:black;'>
                            <strong>{row['Nama_Produk']}</strong><br>
                            <span style='color:green; font-weight:bold;'>Rp {int(row['Harga_Jual']):,}</span><br>
                            <small style='color:gray;'>Stok: {int(stok_tampil)}</small>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    
                    # Cek jika stok masih ada
                    if int(row.get('Stock_Sistem', row.get('Stock', 0))) > 0:
                        if st.button(f"Tambah", key=f"add_{row['ID_Produk']}"):
                            # Tambah ke keranjang belanja
                            # Cari apakah barang sudah ada di keranjang
                            found = False
                            for item in st.session_state.cart:
                                if item["id"] == row["ID_Produk"]:
                                    if item["qty"] < int(row["Stock_Sistem"]):
                                        item["qty"] += 1
                                    else:
                                        st.warning("Jumlah pembelian melebihi stock yang tersedia!")
                                    found = True
                                    break
                            if not found:
                                st.session_state.cart.append({
                                    "id": row["ID_Produk"],
                                    "nama": row["Nama_Produk"],
                                    "harga": int(row["Harga_Jual"]),
                                    "hpp": int(row["Harga_Beli"]),
                                    "qty": 1,
                                    "stok_max": int(row["Stock_Sistem"])
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
                                    "stok_max": int(p_info.iloc[0]["Stock_Sistem"])
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
        st.write(f"Subtotal: **Rp {int(total_belanja):,}**")
        if nilai_diskon > 0:
            st.write(f"Potongan Diskon: <span style='color:red;'>- Rp {int(nilai_diskon):,}</span>", unsafe_allow_html=True)
        st.markdown(f"### Total Tagihan: <span style='color:green;'>Rp {int(total_akhir):,}</span>", unsafe_allow_html=True)
        
        # Pilihan Metode Bayar
        metode_pembayaran = st.radio("Metode Pembayaran", ["Tunai", "QRIS"], horizontal=True)
        
        input_bayar = 0
        kembalian = 0
        
        if metode_pembayaran == "Tunai":
            input_bayar = st.number_input("Uang Diterima (Rp)", min_value=0, step=1000, value=int(total_akhir))
            kembalian = input_bayar - total_akhir
            if kembalian >= 0:
                st.write(f"Kembalian: **Rp {int(kembalian):,}**")
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
                stok_baru = int(p_row["Stock_Sistem"]) - item["qty"]
                
                # Update stok di Google Sheets
                update_cell_by_id("tb_produk", "ID_Produk", item["id"], "Stock_Sistem", stok_baru)
                
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
                <p style="margin: 3px 0; font-size: 11px;">{store_address}</p>
                <p style="margin: 3px 0; font-size: 11px;">Telp: {store_phone}</p>
                <p style="margin: 0;">===============================</p>
            </div>
            <div>
                <p style="margin: 3px 0;">No  : {st_data['id']}</p>
                <p style="margin: 3px 0;">Tgl : {st_data['tgl']} {st_data['jam']}</p>
                <p style="margin: 3px 0;">Kasir : {st.session_state.username}</p>
                <p style="margin: 0;">-------------------------------</p>
            </div>
            <div style="margin: 10px 0;">
        """
        for item in st_data["items"]:
            struk_html += f"""
                <div style="display: flex; justify-content: space-between;">
                    <span>{item['nama']}</span>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 3px;">
                    <span>   {item['qty']} x {item['harga']:,}</span>
                    <span>Rp {item['qty']*item['harga']:,}</span>
                </div>
            """
            
        struk_html += f"""
                <p style="margin: 0;">-------------------------------</p>
                <div style="display: flex; justify-content: space-between;">
                    <span>Subtotal:</span>
                    <span>Rp {st_data['total']:,}</span>
                </div>
        """
        if st_data["diskon"] > 0:
            struk_html += f"""
                <div style="display: flex; justify-content: space-between; color: red;">
                    <span>Diskon:</span>
                    <span>-Rp {st_data['diskon']:,}</span>
                </div>
            """
            
        struk_html += f"""
                <div style="display: flex; justify-content: space-between; font-weight: bold; margin-top: 5px;">
                    <span>GRAND TOTAL:</span>
                    <span>Rp {st_data['grand_total']:,}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span>Metode:</span>
                    <span>{st_data['metode']}</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span>Bayar:</span>
                    <span>Rp {st_data['bayar']:,}</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span>Kembali:</span>
                    <span>Rp {st_data['kembalian']:,}</span>
                </div>
                <p style="margin: 10px 0 0 0; text-align: center;">===============================</p>
                <p style="margin: 5px 0 0 0; text-align: center; font-size: 11px;">{store_footer}</p>
            </div>
        </div>
        """
        
        st.markdown(struk_html, unsafe_allow_html=True)
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            # Menggunakan JavaScript bawaan browser untuk memicu dialog print halaman struk
            if st.button("🖨️ Cetak Struk (Sistem)", use_container_width=True):
                st.components.v1.html(
                    f"""
                    <script>
                        var win = window.open("", "PRINT", "height=400,width=600");
                        win.document.write('<html><head><title>Print Struk</title></head><body>');
                        win.document.write(`{struk_html}`);
                        win.document.write('</body></html>');
                        win.document.close();
                        win.focus();
                        win.print();
                        win.close();
                    </script>
                    """,
                    height=0,
                    width=0
                )
        with col_btn2:
            if st.button("Clear Layar Struk", use_container_width=True):
                del st.session_state["struk_cetak"]
                st.rerun()
                
# --- HALAMAN DASHBOARD / LAPORAN ---
def dashboard_page():
    st.markdown("### 📊 Laporan Keuangan & Analisa Produk")
    
    df_penjualan = get_data("tb_penjualan")
    df_produk = get_data("tb_produk")
    
    if df_penjualan.empty:
        st.warning("Belum ada transaksi penjualan terekam.")
        return
        
    # Gabung data penjualan dengan HPP untuk menghitung profit
    df_joined = df_penjualan.merge(df_produk[["ID_Produk", "Harga_Beli", "Nama_Produk"]], on="ID_Produk", how="left")
    df_joined["Total_HPP"] = df_joined["Harga_Beli"].astype(float) * df_joined["Jumlah"].astype(int)
    df_joined["Profit"] = df_joined["Total"].astype(float) - df_joined["Total_HPP"]
    
    # 1. Metrik Utama
    total_omzet = df_joined["Total"].sum()
    total_hpp = df_joined["Total_HPP"].sum()
    total_profit = df_joined["Profit"].sum()
    total_trx = df_joined["ID_Transaksi"].nunique()
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Total Omzet Kotor (Revenue)", f"Rp {int(total_omzet):,}")
    with col_m2:
        st.metric("Total HPP (Modal Terjual)", f"Rp {int(total_hpp):,}")
    with col_m3:
        st.metric("Keuntungan Bersih (Profit)", f"Rp {int(total_profit):,}")
    with col_m4:
        st.metric("Total Transaksi", f"{total_trx:,}")
        
    st.write("---")
    
    # 2. Grafik Tren Penjualan Harian
    st.subheader("📈 Tren Omzet & Profit Harian")
    df_daily = df_joined.groupby("Tanggal")[["Total", "Profit"]].sum().reset_index()
    fig_line = px.line(
        df_daily, x="Tanggal", y=["Total", "Profit"], 
        labels={"value": "Rupiah", "variable": "Tipe"}, 
        title="Perkembangan Omzet vs Keuntungan Bersih Harian"
    )
    st.plotly_chart(fig_line, use_container_width=True)
    
    # 3. Produk Terlaris & Kontribusi Margin
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("🏆 5 Produk Terlaris (Qty)")
        df_top_qty = df_joined.groupby("Nama_Produk")["Jumlah"].sum().reset_index().sort_values(by="Jumlah", ascending=False).head(5)
        fig_bar_qty = px.bar(df_top_qty, x="Nama_Produk", y="Jumlah", color="Nama_Produk", title="Banyaknya Porsi Terjual")
        st.plotly_chart(fig_bar_qty, use_container_width=True)
        
    with col_g2:
        st.subheader("💰 Kontributor Profit Terbesar")
        df_top_profit = df_joined.groupby("Nama_Produk")["Profit"].sum().reset_index().sort_values(by="Profit", ascending=False).head(5)
        fig_pie = px.pie(df_top_profit, values="Profit", names="Nama_Produk", title="Porsi Keuntungan Per Produk")
        st.plotly_chart(fig_pie, use_container_width=True)

# --- HALAMAN MANAJEMEN STOK & STOCK OPNAME ---
def stock_management_page():
    st.markdown("### 📦 Manajemen Stock & Stock Opname")
    
    df_produk = get_data("tb_produk")
    
    tab_stok, tab_opname = st.tabs(["📋 Sisa Stock Sistem", "🔍 Stock Opname Bulanan"])
    
    with tab_stok:
        st.subheader("Daftar Inventori Terkini")
        st.dataframe(df_produk, use_container_width=True)
        
        # Tambah Stok Masuk (Restock Supplier)
        st.write("---")
        st.subheader("📥 Input Restock Barang dari Supplier")
        with st.form("form_restock"):
            col_rs1, col_rs2, col_rs3 = st.columns(3)
            with col_rs1:
                produk_restock = st.selectbox("Pilih Produk", df_produk["Nama_Produk"])
            with col_rs2:
                jumlah_masuk = st.number_input("Jumlah Unit Masuk", min_value=1, step=1)
            with col_rs3:
                nama_supplier = st.text_input("Nama Supplier", "PT Sumber Berkah")
                
            btn_restock = st.form_submit_button("Simpan Stock Masuk")
            if btn_restock:
                p_row = df_produk[df_produk["Nama_Produk"] == produk_restock].iloc[0]
                p_id = p_row["ID_Produk"]
                # --- GANTI BARIS 619 DENGAN KODE AMAN INI ---
                stok_lama = int(p_row.get('Stock_sistem', p_row.get('Stock_Sistem', 0)))
                stok_baru_calc = stok_lama + jumlah_masuk
                
                # Simpan ke tb_stok_masuk
                log_id = f"LOG-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                tgl_now = datetime.datetime.now().strftime('%Y-%m-%d')
                append_data("tb_stock_masuk", [log_id, tgl_now, p_id, jumlah_masuk, nama_supplier])
                
                # Update stok di tb_produk
                update_cell_by_id("tb_produk", "ID_Produk", p_id, "Stock_Sistem", stok_baru_calc)
                
                st.success(f"Stok {produk_restock} berhasil diperbarui dari {stok_lama} ke {stok_baru_calc}!")
                st.rerun()

    with tab_opname:
        st.subheader("Proses Pencocokan Fisik (Stock Opname)")
        st.caption("Lakukan audit fisik barang sebulan sekali untuk mendeteksi kehilangan barang.")
        
        # Form Input Opname
        with st.form("form_opname"):
            col_op1, col_op2, col_op3 = st.columns(3)
            with col_op1:
                prod_opname_name = st.selectbox("Produk yang Diaudit", df_produk["Nama_Produk"], key="opname_prod")
            with col_op2:
                stok_fisik_riil = st.number_input("Jumlah Fisik di Toko", min_value=0, step=1)
            with col_op3:
                keterangan_opname = st.text_area("Keterangan Selisih", placeholder="Gelas pecah / Expired", height=68)
                
            btn_opname_save = st.form_submit_button("Simpan Hasil Opname")
            
            if btn_opname_save:
                p_row = df_produk[df_produk["Nama_Produk"] == prod_opname_name].iloc[0]
                p_id = p_row["ID_Produk"]
                stok_sistem_sebelum = int(p_row["Stock_Sistem"])
                selisih_perhitungan = stok_fisik_riil - stok_sistem_sebelum
                
                # Simpan log ke tb_opname
                opn_id = f"OPN-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                tgl_now = datetime.datetime.now().strftime('%Y-%m-%d')
                append_data("tb_opname", [
                    opn_id,
                    tgl_now,
                    p_id,
                    stok_sistem_sebelum,
                    stok_fisik_riil,
                    selisih_perhitungan,
                    keterangan_opname
                ])
                
                # Sesuaikan stok sistem di tb_produk mengikuti stok fisik asli
                update_cell_by_id("tb_produk", "ID_Produk", p_id, "Stock_Sistem", stok_fisik_riil)
                
                st.success(f"Opname sukses! Stock Sistem diperbarui menjadi {stok_fisik_riil} (Selisih: {selisih_perhitungan})")
                st.rerun()
                
        # Histori Opname
        st.write("---")
        st.subheader("Histori Stock Opname Terakhir")
        df_history_opname = get_data("tb_opname")
        if df_history_opname.empty:
            st.info("Belum ada histori audit opname.")
        else:
            st.dataframe(df_history_opname, use_container_width=True)
    
# --- HALAMAN CONFIG & SETTING ---
def config_setting_page():
    st.markdown("### ⚙️ Pusat Konfigurasi (Config & Settings)")
    st.caption("Akses Pengaturan Utama Master Data dan Toko Anda")
    
    df_produk = get_data("tb_produk")
    df_users = get_data("tb_users")
    df_diskon = get_data("tb_diskon")
    df_toko = get_data("tb_setting_toko")
    
    tab_m_prod, tab_m_usr, tab_m_disc, tab_m_shop = st.tabs([
        "🍔 Master Menu/Produk", "👥 Master User", "🏷️ Diskon/Promo", "🏢 Profil Toko"
    ])
    
    # 1. TAB MENU / PRODUK
    with tab_m_prod:
        st.subheader("Kelola Menu & Harga Jual")
        col_cp1, col_cp2 = st.columns([1, 2])
        
        with col_cp1:
            st.write("**Tambah Produk Baru**")
            with st.form("form_add_product"):
                new_pid = st.text_input("ID Produk", placeholder="P001")
                new_pname = st.text_input("Nama Produk")
                new_pcat = st.text_input("Kategori", placeholder="Makanan/Minuman")
                new_pbeli = st.number_input("Harga Modal (Beli)", min_value=0, step=500)
                new_pjual = st.number_input("Harga Jual", min_value=0, step=500)
                new_pstok = st.number_input("Stock Awal", min_value=0, step=1)
                
                btn_add_p = st.form_submit_button("Simpan Produk", use_container_width=True)
                if btn_add_p:
                    if not new_pid or not new_pname:
                        st.error("ID dan Nama Produk wajib diisi!")
                    else:
                        append_data("tb_produk", [new_pid, new_pname, new_pcat, new_pbeli, new_pjual, new_pstok])
                        st.success("Produk baru berhasil didaftarkan!")
                        st.rerun()
                        
        with col_cp2:
            st.write("**Daftar Produk Aktif**")
            st.dataframe(df_produk, use_container_width=True)
            
            # Form Update Harga
            st.write("---")
            st.write("**Update Harga/Stock Cepat**")
        
        # Pengecekan: Jika database produk TIDAK KOSONG, jalankan form edit
                # 1. 'if' utama harus sejajar lurus dengan 'else' pasangannya
        if not df_produk.empty:
            prod_edit = st.selectbox("Pilih Produk yang Diedit", df_produk["Nama_Produk"])
            p_match = df_produk[df_produk["Nama_Produk"] == prod_edit]
            
            if not p_match.empty:
                p_match_row = p_match.iloc[0]
                
                # --- AREA FORM EDIT (Semua input & tombol harus di dalam sini) ---
                with st.form("form_edit_product"):
                    col_e1, col_e2, col_e3 = st.columns(3)
                    with col_e1:
                        edit_beli = st.number_input("Harga Modal Baru", min_value=0, value=int(p_match_row["Harga_Beli"]))
                    with col_e2:
                        edit_jual = st.number_input("Harga Jual Baru", min_value=0, value=int(p_match_row["Harga_Jual"]))
                    with col_e3:
                        edit_stok = st.number_input("Edit Stock", min_value=0, value=int(p_match_row.get('Stock_Sistem', p_match_row.get('Stok', 0))))

                    
                    # TOMBOL SUBMIT: Sekarang posisinya aman di dalam form & sejajar lurus
                    if st.form_submit_button("Terapkan Perubahan", use_container_width=True):
                        update_cell_by_id("tb_produk", "ID_Produk", p_match_row["ID_Produk"], "Harga_Beli", edit_beli)
                        update_cell_by_id("tb_produk", "ID_Produk", p_match_row["ID_Produk"], "Harga_Jual", edit_jual)
                        update_cell_by_id("tb_produk", "ID_Produk", p_match_row["ID_Produk"], "Stock_Sistem", edit_stok)
                        st.success("Perubahan data menu berhasil diperbarui!")
                        st.rerun()
            else:
                st.warning("Produk tidak ditemukan.")
        else:
            st.info("💡 Database produk Anda masih kosong...")

    # 2. TAB USER (KASIR & ADMIN)
    with tab_m_usr:
        st.subheader("Manajemen Hak Akses Karyawan")
        col_cu1, col_cu2 = st.columns([1, 2])
        
        with col_cu1:
            st.write("**Daftarkan Akun Baru**")
            with st.form("form_add_user"):
                new_uname = st.text_input("Username")
                new_pass = st.text_input("Password Awal", type="password")
                new_fullname = st.text_input("Nama Lengkap Karyawan")
                new_role = st.selectbox("Role", ["Kasir", "Admin"])
                
                if st.form_submit_button("Simpan Akun", use_container_width=True):
                    if not new_uname or not new_pass or not new_fullname:
                        st.error("Semua kolom harus diisi!")
                    else:
                        encrypted_pw = hash_password(new_pass)
                        append_data("tb_users", [new_uname, encrypted_pw, new_fullname, new_role])
                        st.success(f"Akun {new_fullname} ({new_role}) sukses ditambahkan!")
                        st.rerun()
                        
        with col_cu2:
            st.write("**Daftar Pengguna Aplikasi**")
            # Tampilkan username & password yang aman
            df_users_display = df_users.copy()
            df_users_display["Password"] = "******** [TERENKRIPSI]"
            st.dataframe(df_users_display, use_container_width=True)
            
            # Reset Password Fitur
            st.write("---")
            st.write("**Reset Password Akun Karyawan**")
            usr_reset = st.selectbox("Pilih Karyawan", df_users["Username"])
            with st.form("form_reset_password"):
                pass_baru = st.text_input("Password Baru", type="password")
                if st.form_submit_button("Reset Password"):
                    if not pass_baru:
                        st.error("Password baru tidak boleh kosong!")
                    else:
                        enc_new_pw = hash_password(pass_baru)
                        update_cell_by_id("tb_users", "Username", usr_reset, "Password", enc_new_pw)
                        st.success(f"Password untuk user {usr_reset} berhasil diubah!")
                        st.rerun()

        # 3. TAB DISKON
    with tab_m_disc:
        st.subheader("Atur Potongan Harga & Promo")
        col_cd1, col_cd2 = st.columns([1, 2])
        
        with col_cd1:
            st.write("**Buat Diskon Baru**")
            with st.form("form_add_diskon"):
                d_id = st.text_input("ID Diskon", placeholder="D001")
                d_nama = st.text_input("Nama Promo / Voucher")
                d_tipe = st.selectbox("Jenis", ["Persen", "Nominal"])
                d_nilai = st.number_input("Nilai Potongan (Rp / %)", min_value=0, step=500)
                d_status = st.selectbox("Status Keaktifan", ["Aktif", "Tidak Aktif"])
                
                if st.form_submit_button("Simpan Promo", use_container_width=True):
                    append_data("tb_diskon", [d_id, d_nama, d_tipe, d_nilai, d_status])
                    st.success("Diskon baru berhasil didaftarkan!")
                    st.rerun()
                    
        with col_cd2:
            st.write("**Daftar Promo Tersedia**")
            st.dataframe(df_diskon, use_container_width=True)
            
            # Ubah Status Diskon
            st.write("---")
            st.write("**Aktif / Nonaktifkan Promo**")
            
            # --- PENGAMAN UTAMA AGAR BARIS 827 TIDAK EROR LAGI ---
            if not df_diskon.empty:
                disc_edit_name = st.selectbox("Pilih Promo", df_diskon["Nama_Diskon"])
                p_match_disc = df_diskon[df_diskon["Nama_Diskon"] == disc_edit_name]
                
                if not p_match_disc.empty:
                    disc_row_match = p_match_disc.iloc[0]
                    new_status_act = st.selectbox("Status Baru", ["Aktif", "Tidak Aktif"], index=0 if disc_row_match["Status"] == "Aktif" else 1)
                    if st.button("Ubah Status"):
                        update_cell_by_id("tb_diskon", "ID_Diskon", disc_row_match["ID_Diskon"], "Status", new_status_act)
                        st.success("Status promo berhasil diperbarui!")
                        st.rerun()
                else:
                    st.warning("Promo tidak ditemukan.")
            else:
                # Tampilan aman jika data diskon di Google Sheets masih kosong
                st.info("💡 Belum ada promo yang terdaftar. Silakan buat diskon baru terlebih dahulu di menu sebelah kiri.")

    # 4. TAB PROFIL TOKO (STRUK)
    with tab_m_shop:
        st.subheader("Pengaturan Profil Toko & Tampilan Struk")
        
        if df_toko.empty:
            # Isi default jika kosong
            append_data("tb_setting_toko", ["Toko Baru", "Alamat Toko", "08123", "58mm", "Terima kasih!"])
            st.rerun()
            
        toko_data = df_toko.iloc[0]
        
        with st.form("form_toko"):
            shop_name = st.text_input("Nama Toko / Restoran", value=toko_data["Nama_Toko"])
            shop_address = st.text_area("Alamat Toko", value=toko_data["Alamat"])
            shop_phone = st.text_input("Nomor Telepon Kontak", value=toko_data["Telepon"])
            shop_paper = st.selectbox("Ukuran Kertas Printer Thermal", ["58mm", "80mm"], index=0 if toko_data["Ukuran_Kertas"] == "58mm" else 1)
            shop_footer = st.text_area("Catatan Kaki Struk (Footer)", value=toko_data["Footer_Struk"])
            
            if st.form_submit_button("Simpan Profil Toko"):
                # Update data toko (karena hanya ada 1 baris, kita update per kolom dengan trigger Nama_Toko lama)
                update_cell_by_id("tb_setting_toko", "Nama_Toko", toko_data["Nama_Toko"], "Alamat", shop_address)
                update_cell_by_id("tb_setting_toko", "Nama_Toko", toko_data["Nama_Toko"], "Telepon", shop_phone)
                update_cell_by_id("tb_setting_toko", "Nama_Toko", toko_data["Nama_Toko"], "Ukuran_Kertas", shop_paper)
                update_cell_by_id("tb_setting_toko", "Nama_Toko", toko_data["Nama_Toko"], "Footer_Struk", shop_footer)
                # Nama_Toko diubah terakhir karena dipakai sebagai ID pencari kolom di baris sebelumnya
                update_cell_by_id("tb_setting_toko", "Nama_Toko", toko_data["Nama_Toko"], "Nama_Toko", shop_name)
                
                st.success("Profil toko dan pengaturan cetak berhasil disimpan!")
                st.rerun()

# --- PROGRAM UTAMA (MAIN CONTROLLER) ---
def main():
    if not st.session_state.logged_in:
        login_page()
    else:
        # Tampilan setelah login sukses
        st.sidebar.markdown(f"### 👤 {st.session_state.username}")
        st.sidebar.caption(f"Role Akses: {st.session_state.user_role}")
        st.sidebar.write("---")
        
        # Pilihan Menu Navigasi Berdasarkan Role
        if st.session_state.user_role == "Admin":
            menu_options = [
                "💻 Layar Kasir (POS)", 
                "📊 Dashboard Omzet & Profit", 
                "📦 Stok & Stock Opname", 
                "⚙️ Pusat Pengaturan (Config)"
            ]
        else:
            # Kasir biasa hanya bisa membuka layar kasir
            menu_options = ["💻 Layar Kasir (POS)"]
            
        pilihan_menu = st.sidebar.radio("Navigasi Menu", menu_options)
        
        st.sidebar.write("---")
        if st.sidebar.button("🚪 Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.username = ""
            st.session_state.cart = []
            st.rerun()
            
        # Panggil halaman yang sesuai
        if pilihan_menu == "💻 Layar Kasir (POS)":
            cash_register_page()
        elif pilihan_menu == "📊 Dashboard Omzet & Profit":
            dashboard_page()
        elif pilihan_menu == "📦 Stok & Stock Opname":
            stock_management_page()
        elif pilihan_menu == "⚙️ Pusat Pengaturan (Config)":
            config_setting_page()

if __name__ == "__main__":
    main()
