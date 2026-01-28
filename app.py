import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import os
import html
import logging
# from datetime import datetime
# Thêm timedelta và timezone để xử lý cộng giờ
from datetime import datetime, timedelta, timezone
from tool_tinh_toan import ToolAnDinhTanSo
import importlib

# --- IMPORT AN TOÀN CHO BIẾN MÀU SẮC & QUY HOẠCH TẦN SỐ ---
try:
    import config
    importlib.reload(config) # Reload tại đây để cập nhật màu mới nhất
    PRIORITY_HIGHLIGHT_COLOR = getattr(config, 'PRIORITY_HIGHLIGHT_COLOR', '#F6BE00')
    # Lấy bảng phân bổ để hiển thị lên Combobox
    ALLOC_VHF = getattr(config, 'FREQUENCY_ALLOCATION_VHF', [])
    ALLOC_UHF = getattr(config, 'FREQUENCY_ALLOCATION_UHF', [])
except:
    PRIORITY_HIGHLIGHT_COLOR = '#F6BE00' # Màu mặc định nếu lỗi
    ALLOC_VHF = []
    ALLOC_UHF = []

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- APP VERSION ---
# --- APP VERSION TỰ ĐỘNG THEO QUI TẮC v.ddmmyy.H (Giờ 12h) ---
try:
    file_timestamp = os.path.getmtime(__file__)
    
    # Tạo múi giờ Việt Nam (GMT+7)
    vn_tz = timezone(timedelta(hours=7))
    
    # Chuyển đổi timestamp sang datetime có múi giờ
    dt_vn = datetime.fromtimestamp(file_timestamp, vn_tz)
    
    # Xử lý giờ theo hệ 12h (23h -> 11, 20h -> 8)
    hour_12 = dt_vn.hour % 12
    if hour_12 == 0: hour_12 = 12
    
    # Format thành chuỗi vddmmyy.H
    APP_VERSION = f"v{dt_vn.strftime('%d%m%y')}.{hour_12}"
except Exception:
    APP_VERSION = "v280126.1"

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title=f"PMR tool ({APP_VERSION})", layout="wide")

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
if 'check_result' not in st.session_state:
    st.session_state.check_result = None
if 'bad_freq_results' not in st.session_state:
    st.session_state.bad_freq_results = None
if 'active_view' not in st.session_state:
    st.session_state.active_view = None 

