import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime

st.set_page_config(page_title="DigiPOS Converter", layout="wide")

st.title("DigiPOS Term Converter")

# --- Function ส่วนกลางสำหรับสกัดชื่อสาขาและวันที่ ---
def get_info(df_raw):
    try:
        # อ้างอิงจากตำแหน่งในไฟล์: Store อยู่แถว 2 (index 1), Date อยู่แถว 3 (index 2)
        store = str(df_raw.iloc[1, 1]).strip()
        date_val = str(df_raw.iloc[2, 1]).strip()
        # แปลงวันที่เป็น YYYYMMDD สำหรับตั้งชื่อไฟล์
        suffix = datetime.strptime(date_val, '%d/%m/%Y').strftime('%Y%m%d')
        return store, date_val, suffix
    except:
        return "Unknown", "13/02/2026", "20260213" # ค่า fallback กรณีอ่านไม่ได้

# --- UI: ส่วนอัปโหลดไฟล์ ---
uploaded_files = st.file_uploader("1. อัปโหลดไฟล์ CSV ต้นฉบับ", type="csv", accept_multiple_files=True)

if uploaded_files:
    st.divider()
    st.write("### เลือกรูปแบบที่ต้องการ Convert")
    
    # สร้าง 3 คอลัมน์สำหรับ 3 ฟังก์ชัน
    col1, col2, col3 = st.columns(3)

    # --- ปุ่มที่ 1: Hourly Report ---
    with col1:
        st.subheader("📊 Hourly")
        if st.button("Convert to HOURLY 🚀", type="primary", use_container_width=True):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f in uploaded_files:
                    f.seek(0)
                    df_raw = pd.read_csv(f, header=None)
                    store, date_str, suffix = get_info(df_raw)
                    mask = (df_raw.iloc[:, 0] == 'Time')
                    if mask.any():
                        idx = df_raw[mask].index[0]
                        df = df_raw.iloc[idx+1:idx+25, 0:7].copy()
                        df.columns = ['Time','Sales ($)','Sales %','Receipt','Receipt %','Guest','Qty Sold']
                        df['Time'] = df['Time'].str.replace(' -', '', regex=False)
                        df.insert(0, 'Store', store)
                        df.insert(1, 'Date', date_str)
                        zip_file.writestr(f"{store}{suffix}.csv", df.to_csv(index=False, encoding='utf-8-sig'))
            st.success("Hourly Done!")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(), "Hourly.zip", "application/zip", use_container_width=True)

    # --- ปุ่มที่ 2: Transaction Summary (TS) ---
    with col2:
        st.subheader("📑 TS Summary")
        if st.button("Convert to TS 🚀", type="primary", use_container_width=True):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f in uploaded_files:
                    f.seek(0)
                    df_raw = pd.read_csv(f, header=None)
                    store, date_str, suffix = get_info(df_raw)
                    start_mask = df_raw.iloc[:, 0] == 'TOTAL BEFORE SUBTOTAL DISC/SUR'
                    end_mask = df_raw.iloc[:, 0] == 'GROSS SALES'
                    if start_mask.any() and end_mask.any():
                        start_idx = df_raw[start_mask].index[0]
                        end_idx = df_raw[end_mask].index[0]
                        df_ts = df_raw.iloc[start_idx : end_idx + 1, 0:2].copy()
                        df_ts.insert(0, 'Store_Col', store); df_ts.insert(1, 'Date_Col', date_str)
                        df_ts.iloc[0, 0] = "Store"; df_ts.iloc[0, 1] = "Date"
                        zip_file.writestr(f"TS {store}{suffix}.csv", df_ts.to_csv(index=False, header=False, encoding='utf-8-sig'))
            st.success("TS Done!")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(), "TS_Summary.zip", "application/zip", use_container_width=True)

    # --- ปุ่มที่ 3: Term OG (Original Format) ---
    with col3:
        st.subheader("💾 Term OG")
        if st.button("Convert to OG 🚀", type="primary", use_container_width=True):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for f in uploaded_files:
                    f.seek(0)
                    # อ่านไฟล์แบบ raw ทั้งหมดเพื่อไม่ให้เสียโครงสร้างเดิม
                    df_raw = pd.read_csv(f, header=None)
                    store, date_str, suffix = get_info(df_raw)
                    
                    # บันทึกไฟล์เดิมโดยใช้ชื่อใหม่ตามที่ VBA กำหนด
                    csv_og = df_raw.to_csv(index=False, header=False, encoding='utf-8-sig')
                    zip_file.writestr(f"{store}{suffix}OG.csv", csv_og)
            
            st.success("Term OG Done!")
            st.download_button(
                "📥 Download OG ZIP", 
                zip_buffer.getvalue(), 
                "Term_OG.zip", 
                "application/zip", 
                use_container_width=True
            )

else:
    st.warning("กรุณาอัปโหลดไฟล์ CSV ต้นฉบับก่อน")
