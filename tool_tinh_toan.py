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

EXCEL_COLUMNS = {
    "LICENSE_NO": "Số giấy phép", 
    "FREQUENCY": "Tần số phát",
    "FREQ_RX": "Tần số thu",
    "BANDWIDTH": "Phương thức phát", 
    "LAT": "Vị trí anten: Vĩ độ",
    "LON": "Vị trí anten: Kinh độ", 
    "ADDRESS": "Địa điểm đặt thiết bị", 
    "PROVINCE_OLD": "Tỉnh thành",      
    "ANTENNA_HEIGHT": "Độ cao anten",
    "CONDITIONS": "Các điều kiện khác"
}

MAX_CANDIDATES = 20000

# --- HÀM BỔ TRỢ: CHUẨN HÓA TIẾNG VIỆT ---
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
        if hasattr(excel_file, 'name'):
            file_name = excel_file.name
            file_source = excel_file
        elif isinstance(excel_file, str):
            file_name = excel_file
            file_source = excel_file
        
        try:
            if file_name.lower().endswith('.csv'): self.df = pd.read_csv(file_source)
            else:
                try: self.df = pd.read_excel(file_source, engine='openpyxl')
                except: 
                    try: self.df = pd.read_excel(file_source, engine='xlrd')
                    except: self.df = pd.read_excel(file_source)

            self.df.columns = self.df.columns.str.strip()
            rename_map = {}
            
            def find_col_by_keyword(keywords):
                for col in self.df.columns:
                    col_lower = str(col).lower()
                    for kw in keywords:
                        if kw.lower() in col_lower:
                            return col
                return None

            for key, col_name in EXCEL_COLUMNS.items():
                if col_name in self.df.columns:
                    target = {
                        "LICENSE_NO": "license", "FREQUENCY": "raw_freq", "FREQ_RX": "raw_freq_rx",
                        "BANDWIDTH": "raw_bw", "LAT": "raw_lat",
                        "LON": "raw_lon", "ADDRESS": "raw_address",
                        "PROVINCE_OLD": "raw_province_col", "ANTENNA_HEIGHT": "h_anten",
                        "CONDITIONS": "raw_conditions"
                    }.get(key, key)
                    rename_map[col_name] = target

            # Fallback tìm cột nếu không khớp tên chính xác
            if "raw_freq" not in rename_map.values():
                col = find_col_by_keyword(["Tần số phát", "Frequency"])
                if col: rename_map[col] = "raw_freq"
            
            if "raw_freq_rx" not in rename_map.values():
                col = find_col_by_keyword(["Tần số thu", "Rx Freq"])
                if col: rename_map[col] = "raw_freq_rx"

            if "raw_lat" not in rename_map.values():
                col = find_col_by_keyword(["Vĩ độ", "Lat"])
                if col: rename_map[col] = "raw_lat"
                
            if "raw_lon" not in rename_map.values():
                col = find_col_by_keyword(["Kinh độ", "Lon"])
                if col: rename_map[col] = "raw_lon"
                
            if "license" not in rename_map.values():
                col = find_col_by_keyword(["Số GP", "Giấy phép", "License"])
                if col: rename_map[col] = "license"
                
            if "raw_bw" not in rename_map.values():
                col = find_col_by_keyword(["Phương thức", "Emission", "Bandwidth"])
                if col: rename_map[col] = "raw_bw"

            if "raw_address" not in rename_map.values():
                col = find_col_by_keyword(["Địa điểm", "Địa chỉ", "Address"])
                if col: rename_map[col] = "raw_address"
                
            if "raw_conditions" not in rename_map.values():
                col = find_col_by_keyword(["điều kiện", "conditions", "ghi chú"])
                if col: rename_map[col] = "raw_conditions"

            self.df = self.df.rename(columns=rename_map)
            self.clean_data()
            
        except Exception as e:
            logger.exception("Lỗi khởi tạo Tool")
            self.df = pd.DataFrame() 

    def convert_dms_to_decimal(self, dms_str):
        if pd.isna(dms_str): return None
        s_in = str(dms_str).upper().strip()
        try:
            val = float(s_in.replace(',', '.'))
            if 0 < abs(val) < 180: return val
        except: pass
        nums = re.findall(r"(\d+)[.,]?(\d*)", s_in)
        valid_nums = []
        for n in nums:
            if n[0]: 
                val_str = n[0] + ("." + n[1] if n[1] else "")
                valid_nums.append(float(val_str))
        if len(valid_nums) >= 3:
            d, m, s = valid_nums[0], valid_nums[1], valid_nums[2]
            if d > 180 or m >= 60: return None
            return d + m/60 + s/3600
        elif len(valid_nums) == 2:
             d, m = valid_nums[0], valid_nums[1]
             return d + m/60
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
        # Xử lý chuỗi, loại bỏ MHz, Mhz, mhz... thay thế ; bằng khoảng trắng
        clean_s = str(freq_str).upper().replace(',', '.').replace('MHZ', '').replace(';', ' ')
        freqs = []
        for item in clean_s.split():
            try:
                f = float(item)
                if f > 10: freqs.append(f)
            except: pass
        return freqs

    def clean_data(self):
        cleaned_rows = []
        self.reserved_frequencies = [] 
        
        has_province_col = 'raw_province_col' in self.df.columns
        has_address_col = 'raw_address' in self.df.columns
        has_conditions_col = 'raw_conditions' in self.df.columns
        has_license_col = 'license' in self.df.columns
        
        for idx, row in self.df.iterrows():
            # 1. Xác định thông tin Tỉnh thành/Lưu động TRƯỚC
            raw_prov_extracted = ""
            if has_province_col:
                val = str(row.get('raw_province_col', ''))
                if val.lower() not in ['nan', '', 'none']:
                    raw_prov_extracted = val
            
            if (not raw_prov_extracted) and has_address_col:
                parts = str(row.get('raw_address', '')).split(',')
                raw_prov_extracted = parts[-1] if len(parts) > 0 else str(row.get('raw_address', ''))
            
            clean_prov = chuan_hoa_text(raw_prov_extracted)
            
            # Theo Phụ lục I: Tần số giữ chỗ bao gồm tần số có cột tỉnh thành = "Lưu động toàn quốc"
            is_holding = "LUUDONGTOANQUOC" in clean_prov
            
            # 2. Kiểm tra điều kiện "giữ chỗ" trong cột Ghi chú/Conditions
            is_reserved_cond = False
            if has_conditions_col:
                cond_val = str(row.get('raw_conditions', '')).lower()
                if "giữ chỗ tần số" in cond_val:
                    is_reserved_cond = True
            
            tx_freqs = self.parse_freq_string(row.get('raw_freq'))
            rx_freqs = self.parse_freq_string(row.get('raw_freq_rx'))
            
            # 3. Cập nhật danh sách reserved_frequencies
            # Nếu là lưu động toàn quốc HOẶC có ghi chú giữ chỗ -> Đưa vào danh sách cấm
            # ĐÃ SỬA: Thêm điều kiện is_holding vào đây
            if is_holding or is_reserved_cond:
                for f in tx_freqs: self.reserved_frequencies.append(f)
                for f in rx_freqs: self.reserved_frequencies.append(f)
            
            # Xử lý tọa độ
            lat = self.convert_dms_to_decimal(row.get('raw_lat'))
            lon = self.convert_dms_to_decimal(row.get('raw_lon'))
            
            has_coords = (lat is not None and lon is not None)
            
            # Nếu không có tọa độ VÀ không phải là lưu động -> Bỏ qua dòng này (vì không tính toán được khoảng cách)
            # Lưu ý: Nếu là Lưu động (is_holding=True), dòng này vẫn được giữ lại để tham chiếu (mặc dù đã add vào reserved rồi)
            if not has_coords and not is_holding:
                continue

            bw = self.parse_bandwidth(row.get('raw_bw'))
            
            net_type = "LAN"
            license_str = ""
            if has_license_col:
                license_str = str(row.get('license', '')).strip()
            
            if "WAN" in license_str.upper(): net_type = "WAN_SIMPLEX" 
            
            # Thu thập tất cả các tần số (Phát + Thu) để đưa vào cơ sở dữ liệu tính toán
            all_freqs_to_check = []
            for f in tx_freqs: all_freqs_to_check.append(f)
            for f in rx_freqs: all_freqs_to_check.append(f)
            all_freqs_to_check = list(set(all_freqs_to_check))

            for f in all_freqs_to_check:
                cleaned_rows.append({
                    "freq": f, 
                    "bw": bw, 
                    "lat": lat if lat else 0, 
                    "lon": lon if lon else 0,
                    "has_coords": has_coords, 
                    "province": clean_prov, 
                    "net_type": net_type,
                    "is_holding": is_holding,
                    "license": license_str 
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
        else:
            matrix = config.MATRIX_CROSS
            if "LAN" in user_main_mode and "WAN_SIMPLEX" in db_net_type: table_key = "LAN_VS_WAN_SIMPLEX"
            elif "LAN" in user_main_mode and "WAN_DUPLEX" in db_net_type: table_key = "LAN_VS_WAN_DUPLEX"
            elif "WAN_SIMPLEX" in user_main_mode and "LAN" in db_net_type: table_key = "WAN_SIMPLEX_VS_LAN"
            elif "WAN_DUPLEX" in user_main_mode and "LAN" in db_net_type: table_key = "WAN_DUPLEX_VS_LAN"
            else: return 150.0

        if not matrix: return 150.0
        table_tx = matrix.get(table_key, {}).get(tx_bw)
        if not table_tx: table_tx = matrix.get(table_key, {}).get(12.5, {})

        val = abs(delta_f)
        if val < 3: key_d = 0         
        elif val < 9: key_d = 6.25    
        elif val < 15: key_d = 12.5   
        elif val < 21: key_d = 18.75
        elif val < 30: key_d = 25.0
        else: return 0.0 

        row_delta = table_tx.get(key_d, {})
        
        if rx_bw <= 9: key_rx = 6.25
        elif rx_bw <= 18: key_rx = 12.5
        else: key_rx = 25.0
        
        return row_delta.get(key_rx, 150.0)

    def generate_candidates(self, band, bw, usage_mode, user_province_clean):
        candidates = []
        allocations = config.FREQUENCY_ALLOCATION_VHF if band == 'VHF' else config.FREQUENCY_ALLOCATION_UHF
        step_mhz = bw / 1000.0 
        
        allowed_group_1 = ['HOCHIMINH', 'DANANG', 'TPHOCHIMINH', 'HCM', 'DN']
        allowed_group_2 = ['HOCHIMINH', 'TPHOCHIMINH', 'HCM']

        for start_f, end_f, modes, _ in allocations:
            if usage_mode in modes:
                curr = start_f
                while curr <= end_f + 0.00001:
                    curr_rounded = round(curr, 5) 
                    is_forbidden = any(r_s <= curr_rounded <= r_e for r_s, r_e in config.FORBIDDEN_BANDS)
                    is_shared = any(abs(curr_rounded - f_shared) < 0.0001 for f_shared in config.SHARED_FREQUENCIES)
                    
                    skip_by_note_b = False
                    if usage_mode == 'LAN':
                        in_group_1 = (418.5 <= curr_rounded <= 419.5) or (428.5 <= curr_rounded <= 429.5)
                        if in_group_1 and (user_province_clean not in allowed_group_1):
                            skip_by_note_b = True
                        
                        in_group_2 = (440.5 <= curr_rounded <= 441.0) or (445.5 <= curr_rounded <= 446.0)
                        if in_group_2 and (user_province_clean not in allowed_group_2):
                            skip_by_note_b = True

                    if not is_forbidden and not is_shared and not skip_by_note_b:
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
        
        raw_input_prov = str(user_input.get('province_code', ''))
        user_province_clean = chuan_hoa_text(raw_input_prov)
        
        candidates = self.generate_candidates(band, bw, mode, user_province_clean)
        if not candidates: return []

        # Lọc tần số giữ chỗ (Bao gồm cả tần số trong cột ghi chú và tần số "Lưu động toàn quốc")
        final_candidates = []
        for cand in candidates:
            cand_rounded = round(cand, 5)
            is_reserved = False
            for res_f in self.reserved_frequencies:
                if abs(cand_rounded - round(res_f, 5)) < 0.0001:
                    is_reserved = True
                    break
            if not is_reserved:
                final_candidates.append(cand)
        
        candidates = final_candidates
        if not candidates: return []

        df_freqs = self.df['freq'].values
        df_licenses = self.df['license'].values 
        
        priority_bands = getattr(config, 'MARITIME_PRIORITY_BANDS', [])

        for f_check in candidates:
            f_check_rounded = round(f_check, 5)
            
            # Lấy tập con các trạm trong phạm vi ảnh hưởng
            df_subset = self.df[np.abs(self.df['freq'] - f_check) < 0.035]
            is_usable = True
            
            for _, row in df_subset.iterrows():
                # Bỏ qua dòng giữ chỗ (vì đã lọc ở bước trên rồi) hoặc dòng không có tọa độ
                if row['is_holding'] or not row['has_coords']: 
                    continue 
                
                try:
                    dist_km = geodesic((user_input['lat'], user_input['lon']), 
                                       (row['lat'], row['lon'])).km
                except: continue
                
                delta_f = abs(f_check - row['freq']) * 1000 
                rx_bw = row['bw']
                db_net_type = row['net_type'] 
                
                req_dist = self.get_required_distance(band, user_mode_tuple, db_net_type, bw, delta_f, rx_bw)
                
                if dist_km < req_dist:
                    is_usable = False
                    break 
            
            if is_usable:
                mask_freq_exact = np.abs(df_freqs - f_check) < 0.00001
                relevant_licenses = df_licenses[mask_freq_exact]
                
                unique_lics = sorted(list(set([str(lic).strip() for lic in relevant_licenses if str(lic).lower() not in ['nan', 'none', '', 'nan/gp']])))
                unique_count = len(unique_lics)
                license_str = ", ".join(unique_lics)
                
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