# CSS TÙY CHỈNH
st.markdown("""
    <style>
        .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem; }
        h2 { font-size: 1.3rem !important; margin-top: 0.5rem; margin-bottom: 0.2rem !important; }
        h3 { font-size: 0.95rem !important; padding-top: 0.2rem !important; padding-bottom: 0.2rem !important; }
        div[data-testid="stMarkdownContainer"] > p { margin-bottom: -3px !important; font-weight: 500; }
        [data-testid="stHorizontalBlock"] { gap: 0.1rem !important; }
        .stCaption { font-size: 0.7rem; margin-top: -5px; color: #555; }
        hr { margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
        
        [data-testid='stFileUploader'] { margin-bottom: -30px !important; }
        [data-testid='stFileUploader'] section { padding: 0.5rem !important; min-height: 0px !important; }
        [data-testid='stFileUploader'] section > div > div > span { display: none; }
        [data-testid='stFileUploader'] section > div > div::after { 
            content: "Lưu ý: Chỉ nhận file Excel(.xlsx)"; display: block; font-weight: bold; color: #333; 
        }
        [data-testid='stFileUploader'] section small { display: none; }

        div[data-testid="stColumn"] button[kind="secondary"] { color: #d93025 !important; font-weight: bold !important; border: 1px solid #ddd !important; background-color: #fff !important; width: 100%; transition: all 0.3s; }
        div[data-testid="stColumn"] button[kind="secondary"]:hover { background-color: #fce8e6 !important; border-color: #d93025 !important; color: #d93025 !important; }
        button[kind="primary"] { font-weight: bold !important; margin-top: 5px; }
        
        div[data-testid="stTable"] table { width: 100% !important; }
        div[data-testid="stTable"] th { background-color: #f0f2f6 !important; color: #31333F !important; font-size: 1.2rem !important; font-weight: 800 !important; text-align: center !important; white-space: nowrap !important; padding: 15px !important; }
        div[data-testid="stTable"] td { font-size: 1.1rem !important; text-align: center !important; vertical-align: middle !important; padding: 12px !important; min-width: 200px !important; }
        
        div[role="dialog"] { width: 50vw !important; max-width: 50vw !important; left: auto !important; right: 0 !important; top: 0 !important; bottom: 0 !important; height: 100vh !important; margin: 0 !important; border-radius: 0 !important; transform: none !important; display: flex; flex-direction: column; }
        
        div[data-testid="stSelectbox"] > div, div[data-testid="stSelectbox"] button, div[data-testid="stSelectbox"] select { min-width: 60px !important; max-width: 100% !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; display: inline-block !important; }
        .stTextInput, .stSelectbox, .stNumberInput, .stDateInput { min-width: 50px !important; }

        /* CSS CHO TOOLTIP HƯỚNG DẪN SỬ DỤNG */
        .tooltip-container {
          position: relative;
          display: inline-block;
          cursor: help;
          color: #0068C9;
          font-weight: bold;
          margin-right: 15px;
          z-index: 9999;
        }
        .tooltip-container .tooltiptext {
          visibility: hidden;
          width: 500px;
          background-color: #ffffff;
          color: #333;
          text-align: left;
          border-radius: 6px;
          padding: 15px;
          position: absolute;
          z-index: 10000;
          top: 100%;
          right: 0;
          box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.3);
          border: 1px solid #ddd;
          font-size: 0.9rem;
          font-weight: normal;
          line-height: 1.5;
          max-height: 60vh;
          overflow-y: auto;
        }
        .tooltip-container:hover .tooltiptext {
          visibility: visible;
        }
        .tooltiptext strong { color: #0068C9; }
    </style>
""", unsafe_allow_html=True)

def dms_to_decimal(d, m, s): return d + (m / 60.0) + (s / 3600.0)

def neutralize_excel_value(val):
    if pd.isna(val): return val
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@'): return "'" + s
    return s

def neutralize_df_for_excel(df):
    try: return df.applymap(neutralize_excel_value)
    except Exception: return df.astype(str).applymap(neutralize_excel_value)

def to_excel(df_input, df_result):
    output = io.BytesIO()
    if df_input is not None:
        df_input_safe = neutralize_df_for_excel(df_input.copy())
    else:
        df_input_safe = None
    
    if 'is_priority' in df_result.columns:
        df_result_clean = df_result.drop(columns=['is_priority'])
    else:
        df_result_clean = df_result
        
    df_result_safe = neutralize_df_for_excel(df_result_clean.copy())

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = 'KET_QUA_TINH_TOAN'
        start_row_result = 1
        
        if df_input_safe is not None:
            df_input_safe.to_excel(writer, index=False, sheet_name=sheet_name, startrow=1)
            start_row_result = len(df_input_safe) + 5
            
        df_result_safe.to_excel(writer, sheet_name=sheet_name, startrow=start_row_result, index=False)
        worksheet = writer.sheets[sheet_name]
        
        if df_input_safe is not None:
            cell_input_title = worksheet.cell(row=1, column=1, value="I. THÔNG SỐ ĐẦU VÀO")
            cell_result_title = worksheet.cell(row=start_row_result, column=1, value="II. KẾT QUẢ TÍNH TOÁN")
        else:
            cell_result_title = worksheet.cell(row=start_row_result, column=1, value="DANH SÁCH KẾT QUẢ")

        try:
            from openpyxl.styles import Font
            bold_font = Font(bold=True, size=11)
            if df_input_safe is not None:
                cell_input_title.font = bold_font
            cell_result_title.font = bold_font
            
        except Exception:
            pass
    return output.getvalue()

