"""
CSV 欄位映射器

根據檔案名稱和欄位內容自動偵測 CSV 類型（P1/P2/P3），
並將 CSV 欄位映射到 Record 模型的資料庫欄位。
"""

import re
from enum import StrEnum
from typing import Any

import pandas as pd


class CSVType(StrEnum):
    """CSV 檔案類型"""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    UNKNOWN = "UNKNOWN"


class CSVFieldMapper:
    """CSV 欄位映射器類"""

    # 檔案名稱模式
    P1_FILENAME_PATTERN = re.compile(r"^P1_", re.IGNORECASE)
    P2_FILENAME_PATTERN = re.compile(r"^P2_", re.IGNORECASE)
    P3_FILENAME_PATTERN = re.compile(r"^P3_", re.IGNORECASE)

    # P1 特徵欄位（吹膜製程參數）
    P1_SIGNATURE_COLUMNS = {
        "Actual Temp_C1(℃)",
        "Set Temp_C1(℃)",
        "Line Speed(M/min)",
        "Extruder Speed(rpm)",
    }

    # P2 特徵欄位（分條檢驗）
    P2_SIGNATURE_COLUMNS = {
        "Sheet Width(mm)",
        "Thicknessss1(μm)",
        "Appearance",
        "Slitting Result",
    }

    # P3 特徵欄位（最終檢驗）
    # P3_No. 為可選欄位（舊格式有，新格式沒有）
    P3_SIGNATURE_COLUMNS = {
        "E_Value",
        "E Value",  # 新格式
        "Burr",
        "Finish",
        "Machine NO",  # 新格式特徵
        "Mold NO",  # 新格式特徵
    }

    # P1/P2 可能的材料代號欄位名稱
    MATERIAL_CODE_FIELD_NAMES = [
        "Material",
        "Material Code",
        "material",
        "material_code",
        "材料",
        "材料代號",
    ]

    # P2 可能的分條機編號欄位名稱
    SLITTING_MACHINE_FIELD_NAMES = [
        "Slitting Machine",
        "Slitting machine",
        "slitting_machine",
        "Machine",
        "machine",
        "分條機",
    ]

    # P2 可能的收卷機編號欄位名稱
    WINDER_NUMBER_FIELD_NAMES = [
        "Winder",
        "Winder Number",
        "Winder number",
        "winder",
        "winder_number",
        "收卷機",
        "收卷機編號",
    ]

    # P3 可能的機台編號欄位名稱（從檔案名稱或欄位提取）
    MACHINE_NO_FIELD_NAMES = [
        "Machine NO",  # 新格式（大寫 NO）
        "Machine No",
        "Machine",
        "machine_no",
        "machine",
        "機台",
        "機台編號",
    ]

    # 日期欄位可能的名稱（包含 year-month-day 格式）
    DATE_FIELD_NAMES = [
        "year-month-day",
        "Year-Month-Day",
        "production_date",
        "production date",
        "生產日期",
        "date",
        "Date",
    ]

    # P3 可能的 lot 欄位名稱
    LOT_FIELD_NAMES = ["lot", "Lot", "lot_no", "Lot No", "lot no", "production_lot"]

    # P3 可能的模具編號欄位名稱（從檔案名稱或欄位提取）
    MOLD_NO_FIELD_NAMES = [
        "Mold NO",  # 新格式（大寫 NO）
        "Mold No",
        "Mold",
        "mold_no",
        "mold",
        "模具",
        "模具編號",
    ]

    # P3 可能的規格欄位名稱
    SPECIFICATION_FIELD_NAMES = ["Specification", "specification", "規格", "Spec"]

    # P3 可能的產品編號欄位名稱
    PRODUCT_ID_FIELD_NAMES = [
        "Product ID",
        "Product Id",
        "product_id",
        "product id",
        "P3_No.",
        "P3 No.",
        "P3_No",
        "產品編號",
        "品號",
    ]

    # P3 可能的來源收卷機欄位名稱
    SOURCE_WINDER_FIELD_NAMES = [
        "Source Winder",
        "Source winder",
        "source_winder",
        "source winder",
        "Source Winder No",
        "Source Winder No.",
        "source_winder_number",
        "來源收卷機",
        "來源收卷機編號",
    ]

    # Lot number 欄位可能的名稱（用於 lot_no；避免跟生產 lot 序號/lot 欄位混用）
    # - P1: "LOT NO."
    # - P2: "Semi-finished productsLOT NO"
    # - P3: "lot no"
    LOT_NO_FIELD_NAMES = [
        "LOT NO.",
        "LOT NO",
        "Lot No",
        "Lot NO",
        "lot no",
        "lot_no",
        "Semi-finished productsLOT NO",
        "Semi-finished products LOT NO",
        "Semi-finished productsLOT NO.",
        "Semi-finished products LOT NO.",
    ]

    # P3 可能的下膠編號欄位名稱
    BOTTOM_TAPE_FIELD_NAMES = [
        "Bottom Tape",
        "bottom tape",
        "Bottom Tape LOT",
        "下膠編號",
        "下膠",
    ]

    # P3 可能的下膠批號/LOT 欄位名稱（兼容 import_v2 使用 BOTTOM_TAPE_LOT_FIELD_NAMES）
    BOTTOM_TAPE_LOT_FIELD_NAMES = [
        *BOTTOM_TAPE_FIELD_NAMES,
        "bottom_tape_lot",
        "Bottom Tape Lot",
        "Bottom Tape LOT No",
        "Bottom Tape Lot No",
        "下膠批號",
        "下膠LOT",
    ]

    def __init__(self):
        """初始化映射器"""
        pass

    def detect_csv_type(self, filename: str, columns: list[str]) -> CSVType:
        """
        根據檔案名稱和欄位內容偵測 CSV 類型

        Args:
            filename: 檔案名稱
            columns: CSV 欄位列表

        Returns:
            CSVType: 偵測到的 CSV 類型
        """
        # 優先根據檔案名稱判斷
        if self.P1_FILENAME_PATTERN.match(filename):
            return CSVType.P1
        elif self.P2_FILENAME_PATTERN.match(filename):
            return CSVType.P2
        elif self.P3_FILENAME_PATTERN.match(filename):
            return CSVType.P3

        # 根據欄位特徵判斷
        column_set = set(columns)

        # 檢查 P3 特徵（檢查多個特徵欄位）
        p3_matches = len(self.P3_SIGNATURE_COLUMNS & column_set)
        if (
            p3_matches >= 3
        ):  # 至少匹配 3 個 P3 特徵欄位（Burr, Finish, E_Value/E Value, Machine NO, Mold NO 等）
            return CSVType.P3

        # 檢查 P2 特徵
        p2_matches = len(self.P2_SIGNATURE_COLUMNS & column_set)
        if p2_matches >= 2:  # 至少匹配 2 個 P2 特徵欄位
            return CSVType.P2

        # 檢查 P1 特徵
        p1_matches = len(self.P1_SIGNATURE_COLUMNS & column_set)
        if p1_matches >= 3:  # 至少匹配 3 個 P1 特徵欄位
            return CSVType.P1

        return CSVType.UNKNOWN

    def extract_from_csv_row(
        self, row: pd.Series, csv_type: CSVType, filename: str
    ) -> dict[str, Any]:
        """
        從 CSV 行中提取映射資料

        Args:
            row: pandas Series（CSV 的一行）
            csv_type: CSV 類型
            filename: 檔案名稱（用於 P3 提取機台和模具編號）

        Returns:
            Dict[str, Any]: 映射後的欄位資料
        """
        result = {}

        if csv_type == CSVType.P1:
            # P1: 提取材料代號
            result["material_code"] = self._extract_field_value(
                row, self.MATERIAL_CODE_FIELD_NAMES
            )

        elif csv_type == CSVType.P2:
            # P2: 提取材料代號、分條機編號、收卷機編號
            result["material_code"] = self._extract_field_value(
                row, self.MATERIAL_CODE_FIELD_NAMES
            )
            result["slitting_machine_number"] = self._extract_integer_field(
                row, self.SLITTING_MACHINE_FIELD_NAMES
            )
            result["winder_number"] = self._extract_integer_field(
                row, self.WINDER_NUMBER_FIELD_NAMES
            )

        elif csv_type == CSVType.P3:
            # P3: 提取機台編號、模具編號、生產序號號、來源收卷機
            # 優先從 P3_No. 欄位提取
            p3_no = row.get("P3_No.")
            # 新格式可能使用 'lot no'
            if pd.isna(p3_no):
                p3_no = row.get("lot no")

            if pd.notna(p3_no):
                p3_parts = self._parse_p3_no(str(p3_no))
                result.update(p3_parts)

            # 嘗試從 'lot' 欄位提取 production_lot (新格式)
            if "production_lot" not in result:
                prod_lot = self._extract_field_value(row, self.LOT_FIELD_NAMES)
                if prod_lot:
                    try:
                        result["production_lot"] = int(float(prod_lot))
                    except (ValueError, TypeError):
                        result["production_lot"] = prod_lot

            # 日期優先：若存在 year-month-day 等欄位，嘗試正規化為 YYYYMMDD
            date_val = self._extract_field_value(row, self.DATE_FIELD_NAMES)
            if date_val:
                yyyymmdd = self._normalize_date_to_yyyymmdd(str(date_val))
                if yyyymmdd:
                    result["production_date_yyyymmdd"] = yyyymmdd

            # 如果 P3_No. 沒有提供完整資訊，嘗試從其他欄位或檔案名稱提取
            if not result.get("machine_no"):
                result["machine_no"] = self._extract_field_value(
                    row, self.MACHINE_NO_FIELD_NAMES
                ) or self._extract_machine_from_filename(filename)

            if not result.get("mold_no"):
                result["mold_no"] = self._extract_field_value(
                    row, self.MOLD_NO_FIELD_NAMES
                ) or self._extract_mold_from_filename(filename)

            # 提取規格與下膠編號
            result["specification"] = self._extract_field_value(
                row, self.SPECIFICATION_FIELD_NAMES
            )
            result["bottom_tape_lot"] = self._extract_field_value(
                row, self.BOTTOM_TAPE_FIELD_NAMES
            )

        return result

    def _extract_field_value(
        self, row: pd.Series, field_names: list[str]
    ) -> str | None:
        """
        從多個可能的欄位名稱中提取值

        Args:
            row: pandas Series
            field_names: 可能的欄位名稱列表

        Returns:
            Optional[str]: 提取的值，如果都不存在則返回 None
        """
        for field_name in field_names:
            if field_name in row.index:
                value = row[field_name]
                if pd.notna(value):
                    return str(value).strip()
        return None

    def _extract_integer_field(
        self, row: pd.Series, field_names: list[str]
    ) -> int | None:
        """
        從多個可能的欄位名稱中提取整數值

        Args:
            row: pandas Series
            field_names: 可能的欄位名稱列表

        Returns:
            Optional[int]: 提取的整數值，如果都不存在或無法轉換則返回 None
        """
        value_str = self._extract_field_value(row, field_names)
        if value_str:
            try:
                return int(float(value_str))
            except (ValueError, TypeError):
                pass
        return None

    def _normalize_date_to_yyyymmdd(self, date_str: str) -> int | None:
        """
        將常見日期字串正規化為 YYYYMMDD（整數）
        支援格式：YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, YYMMDD, year-month-day 等
        """
        if not date_str:
            return None
        # 移除空白
        s = date_str.strip()

        import re

        # P3 常見格式：114年09月02日（民國年中文格式）
        chinese_match = re.match(
            r"^(\d{3})年(\d{1,2})月(\d{1,2})日(?:\s*\d{1,2}:\d{1,2}(?::\d{1,2})?)?$", s
        )
        if chinese_match:
            try:
                roc_year = int(chinese_match.group(1))
                month = int(chinese_match.group(2))
                day = int(chinese_match.group(3))
                ad_year = roc_year + 1911
                return ad_year * 10000 + month * 100 + day
            except ValueError:
                return None

        # 用非數字字符分隔
        digits = re.findall(r"\d+", s)
        if not digits:
            return None

        # 如果整串是純數字並長度為8，直接使用
        if s.isdigit() and len(s) == 8:
            try:
                return int(s)
            except ValueError:
                return None

        # 如果存在 '-' 或 '/'，嘗試以分隔符解析
        if "-" in s or "/" in s:
            sep = "-" if "-" in s else "/"
            parts = s.split(sep)
            if len(parts) == 3:
                y, m, d = parts
                # 處理兩位年（如 25 -> 2025）
                if len(y) == 2:
                    y = "20" + y
                # 處理民國年（如 114/09/02 -> 2025/09/02）
                elif len(y) == 3 and y.isdigit():
                    y = str(int(y) + 1911)
                try:
                    y_i = int(y)
                    m_i = int(m)
                    d_i = int(d)
                    return y_i * 10000 + m_i * 100 + d_i
                except ValueError:
                    return None

        # 若拆出多段數字，試用常見排列
        all_digits = "".join(digits)
        if len(all_digits) == 8:
            try:
                return int(all_digits)
            except ValueError:
                return None
        if len(all_digits) == 7:
            # YYYMMDD (民國年) -> YYYYMMDD
            # 例如：1140902 -> 20250902
            try:
                roc_year = int(all_digits[:3])
                month = int(all_digits[3:5])
                day = int(all_digits[5:7])
                ad_year = roc_year + 1911
                return ad_year * 10000 + month * 100 + day
            except ValueError:
                return None
        if len(all_digits) == 6:
            # YYMMDD -> assume 20YY
            try:
                y = int(all_digits[:2])
                m = int(all_digits[2:4])
                d = int(all_digits[4:6])
                y_full = 2000 + y
                return y_full * 10000 + m * 100 + d
            except ValueError:
                return None
        return None

    def _parse_p3_no(self, p3_no: str) -> dict[str, Any]:
        """
        解析 P3_No. 欄位

        格式：YYYYMDD_MM_WW_LLL
        - YYYYMDD: 7位數字日期
        - MM: 2位數字機台/批次
        - WW: 收卷機編號（來源）
        - LLL: 生產序號號

        範例：2411012_04_34_301
        - lot_no: 2411012_04 （正規化後：2411012-04）
        - source_winder: 34
        - production_lot: 301

        Args:
            p3_no: P3_No. 欄位值

        Returns:
            Dict[str, Any]: 解析後的資料
        """
        result = {}

        if not p3_no:
            return result

        parts = p3_no.split("_")

        if len(parts) >= 4:
            # 提取各部分
            date_part = parts[0]  # YYYYMDD
            machine_part = parts[1]  # MM
            winder_part = parts[2]  # WW
            lot_part = parts[3]  # LLL

            # lot_no: YYYYMDD-MM
            result["lot_no"] = f"{date_part}-{machine_part}"

            # source_winder: 收卷機編號
            try:
                result["source_winder"] = int(winder_part)
            except (ValueError, TypeError):
                pass

            # production_lot: 生產序號號
            try:
                result["production_lot"] = int(lot_part)
            except (ValueError, TypeError):
                pass
        elif len(parts) == 3:
            # 新格式：YYYYMDD_MM_WW (e.g. 2507173_02_17)
            date_part = parts[0]
            machine_part = parts[1]
            winder_part = parts[2]

            # lot_no: YYYYMDD-MM
            result["lot_no"] = f"{date_part}-{machine_part}"

            # source_winder: 收卷機編號
            try:
                result["source_winder"] = int(winder_part)
            except (ValueError, TypeError):
                pass

        return result

    def _extract_machine_from_filename(self, filename: str) -> str | None:
        """
        從 P3 檔案名稱中提取機台編號

        範例：
        - P3_0902_P24.csv → P24
        - P3_0210_P02.csv → P02

        Args:
            filename: 檔案名稱

        Returns:
            Optional[str]: 機台編號，如果無法提取則返回 None
        """
        # P3 檔案名稱格式：P3_日期_機台.csv
        pattern = re.compile(r"P3_\d+_(P\d+)", re.IGNORECASE)
        match = pattern.search(filename)
        if match:
            return match.group(1).upper()
        return None

    def _extract_mold_from_filename(self, filename: str) -> str | None:
        """
        從檔案名稱中提取模具編號（如果有）

        Args:
            filename: 檔案名稱

        Returns:
            Optional[str]: 模具編號，如果無法提取則返回 None
        """
        # 模具編號通常需要從其他來源提供，檔案名稱中不一定包含
        # 這裡預留擴充功能
        return None

    def map_csv_to_record_fields(
        self, df: pd.DataFrame, filename: str, csv_type: CSVType | None = None
    ) -> list[dict[str, Any]]:
        """
        將整個 DataFrame 映射到 Record 欄位

        Args:
            df: pandas DataFrame
            filename: 檔案名稱
            csv_type: CSV 類型（如果為 None 則自動偵測）

        Returns:
            List[Dict[str, Any]]: 映射後的資料列表
        """
        # 自動偵測 CSV 類型
        if csv_type is None:
            csv_type = self.detect_csv_type(filename, df.columns.tolist())

        results = []

        for _, row in df.iterrows():
            mapped_data = self.extract_from_csv_row(row, csv_type, filename)

            # 將整行資料作為 additional_data（JSONB）
            row_dict = row.to_dict()
            # 清理 NaN 值
            cleaned_row = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}

            mapped_data["additional_data"] = cleaned_row
            results.append(mapped_data)

        return results


# 創建單例實例
csv_field_mapper = CSVFieldMapper()
