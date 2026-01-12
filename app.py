# Full app.py with only UI/display changes around results.
# (Other logic kept as in your repo; adapted to highlight suggestions and priority bands)
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import os
import html
import logging
from datetime import datetime
from tool_tinh_toan import ToolAnDinhTanSo
from config import PRIORITY_HIGHLIGHT_COLOR, PRIORITY_BANDS  # get color & bands from config

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- APP VERSION (if you already have it above, keep that) ---
try:
    APP_VERSION  # if defined earlier by you
except NameError:
    APP_VERSION = "1.0"

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

# CSS TÙY CHỈNH (h2/h3 giảm, và giữ style)
st.markdown("""
    <style>
        header[data-testid="stHeader"] { display: none; }
        .block-container { padding-top: 0rem !important; padding-bottom: 2rem; }
        h2 { font-size: 1.3rem !important; margin-top: 0.5rem; margin-bottom: 0.2rem !important; }
        h3 { font-size: 0.95rem !important; padding-top: 0.2rem !important; padding-bottom: 0.2rem !important; }
        .stCaption { font-size: 0.7rem; margin-top: -5px; color: #555; }
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

# --- HÀM XUẤT EXCEL ---
def to_excel(df_input, df_result):
    output = io.BytesIO()
    df_input_safe = neutralize_df_for_excel(df_input.copy())
    df_result_safe = neutralize_df_for_excel(df_result.copy())

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
            logger.debug("openpyxl.styles not available or formatting failed", exc_info=True)
    return output.getvalue()

# Helper: check if a freq belongs to priority bands
def is_freq_in_priority(freq_mhz):
    try:
        f = float(freq_mhz)
    except Exception:
        return False
    for lo, hi in PRIORITY_BANDS:
        if lo <= f <= hi:
            return True
    return False

# --- MAP POPUP (same as before) ---
@st.dialog("Vị trí trên Google Maps")
def show_map_popup(lat, lon):
    map_url = f"https://www.google.com/maps?q={lat},{lon}&z=15&output=embed"
    st.write(f"📍 Tọa độ: {lat:.5f}, {lon:.5f}")
    components.iframe(map_url, height=600)

# =============================================================================
# BANNER + TITLE
# =============================================================================
banner_file = "logo_CTS.jpg"
if os.path.exists(banner_file):
    st.image(banner_file, use_container_width=True)
else:
    st.warning(f"⚠️ Chưa tìm thấy file '{banner_file}'. Vui lòng copy file ảnh vào cùng thư mục với app.py")

st.markdown("<h2 style='text-align: center; color: #0068C9;'>CÔNG CỤ TÍNH TOÁN ẤN ĐỊNH TẦN SỐ MẠNG DÙNG RIÊNG</h2>", unsafe_allow_html=True)
st.markdown(f"<div style='text-align: right; color: #666; font-size:0.85rem; margin-top:-8px;'>Phiên bản: {APP_VERSION}</div>", unsafe_allow_html=True)
st.markdown("---")

# =============================================================================
# LAYOUT (left/right) - giữ nguyên phần inputs
# =============================================================================
col_layout_left, col_space_layout, col_layout_right = st.columns([1.8, 0.1, 1.2])

with col_layout_left:
    st.subheader("1. THÔNG SỐ KỸ THUẬT & VỊ TRÍ MẠNG")
    # ... (inputs: lon/lat, mode, h_anten, band, bw, province, qty) ...
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
            if st.button("👉 Xem vị trí trên bản đồ", use_container_width=True):
                show_map_popup(lat, lon)
        else:
            st.button("👉 Xem vị trí trên bản đồ", disabled=True, use_container_width=True)

    c_mode, c1, c2, c3, c4, c5 = st.columns([1.3, 0.8, 0.8, 0.9, 1.2, 0.7])
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
            index=0, label_visibility="collapsed", disabled=is_wan
        )
        province_manual_input = ""
        if province_selection == "KHAC" and not is_wan:
            province_manual_input = st.text_input("Nhập tên Tỉnh/TP cụ thể:", placeholder="Ví dụ: Bà Rịa Vũng Tàu", label_visibility="collapsed")
    with c5:
        st.markdown("**Số lượng**")
        qty = st.number_input("Số lượng", value=1, min_value=1, label_visibility="collapsed")

with col_layout_right:
    st.subheader("2. NẠP DỮ LIỆU ĐẦU VÀO")
    uploaded_file = st.file_uploader("Label ẩn", type=['xls', 'xlsx', 'csv'], label_visibility="collapsed")
    if uploaded_file is not None:
        size = getattr(uploaded_file, "size", None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            st.error(f"File quá lớn (> {MAX_UPLOAD_MB} MB). Vui lòng giảm kích thước hoặc dùng file nhỏ hơn.")
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
    st.markdown(f"<div style='height: 20px; margin-top: 2px; margin-bottom: 0px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #28a745; font-weight: 500; font-size: 0.8rem;'>{file_status_html}</div>", unsafe_allow_html=True)
    btn_disabled = True if uploaded_file is None else False
    btn_calc = st.button("TÍNH TOÁN TẦN SỐ KHẢ DỤNG", type="primary", use_container_width=True, disabled=btn_disabled)

# =============================================================================
# XỬ LÝ LOGIC TÍNH TOÁN (giữ nguyên)
# =============================================================================
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
                # ensure results is list of dicts and that each has 'frequency'
                # annotate is_priority if tool didn't already
                for r in results:
                    if "is_priority" not in r:
                        r["is_priority"] = is_freq_in_priority(r.get("frequency"))
                st.session_state.results = results

                # input snapshot (unchanged)
                st.session_state.input_snapshot = {
                    "THAM SỐ": [
                        "Phiên bản App",
                        "Kinh độ (Decimal)", "Vĩ độ (Decimal)",
                        "Kinh độ (DMS)", "Vĩ độ (DMS)",
                        "Tỉnh / Thành phố", "Độ cao Anten (m)",
                        "Dải tần", "Băng thông (kHz)",
                        "Loại mạng", "Số lượng xin"
                    ],
                    "GIÁ TRỊ": [
                        APP_VERSION,
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

# =============================================================================
# HIỂN THỊ KẾT QUẢ — với logic chọn đề xuất và highlight
# =============================================================================
if st.session_state.results is not None:
    st.markdown("---")
    st.subheader("📊 KẾT QUẢ TÍNH TOÁN")
    results = st.session_state.results
    if not results:
        st.error("❌ Không tìm thấy tần số khả dụng!")
    else:
        # DataFrame để phục vụ download (giữ nguyên fields)
        df_res = pd.DataFrame(results)

        # Build display table WITHOUT is_priority column
        display_cols = ["STT", "frequency", "reuse_factor", "license_list"]
        if set(display_cols).issubset(df_res.columns):
            df_display = df_res[display_cols].copy()
            df_display.columns = ["STT", "Tần số Khả dụng (MHz)", "Hệ số Tái sử dụng (Điểm)", "Chú thích (Số GP)"]
            df_display.set_index("STT", inplace=True)
        else:
            # fallback display all except is_priority if present
            df_display = df_res.copy()
            if "is_priority" in df_display.columns:
                df_display = df_display.drop(columns=["is_priority"])
            if "STT" in df_display.columns:
                df_display.set_index("STT", inplace=True)

        # Metrics (same as before)
        m1, m2 = st.columns(2)
        m1.metric("Số lượng tìm thấy", f"{len(results)}")
        try:
            best_freq = results[0].get('frequency', '')
            m2.metric("Tần số tốt nhất", f"{best_freq} MHz")
        except Exception:
            pass

        # --- Build suggestion list (qty) preferring non-priority freqs ---
        try:
            want_n = int(qty)
        except Exception:
            want_n = 1

        suggested = []
        suggested_set = set()
        # first pass: non-priority frequencies in order
        for r in results:
            f = r.get("frequency")
            if f is None: continue
            if is_freq_in_priority(f):
                continue
            if f not in suggested_set:
                suggested.append(f)
                suggested_set.add(f)
            if len(suggested) >= want_n:
                break
        # second pass: if still need, add priority freqs
        if len(suggested) < want_n:
            for r in results:
                f = r.get("frequency")
                if f is None: continue
                if f in suggested_set: continue
                if is_freq_in_priority(f):
                    suggested.append(f)
                    suggested_set.add(f)
                if len(suggested) >= want_n:
                    break

        # show suggested list (green)
        if suggested:
            sug_html = "<div style='margin-bottom:8px;'>Đề xuất tần số (màu xanh): "
            sug_html += ", ".join([f"<span style='color:#0a7f1a; font-weight:700'>{s} MHz</span>" for s in suggested])
            sug_html += "</div>"
            st.markdown(sug_html, unsafe_allow_html=True)

        # Build HTML table that highlights suggested (green) and priority (yellow)
        def build_html_table(rows):
            header = """
            <table style="width:100%; border-collapse: collapse; font-size:14px;">
              <thead>
                <tr>
                  <th style="text-align:center; padding:8px; border-bottom:1px solid #ddd;">STT</th>
                  <th style="text-align:center; padding:8px; border-bottom:1px solid #ddd;">Tần số (MHz)</th>
                  <th style="text-align:center; padding:8px; border-bottom:1px solid #ddd;">Hệ số Tái sử dụng</th>
                  <th style="text-align:center; padding:8px; border-bottom:1px solid #ddd;">Chú thích (Số GP)</th>
                </tr>
              </thead>
              <tbody>
            """
            body = []
            for r in rows:
                stt = r.get("STT", "")
                freq = r.get("frequency", "")
                reuse = r.get("reuse_factor", "")
                note = r.get("license_list", "")
                is_pr = bool(r.get("is_priority", False))
                # decide color: suggested -> green; else if priority -> yellow; else default
                if freq in suggested_set:
                    freq_html = f"<span style='color:#0a7f1a; font-weight:700'>{freq}</span>"
                elif is_pr:
                    freq_html = f"<span style='color:{PRIORITY_HIGHLIGHT_COLOR}; font-weight:700'>{freq}</span>"
                else:
                    freq_html = str(freq)
                row_html = f"""
                  <tr>
                    <td style="text-align:center; padding:8px; border-bottom:1px solid #eee;">{stt}</td>
                    <td style="text-align:center; padding:8px; border-bottom:1px solid #eee;">{freq_html}</td>
                    <td style="text-align:center; padding:8px; border-bottom:1px solid #eee;">{reuse}</td>
                    <td style="text-align:center; padding:8px; border-bottom:1px solid #eee;">{note}</td>
                  </tr>
                """
                body.append(row_html)
            footer = "</tbody></table>"
            return header + "\n".join(body) + footer

        # Show top qty rows (visual)
        top_html = build_html_table(results[:max(10, want_n)])  # show at least few rows
        st.markdown(top_html, unsafe_allow_html=True)

        # Expander: full list
        with st.expander("Xem danh sách đầy đủ"):
            all_html = build_html_table(results)
            st.markdown(all_html, unsafe_allow_html=True)

        # DOWNLOAD (excel) - keep behavior but ensure is_priority not breaking Excel safety
        if st.session_state.input_snapshot:
            df_input_report = pd.DataFrame(st.session_state.input_snapshot)
            # For excel, we use df_res (which may include is_priority). If you prefer,
            # drop 'is_priority' from excel output; currently we keep it.
            excel_data = to_excel(df_input_report, df_res)

            now = datetime.now()
            time_str = now.strftime("%H%M%Y")
            input_file_name = "data"
            try:
                if uploaded_file is not None:
                    input_file_name = os.path.splitext(uploaded_file.name)[0]
            except Exception:
                pass
            dl_file_name = f"ket_qua_an_dinh_{time_str}_{input_file_name}_v{APP_VERSION}.xlsx"
            st.markdown("---")
            st.download_button(
                label=f"LƯU KẾT QUẢ(EXCEL)",
                data=excel_data,
                file_name=dl_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
