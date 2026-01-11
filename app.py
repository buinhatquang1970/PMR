import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import os
import html
import logging
from datetime import datetime
from tool_tinh_toan import ToolAnDinhTanSo

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CẤU HÌNH PHIÊN BẢN (BẠN CẬP NHẬT Ở ĐÂY)
# =============================================================================
APP_VERSION = "1.0"  # <--- Thay đổi số này khi bạn cập nhật phần mềm (VD: 1.1, 1.2...)

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title=f"Công cụ Ấn định Tần số (v{APP_VERSION})", layout="wide")

# --- HẠN CHẾ KÍCH THƯỚC UPLOAD (MB) ---
MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# --- KHỞI TẠO BỘ NHỚ ĐỆM ---
if 'results' not in st.session_state:
    st.session_state.results = None
if 'input_snapshot' not in st.session_state:
    st.session_state.input_snapshot = None
if 'last_uploaded_file_id' not in st.session_state:
    st.session_state.last_uploaded_file_id = None

# CSS TÙY CHỈNH NÂNG CAO
st.markdown("""
    <style>
        /* --- 1. ẨN THANH HEADER MẶC ĐỊNH CỦA STREAMLIT --- */
        header[data-testid="stHeader"] {
            display: none;
        }

        /* --- ĐẨY NỘI DUNG SÁT LÊN TRÊN --- */
        .block-container {
            padding-top: 0rem !important; 
            padding-bottom: 2rem;
        }

        h2 {
            margin-top: 0.5rem;
            margin-bottom: 0rem !important;
        }
        .version-text {
            text-align: center;
            color: #888;
            font-size: 0.8rem;
            margin-bottom: 1rem;
            font-style: italic;
        }
        div[data-testid="stMarkdownContainer"] > p {
            margin-bottom: -3px !important;
            font-weight: 500;
        }
        [data-testid="stHorizontalBlock"] {
            gap: 0.1rem !important;
        }
        .stCaption {
            font-size: 0.7rem;
            margin-top: -5px;
            color: #555;
        }
        hr {
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }
        h3 {
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
        }

        /* --- CSS TỐI ƯU KHUNG UPLOAD --- */
        [data-testid='stFileUploader'] {
            height: 65px !important; 
            overflow: hidden !important; 
            margin-bottom: 0px !important;
            padding-top: 0px;
        }
        [data-testid='stFileUploader'] section {
            padding: 0.5rem !important;
            min-height: 0px !important; 
        }
        [data-testid='stFileUploader'] section > div > div > span {
            display: none;
        }
        [data-testid='stFileUploader'] section > div > div::after {
            content: "Nhập file Excel (xlsx)";
            display: block;
            font-weight: bold;
            color: #333;
        }
        [data-testid='stFileUploader'] section small {
            display: none;
        }

        /* CSS cho nút Google Maps */
        div[data-testid="stColumn"] button[kind="secondary"] {
            color: #d93025 !important;
            font-weight: bold !important;
            border: 1px solid #ddd !important;
            background-color: #fff !important;
            width: 100%;
            transition: all 0.3s;
        }
        div[data-testid="stColumn"] button[kind="secondary"]:hover {
            background-color: #fce8e6 !important;
            border-color: #d93025 !important;
            color: #d93025 !important;
        }

        /* CSS nút Tính toán */
        button[kind="primary"] {
            font-weight: bold !important;
            margin-top: 5px; 
        }

        /* --- CSS SỬA LỖI BẢNG KẾT QUẢ BỊ CO --- */
        div[data-testid="stTable"] table {
            width: 100% !important; 
        }
        div[data-testid="stTable"] th {
            background-color: #f0f2f6 !important;
            color: #31333F !important;
            font-size: 1.2rem !important; 
            font-weight: 800 !important;  
            text-align: center !important; 
            white-space: nowrap !important; 
            padding: 15px !important;
        }
        div[data-testid="stTable"] td {
            font-size: 1.1rem !important;
            text-align: center !important; 
            vertical-align: middle !important;
            padding: 12px !important;
            min-width: 200px !important; 
        }

        /* --- CSS TÙY CHỈNH POPUP (DIALOG) --- */
        div[role="dialog"] {
            width: 50vw !important;        
            max-width: 50vw !important;
            left: auto !important;         
            right: 0 !important;           
            top: 0 !important;             
            bottom: 0 !important;          
            height: 100vh !important;      
            margin: 0 !important;
            border-radius: 0 !important;   
            transform: none !important;    
            display: flex;
            flex-direction: column;
        }

        /* --- FIX: tránh selectbox bị truncate --- */
        div[data-testid="stSelectbox"] > div,
        div[data-testid="stSelectbox"] button,
        div[data-testid="stSelectbox"] select {
            min-width: 120px !important;
            max-width: 320px !important;
            white-space: nowrap !important;
            overflow: visible !important;
            text-overflow: clip !important;
            display: inline-block !important;
        }
        div[role="combobox"] > div,
        div[role="combobox"] button,
        div[role="combobox"] select {
            min-width: 120px !important;
            max-width: 320px !important;
            white-space: nowrap !important;
            overflow: visible !important;
            text-overflow: clip !important;
            display: inline-block !important;
        }
        .stTextInput, .stSelectbox, .stNumberInput, .stDateInput {
            min-width: 80px !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- HÀM CHUYỂN ĐỔI DMS -> DECIMAL ---
def dms_to_decimal(d, m, s):
    return d + (m / 60.0) + (s / 3600.0)

# --- HÀM NEUTRALIZE DỮ LIỆU TRƯỚC KHI GHI EXCEL ---
def neutralize_excel_value(val):
    if pd.isna(val):
        return val
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@'):
        return "'" + s
    return s

def neutralize_df_for_excel(df):
    try:
        return df.applymap(neutralize_excel_value)
    except Exception:
        return df.astype(str).applymap(neutralize_excel_value)

# --- HÀM XUẤT EXCEL (ĐÃ SỬA: GỘP CHUNG 1 SHEET) ---
def to_excel(df_input, df_result):
    output = io.BytesIO()
    df_input_safe = neutralize_df_for_excel(df_input.copy())
    df_result_safe = neutralize_df_for_excel(df_result.copy())

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = 'KET_QUA_TINH_TOAN'
        df_input_safe.to_excel(writer, index=False, sheet_name=sheet_name, startrow=1)
        start_row_result = len(df_input_safe) + 5
        df_result_safe.to_excel(writer, sheet_name=sheet_name, startrow=start_row_result)
        
        # Thêm tiêu đề
        worksheet = writer.sheets[sheet_name]
        cell_input_title = worksheet.cell(row=1, column=1, value="I. THÔNG SỐ ĐẦU VÀO")
        cell_result_title = worksheet.cell(row=start_row_result, column=1, value="II. KẾT QUẢ TÍNH TOÁN")
        try:
            from openpyxl.styles import Font
            bold_font = Font(bold=True, size=11)
            cell_input_title.font = bold_font
            cell_result_title.font = bold_font
        except Exception:
            logger.debug("openpyxl.styles not available or formatting failed", exc_info=True)
    return output.getvalue()

# --- HÀM HIỂN THỊ POPUP BẢN ĐỒ ---
@st.dialog("Vị trí trên Google Maps")
def show_map_popup(lat, lon):
    map_url = f"https://www.google.com/maps?q={lat},{lon}&z=15&output=embed"
    st.write(f"📍 Tọa độ: {lat:.5f}, {lon:.5f}")
    components.iframe(map_url, height=600)

# =============================================================================
# PHẦN BANNER VÀ TIÊU ĐỀ
# =============================================================================
banner_file = "logo_CTS.jpg"
if os.path.exists(banner_file):
    st.image(banner_file, use_container_width=True)
else:
    st.warning(f"⚠️ Chưa tìm thấy file '{banner_file}'. Vui lòng copy file ảnh vào cùng thư mục với app.py")

st.markdown("<h2 style='text-align: center; color: #0068C9;'>CÔNG CỤ ẤN ĐỊNH TẦN SỐ MẠNG DÙNG RIÊNG</h2>", unsafe_allow_html=True)
# --- HIỂN THỊ PHIÊN BẢN ---
st.markdown(f"<p class='version-text'>Phiên bản: {APP_VERSION}</p>", unsafe_allow_html=True)
st.markdown("---")

# =============================================================================
# BỐ CỤC CHÍNH: 2 CỘT
# =============================================================================
col_layout_left, col_space_layout, col_layout_right = st.columns([1.8, 0.1, 1.2])

# ----------------------------------------------------------------------------- 
# CỘT TRÁI: MỤC 1
# ----------------------------------------------------------------------------- 
with col_layout_left:
    st.subheader("1. THÔNG SỐ KỸ THUẬT & VỊ TRÍ MẠNG")

    # --- HÀNG 1: TỌA ĐỘ VÀ NÚT MAPS ---
    c_grp1, c_sep1, c_grp2, c_sep2, c_grp3 = st.columns([1.3, 0.1, 1.3, 0.1, 1.5])

    # 1. KINH ĐỘ
    with c_grp1:
        st.markdown("📍 **Kinh độ (Longitude)**")
        c1_d, c1_m, c1_s = st.columns([1, 1, 1.2])
        with c1_d: lon_d = st.number_input("Độ", 0, 180, 105, 1, key="lon_d", label_visibility="collapsed")
        with c1_m: lon_m = st.number_input("Phút", 0, 59, 0, 1, key="lon_m", label_visibility="collapsed")
        with c1_s: lon_s = st.number_input("Giây", 0.0, 59.99, 0.0, 0.1, "%.2f", key="lon_s", label_visibility="collapsed")
        lon = dms_to_decimal(lon_d, lon_m, lon_s)

    # 2. VĨ ĐỘ
    with c_grp2:
        st.markdown("📍 **Vĩ độ (Latitude)**")
        c2_d, c2_m, c2_s = st.columns([1, 1, 1.2])
        with c2_d: lat_d = st.number_input("Độ", 0, 90, 21, 1, key="lat_d", label_visibility="collapsed")
        with c2_m: lat_m = st.number_input("Phút", 0, 59, 0, 1, key="lat_m", label_visibility="collapsed")
        with c2_s: lat_s = st.number_input("Giây", 0.0, 59.99, 0.0, 0.1, "%.2f", key="lat_s", label_visibility="collapsed")
        lat = dms_to_decimal(lat_d, lat_m, lat_s)

    # 3. NÚT GOOGLE MAPS (DẠNG POPUP)
    with c_grp3:
        st.markdown("🗺️ **Bản đồ**")
        if lat != 0 and lon != 0:
            if st.button("👉 Xem vị trí trên bản đồ", use_container_width=True):
                show_map_popup(lat, lon)
        else:
            st.button("👉 Xem vị trí trên bản đồ", disabled=True, use_container_width=True)

    # --- HÀNG 2: CÁC THÔNG SỐ KHÁC ---
    c_mode, c1, c2, c3, c4, c5 = st.columns([1.3, 0.8, 0.8, 0.9, 1.2, 0.7])

    # 4. LOẠI MẠNG
    with c_mode:
        st.markdown("📡 **Loại mạng**")
        mode = st.selectbox("Loại mạng", ["LAN", "WAN_SIMPLEX", "WAN_DUPLEX"], label_visibility="collapsed")

    with c1:
        st.markdown("**Độ cao (m)**")
        h_anten = st.number_input("Độ cao", value=0.0, step=1.0, label_visibility="collapsed")
    with c2:
        st.markdown("**Dải tần**")
        band = st.selectbox("Dải tần", ["VHF", "UHF"], label_visibility="collapsed")
    with c3:
        st.markdown("**Băng thông**")
        bw = st.selectbox("Băng thông", [6.25, 12.5, 25.0], index=1, label_visibility="collapsed")

    with c4:
        st.markdown("**Tỉnh / Thành phố**")
        is_wan = "WAN" in mode

        province_selection = st.selectbox(
            "Chọn Tỉnh/TP",
            ["-- Chọn Tỉnh/TP --", "HANOI", "HCM", "DANANG", "KHAC"],
            index=0,
            label_visibility="collapsed",
            disabled=is_wan
        )

        province_manual_input = ""
        if province_selection == "KHAC" and not is_wan:
            province_manual_input = st.text_input(
                "Nhập tên Tỉnh/TP cụ thể:",
                placeholder="Ví dụ: Bà Rịa Vũng Tàu",
                label_visibility="collapsed"
            )

    with c5:
        st.markdown("**Số lượng**")
        qty = st.number_input("Số lượng", value=1, min_value=1, label_visibility="collapsed")

# ----------------------------------------------------------------------------- 
# CỘT PHẢI: MỤC 2 & MỤC 3
# ----------------------------------------------------------------------------- 
with col_layout_right:
    st.subheader("2. NẠP DỮ LIỆU ĐẦU VÀO")

    uploaded_file = st.file_uploader("Label ẩn", type=['xls', 'xlsx', 'csv'], label_visibility="collapsed")

    # Kiểm tra kích thước file
    if uploaded_file is not None:
        size = getattr(uploaded_file, "size", None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            st.error(f"File quá lớn (> {MAX_UPLOAD_MB} MB). Vui lòng giảm kích thước hoặc dùng file nhỏ hơn.")
            st.stop()

    # --- RESET KẾT QUẢ KHI ĐỔI FILE ---
    if uploaded_file is not None:
        current_file_id = f"{uploaded_file.name}_{getattr(uploaded_file, 'size', '')}"
        if st.session_state.last_uploaded_file_id != current_file_id:
            st.session_state.results = None
            st.session_state.input_snapshot = None
            st.session_state.last_uploaded_file_id = current_file_id
            st.rerun()

        safe_name = html.escape(uploaded_file.name)
        file_status_html = f"✅ Đã nhận: {safe_name}"
    else:
        if st.session_state.last_uploaded_file_id is not None:
            st.session_state.results = None
            st.session_state.input_snapshot = None
            st.session_state.last_uploaded_file_id = None
            st.rerun()

        file_status_html = " "

    st.markdown(f"""
        <div style='height: 20px; margin-top: 2px; margin-bottom: 0px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #28a745; font-weight: 500; font-size: 0.8rem;'>
            {file_status_html}
        </div>
    """, unsafe_allow_html=True)

    # --- MỤC 3: TÍNH TOÁN ---
    btn_disabled = True if uploaded_file is None else False
    btn_calc = st.button("TÍNH TOÁN TẦN SỐ KHẢ DỤNG", type="primary", use_container_width=True, disabled=btn_disabled)

# =============================================================================
# XỬ LÝ LOGIC
# =============================================================================
if btn_calc:
    error_msg = []
    if lon == 0.0: error_msg.append("Kinh độ chưa nhập")
    if lat == 0.0: error_msg.append("Vĩ độ chưa nhập")

    if "LAN" in mode:
        if province_selection == "-- Chọn Tỉnh/TP --":
            error_msg.append("Thiếu Tỉnh/TP (Bắt buộc cho mạng LAN)")
        if province_selection == "KHAC" and province_manual_input.strip() == "":
            error_msg.append("Vui lòng nhập tên Tỉnh/TP cụ thể")

    if error_msg:
        st.error(f"⚠️ LỖI: {', '.join(error_msg)}")
    else:
        prov_to_send = province_selection
        if province_selection == "KHAC":
            prov_to_send = province_manual_input

        if "WAN" in mode:
            prov_to_send = "KHAC"

        if h_anten == 0.0:
            st.warning("⚠️ Lưu ý: Độ cao Anten đang là 0m.")

        with st.spinner('Đang tính toán...'):
            try:
                tool = ToolAnDinhTanSo(uploaded_file)
                user_input = {
                    "lat": lat, "lon": lon,
                    "province_code": prov_to_send,
                    "antenna_height": h_anten,
                    "band": band, "bw": bw, "usage_mode": mode
                }

                results = tool.tinh_toan(user_input)

                st.session_state.results = results
                # --- LƯU THÔNG SỐ ĐẦU VÀO (KÈM PHIÊN BẢN) ---
                st.session_state.input_snapshot = {
                    "THAM SỐ": [
                        "Phiên bản App", # Thêm dòng này
                        "Kinh độ (Decimal)", "Vĩ độ (Decimal)",
                        "Kinh độ (DMS)", "Vĩ độ (DMS)",
                        "Tỉnh / Thành phố", "Độ cao Anten (m)",
                        "Dải tần", "Băng thông (kHz)",
                        "Loại mạng", "Số lượng xin"
                    ],
                    "GIÁ TRỊ": [
                        APP_VERSION, # Giá trị phiên bản
                        lon, lat,
                        f"{lon_d}° {lon_m}' {lon_s}\"", f"{lat_d}° {lat_m}' {lat_s}\"",
                        prov_to_send if "LAN" in mode else "Toàn quốc (WAN)", h_anten,
                        band, bw,
                        mode, qty
                    ]
                }
            except Exception as e:
                logger.exception("Lỗi khi tính toán", exc_info=e)
                st.error(f"Có lỗi xảy ra: {e}")

# --- HIỂN THỊ KẾT QUẢ ---
if st.session_state.results is not None:
    st.markdown("---")
    st.subheader("📊 KẾT QUẢ TÍNH TOÁN")

    results = st.session_state.results

    if not results:
        st.error("❌ Không tìm thấy tần số khả dụng!")
    else:
        df_res = pd.DataFrame(results)

        df_res = df_res[["STT", "frequency", "reuse_factor", "license_list"]]
        df_res.columns = ["STT", "Tần số Khả dụng (MHz)", "Hệ số Tái sử dụng (Điểm)", "Chú thích (Số GP)"]
        df_res.set_index("STT", inplace=True)

        m1, m2 = st.columns(2)
        m1.metric("Số lượng tìm thấy", f"{len(results)}")
        best_freq = results[0]['frequency']
        m2.metric("Tần số tốt nhất", f"{best_freq} MHz")

        st.table(df_res.head(qty))

        with st.expander("Xem danh sách đầy đủ"):
            st.dataframe(df_res, use_container_width=True)

        if st.session_state.input_snapshot:
            df_input_report = pd.DataFrame(st.session_state.input_snapshot)
            excel_data = to_excel(df_input_report, df_res)

            now = datetime.now()
            time_str = now.strftime("%H%M%Y")

            input_file_name = "data"
            if uploaded_file is not None:
                input_file_name = os.path.splitext(uploaded_file.name)[0]

            # --- TÊN FILE KÈM VERSION ---
            dl_file_name = f"ket_qua_an_dinh_{time_str}_{input_file_name}_v{APP_VERSION}.xlsx"

            st.markdown("---")
            st.download_button(
                label=f"LƯU KẾT QUẢ(EXCEL)",
                data=excel_data,
                file_name=dl_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True

            )