@st.dialog("Vị trí trên Google Maps")
def show_map_popup(lat, lon):
    map_url = f"https://www.google.com/maps?q={lat},{lon}&z=15&output=embed"
    st.write(f"📍 Tọa độ: {lat:.5f}, {lon:.5f}")
    components.iframe(map_url, height=600)

banner_file = "logo_CTS.jpg" 
if os.path.exists(banner_file):
    st.image(banner_file)
else:
    st.warning(f"⚠️ Chưa tìm thấy file '{banner_file}'.")

# --- NỘI DUNG HƯỚNG DẪN SỬ DỤNG ---
help_html = """<span class='tooltip-container'>📖 Hướng dẫn sử dụng
<span class='tooltiptext'>
<h4 style='margin:0; text-align:center; color:#0068C9'>HƯỚNG DẪN SỬ DỤNG NHANH</h4><hr>
<strong>1. Chuẩn bị dữ liệu đầu vào</strong><br>
• File Excel (.xlsx) trích xuất từ PM cấp phép.<br>
• Các trường tối thiểu cần có : Số GP, Tần số, Tọa độ, Độ cao, Khách hàng.<br>
<strong>2. Nhập thông số (Cột bên trái)</strong><br>
• Nhập Tọa độ, Loại mạng (LAN/WAN), Độ cao, Dải tần.<br>
• <strong>Đoạn băng tần quét:</strong> Chọn dải tần con (VD: 141.5 - 142.0).<br>
• Chọn Tỉnh/TP (với mạng LAN).<br><br>
<strong>3. Các chức năng tính toán</strong><br>
• <strong>TÍNH TẦN SỐ KHẢ DỤNG:</strong> Tìm tần số sạch, sắp xếp theo độ ưu tiên.<br>
• <strong>LỌC TS KHÔNG KHẢ DỤNG:</strong> Tìm tần số gây nhiễu và nguyên nhân.<br>
• <strong>KIỂM TRA CỤ THỂ:</strong> Kiểm tra nhanh 1 tần số bất kỳ xem có gây nhiễu hay không.<br><br>
<strong>4. Lưu kết quả</strong><br>
• Nút <strong>📥 LƯU KẾT QUẢ (EXCEL)</strong> sẽ xuất hiện sau khi tính xong.<br><br>
<strong>5. Cách đọc kết quả</strong><br>
• Cột "Các GP sử dụng tần số này" hiển thị dạng: <strong>SốGP(Khoảng_cách_km)</strong><br>
• VD: 399123(65) -> GP 399123 đang dùng, cách 65km.
</span>
</span>"""

st.markdown("<h2 style='text-align: center; color: #0068C9;'>Ấn định tần số cho mạng nội bộ dùng riêng </h2>", unsafe_allow_html=True)
# --- HIỂN THỊ HƯỚNG DẪN SỬ DỤNG + PHIÊN BẢN ---
st.markdown(f"<div style='text-align: right; color: #666; font-size:0.85rem; margin-top:-8px;'>{help_html} | Phiên bản: {APP_VERSION}</div>", unsafe_allow_html=True)
st.markdown("---")

col_layout_left, col_space_layout, col_layout_right = st.columns([1.8, 0.1, 1.2])

