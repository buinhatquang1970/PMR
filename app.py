import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import os
import html
import logging
from datetime import datetime
from tool_tinh_toan import ToolAnDinhTanSo
import importlib

# --- IMPORT AN TOÀN CHO BIẾN MÀU SẮC ---
try:
    import config
    importlib.reload(config) # Reload tại đây để cập nhật màu mới nhất
    PRIORITY_HIGHLIGHT_COLOR = getattr(config, 'PRIORITY_HIGHLIGHT_COLOR', '#F6BE00')
except:
    PRIORITY_HIGHLIGHT_COLOR = '#F6BE00' # Màu mặc định nếu lỗi

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- APP VERSION ---
APP_VERSION = "1.0"

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title=f"Ấn định tần số cho mạng nội bộ dùng riêng (v{APP_VERSION})", layout="wide")

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
        header[data-testid="stHeader"] { display: none; }
        .block-container { padding-top: 0rem !important; padding-bottom: 2rem; }
        h2 { font-size: 1.3rem !important; margin-top: 0.5rem; margin-bottom: 0.2rem !important; }
        h3 { font-size: 0.95rem !important; padding-top: 0.2rem !important; padding-bottom: 0.2rem !important; }
        div[data-testid="stMarkdownContainer"] > p { margin-bottom: -3px !important; font-weight: 500; }
        [data-testid="stHorizontalBlock"] { gap: 0.1rem !important; }
        .stCaption { font-size: 0.7rem; margin-top: -5px; color: #555; }
        hr { margin-top: 0.5rem !important; margin-bottom: 0.5rem !important; }
        [data-testid='stFileUploader'] { height: 65px !important; overflow: hidden !important; margin-bottom: 0px !important; padding-top: 0px; }
        [data-testid='stFileUploader'] section { padding: 0.5rem !important; min-height: 0px !important; }
        [data-testid='stFileUploader'] section > div > div > span { display: none; }
        [data-testid='stFileUploader'] section > div > div::after { content: "Nhập file Excel (xlsx)"; display: block; font-weight: bold; color: #333; }
        [data-testid='stFileUploader'] section small { display: none; }
        div[data-testid="stColumn"] button[kind="secondary"] { color: #d93025 !important; font-weight: bold !important; border: 1px solid #ddd !important; background-color: #fff !important; width: 100%; transition: all 0.3s; }
        div[data-testid="stColumn"] button[kind="secondary"]:hover { background-color: #fce8e6 !important; border-color: #d93025 !important; color: #d93025 !important; }
        button[kind="primary"] { font-weight: bold !important; margin-top: 5px; }
        div[data-testid="stTable"] table { width: 100% !important; }
        div[data-testid="stTable"] th { background-color: #f0f2f6 !important; color: #31333F !important; font-size: 1.2rem !important; font-weight: 800 !important; text-align: center !important; white-space: nowrap !important; padding: 15px !important; }
        div[data-testid="stTable"] td { font-size: 1.1rem !important; text-align: center !important; vertical-align: middle !important; padding: 12px !important; min-width: 200px !important; }
        div[role="dialog"] { width: 50vw !important; max-width: 50vw !important; left: auto !important; right: 0 !important; top: 0 !important; bottom: 0 !important; height: 100vh !important; margin: 0 !important; border-radius: 0 !important; transform: none !important; display: flex; flex-direction: column; }
        div[data-testid="stSelectbox"] > div, div[data-testid="stSelectbox"] button, div[data-testid="stSelectbox"] select { min-width: 120px !important; max-width: 320px !important; white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; display: inline-block !important; }
        .stTextInput, .stSelectbox, .stNumberInput, .stDateInput { min-width: 80px !important; }
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
    df_input_safe = neutralize_df_for_excel(df_input.copy())
    
    # Loại bỏ cột cờ trước khi xuất Excel để file sạch
    if 'is_priority' in df_result.columns:
        df_result_clean = df_result.drop(columns=['is_priority'])
    else:
        df_result_clean = df_result
        
    df_result_safe = neutralize_df_for_excel(df_result_clean.copy())

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = 'KET_QUA_TINH_TOAN'
        df_input_safe.to_excel(writer, index=False, sheet_name=sheet_name, startrow=1)
        start_row_result = len(df_input_safe) + 5
        df_result_safe.to_excel(writer, sheet_name=sheet_name, startrow=start_row_result)
        
        worksheet = writer.sheets[sheet_name]
        cell_input_title = worksheet.cell(row=1, column=1, value="I. THÔNG SỐ ĐẦU VÀO")
        cell_result_title = worksheet.cell(row=start_row_result, column=1, value="II. KẾT QUẢ TÍNH TOÁN")
        try:
            from openpyxl.styles import Font
            bold_font = Font(bold=True, size=11)
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
    st.image(banner_file, use_container_width=True)
else:
    st.warning(f"⚠️ Chưa tìm thấy file '{banner_file}'.")

st.markdown("<h2 style='text-align: center; color: #0068C9;'>Ấn định tần số cho mạng nội bộ dùng riêng (Version cho các Sở)</h2>", unsafe_allow_html=True)
st.markdown(f"<div style='text-align: right; color: #666; font-size:0.85rem; margin-top:-8px;'>Phiên bản: {APP_VERSION}</div>", unsafe_allow_html=True)
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

    # ĐIỀU CHỈNH TỶ LỆ CỘT TẠI ĐÂY: Giảm cột 1 (c_mode), Tăng cột 6 (c5)
    c_mode, c1, c2, c3, c4, c5 = st.columns([0.9, 0.8, 0.8, 0.9, 1.2, 1.1])
    
    with c_mode:
        st.markdown("📡 **Loại mạng**")
        mode = st.selectbox("Loại mạng", ["LAN"], label_visibility="collapsed")
     #   mode = st.selectbox("Loại mạng", ["LAN", "WAN_SIMPLEX", "WAN_DUPLEX"], label_visibility="collapsed")

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
        province_selection = st.selectbox("Chọn Tỉnh/TP", ["-- Chọn Tỉnh/TP --", "HANOI", "HCM", "DANANG", "KHAC"], index=0, label_visibility="collapsed", disabled=is_wan)
        province_manual_input = ""
        if province_selection == "KHAC" and not is_wan:
            province_manual_input = st.text_input("Nhập tên Tỉnh/TP cụ thể:", placeholder="Ví dụ: Bà Rịa Vũng Tàu", label_visibility="collapsed")
    
    with c5:
        st.markdown("**Số lượng tần số**")
        qty = st.number_input("Số lượng", value=1, min_value=1, label_visibility="collapsed")

with col_layout_right:
    st.subheader("2. NẠP DỮ LIỆU ĐẦU VÀO")
    uploaded_file = st.file_uploader("Label ẩn", type=['xls', 'xlsx', 'csv'], label_visibility="collapsed")
    
    if uploaded_file is not None:
        size = getattr(uploaded_file, "size", None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            st.error(f"File quá lớn (> {MAX_UPLOAD_MB} MB).")
            st.stop()
            
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
        
    st.markdown(f"<div style='height: 20px; margin-top: 2px; color: #28a745; font-weight: 500; font-size: 0.8rem;'>{file_status_html}</div>", unsafe_allow_html=True)

    btn_disabled = True if uploaded_file is None else False
    btn_calc = st.button("TÍNH TOÁN TẦN SỐ KHẢ DỤNG", type="primary", use_container_width=True, disabled=btn_disabled)

if btn_calc:
    error_msg = []
    if lon == 0.0: error_msg.append("Kinh độ chưa nhập")
    if lat == 0.0: error_msg.append("Vĩ độ chưa nhập")
    if "LAN" in mode:
        if province_selection == "-- Chọn Tỉnh/TP --": error_msg.append("Thiếu Tỉnh/TP (Bắt buộc cho mạng LAN)")
        if province_selection == "KHAC" and province_manual_input.strip() == "": error_msg.append("Vui lòng nhập tên Tỉnh/TP cụ thể")
    
    if error_msg:
        st.error(f"⚠️ LỖI: {', '.join(error_msg)}")
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
                    "band": band, "bw": bw, "usage_mode": mode
                }
                results = tool.tinh_toan(user_input)
                st.session_state.results = results
                st.session_state.input_snapshot = {
                    "THAM SỐ": ["Phiên bản App", "Kinh độ (Decimal)", "Vĩ độ (Decimal)", "Kinh độ (DMS)", "Vĩ độ (DMS)", "Tỉnh / Thành phố", "Độ cao Anten (m)", "Dải tần", "Băng thông (kHz)", "Loại mạng", "Số lượng xin"],
                    "GIÁ TRỊ": [APP_VERSION, lon, lat, f"{lon_d}° {lon_m}' {lon_s}\"", f"{lat_d}° {lat_m}' {lat_s}\"", prov_to_send if "LAN" in mode else "Toàn quốc (WAN)", h_anten, band, bw, mode, qty]
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
        
        # --- CHUẨN BỊ DATAFRAME GỐC (Dùng để tra cứu màu) ---
        has_priority = "is_priority" in df_res.columns
        
        # --- CHUẨN BỊ DATAFRAME HIỂN THỊ (ĐÃ XÓA CỘT is_priority) ---
        cols_display = ["STT", "frequency", "reuse_factor", "license_list"]
        df_view = df_res[cols_display].copy()
        
        df_view.columns = ["STT", "Tần số Khả dụng (MHz)", "Hệ số Tái sử dụng (Điểm)", "Chú thích (Số GP)"]
        df_view.set_index("STT", inplace=True)

        m1, m2 = st.columns(2)
        m1.metric("Số lượng tìm thấy", f"{len(results)}")
        best_freq = results[0]['frequency']
        m2.metric("Tần số tốt nhất", f"{best_freq} MHz")

        # --- TÁCH BẢNG: ĐỀ XUẤT (TOP N) ---
        df_top = df_view.head(qty)

        # --- HÀM TÔ MÀU ---
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
            df_input_report = pd.DataFrame(st.session_state.input_snapshot)
            excel_data = to_excel(df_input_report, df_res)
            
            now = datetime.now()
            time_str = now.strftime("%H%M%Y")
            input_file_name = "data"
            if uploaded_file is not None:
                input_file_name = os.path.splitext(uploaded_file.name)[0]
                
            dl_file_name = f"ket_qua_an_dinh_{time_str}_{input_file_name}_v{APP_VERSION}.xlsx"
            
            st.markdown("---")
            st.download_button(
                label=f"LƯU KẾT QUẢ(EXCEL)",
                data=excel_data,
                file_name=dl_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )