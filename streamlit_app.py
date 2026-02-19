import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="DigiPOS Convert", layout="wide")

st.markdown("""
<style>
    .main-header {font-size: 3rem; font-weight: bold; color: #b00000;}
    .sub-header {font-size: 2rem; font-weight: bold; color: #333;}
    div.stButton > button:first-child {width: 100%;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">DigiPOS Data Convert (Term/E-Journal)</div>', unsafe_allow_html=True)

# ==========================================
# 1. HELPER FUNCTIONS
# ==========================================

def get_info_term(df_raw):
    """
    ดึงชื่อสาขาและวันที่จากไฟล์ Term 
    - Store = B2 (iloc[1, 1])
    - Date = B3 (iloc[2, 1])
    """
    try:
        store = str(df_raw.iloc[1, 1]).strip()
        date_val = str(df_raw.iloc[2, 1]).strip()
        suffix = datetime.strptime(date_val, '%d/%m/%Y').strftime('%Y%m%d')
        return store, date_val, suffix
    except:
        return "Unknown", "01/01/2026", "20260101"

def get_info_ejournal(df_raw):
    """
    ดึงชื่อสาขาและวันที่จากไฟล์ E-Journal 
    - พยายามหาจาก D2 (Standard) ก่อน
    - ถ้าไม่เจอ (เช่นไฟล์ Union Mall) ให้ลองหาจาก B2 (Fallback)
    """
    try:
        # ลองหาที่ D2 (Column Index 3)
        store = str(df_raw.iloc[1, 3]).strip()
        date_val = str(df_raw.iloc[2, 3]).strip()
        
        # เช็คว่าค่าที่ได้ถูกต้องไหม (ไม่ใช่ nan หรือว่าง)
        if not store or store.lower() == 'nan':
            raise ValueError("Store not found in D2")
            
        suffix = datetime.strptime(date_val, '%d/%m/%Y').strftime('%Y%m%d')
        return store, date_val, suffix
    except:
        # ถ้าหาที่ D2 ไม่เจอ ให้ไปใช้ Logic เดียวกับ Term (หาที่ B2)
        return get_info_term(df_raw)

def process_ej_report_logic(df_raw):
    """
    Logic สำหรับแปลง E-Journal Report (Updated):
    1. ดึง Store/Date (รองรับทั้งไฟล์ปกติและ Union Mall)
    2. Insert Col A, B
    3. Sort ตามคอลัมน์แรกของข้อมูลดิบ (Key1:=Range("C1") ใน Excel คือ Old Col A)
    4. Filter แถวที่มี "RCT"
    """
    try:
        # 1. ดึงค่า Store/Date แบบฉลาดขึ้น
        store_val, date_val, _ = get_info_ejournal(df_raw)
        
        # 2. เตรียมข้อมูล
        df_processed = df_raw.copy()
        
        # 3. Insert Columns (เหมือน VBA)
        df_processed.insert(0, 'New_Store', store_val)
        df_processed.insert(1, 'New_Date', date_val)
        
        # 4. Sort ข้อมูล
        # เรียงตามคอลัมน์แรกของข้อมูลดิบ (Label 0)
        df_sorted = df_processed.sort_values(by=0) 
        
        # 5. Filter ข้อมูล "RCT"
        # เช็คที่คอลัมน์แรกของข้อมูลดิบ (Label 0)
        mask = df_sorted[0].astype(str).str.startswith('RCT', na=False)
        df_final = df_sorted[mask].copy()
        
        return df_final, store_val, date_val
        
    except Exception as e:
        return None, None, None

def parse_receipt_data(file_obj):
    """
    Receipt Extract Logic (VBA Replica):
    1. อ่านเฉพาะ Column A (เหมือน VBA ws.Cells(r, "A"))
    2. RCT#: ตัดเอาเฉพาะตัวเลข
    3. Date: ตัดเอา 8 ตัวแรก (dd/mm/yy)
    4. Time: ตัดเอา 5 ตัวแรก (HH:MM)
    5. Tax Amount: ดึงตัวเลขสุดท้ายในวงเล็บ GST SUMMARY
    """
    try:
        # 1. ใช้ Pandas อ่านไฟล์เพื่อดึงเฉพาะ Column A (Index 0)
        # เพื่อป้องกันไม่ให้ติดเครื่องหมาย Comma หรือข้อมูลคอลัมน์อื่นมาด้วย
        df_raw = pd.read_csv(file_obj, header=None, on_bad_lines='skip', encoding='utf-8')
        
        # แปลงข้อมูล Column A เป็น List (ตัดบรรทัดว่างทิ้ง)
        lines = df_raw[0].dropna().astype(str).tolist()
        
        data_rows = []
        
        # ตัวแปรเก็บค่า
        rct = ""
        status = ""
        tax_inv = ""
        dt_date = ""
        dt_time = ""
        total = ""
        tax = ""
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # --- 1. RCT # ---
            if "RCT#" in line:
                if "CANCELLED" in line:
                    status = "CANCELLED"
                    # ลบคำว่า RCT# และ (CANCELLED)
                    temp = line.replace("RCT#", "").strip()
                    if "(" in temp:
                        rct = temp.split("(")[0].strip()
                    else:
                        rct = temp
                else:
                    status = "ISSUED"
                    temp = line.replace("RCT#", "").strip()
                    # เอาเฉพาะตัวเลข (ตัด Space ทิ้ง)
                    rct = temp.split(" ")[0].strip()
            
            # --- 2. TAX INVOICE # ---
            elif "TAX INVOICE#" in line:
                temp = line.replace("TAX INVOICE#", "").strip()
                tax_inv = temp.split(" ")[0].strip()

            # --- 3. Date & Time ---
            # Pattern: 17/02/26 (MON) 10:07:44
            elif "/" in line and " (" in line and len(line) > 0 and line[0].isdigit():
                # Date: VBA ใช้ Left(8) -> "17/02/26"
                dt_date = line[:8].strip()
                
                # Time: VBA ใช้ Right(5) แต่เพื่อความชัวร์ ให้หา token ที่มี : แล้วตัดเอา 5 ตัวแรก
                parts = line.split()
                for p in parts:
                    if ":" in p:
                        dt_time = p[:5] # เอาแค่ HH:MM
                        break
            
            # --- 4. TOTAL TENDERED ---
            elif "TOTAL TENDERED" in line:
                temp = line.replace("TOTAL TENDERED", "").strip()
                # Clean: เก็บเฉพาะตัวเลข จุด และคอมม่า (ตัดสกุลเงินทิ้ง)
                total = "".join([c for c in temp if c.isdigit() or c in ['.', ',']])

            # --- 5. GST SUMMARY ---
            elif "GST SUMMARY" in line:
                # ดูบรรทัดถัดไป
                if i + 1 < len(lines):
                    tax_line = lines[i+1].strip()
                    # Pattern: ... (7.00%)  123.00  8.05)
                    # เราต้องการเลขตัวสุดท้าย (8.05)
                    if ")" in tax_line:
                        # ตัดวงเล็บปิดตัวสุดท้ายออก
                        content = tax_line[:tax_line.rfind(")")]
                        # หาช่องว่างสุดท้าย
                        last_space = content.rfind(" ")
                        if last_space != -1:
                            raw_tax = content[last_space+1:]
                            # Clean
                            tax = "".join([c for c in raw_tax if c.isdigit() or c in ['.', ',']])
                
                # บันทึกข้อมูล
                if rct:
                    data_rows.append({
                        "RCT #": rct,
                        "Status": status,
                        "TAX INVOICE #": "#" + tax_inv, # ใส่ # ตาม Recon
                        "Date": dt_date,
                        "Time": dt_time,
                        "TOTAL TENDERED": total,
                        "TAX AMOUNT": tax
                    })
                
                # Reset
                rct, status, tax_inv, dt_date, dt_time, total, tax = "", "", "", "", "", "", ""
                i += 1 # ข้ามบรรทัด Tax
            
            i += 1
            
        return pd.DataFrame(data_rows)
        
    except Exception as e:
        st.error(f"Error parsing receipt: {e}")
        return None

# ==========================================
# 2. UI SECTION: TERM FILE
# ==========================================
st.divider()
st.markdown('<div class="sub-header">📂 1. Term Files Convert</div>', unsafe_allow_html=True)

term_files = st.file_uploader("เลือกไฟล์ Term (CSV)", type="csv", accept_multiple_files=True, key="term_up")

if term_files:
    c1, c2, c3 = st.columns(3)
    
    # --- 1.1 Hourly ---
    with c1:
        st.write("##### 📊 Hourly")
        if st.button("Convert Hourly 🚀", key="btn_hourly"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in term_files:
                    f.seek(0)
                    df = pd.read_csv(f, header=None)
                    s, d, suf = get_info_term(df)
                    mask = df.iloc[:,0] == 'Time'
                    if mask.any():
                        idx = df[mask].index[0]
                        out = df.iloc[idx+1:idx+25, 0:7].copy()
                        out.columns = ['Time','Sales ($)','Sales %','Receipt','Receipt %','Guest','Qty Sold']
                        out['Time'] = out['Time'].str.replace(' -', '', regex=False)
                        out.insert(0,'Store',s); out.insert(1,'Date',d)
                        zf.writestr(f"{s}{suf}.csv", out.to_csv(index=False, encoding='utf-8-sig'))
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download Hourly", buf.getvalue(), "Hourly_Report.zip", "application/zip")

    # --- 1.2 TS Summary ---
    with c2:
        st.write("##### 📑 TS Summary")
        if st.button("Convert TS 🚀", key="btn_ts"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in term_files:
                    f.seek(0)
                    df = pd.read_csv(f, header=None)
                    s, d, suf = get_info_term(df)
                    s_mask = df.iloc[:,0] == 'TOTAL BEFORE SUBTOTAL DISC/SUR'
                    e_mask = df.iloc[:,0] == 'GROSS SALES'
                    if s_mask.any() and e_mask.any():
                        idx1 = df[s_mask].index[0]; idx2 = df[e_mask].index[0]
                        out = df.iloc[idx1:idx2+1, 0:2].copy()
                        out.insert(0,'S',s); out.insert(1,'D',d)
                        out.iloc[0,0] = "Store"; out.iloc[0,1] = "Date"
                        zf.writestr(f"TS {s}{suf}.csv", out.to_csv(index=False, header=False, encoding='utf-8-sig'))
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download TS", buf.getvalue(), "TS_Report.zip", "application/zip")

    # --- 1.3 Term OG ---
    with c3:
        st.write("##### 💾 Term OG")
        if st.button("Convert Term OG 🚀", key="btn_term_og"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in term_files:
                    f.seek(0)
                    df = pd.read_csv(f, header=None)
                    s, d, suf = get_info_term(df)
                    zf.writestr(f"{s}{suf}OG.csv", df.to_csv(index=False, header=False, encoding='utf-8-sig'))
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download OG", buf.getvalue(), "Term_OG.zip", "application/zip")

# ==========================================
# 3. UI SECTION: E-JOURNAL FILE
# ==========================================
st.divider()
st.markdown('<div class="sub-header">📂 2. E-Journal Files Convert</div>', unsafe_allow_html=True)

ej_files = st.file_uploader("เลือกไฟล์ E-Journal (CSV)", type="csv", accept_multiple_files=True, key="ej_up")

if ej_files:
    ec1, ec2, ec3 = st.columns(3)

    # --- 2.1 EJ Report (Updated Logic) ---
    with ec1:
        st.write("##### 📋 EJ Report")
        if st.button("Convert EJ Report 🚀", key="btn_ej"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in ej_files:
                    f.seek(0)
                    df = pd.read_csv(f, header=None)
                    
                    # เรียกใช้ Logic ที่ปรับปรุงใหม่
                    df_out, s, d = process_ej_report_logic(df)
                    
                    if df_out is not None:
                        suf = datetime.strptime(d, '%d/%m/%Y').strftime('%Y%m%d')
                        # Save แบบไม่มี Header เหมือน VBA (Paste Values)
                        zf.writestr(f"EJ_{s}{suf}.csv", df_out.to_csv(index=False, header=False, encoding='utf-8-sig'))
            
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download EJ Report", buf.getvalue(), "EJ_Report.zip", "application/zip")
    # --- 2.2 EJ OG ---
    with ec3:
        st.write("##### 💾 EJ OG")
        if st.button("Convert EJ OG 🚀", key="btn_ej_og"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in ej_files:
                    f.seek(0)
                    df = pd.read_csv(f, header=None)
                    s, d, suf = get_info_ejournal(df)
                    zf.writestr(f"EJ_OG{s}{suf}.csv", df.to_csv(index=False, header=False, encoding='utf-8-sig'))
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download EJ OG", buf.getvalue(), "EJ_OG.zip", "application/zip")

    # --- 2.3 Receipt Extract ---
    with ec2:
        st.write("##### 🧾 Receipt Extract")
        if st.button("Convert Extract Receipt 🚀", key="btn_recon"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in ej_files:
                    f.seek(0)
                    df_out = parse_receipt_data(f)
                    if df_out is not None and not df_out.empty:
                        zf.writestr(f"Recon_{f.name}", df_out.to_csv(index=False, encoding='utf-8-sig'))
            st.success("เสร็จสิ้น!")
            st.download_button("📥 Download Recon", buf.getvalue(), "Receipt_Extract.zip", "application/zip")


    
