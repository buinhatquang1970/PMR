import pandas as pd
import re
from geopy.distance import geodesic
import config
import numpy as np

EXCEL_COLUMNS = {
    "LICENSE_NO": "Số giấy phép", 
    "FREQUENCY": "Tần số phát",
    "BANDWIDTH": "Phương thức phát", 
    "LAT": "Vị trí anten: Vĩ độ",
    "LON": "Vị trí anten: Kinh độ", 
    "ADDRESS": "Địa điểm đặt thiết bị", 
    "PROVINCE_OLD": "Tỉnh thành",      
    "ANTENNA_HEIGHT": "Kích thước anten" 
}

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
    # Loại bỏ các từ khóa hành chính
    text = re.sub(r'thanh pho|tinh|tp\.|tp ', '', text)
    text = re.sub(r'[^a-z0-9]', '', text) 
    return text.upper()

class ToolAnDinhTanSo:
    def __init__(self, excel_file):
        file_name = ""
        if hasattr(excel_file, 'name'):
            file_name = excel_file.name
            file_source = excel_file
        elif isinstance(excel_file, str):
            file_name = excel_file
            file_source = excel_file
        
        print(f"--- ĐỌC DB: {file_name} ---")
        try:
            if file_name.lower().endswith('.csv'): self.df = pd.read_csv(file_source)
            else:
                try: self.df = pd.read_excel(file_source, engine='openpyxl')
                except: 
                    try: self.df = pd.read_excel(file_source, engine='xlrd')
                    except: self.df = pd.read_excel(file_source)

            self.df.columns = self.df.columns.str.strip()
            rename_map = {}
            for key, col_name in EXCEL_COLUMNS.items():
                if col_name in self.df.columns:
                    rename_map[col_name] = {
                        "LICENSE_NO": "license", "FREQUENCY": "raw_freq",
                        "BANDWIDTH": "raw_bw", "LAT": "raw_lat",
                        "LON": "raw_lon", "ADDRESS": "raw_address",
                        "PROVINCE_OLD": "raw_province_col", "ANTENNA_HEIGHT": "h_anten"
                    }.get(key, key)
            
            if "raw_freq" not in rename_map.values():
                 for c in self.df.columns:
                     if "Tần số" in c and "phát" in c: rename_map[c] = "raw_freq"; break
            if "raw_address" not in rename_map.values():
                for c in self.df.columns:
                    c_lower = c.lower()
                    if "địa điểm" in c_lower or "địa chỉ" in c_lower: rename_map[c] = "raw_address"; break

            self.df = self.df.rename(columns=rename_map)
            self.clean_data()
            print(f"-> Đã tải và làm sạch {len(self.df)} hồ sơ.")
        except Exception as e:
            print(f"LỖI KHI ĐỌC FILE: {e}")
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
        return None

    def parse_bandwidth(self, emission_code):
        if pd.isna(emission_code): return 12.5
        code = str(emission_code).upper()
        if "16K" in code: return 25.0
        if "11K" in code or "8K5" in code: return 12.5
        if "4K0" in code: return 6.25
        return 12.5

    def clean_data(self):
        cleaned_rows = []
        has_province_col = 'raw_province_col' in self.df.columns
        has_address_col = 'raw_address' in self.df.columns
        
        for idx, row in self.df.iterrows():
            lat = self.convert_dms_to_decimal(row.get('raw_lat'))
            lon = self.convert_dms_to_decimal(row.get('raw_lon'))
            
            raw_prov_extracted = ""
            if has_province_col:
                val = str(row.get('raw_province_col', ''))
                if val.lower() not in ['nan', '', 'none']:
                    raw_prov_extracted = val
            
            if (not raw_prov_extracted) and has_address_col:
                parts = str(row.get('raw_address', '')).split(',')
                raw_prov_extracted = parts[-1] if len(parts) > 0 else str(row.get('raw_address', ''))
            
            clean_prov = chuan_hoa_text(raw_prov_extracted)
            is_holding = "LUUDONGTOANQUOC" in clean_prov
            
            has_coords = (lat is not None and lon is not None)
            
            if not has_coords and clean_prov == "":
                continue

            bw = self.parse_bandwidth(row.get('raw_bw'))
            clean_freq = str(row.get('raw_freq', '')).replace(',', '.').replace('MHZ', '').replace('MHz', '').replace(';', ' ')
            
            freqs = []
            for item in clean_freq.split():
                try:
                    f = float(item)
                    if f > 10: freqs.append(f)
                except: pass
            
            net_type = "LAN"
            license_str = str(row.get('license', '')).strip() # Giữ nguyên form gốc của giấy phép
            if "WAN" in license_str.upper(): net_type = "WAN_SIMPLEX" 
            
            for f in freqs:
                cleaned_rows.append({
                    "freq": f, "bw": bw, 
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

    def generate_candidates(self, band, bw, usage_mode):
        candidates = []
        allocations = config.FREQUENCY_ALLOCATION_VHF if band == 'VHF' else config.FREQUENCY_ALLOCATION_UHF
        step_mhz = bw / 1000.0 
        
        for start, end, modes, _ in allocations:
            if usage_mode in modes:
                curr = start
                while curr <= end + 0.00001:
                    curr_rounded = round(curr, 5) 
                    is_forbidden = any(r_s <= curr_rounded <= r_e for r_s, r_e in config.FORBIDDEN_BANDS)
                    is_shared = any(abs(curr_rounded - f_shared) < 0.0001 for f_shared in config.SHARED_FREQUENCIES)
                    if not is_forbidden and not is_shared:
                        candidates.append(curr_rounded)
                    curr += step_mhz
        return sorted(list(set(candidates)))

    def tinh_toan(self, user_input):
        if self.df.empty: return []
        results = []
        
        user_mode_tuple = self.xac_dinh_kich_ban_user(user_input)
        band = user_input['band']
        bw = user_input['bw']
        mode = user_input['usage_mode']
        
        raw_input_prov = str(user_input.get('province_code', ''))
        user_province_clean = chuan_hoa_text(raw_input_prov)
        
        candidates = self.generate_candidates(band, bw, mode)
        if not candidates: return []

        holding_mask = self.df['is_holding'] == True
        holding_freqs = self.df[holding_mask]['freq'].unique()
        candidates = [f for f in candidates if not any(abs(f - hf) < 0.0001 for hf in holding_freqs)]

        df_freqs = self.df['freq'].values
        df_provinces = self.df['province'].values 
        df_licenses = self.df['license'].values 
        
        for f_check in candidates:
            df_subset = self.df[np.abs(self.df['freq'] - f_check) < 0.035]
            is_usable = True
            
            for _, row in df_subset.iterrows():
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
                if "LAN" in mode:
                    mask_province = (df_provinces == user_province_clean)
                    mask_final = mask_freq_exact & mask_province
                else: 
                    mask_final = mask_freq_exact
                
                # --- LẤY DANH SÁCH SỐ GP ĐỂ HIỂN THỊ CHÚ THÍCH ---
                relevant_licenses = df_licenses[mask_final]
                # Lọc danh sách duy nhất, loại bỏ nan/rỗng, sắp xếp
                unique_lics = sorted(list(set([str(lic) for lic in relevant_licenses if str(lic).lower() not in ['nan', 'none', '']])))
                
                unique_count = len(unique_lics)
                license_str = ", ".join(unique_lics) # Tạo chuỗi: "123/GP, 456/GP"
                
                results.append({
                    "frequency": f_check, 
                    "reuse_factor": int(unique_count),
                    "license_list": license_str # Thêm trường này
                })
        
        results.sort(key=lambda x: x['reuse_factor'], reverse=True)
        
        for i, item in enumerate(results):
            new_item = {
                "STT": i + 1,
                "frequency": item["frequency"],
                "reuse_factor": item["reuse_factor"],
                "license_list": item["license_list"]
            }
            results[i] = new_item
            
        return results