with col_layout_left:
    st.subheader("1. THÔNG SỐ KỸ THUẬT & VỊ TRÍ MẠNG")
    c_grp1, c_sep1, c_grp2, c_sep2, c_grp3 = st.columns([1.3, 0.1, 1.3, 0.1, 1.5])
    
    with c_grp1:
        st.markdown("📍 **Kinh độ (Longitude)**")
        c1_d, c1_m, c1_s = st.columns([1, 1, 1.2])
        with c1_d: lon_d = st.number_input("Độ", 0, 180, 105, 1, key="lon_d", label_visibility="collapsed")
        with c1_m: lon_m = st.number_input("Phút", 0, 59, 0, 1, key="lon_m", label_visibility="collapsed")
        with c1_s: lon_s = st.number_input("Giây", 0.0, 59.99, 0.0, 0.1, "%.2f", key="lon_s", label_visibility="collapsed")
        lon = dms_to_decimal(lon_d, lon_m, lon_s)

    with c_grp2:
        st.markdown("📍 **Vĩ độ (Latitude)**")
        c2_d, c2_m, c2_s = st.columns([1, 1, 1.2])
        with c2_d: lat_d = st.number_input("Độ", 0, 90, 21, 1, key="lat_d", label_visibility="collapsed")
        with c2_m: lat_m = st.number_input("Phút", 0, 59, 0, 1, key="lat_m", label_visibility="collapsed")
        with c2_s: lat_s = st.number_input("Giây", 0.0, 59.99, 0.0, 0.1, "%.2f", key="lat_s", label_visibility="collapsed")
        lat = dms_to_decimal(lat_d, lat_m, lat_s)

    with c_grp3:
        st.markdown("🗺️ **Bản đồ**")
        if lat != 0 and lon != 0:
            if st.button("👉 Xem vị trí trên bản đồ", use_container_width=True): show_map_popup(lat, lon)
        else: st.button("👉 Xem vị trí trên bản đồ", disabled=True, use_container_width=True)

    c_mode, c_h, c_band, c_subband, c_bw = st.columns([1.2, 0.7, 0.7, 1.6, 0.8], gap="small")
    
    with c_mode:
        st.markdown("📡 **Loại mạng**")
        mode = st.selectbox("Loại mạng", ["LAN", "WAN_SIMPLEX", "WAN_DUPLEX"], label_visibility="collapsed")

    with c_h:
        st.markdown("**Độ cao (m)**")
        h_anten = st.number_input("Độ cao", value=0.0, step=1.0, label_visibility="collapsed")
    
    with c_band:
        st.markdown("**Dải tần**")
        band = st.selectbox("Dải tần", ["VHF", "UHF"], label_visibility="collapsed")
        
    with c_subband:
        st.markdown("**Đoạn băng tần quét**")
        if band == "VHF":
            current_alloc = ALLOC_VHF
        else:
            current_alloc = ALLOC_UHF
            
        subband_map = {}
        subband_labels = []
        
        for item in current_alloc:
            s_f, e_f, m_list, note = item
            if mode in m_list:
                label = f"{s_f} - {e_f} MHz ({note})"
                subband_map[label] = (s_f, e_f)
                subband_labels.append(label)
            
        selected_subband_label = st.selectbox("Chọn dải con", subband_labels, label_visibility="collapsed")
        scan_start, scan_end = subband_map.get(selected_subband_label, (0, 0))

    with c_bw:
        st.markdown("**Băng thông**")
        bw = st.selectbox("Băng thông", [6.25, 12.5, 25.0], index=1, label_visibility="collapsed")
    
    # --- ĐỘ RỘNG CỘT TỈNH = LOẠI MẠNG (1.2) ---
    c_prov, c_qty, c_space = st.columns([1.2, 0.8, 3.0], gap="small")
    with c_prov:
        st.markdown("**Tỉnh / Thành phố**")
        is_wan = "WAN" in mode
        province_selection = st.selectbox("Chọn Tỉnh/TP", ["-- Chọn Tỉnh/TP --", "HANOI", "HCM", "DANANG", "KHAC"], index=0, label_visibility="collapsed", disabled=is_wan)
        province_manual_input = ""
        if province_selection == "KHAC" and not is_wan:
            province_manual_input = st.text_input("Nhập tên Tỉnh/TP cụ thể:", placeholder="Ví dụ: Bà Rịa Vũng Tàu", label_visibility="collapsed")
    
    with c_qty:
        st.markdown("**Số lượng**")
        qty = st.number_input("Số lượng", value=1, min_value=1, label_visibility="collapsed")
    
    with c_space:
        st.empty() # Cột trống để căn lề

