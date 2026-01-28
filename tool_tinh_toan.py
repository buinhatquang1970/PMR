import pandas as pd
import re
from geopy.distance import geodesic
import config
import numpy as np
import logging
import os
import importlib 

# --- RELOAD CONFIG ---
importlib.reload(config)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Cấu hình ánh xạ cột (Mặc định)
DEFAULT_COL_MAPPING = {
    "LICENSE_NO": ["Số giấy phép", "Số GP", "License", "Lic"], 
    "CUSTOMER": ["Tên khách hàng", "Khách hàng", "Customer", "User"], 
    "FREQUENCY": ["Tần số phát", "Frequency", "Freq", "Tx Freq", "Tần số"],
    "FREQ_RX": ["Tần số thu", "Rx Freq", "Freq Rx"],
    "BANDWIDTH": ["Phương thức phát", "Emission", "Bandwidth", "BW", "Dải thông"], 
    "LAT": ["Vị trí anten: Vĩ độ", "Vĩ độ", "Lat", "Latitude"],
    "LON": ["Vị trí anten: Kinh độ", "Kinh độ", "Lon", "Long", "Longitude"], 
    "ADDRESS": ["Địa điểm đặt thiết bị", "Địa chỉ", "Address", "Location"], 
    "PROVINCE_OLD": ["Tỉnh thành", "Province", "Tỉnh"],      
    "ANTENNA_HEIGHT": ["Độ cao anten", "Height", "Độ cao"],
    "CONDITIONS": ["Các điều kiện khác", "Ghi chú", "Condition"]
}

MAX_CANDIDATES = 20000

def chuan_hoa_text(text):
    if pd.isna(text) or str(text).strip() == "":
        return ""
    text = str(text).strip().lower()
    patterns = {
        '[àáảãạăắằẳẵặâấầẩẫậ]': 'a', '[đ]': 'd',
        '[èéẻẽẹêếềểễệ]': 'e', '[ìíỉĩị]': 'i',
        '[òóỏõọôốồổỗộơớờởỡợ]': 'o', '[ùúủũụưứừửữự]': 'u',
        '[ỳýỷỹỵ]': 'y'
    }
    for regex, replace in patterns.items():
        text = re.sub(regex, replace, text)
    
    text = re.sub(r'thanh pho|tinh|tp\.|tp ', '', text)
    text = re.sub(r'[^a-z0-9]', '', text) 
    return text.upper()