with col_layout_right:
    st.subheader("2. NẠP DỮ LIỆU ĐẦU VÀO")
    uploaded_file = st.file_uploader("Label ẩn", type=None, label_visibility="collapsed")
    
    btn_disabled = True 
    if uploaded_file is not None:
        size = getattr(uploaded_file, "size", None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            st.error(f"File quá lớn (> {MAX_UPLOAD_MB} MB).")
            btn_disabled = True
        elif not uploaded_file.name.lower().endswith('.xlsx'):
            st.error("⚠️ Cần nhập file định dạng xlsx")
            btn_disabled = True
        else:
            current_file_id = f"{uploaded_file.name}_{getattr(uploaded_file, 'size', '')}"
            if st.session_state.last_uploaded_file_id != current_file_id:
                st.session_state.results = None
                st.session_state.input_snapshot = None
                st.session_state.check_result = None
                st.session_state.bad_freq_results = None
                st.session_state.active_view = None
                st.session_state.last_uploaded_file_id = current_file_id
                st.rerun() 
            btn_disabled = False 
    else:
        if st.session_state.last_uploaded_file_id is not None:
            st.session_state.results = None
            st.session_state.input_snapshot = None
            st.session_state.check_result = None
            st.session_state.bad_freq_results = None
            st.session_state.active_view = None
            st.session_state.last_uploaded_file_id = None
            st.rerun()
    
    st.markdown('<div style="margin-top: -25px;"></div>', unsafe_allow_html=True)
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        btn_calc = st.button("TÍNH TẦN SỐ KHẢ DỤNG", type="primary", use_container_width=True, disabled=btn_disabled)
    with c_btn2:
        btn_scan_bad_freq = st.button("LỌC TS KHÔNG KHẢ DỤNG", type="secondary", disabled=btn_disabled, use_container_width=True)

st.markdown("---")
st.subheader("3. KIỂM TRA TẦN SỐ CỤ THỂ")
# --- ĐỘ RỘNG CỘT NHẬP TẦN SỐ TỪ 0.5 LÊN 1.0 ---
c_check_1, c_check_2 = st.columns([1.0, 4.0]) 
with c_check_1:
    f_check_val = st.number_input("Nhập tần số (MHz):", value=0.0, step=0.0125, format="%.4f")
with c_check_2:
    st.markdown(" ") 
    st.markdown(" ")
    btn_check_specific = st.button("KIỂM TRA CAN NHIỄU", type="secondary", disabled=btn_disabled)

# =========================================================================
# XỬ LÝ SỰ KIỆN NÚT BẤM (PROCESS)
# =========================================================================

if btn_calc:
    st.session_state.check_result = None
    st.session_state.bad_freq_results = None
    st.session_state.active_view = "AVAILABLE"
    
    error_msg = []
    if lon == 0.0: error_msg.append("Kinh độ chưa nhập")
    if lat == 0.0: error_msg.append("Vĩ độ chưa nhập")
    if "LAN" in mode:
        if province_selection == "-- Chọn Tỉnh/TP --": error_msg.append("Thiếu Tỉnh/TP (Bắt buộc cho mạng LAN)")
        if province_selection == "KHAC" and province_manual_input.strip() == "": error_msg.append("Vui lòng nhập tên Tỉnh/TP cụ thể")
    
    if error_msg:
        st.error(f"⚠️ LỖI: {', '.join(error_msg)}")
        st.session_state.active_view = None
    else:
        prov_to_send = province_selection
        if province_selection == "KHAC": prov_to_send = province_manual_input
        if "WAN" in mode: prov_to_send = "KHAC"
        if h_anten == 0.0: st.warning("⚠️ Lưu ý: Độ cao Anten đang là 0m.")
        
        with st.spinner('Đang tính toán...'):
            try:
                tool = ToolAnDinhTanSo(uploaded_file)
                user_input = {
                    "lat": lat, "lon": lon,
                    "province_code": prov_to_send,
                    "antenna_height": h_anten,
                    "band": band, "bw": bw, "usage_mode": mode,
                    "scan_start": scan_start, "scan_end": scan_end 
                }
                results = tool.tinh_toan(user_input)
                st.session_state.results = results
                st.session_state.input_snapshot = {
                    "THAM SỐ": ["Phiên bản App", "Kinh độ", "Vĩ độ", "Tỉnh / TP", "Độ cao Anten (m)", "Dải tần", "Phạm vi quét", "Băng thông", "Loại mạng", "Số lượng xin"],
                    "GIÁ TRỊ": [APP_VERSION, f"{lon:.5f}", f"{lat:.5f}", prov_to_send if "LAN" in mode else "Toàn quốc (WAN)", h_anten, band, selected_subband_label, bw, mode, qty]
                }
            except Exception as e:
                logger.exception("Lỗi khi tính toán", exc_info=e)
                st.error(f"Có lỗi xảy ra: {e}")
                st.session_state.active_view = None

if btn_scan_bad_freq:
    st.session_state.results = None
    st.session_state.check_result = None
    st.session_state.active_view = "UNAVAILABLE"
    
    if uploaded_file is None:
        st.error("Vui lòng nạp file Excel trước.")
        st.session_state.active_view = None
    elif btn_disabled: 
         st.error("Vui lòng nạp đúng định dạng file (.xlsx).")
         st.session_state.active_view = None
    else:
        prov_to_send = province_selection
        if province_selection == "KHAC": prov_to_send = province_manual_input
        if "WAN" in mode: prov_to_send = "KHAC"
        
        with st.spinner("Đang quét dải tần đã chọn..."):
            try:
                tool = ToolAnDinhTanSo(uploaded_file)
                user_input = {
                    "lat": lat, "lon": lon,
                    "province_code": prov_to_send,
                    "antenna_height": h_anten,
                    "band": band, "bw": bw, "usage_mode": mode,
                    "scan_start": scan_start, "scan_end": scan_end 
                }
                bad_results = tool.tim_cac_tan_so_khong_kha_dung(user_input)
                st.session_state.bad_freq_results = bad_results
                
                st.session_state.input_snapshot = {
                    "THAM SỐ": ["Phiên bản App", "Kinh độ", "Vĩ độ", "Tỉnh / TP", "Độ cao Anten (m)", "Dải tần", "Phạm vi quét", "Băng thông", "Loại mạng", "Số lượng xin"],
                    "GIÁ TRỊ": [APP_VERSION, f"{lon:.5f}", f"{lat:.5f}", prov_to_send if "LAN" in mode else "Toàn quốc (WAN)", h_anten, band, selected_subband_label, bw, mode, qty]
                }
                
            except Exception as e:
                logger.exception("Lỗi khi quét tần số", exc_info=e)
                st.error(f"Có lỗi xảy ra: {e}")
                st.session_state.active_view = None

if btn_check_specific:
    st.session_state.results = None
    st.session_state.bad_freq_results = None
    st.session_state.active_view = "CHECK_SPECIFIC"

    if uploaded_file is None:
        st.error("Vui lòng nạp file Excel trước.")
        st.session_state.active_view = None
    elif btn_disabled:
         st.error("Vui lòng nạp đúng định dạng file (.xlsx).")
         st.session_state.active_view = None
    elif f_check_val <= 0:
        st.error("Vui lòng nhập tần số hợp lệ.")
        st.session_state.active_view = None
    else:
        prov_to_send = province_selection
        if province_selection == "KHAC": prov_to_send = province_manual_input
        if "WAN" in mode: prov_to_send = "KHAC"
        
        with st.spinner(f"Đang kiểm tra tần số {f_check_val} MHz..."):
            try:
                tool = ToolAnDinhTanSo(uploaded_file)
                user_input = {
                    "lat": lat, "lon": lon,
                    "province_code": prov_to_send,
                    "antenna_height": h_anten,
                    "band": band, "bw": bw, "usage_mode": mode
                }
                check_res = tool.kiem_tra_tan_so_cu_the(user_input, f_check_val)
                st.session_state.check_result = check_res
            except Exception as e:
                logger.exception("Lỗi khi kiểm tra tần số", exc_info=e)
                st.error(f"Có lỗi xảy ra: {e}")
                st.session_state.active_view = None

# VIEW 1: KẾT QUẢ TẦN SỐ KHẢ DỤNG
if st.session_state.active_view == "AVAILABLE" and st.session_state.results is not None:
    st.markdown("---")
    st.subheader("📊 KẾT QUẢ TÍNH TOÁN: TẦN SỐ KHẢ DỤNG")
    results = st.session_state.results
    
    if not results:
        st.error("❌ Không tìm thấy tần số khả dụng trong dải quét!")
    else:
        df_res = pd.DataFrame(results)
        cols_display = ["STT", "frequency", "reuse_factor", "license_list"]
        df_view = df_res[cols_display].copy()
        df_view.columns = ["STT", "Tần số Khả dụng (MHz)", "Hệ số Tái sử dụng (Điểm)", "Các GP sử dụng tần số này"]
        df_view.set_index("STT", inplace=True)

        m1, m2 = st.columns(2)
        m1.metric("Số lượng tìm thấy", f"{len(results)}")
        best_freq = results[0]['frequency']
        m2.metric("Tần số tốt nhất", f"{best_freq} MHz")

        df_top = df_view.head(qty)

        def style_logic(df):
            styles = pd.DataFrame('', index=df.index, columns=df.columns)
            for idx in df.index:
                row_data = df_res[df_res['STT'] == idx].iloc[0]
                is_prio = row_data.get('is_priority', False)
                if is_prio:
                    styles.loc[idx, :] = f'color: {PRIORITY_HIGHLIGHT_COLOR}; font-weight: bold'
                elif idx <= results[min(qty-1, len(results)-1)]['STT']: 
                    top_ids = [item['STT'] for item in results[:qty]]
                    if idx in top_ids:
                        styles.loc[idx, :] = 'color: #28a745; font-weight: bold'
            return styles

        styler_top = df_top.style.apply(lambda x: style_logic(df_top), axis=None)
        styler_full = df_view.style.apply(lambda x: style_logic(df_view), axis=None)

        st.markdown(f"**Danh sách {qty} tần số đề xuất tốt nhất:**")
        st.table(styler_top)
        
        with st.expander("Xem danh sách đầy đủ (Tất cả kết quả)"):
            st.dataframe(styler_full, use_container_width=True)

        if st.session_state.input_snapshot:
            df_export = df_res.copy()
            df_export.rename(columns={
                "STT": "STT",
                "frequency": "Tần số Khả dụng (MHz)",
                "reuse_factor": "Hệ số Tái sử dụng",
                "license_list": "Các GP sử dụng tần số này (kèm khoảng cách)"
            }, inplace=True)
            
            df_input_report = pd.DataFrame(st.session_state.input_snapshot)
            excel_data = to_excel(df_input_report, df_export)
            
            now = datetime.now()
            time_str = now.strftime("%H%M%S_%d%m%Y")
            input_file_name = "data"
            if uploaded_file is not None:
                input_file_name = os.path.splitext(uploaded_file.name)[0]
                
            dl_file_name = f"DS_TanSo_KhaDung_{time_str}_{input_file_name}.xlsx"
            
            st.markdown("---")
            st.download_button(
                label=f"📥 LƯU KẾT QUẢ (EXCEL)",
                data=excel_data,
                file_name=dl_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# VIEW 2: KẾT QUẢ TẦN SỐ KHÔNG KHẢ DỤNG
elif st.session_state.active_view == "UNAVAILABLE" and st.session_state.bad_freq_results is not None:
    st.markdown("---")
    st.subheader("⚠️ CÁC TẦN SỐ KHÔNG KHẢ DỤNG (GÂY NHIỄU)")
    
    bad_list = st.session_state.bad_freq_results
    if not bad_list:
        st.info("Tuyệt vời! Không tìm thấy tần số nào bị nhiễu trong dải quét.")
    else:
        st.warning(f"⚠️ Tìm thấy {len(bad_list)} trường hợp tần số gây nhiễu (không khả dụng).")
        df_bad = pd.DataFrame(bad_list)
        
        # --- [ĐÃ CẬP NHẬT] GỘP CỘT KHOẢNG CÁCH ---
        if "Khoảng cách thực tế (km)" in df_bad.columns and "Khoảng cách yêu cầu (km)" in df_bad.columns:
             df_bad["Khoảng cách thực tế/Chỉ tiêu"] = df_bad.apply(lambda x: f"{x['Khoảng cách thực tế (km)']:.2f}/{x['Khoảng cách yêu cầu (km)']:.2f}", axis=1)
             df_bad.drop(columns=["Khoảng cách thực tế (km)", "Khoảng cách yêu cầu (km)"], inplace=True)
        elif "dist_km" in df_bad.columns and "req_dist_km" in df_bad.columns:
             df_bad["Khoảng cách thực tế/Chỉ tiêu"] = df_bad.apply(lambda x: f"{x['dist_km']:.2f}/{x['req_dist_km']:.2f}", axis=1)
             df_bad.drop(columns=["dist_km", "req_dist_km"], inplace=True)
             
        st.dataframe(
            df_bad, 
            use_container_width=True,
            column_config={
                "Tên Khách Hàng": st.column_config.TextColumn(width="large"), 
                "Địa chỉ trạm bị nhiễu": st.column_config.TextColumn(width="medium"),
                "Khoảng cách thực tế/Chỉ tiêu": st.column_config.TextColumn(width="medium", label="K.Cách Thực tế/Chỉ tiêu (km)"),
                "Tần số (MHz)": st.column_config.NumberColumn(format="%.4f"),
                "Tần số trạm bị nhiễu (MHz)": st.column_config.NumberColumn(format="%.4f"),
            }
        )
        
        if st.session_state.input_snapshot:
            df_input_report = pd.DataFrame(st.session_state.input_snapshot)
            csv_data = to_excel(df_input_report, df_bad)
        else:
            csv_data = to_excel(None, df_bad)
            
        now = datetime.now()
        time_str = now.strftime("%H%M%S_%d%m%Y")
        input_file_name = "data"
        if uploaded_file is not None:
            input_file_name = os.path.splitext(uploaded_file.name)[0]
            
        dl_name = f"DS_TanSo_KhongKhaDung_{time_str}_{input_file_name}.xlsx"
        
        st.download_button(
            label="📥 Tải danh sách Excel",
            data=csv_data,
            file_name=dl_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# VIEW 3: KẾT QUẢ KIỂM TRA CỤ THỂ
elif st.session_state.active_view == "CHECK_SPECIFIC" and st.session_state.check_result is not None:
    st.markdown("---")
    st.subheader("🔎 KẾT QUẢ KIỂM TRA TẦN SỐ CỤ THỂ")
    
    res = st.session_state.check_result
    if res.get("status") == "OK":
        st.success(f"✅ {res.get('msg')}")
    else:
        st.error(f"❌ {res.get('msg')}")
        if "conflicts" in res and res["conflicts"]:
            st.markdown("**Danh sách các giấy phép gây nhiễu (không đảm bảo khoảng cách):**")
            df_conflict = pd.DataFrame(res["conflicts"])
            if not df_conflict.empty:
                # --- [ĐÃ CẬP NHẬT] GỘP CỘT KHOẢNG CÁCH CHO BẢNG KIỂM TRA CỤ THỂ ---
                df_conflict["Khoảng cách thực tế/Chỉ tiêu"] = df_conflict.apply(lambda x: f"{x['dist_km']:.2f}/{x['req_dist_km']:.2f}", axis=1)
                df_conflict.drop(columns=["dist_km", "req_dist_km"], inplace=True)
                
                df_conflict.rename(columns={
                    "license": "Số Giấy Phép",
                    "customer": "Tên Khách Hàng",
                    "freq_conflict": "Tần số GP (MHz)",
                    "address": "Địa chỉ trạm",
                    "type": "Loại nhiễu"
                }, inplace=True)
                st.table(df_conflict)