class ToolAnDinhTanSo:
    def __init__(self, excel_file):
        importlib.reload(config)
        self.reserved_frequencies = [] 
        
        file_name = ""
        file_source = excel_file
        if hasattr(excel_file, 'name'):
            file_name = excel_file.name
        elif isinstance(excel_file, str):
            file_name = excel_file
        
        self.df = pd.DataFrame()
        try:
            if file_name.lower().endswith('.csv'):
                self.df = pd.read_csv(file_source)
            elif file_name.lower().endswith('.xlsx'):
                self.df = pd.read_excel(file_source, engine='openpyxl')
            else:
                self.df = pd.DataFrame()
            
            if not self.df.empty:
                self.df.columns = self.df.columns.str.strip()
                self.map_columns_smart()
                self.clean_data()
            
        except Exception as e:
            logger.exception("Lỗi khởi tạo Tool")
            self.df = pd.DataFrame() 

    def map_columns_smart(self):
        rename_map = {}
        cols = self.df.columns
        
        internal_names = {
            "LICENSE_NO": "license", "CUSTOMER": "raw_customer",
            "FREQUENCY": "raw_freq", "FREQ_RX": "raw_freq_rx",
            "BANDWIDTH": "raw_bw", "LAT": "raw_lat",
            "LON": "raw_lon", "ADDRESS": "raw_address",
            "PROVINCE_OLD": "raw_province_col", "ANTENNA_HEIGHT": "h_anten",
            "CONDITIONS": "raw_conditions"
        }

        for key, keywords in DEFAULT_COL_MAPPING.items():
            found = False
            for col in cols:
                for kw in keywords:
                    if kw.lower() == str(col).lower().strip():
                        rename_map[col] = internal_names[key]
                        found = True
                        break
                if found: break
            
            if not found:
                for col in cols:
                    col_str = str(col).lower()
                    for kw in keywords:
                        if kw.lower() in col_str:
                            rename_map[col] = internal_names[key]
                            found = True
                            break
                    if found: break
        
        self.df = self.df.rename(columns=rename_map)

    def convert_dms_to_decimal(self, dms_str):
        if pd.isna(dms_str): return None
        s_in = str(dms_str).upper().strip()
        s_clean = re.sub(r"[NSEWnsew°'\"’;:_]", " ", s_in)
        
        if s_clean.count('.') > 1: s_clean = s_clean.replace('.', ' ')
        else: s_clean = s_clean.replace(',', '.')

        numbers = re.findall(r"(\d+(?:\.\d+)?)", s_clean)
        
        if len(numbers) >= 2: 
            try:
                d = float(numbers[0])
                m = float(numbers[1])
                s = float(numbers[2]) if len(numbers) > 2 else 0.0
                decimal = d + (m / 60.0) + (s / 3600.0)
                if 'S' in s_in or 'W' in s_in: decimal = -decimal
                if abs(decimal) > 180: return None
                return decimal
            except: return None
            
        try:
            val = float(s_in.replace(',', '.'))
            if 0 < abs(val) < 180: return val
        except: pass
        return None

    def parse_bandwidth(self, emission_code):
        if pd.isna(emission_code): return 12.5
        code = str(emission_code).upper()
        if "16K" in code: return 25.0
        if "11K" in code or "8K5" in code: return 12.5
        if "4K0" in code: return 6.25
        return 12.5

    def parse_freq_string(self, freq_str):
        if pd.isna(freq_str): return []
        clean_s = str(freq_str).upper().replace(',', '.').replace('MHZ', '').replace(';', ' ')
        
        freqs = []
        range_match = re.findall(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", clean_s)
        
        if range_match:
            for start_str, end_str in range_match:
                try:
                    start_f = float(start_str)
                    end_f = float(end_str)
                    if start_f > end_f: start_f, end_f = end_f, start_f 
                    current = start_f
                    while current <= end_f + 0.0001:
                        freqs.append(round(current, 5))
                        current += 0.0125
                except: pass
        
        for item in clean_s.split():
            if item == '-': continue 
            try:
                f = float(item)
                if f > 10: freqs.append(f)
            except: pass
            
        return sorted(list(set(freqs)))

    def infer_net_type_from_freq(self, f_val):
        alloc = []
        if 130 <= f_val <= 180: alloc = config.FREQUENCY_ALLOCATION_VHF
        elif 380 <= f_val <= 500: alloc = config.FREQUENCY_ALLOCATION_UHF
        
        for start, end, modes, _ in alloc:
            if start <= f_val <= end:
                if "WAN_SIMPLEX" in modes: return "WAN_SIMPLEX"
                if "WAN_DUPLEX" in modes: return "WAN_DUPLEX"
                return "LAN"
        return "LAN" 

    def clean_data(self):
        cleaned_rows = []
        self.reserved_frequencies = [] 
        
        has_license_col = 'license' in self.df.columns
        has_customer_col = 'raw_customer' in self.df.columns
        has_freq_col = 'raw_freq' in self.df.columns
        has_lat_col = 'raw_lat' in self.df.columns
        has_lon_col = 'raw_lon' in self.df.columns
        
        if not has_freq_col:
            logger.error("Không tìm thấy cột Tần số trong file Excel!")
            return 

        for idx, row in self.df.iterrows():
            raw_prov_extracted = ""
            if 'raw_province_col' in self.df.columns:
                val = str(row.get('raw_province_col', ''))
                if val.lower() not in ['nan', '', 'none']: raw_prov_extracted = val
            
            if (not raw_prov_extracted) and 'raw_address' in self.df.columns:
                parts = str(row.get('raw_address', '')).split(',')
                raw_prov_extracted = parts[-1] if len(parts) > 0 else str(row.get('raw_address', ''))
            
            clean_prov = chuan_hoa_text(raw_prov_extracted)
            is_holding = "LUUDONGTOANQUOC" in clean_prov
            
            tx_freqs = self.parse_freq_string(row.get('raw_freq')) if has_freq_col else []
            rx_freqs = self.parse_freq_string(row.get('raw_freq_rx')) if 'raw_freq_rx' in self.df.columns else []
            
            if is_holding:
                for f in tx_freqs: self.reserved_frequencies.append(f)
                for f in rx_freqs: self.reserved_frequencies.append(f)
            
            lat = self.convert_dms_to_decimal(row.get('raw_lat')) if has_lat_col else None
            lon = self.convert_dms_to_decimal(row.get('raw_lon')) if has_lon_col else None
            
            has_coords = (lat is not None and lon is not None)
            
            if not has_coords and not is_holding:
                continue

            bw = self.parse_bandwidth(row.get('raw_bw')) if 'raw_bw' in self.df.columns else 12.5
            
            license_str = str(row.get('license', '')).strip().upper() if has_license_col else ""
            customer_str = str(row.get('raw_customer', '')).strip() if has_customer_col else ""
            if customer_str.lower() in ['nan', 'none']: customer_str = ""

            all_freqs_to_check = []
            for f in tx_freqs: all_freqs_to_check.append(f)
            for f in rx_freqs: all_freqs_to_check.append(f)
            all_freqs_to_check = list(set(all_freqs_to_check))

            for f in all_freqs_to_check:
                net_type = self.infer_net_type_from_freq(f)
                
                cleaned_rows.append({
                    "freq": f, 
                    "bw": bw, 
                    "lat": lat if lat else 0, 
                    "lon": lon if lon else 0,
                    "has_coords": has_coords, 
                    "province": clean_prov, 
                    "net_type": net_type,
                    "is_holding": is_holding, 
                    "license": license_str,
                    "customer": customer_str
                })
        self.df = pd.DataFrame(cleaned_rows)

    def xac_dinh_kich_ban_user(self, user_input):
        mode = user_input.get('usage_mode', 'LAN')
        h = float(user_input.get('antenna_height', 0))
        prov_code = str(user_input.get('province_code', '')).upper()
        
        big_cities = ["HANOI", "HCM", "DANANG", "HOCHIMINH", "THANHPHOHOCHIMINH"] 
        user_prov_clean = chuan_hoa_text(prov_code)
        is_big_city = any(c == user_prov_clean for c in big_cities)
        
        if "WAN" in mode:
            if "SIMPLEX" in mode: return ("WAN_SIMPLEX", "WAN_SIMPLEX")
            else: return ("WAN_DUPLEX", "WAN_DUPLEX")
        
        if is_big_city:
            if h > 15: return ("LAN", "LAN_BIG_CITY_HIGH")
            else: return ("LAN", "LAN_BIG_CITY_LOW")
        else: return ("LAN", "LAN_PROVINCE")

    def get_required_distance(self, band, user_mode_tuple, db_net_type, tx_bw, delta_f, rx_bw):
        user_main_mode, user_scenario_key = user_mode_tuple
        matrix = None
        table_key = None
        
        is_intra_lan = ("LAN" in user_main_mode and "LAN" in db_net_type)
        is_intra_wan = ("WAN" in user_main_mode and "WAN" in db_net_type)
        
        if is_intra_lan or is_intra_wan:
            matrix = config.MATRIX_VHF if band == 'VHF' else config.MATRIX_UHF
            table_key = user_scenario_key
            if is_intra_wan:
                table_key = user_main_mode 
        else:
            matrix = config.MATRIX_CROSS
            if "LAN" in user_main_mode and "WAN_SIMPLEX" in db_net_type: table_key = "LAN_VS_WAN_SIMPLEX"
            elif "LAN" in user_main_mode and "WAN_DUPLEX" in db_net_type: table_key = "LAN_VS_WAN_DUPLEX"
            elif "WAN_SIMPLEX" in user_main_mode and "LAN" in db_net_type: table_key = "WAN_SIMPLEX_VS_LAN"
            elif "WAN_DUPLEX" in user_main_mode and "LAN" in db_net_type: table_key = "WAN_DUPLEX_VS_LAN"
            else: return 0.0

        if not matrix: return 0.0
        table_tx = matrix.get(table_key, {}).get(tx_bw)
        if not table_tx: table_tx = matrix.get(table_key, {}).get(12.5, {})

        val = abs(delta_f)
        if val < 3: key_d = 0         
        elif val < 9: key_d = 6.25    
        elif val < 15: key_d = 12.5   
        elif val < 21: key_d = 18.75
        elif val < 30: key_d = 25.0
        else: return 0.0 

        row_delta = table_tx.get(key_d, None)
        if row_delta is None: return 0.0

        if rx_bw <= 9: key_rx = 6.25
        elif rx_bw <= 18: key_rx = 12.5
        else: key_rx = 25.0
        
        return row_delta.get(key_rx, 0.0)

    # --- HÀM 1: KIỂM TRA TẦN SỐ CỤ THỂ ---
    def kiem_tra_tan_so_cu_the(self, user_input, f_check):
        if self.df.empty: 
            return {"status": "ERROR", "msg": "Chưa có dữ liệu Excel hoặc dữ liệu rỗng (Không tìm thấy cột Tần số/Tọa độ)."}

        user_mode_tuple = self.xac_dinh_kich_ban_user(user_input)
        band = user_input['band']
        bw = user_input['bw']
        f_check_rounded = round(f_check, 5)
        
        allocations = config.FREQUENCY_ALLOCATION_VHF if band == 'VHF' else config.FREQUENCY_ALLOCATION_UHF
        is_allocated_mode = False
        found_band = False
        allowed_for_freq = []
        
        for start_f, end_f, modes, _ in allocations:
            if start_f <= f_check_rounded <= end_f:
                found_band = True
                allowed_for_freq = modes
                if user_input['usage_mode'] in modes:
                    is_allocated_mode = True
                break
                
        if not found_band:
             return {"status": "FAIL", "msg": f"Tần số {f_check_rounded} nằm ngoài dải phân bổ VHF/UHF hỗ trợ.", "conflicts": []}
        if not is_allocated_mode:
            return {"status": "FAIL", "msg": f"Tần số được quy hoạch cho {allowed_for_freq}, KHÔNG cấp cho {user_input['usage_mode']}.", "conflicts": []}

        is_forbidden = any((r_s - 0.025) <= f_check_rounded <= (r_e + 0.025) for r_s, r_e in config.FORBIDDEN_BANDS)
        if is_forbidden:
            return {"status": "FAIL", "msg": "Tần số nằm trong dải tần CẤM (bao gồm biên bảo vệ ±25kHz).", "conflicts": []}

        is_shared = any(abs(f_check_rounded - f_shared) < 0.0001 for f_shared in config.SHARED_FREQUENCIES)
        if is_shared:
            return {"status": "FAIL", "msg": "Tần số thuộc kênh DÙNG CHUNG.", "conflicts": []}

        for res_f in self.reserved_frequencies:
            if abs(f_check_rounded - res_f) < 0.001:
                return {
                    "status": "FAIL", 
                    "msg": f"Vướng tần số giữ chỗ/Lưu động toàn quốc (Tần số: {res_f}).", 
                    "conflicts": []
                }

        conflicts = []
        df_subset = self.df[np.abs(self.df['freq'] - f_check) < 0.035]
        
        for _, row in df_subset.iterrows():
            if row['is_holding'] or not row['has_coords']: continue 
            try:
                dist_km = geodesic((user_input['lat'], user_input['lon']), (row['lat'], row['lon'])).km
            except: continue
            
            if dist_km < 0.05: continue
            
            delta_f = abs(f_check - row['freq']) * 1000 
            rx_bw = row['bw']
            db_net_type = row['net_type'] 
            
            req_dist = self.get_required_distance(band, user_mode_tuple, db_net_type, bw, delta_f, rx_bw)
            
            if dist_km < req_dist:
                if delta_f < 3: int_type = "Đồng kênh"
                elif delta_f < 9: int_type = "Kênh kề 6.25kHz"
                elif delta_f < 15: int_type = "Kênh kề 12.5kHz"
                elif delta_f < 21: int_type = "Kênh kề 18.75kHz"
                elif delta_f < 30: int_type = "Kênh kề 25kHz"
                else: int_type = f"Lệch {delta_f:.2f} kHz"

                conflict_coords = f"{row['lat']:.4f}, {row['lon']:.4f}"
                
                conflicts.append({
                    "license": row['license'],
                    "customer": row.get('customer', ''), 
                    "freq_conflict": row['freq'],
                    "dist_km": round(dist_km, 2),
                    "req_dist_km": req_dist,
                    "address": row.get('province', '') + f" (Toạ độ: {conflict_coords})",
                    "type": int_type
                })

        if len(conflicts) > 0:
            return {"status": "FAIL", "msg": "Tần số gây nhiễu.", "conflicts": conflicts}
        return {"status": "OK", "msg": "Tần số KHẢ DỤNG.", "conflicts": []}

    # --- HÀM 2: TÌM CÁC TẦN SỐ KHÔNG KHẢ DỤNG ---
    def tim_cac_tan_so_khong_kha_dung(self, user_input):
        if self.df.empty: return []
        
        user_mode_tuple = self.xac_dinh_kich_ban_user(user_input)
        band = user_input['band']
        bw = user_input['bw']
        mode = user_input['usage_mode']
        scan_start = user_input.get('scan_start', 0) 
        scan_end = user_input.get('scan_end', 0)
        
        raw_input_prov = str(user_input.get('province_code', ''))
        user_province_clean = chuan_hoa_text(raw_input_prov)
        
        candidates = self.generate_candidates(band, bw, mode, user_province_clean, scan_start, scan_end)
        bad_results = []
        
        for f_check in candidates:
            df_subset = self.df[np.abs(self.df['freq'] - f_check) < 0.035]
            
            for _, row in df_subset.iterrows():
                if row['is_holding'] or not row['has_coords']: continue 
                try:
                    dist_km = geodesic((user_input['lat'], user_input['lon']), (row['lat'], row['lon'])).km
                except: continue
                
                if dist_km < 0.05: continue
                
                delta_f = abs(f_check - row['freq']) * 1000 
                rx_bw = row['bw']
                db_net_type = row['net_type'] 
                
                req_dist = self.get_required_distance(band, user_mode_tuple, db_net_type, bw, delta_f, rx_bw)
                
                if dist_km < req_dist:
                    if delta_f < 3: int_type = "Đồng kênh"
                    elif delta_f < 9: int_type = "Kênh kề 6.25kHz"
                    elif delta_f < 15: int_type = "Kênh kề 12.5kHz"
                    elif delta_f < 21: int_type = "Kênh kề 18.75kHz"
                    elif delta_f < 30: int_type = "Kênh kề 25kHz"
                    else: int_type = f"Lệch {delta_f:.2f} kHz"
                    
                    bad_results.append({
                        "Tần số (MHz)": f_check,
                        "Số GP bị nhiễu": row['license'],
                        "Tên Khách Hàng": row.get('customer', ''), 
                        "Tần số trạm bị nhiễu (MHz)": row['freq'],
                        "Loại nhiễu": int_type,
                        "Khoảng cách thực tế (km)": round(dist_km, 2),
                        "Khoảng cách yêu cầu (km)": req_dist,
                        "Địa chỉ trạm bị nhiễu": row.get('province', '')
                    })

        return bad_results

    def generate_candidates(self, band, bw, usage_mode, user_province_clean, scan_start=0, scan_end=0):
        candidates = []
        allocations = config.FREQUENCY_ALLOCATION_VHF if band == 'VHF' else config.FREQUENCY_ALLOCATION_UHF
        step_mhz = bw / 1000.0 
        
        allowed_group_1 = ['HOCHIMINH', 'DANANG', 'TPHOCHIMINH', 'HCM', 'DN']
        allowed_group_2 = ['HOCHIMINH', 'TPHOCHIMINH', 'HCM']

        for start_f, end_f, modes, _ in allocations:
            if (end_f < scan_start) or (start_f > scan_end):
                continue
                
            if usage_mode in modes:
                loop_start = max(start_f, scan_start)
                loop_end = min(end_f, scan_end)
                
                curr = loop_start
                while curr <= loop_end + 0.00001:
                    curr_rounded = round(curr, 5) 
                    
                    is_forbidden = any((r_s - 0.025) <= curr_rounded <= (r_e + 0.025) for r_s, r_e in config.FORBIDDEN_BANDS)
                    is_shared = any(abs(curr_rounded - f_shared) < 0.0001 for f_shared in config.SHARED_FREQUENCIES)
                    
                    is_reserved = False
                    for res_f in self.reserved_frequencies:
                         if abs(curr_rounded - res_f) < 0.001:
                             is_reserved = True
                             break
                    
                    skip_by_note_b = False
                    if usage_mode == 'LAN':
                        in_group_1 = (418.5 <= curr_rounded <= 419.5) or (428.5 <= curr_rounded <= 429.5)
                        if in_group_1 and (user_province_clean not in allowed_group_1):
                            skip_by_note_b = True
                        in_group_2 = (440.5 <= curr_rounded <= 441.0) or (445.5 <= curr_rounded <= 446.0)
                        if in_group_2 and (user_province_clean not in allowed_group_2):
                            skip_by_note_b = True

                    if not is_forbidden and not is_shared and not skip_by_note_b and not is_reserved:
                        candidates.append(curr_rounded)
                    curr += step_mhz
        
        candidates = sorted(list(set(candidates)))
        if len(candidates) > MAX_CANDIDATES:
            candidates = candidates[:MAX_CANDIDATES]
        return candidates

    def tinh_toan(self, user_input):
        if self.df.empty: return []
        results = []
        
        user_mode_tuple = self.xac_dinh_kich_ban_user(user_input)
        band = user_input['band']
        bw = user_input['bw']
        mode = user_input['usage_mode']
        scan_start = user_input.get('scan_start', 0) 
        scan_end = user_input.get('scan_end', 0)
        
        raw_input_prov = str(user_input.get('province_code', ''))
        user_province_clean = chuan_hoa_text(raw_input_prov)
        
        candidates = self.generate_candidates(band, bw, mode, user_province_clean, scan_start, scan_end)
        if not candidates: return []

        df_freqs = self.df['freq'].values
        
        priority_bands = getattr(config, 'MARITIME_PRIORITY_BANDS', [])

        for f_check in candidates:
            f_check_rounded = round(f_check, 5)
            df_subset = self.df[np.abs(self.df['freq'] - f_check) < 0.035]
            is_usable = True
            
            for _, row in df_subset.iterrows():
                if row['is_holding'] or not row['has_coords']: continue 
                try:
                    dist_km = geodesic((user_input['lat'], user_input['lon']), (row['lat'], row['lon'])).km
                except: continue
                
                if dist_km < 0.05: continue
                
                delta_f = abs(f_check - row['freq']) * 1000 
                rx_bw = row['bw']
                db_net_type = row['net_type'] 
                
                req_dist = self.get_required_distance(band, user_mode_tuple, db_net_type, bw, delta_f, rx_bw)
                
                if dist_km < req_dist:
                    is_usable = False
                    break 
            
            if is_usable:
                # --- [CHỈNH SỬA] FORM HIỂN THỊ GP & KHOẢNG CÁCH (GROUP BY LICENSE) ---
                df_exact = self.df[np.abs(self.df['freq'] - f_check) < 0.00001]
                
                # Dictionary: License -> Min Distance
                lic_dist_map = {} 

                for _, row_e in df_exact.iterrows():
                    raw_lic = str(row_e['license']).strip()
                    if raw_lic.lower() in ['nan', 'none', '', 'nan/gp']: continue
                    
                    short_lic = raw_lic.split('/')[0]
                    
                    d_km = 0
                    if row_e['has_coords']:
                        try:
                            d_km = geodesic((user_input['lat'], user_input['lon']), (row_e['lat'], row_e['lon'])).km
                        except: pass
                    
                    # Logic: Nếu chưa có GP này hoặc khoảng cách mới nhỏ hơn khoảng cách cũ thì cập nhật
                    if short_lic not in lic_dist_map:
                        lic_dist_map[short_lic] = d_km
                    else:
                        if d_km < lic_dist_map[short_lic]:
                            lic_dist_map[short_lic] = d_km

                # Sắp xếp theo khoảng cách tăng dần (gần nhất đứng trước)
                sorted_items = sorted(lic_dist_map.items(), key=lambda x: x[1])
                
                list_formatted = []
                for lic, dist in sorted_items:
                    list_formatted.append(f"{lic}({int(dist)})")

                unique_count = len(list_formatted)
                license_str = ", ".join(list_formatted)
                # ---------------------------------------------------------------------
                
                is_priority = False
                for p_start, p_end in priority_bands:
                    if p_start <= f_check_rounded <= p_end:
                        is_priority = True
                        break

                results.append({
                    "frequency": f_check, 
                    "reuse_factor": int(unique_count),
                    "license_list": license_str,
                    "is_priority": is_priority 
                })
        
        results.sort(key=lambda x: (x['is_priority'], -x['reuse_factor']))
        
        for i, item in enumerate(results):
            new_item = {
                "STT": i + 1,
                "frequency": item["frequency"],
                "reuse_factor": item["reuse_factor"],
                "license_list": item["license_list"],
                "is_priority": item["is_priority"]
            }
            results[i] = new_item
            
        return results