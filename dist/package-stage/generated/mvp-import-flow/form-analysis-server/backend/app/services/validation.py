"""
資料驗證服務

提供檔案上傳和資料驗證的業務邏輯。
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# 導入常數配置
from app.config.constants import (
    VALID_MATERIALS,
    VALID_SLITTING_MACHINES,
    get_material_list,
    get_slitting_machine_list,
)
from app.services.csv_field_mapper import CSVFieldMapper


class ValidationError(Exception):
    """驗證錯誤例外"""

    def __init__(self, message: str, errors: list[dict[str, Any]] = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)


class FileValidationService:
    """檔案驗證服務類"""

    # 必要欄位集合 - 移除product_name, quantity, production_date的必要性
    REQUIRED_COLUMNS = set()  # 不再強制要求特定欄位

    # 批號正規表示式：7位數字_2位數字（標準格式）
    LOT_NO_PATTERN = re.compile(r"^\d{7}_\d{2}$")

    # 批號彈性格式：支援 -/_ 分隔，與 7+2+任意後續
    LOT_NO_FLEXIBLE_PATTERN = re.compile(r"^(\d{7})[-_](\d{1,2})(?:[-_].+)?$")

    # P3檔案名稱檢測模式
    P3_PATTERN = re.compile(r"P3_")

    # 日期格式
    DATE_FORMAT = "%Y-%m-%d"

    def __init__(self):
        """初始化驗證服務"""
        self.errors: list[dict[str, Any]] = []
        self.total_rows = 0
        self.valid_rows = 0
        self.invalid_rows = 0

    def reset_counters(self):
        """重置計數器和錯誤清單"""
        self.errors.clear()
        self.total_rows = 0
        self.valid_rows = 0
        self.invalid_rows = 0

    def validate_file_format(self, filename: str) -> bool:
        """
        驗證檔案格式是否支援

        Args:
            filename: 檔案名稱

        Returns:
            bool: 是否為支援的格式
        """
        if not filename:
            return False

        filename_lower = filename.lower()
        return (
            filename_lower.endswith(".csv")
            or filename_lower.endswith(".xlsx")
            or filename_lower.endswith(".xls")
        )

    def read_file(self, file_content: bytes, filename: str) -> pd.DataFrame:
        """
        讀取檔案內容為 DataFrame

        Args:
            file_content: 檔案二進位內容
            filename: 檔案名稱

        Returns:
            pd.DataFrame: 解析後的資料框

        Raises:
            ValidationError: 檔案讀取或解析錯誤
        """
        try:
            if filename.lower().endswith(".csv"):
                # 讀取 CSV 檔案，自動偵測編碼
                df = pd.read_csv(
                    pd.io.common.BytesIO(file_content),
                    encoding="utf-8-sig",  # 處理 BOM
                )
            elif filename.lower().endswith((".xlsx", ".xls")):
                # 讀取 Excel 檔案
                df = pd.read_excel(
                    pd.io.common.BytesIO(file_content),
                    engine="openpyxl" if filename.lower().endswith(".xlsx") else "xlrd",
                )
            else:
                raise ValidationError("不支援的檔案格式，僅支援 CSV 和 Excel 檔案")

            # 常見情況：檔案尾端有「整行空白」或全是空白字元的列
            # 這些列不應影響驗證結果，直接排除。
            df = df.replace(r"^\s*$", pd.NA, regex=True)
            df = df.dropna(how="all")

            return df

        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(f"檔案讀取失敗：{str(e)}")

    def validate_columns(self, df: pd.DataFrame, filename: str) -> None:
        """
        驗證資料框欄位是否符合要求

        Args:
            df: 要驗證的資料框
            filename: 檔案名稱，用於判斷是否為P3檔案

        Raises:
            ValidationError: 欄位驗證失敗
        """
        # P3 檔案不再強制要求 P3_No. 欄位（新舊格式都支援）
        # 新格式 P3 檔案會有 Machine NO, Mold NO, lot no 等欄位
        # 不再檢查必要欄位，允許任何欄位存在

    def _extract_lot_no_from_row(self, row: pd.Series) -> tuple[str, str]:
        """從單列資料中找出 lot_no（回傳 lot_value, source_field）。"""
        for field in CSVFieldMapper.LOT_NO_FIELD_NAMES:
            if field in row.index:
                v = row.get(field)
                if pd.isna(v) or v is None:
                    continue
                s = str(v).strip()
                if s:
                    return s, field
        return "", "lot_no"

    def _infer_lot_no_from_filename(self, filename: str) -> str:
        """從檔名推論 lot_no（備援）。

        目標：支援常見命名如 P1_2507173_02.csv / P2_2507173_2_17.csv。
        回傳值會先做 normalize_lot_no（7位數字_2位數字）。
        """
        name = Path(filename or "").name
        if not name:
            return ""

        stem = Path(name).stem
        # Find 7-digit + ('_' or '-') + 1~2-digit (and ignore trailing segments)
        m = re.search(r"(\d{7}[-_]\d{1,2})(?:[-_].+)?$", stem)
        if not m:
            return ""
        return self.normalize_lot_no(m.group(1))

    def extract_lot_no_from_p3_field(self, p3_no_value: Any) -> str:
        """
        從P3_No.欄位中擷取lot_no (格式: 7位數字_2位數字)
        P3_No.格式例: 2411012_04_31_302 → 擷取: 2411012_04

        Args:
            p3_no_value: P3_No.欄位的值

        Returns:
            str: 擷取的lot_no，如果無法擷取則返回空字串
        """
        if pd.isna(p3_no_value) or p3_no_value is None:
            return ""

        p3_str = str(p3_no_value).strip()

        normalized = self.normalize_lot_no(p3_str)
        if normalized and self.LOT_NO_PATTERN.match(normalized):
            return normalized
        return ""

    def normalize_lot_no(self, lot_no_value: Any) -> str:
        """
        正規化批號：將 7+2+2 格式截取為標準 7+2 格式

        支援格式：
        - 7+2: 2507173_02 → 2507173_02
        - 7+2+2: 2507173_02_17 → 2507173_02
        - 7+2+其他: 2507173_02_xxx → 2507173_02

        Args:
            lot_no_value: 批號值

        Returns:
            str: 正規化後的批號（7+2格式），如果無法解析則返回空字串
        """
        if pd.isna(lot_no_value) or lot_no_value is None:
            return ""

        lot_no_str = str(lot_no_value).strip()

        # 支援格式：7位數字[-_](1~2位數字)([-_]*...)
        # 例：2507173_02_17 / 2507173-2-17 / 2507173-02
        m = re.match(r"^(\d{7})[-_](\d{1,2})(?:[-_].+)?$", lot_no_str)
        if m:
            head = m.group(1)
            tail = m.group(2).zfill(2)
            return f"{head}_{tail}"

        # 如果不符合任何格式，返回原值（讓後續驗證處理）
        return lot_no_str

    def validate_lot_no(self, lot_no: Any, row_index: int) -> bool:
        """
        驗證批號格式（支援彈性格式）

        支援格式：
        - 標準格式：7位數字_2位數字 (例如：2507173_02)
        - 擴充格式：7位數字_2位數字_其他 (例如：2507173_02_17，會自動截取前9碼)

        Args:
            lot_no: 批號值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(lot_no) or lot_no is None:
            self.add_error(row_index, "lot_no", "REQUIRED_FIELD", "批號不能為空")
            return False

        lot_no_str = str(lot_no).strip()
        if not lot_no_str:
            self.add_error(row_index, "lot_no", "REQUIRED_FIELD", "批號不能為空")
            return False

        # 先嘗試正規化（支援 7+2+2 格式）
        normalized_lot_no = self.normalize_lot_no(lot_no)

        # 驗證正規化後的批號
        if not normalized_lot_no or not self.LOT_NO_PATTERN.match(normalized_lot_no):
            self.add_error(
                row_index,
                "lot_no",
                "INVALID_FORMAT",
                f"批號格式錯誤，應為 7位數字[-_]2位數字 格式（可帶後綴），實際值：{lot_no_str}",
            )
            return False

        return True

    def validate_product_name(self, product_name: Any, row_index: int) -> bool:
        """
        驗證產品名稱

        Args:
            product_name: 產品名稱值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(product_name) or product_name is None:
            self.add_error(
                row_index, "product_name", "REQUIRED_FIELD", "產品名稱不能為空"
            )
            return False

        product_name_str = str(product_name).strip()
        if not product_name_str:
            self.add_error(
                row_index, "product_name", "REQUIRED_FIELD", "產品名稱不能為空"
            )
            return False

        if len(product_name_str) > 100:
            self.add_error(
                row_index,
                "product_name",
                "TOO_LONG",
                f"產品名稱長度不能超過100字元，實際長度：{len(product_name_str)}",
            )
            return False

        return True

    def validate_quantity(self, quantity: Any, row_index: int) -> bool:
        """
        驗證數量

        Args:
            quantity: 數量值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(quantity) or quantity is None:
            self.add_error(row_index, "quantity", "REQUIRED_FIELD", "數量不能為空")
            return False

        try:
            quantity_int = int(
                float(quantity)
            )  # 先轉 float 再轉 int，處理 "123.0" 的情況
        except (ValueError, TypeError):
            self.add_error(
                row_index,
                "quantity",
                "INVALID_FORMAT",
                f"數量必須為整數，實際值：{quantity}",
            )
            return False

        if quantity_int < 0:
            self.add_error(
                row_index,
                "quantity",
                "INVALID_RANGE",
                f"數量不能為負數，實際值：{quantity_int}",
            )
            return False

        return True

    def validate_production_date(self, production_date: Any, row_index: int) -> bool:
        """
        驗證生產日期

        Args:
            production_date: 生產日期值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(production_date) or production_date is None:
            self.add_error(
                row_index, "production_date", "REQUIRED_FIELD", "生產日期不能為空"
            )
            return False

        # 如果是 pandas Timestamp 或 datetime 物件
        if isinstance(production_date, (pd.Timestamp, datetime, date)):
            return True

        # 如果是字串，嘗試解析
        date_str = str(production_date).strip()
        if not date_str:
            self.add_error(
                row_index, "production_date", "REQUIRED_FIELD", "生產日期不能為空"
            )
            return False

        try:
            datetime.strptime(date_str, self.DATE_FORMAT)
            return True
        except ValueError:
            self.add_error(
                row_index,
                "production_date",
                "INVALID_FORMAT",
                f"生產日期格式錯誤，應為YYYY-MM-DD格式，實際值：{date_str}",
            )
            return False

    def extract_source_winder(self, lot_no: str) -> int | None:
        """
        從 P3 的 lot_no 中提取 source_winder（來源收卷機編號）

        範例：
        - 2507173_02_17 → 17
        - 2507173_02_5 → 5
        - 2507173_02 → None

        Args:
            lot_no: 批號字串（格式：YYYYMDD_MM_WW）

        Returns:
            Optional[int]: 收卷機編號，如果無法提取則返回 None
        """
        if not lot_no:
            return None

        lot_no_str = str(lot_no).strip()

        # 使用底線分割
        parts = lot_no_str.split("_")

        # P3 格式應該至少有 3 部分：日期_機台_收卷機
        if len(parts) < 3:
            return None

        # 取第三部分（收卷機編號）
        winder_part = parts[2]

        try:
            return int(winder_part)
        except (ValueError, TypeError):
            return None

    def validate_material_code(self, material_code: Any, row_index: int) -> bool:
        """
        驗證材料代號是否在有效清單中

        Args:
            material_code: 材料代號值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(material_code) or material_code is None:
            # 材料代號可選，不是必填欄位
            return True

        material_str = str(material_code).strip().upper()

        if material_str not in VALID_MATERIALS:
            valid_list = get_material_list()
            self.add_error(
                row_index,
                "material_code",
                "INVALID_VALUE",
                f"材料代號無效：{material_str}，有效值為：{', '.join(valid_list)}",
            )
            return False

        return True

    def validate_slitting_machine_number(
        self, machine_number: Any, row_index: int
    ) -> bool:
        """
        驗證分條機編號是否在有效清單中

        Args:
            machine_number: 分條機編號值
            row_index: 行索引

        Returns:
            bool: 驗證是否通過
        """
        if pd.isna(machine_number) or machine_number is None:
            # 分條機編號可選，不是必填欄位
            return True

        try:
            machine_int = int(float(machine_number))
        except (ValueError, TypeError):
            self.add_error(
                row_index,
                "slitting_machine_number",
                "INVALID_FORMAT",
                f"分條機編號必須為整數，實際值：{machine_number}",
            )
            return False

        if machine_int not in VALID_SLITTING_MACHINES:
            valid_list = get_slitting_machine_list()
            self.add_error(
                row_index,
                "slitting_machine_number",
                "INVALID_VALUE",
                f"分條機編號無效：{machine_int}，有效值為：{', '.join(map(str, valid_list))}",
            )
            return False

        return True

    def add_error(
        self, row_index: int, field: str, error_code: str, message: str
    ) -> None:
        """
        添加驗證錯誤

        Args:
            row_index: 行索引（從0開始）
            field: 欄位名稱
            error_code: 錯誤程式碼
            message: 錯誤訊息
        """
        error = {
            "row_index": row_index,
            "field": field,
            "error_code": error_code,
            "message": message,
        }
        self.errors.append(error)

    def validate_data_rows(
        self, df: pd.DataFrame, filename: str
    ) -> tuple[int, int, int]:
        """
        驗證所有資料列

        Args:
            df: 要驗證的資料框
            filename: 檔案名稱，用於判斷檔案類型和擷取lot_no

        Returns:
            Tuple[int, int, int]: (總行數, 有效行數, 無效行數)
        """
        self.reset_counters()
        self.total_rows = len(df)

        # 記錄每行是否有錯誤
        row_has_error = set()

        # 判斷檔案類型
        is_p3_file = self.P3_PATTERN.search(filename) is not None

        for row_num, (index, row) in enumerate(df.iterrows()):
            # pandas index may be int-like (RangeIndex) OR tuple (MultiIndex) depending on how the CSV was parsed.
            # We only need a stable 0-based row number for error reporting.
            try:
                row_index = int(index)
            except (TypeError, ValueError):
                row_index = int(row_num)

            # 根據檔案類型驗證lot_no
            if is_p3_file:
                # P3檔案：支援新舊兩種格式
                # 1. 新格式：從 "lot no" 欄位提取（優先）
                # 2. 舊格式：從 "P3_No." 欄位提取

                lot_no_value = None
                source_field = None

                # 嘗試從新格式的 "lot no" 欄位提取
                if "lot no" in row.index:
                    lot_no_value = row.get("lot no")
                    source_field = "lot no"
                # 回退到舊格式的 "P3_No." 欄位
                elif "P3_No." in row.index:
                    p3_no_value = row.get("P3_No.")
                    if pd.notna(p3_no_value):
                        lot_no_value = self.extract_lot_no_from_p3_field(p3_no_value)
                        source_field = "P3_No."

                # 驗證批號
                if not lot_no_value or pd.isna(lot_no_value):
                    self.add_error(
                        row_index,
                        source_field or "lot_no",
                        "REQUIRED_FIELD",
                        'P3檔案需要批號欄位（"lot no"）',
                    )
                    row_has_error.add(row_index)
                else:
                    # 正規化批號（支援 7+2+2 格式）
                    normalized_lot_no = self.normalize_lot_no(lot_no_value)

                    if not normalized_lot_no or not self.LOT_NO_PATTERN.match(
                        normalized_lot_no
                    ):
                        self.add_error(
                            row_index,
                            source_field,
                            "INVALID_FORMAT",
                            f"批號格式錯誤，應為 7位數字[-_]2位數字 格式（可帶後綴），實際值：{lot_no_value}",
                        )
                        row_has_error.add(row_index)
            else:
                # P1/P2 檔案：一律從內容欄位取得 lot_no（不再從檔名擷取）
                lot_no_value, source_field = self._extract_lot_no_from_row(row)
                if not lot_no_value:
                    # 備援：從檔名推論 lot_no（僅 P1/P2）
                    inferred_lot_no = self._infer_lot_no_from_filename(filename)
                    if inferred_lot_no:
                        lot_no_value = inferred_lot_no
                        source_field = "filename"
                    else:
                        self.add_error(
                            row_index, source_field, "REQUIRED_FIELD", "批號不能為空"
                        )
                        row_has_error.add(row_index)

                if lot_no_value:
                    # 正規化並驗證格式（7位數字_2位數字；允許後綴）
                    normalized_lot_no = self.normalize_lot_no(lot_no_value)
                    if not normalized_lot_no or not self.LOT_NO_PATTERN.match(
                        normalized_lot_no
                    ):
                        self.add_error(
                            row_index,
                            source_field,
                            "INVALID_FORMAT",
                            f"批號格式錯誤，應為 7位數字[-_]2位數字 格式（可帶後綴），實際值：{lot_no_value}",
                        )
                        row_has_error.add(row_index)

            # 不再驗證product_name, quantity, production_date等欄位

        # 計算統計資料
        self.invalid_rows = len(row_has_error)
        self.valid_rows = self.total_rows - self.invalid_rows

        return self.total_rows, self.valid_rows, self.invalid_rows

    def get_sample_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        取得錯誤樣本

        Args:
            limit: 最大錯誤數量

        Returns:
            List[Dict[str, Any]]: 錯誤清單
        """
        return self.errors[:limit]

    def validate_file(self, file_content: bytes, filename: str) -> dict[str, Any]:
        """
        完整檔案驗證流程

        Args:
            file_content: 檔案二進位內容
            filename: 檔案名稱

        Returns:
            Dict[str, Any]: 驗證結果

        Raises:
            ValidationError: 驗證失敗
        """
        # 1. 驗證檔案格式
        if not self.validate_file_format(filename):
            raise ValidationError("不支援的檔案格式，僅支援 CSV 和 Excel 檔案")

        # 2. 讀取檔案
        df = self.read_file(file_content, filename)

        # 3. 檢查是否為空檔案
        if df.empty:
            raise ValidationError("檔案內容為空")

        # 4. 驗證欄位
        self.validate_columns(df, filename)

        # 5. 驗證資料列
        total_rows, valid_rows, invalid_rows = self.validate_data_rows(df, filename)

        # 6. 判斷資料類型
        from app.models.record import DataType

        filename_lower = filename.lower()
        detected_data_type = DataType.P1  # 預設值
        detected_columns = list(df.columns) if not df.empty else []

        if filename_lower.startswith("p1_"):
            detected_data_type = DataType.P1
        elif filename_lower.startswith("p2_"):
            detected_data_type = DataType.P2
        elif filename_lower.startswith("p3_"):
            detected_data_type = DataType.P3
        else:
            # 根據欄位內容判斷
            if "P3_No." in detected_columns:
                detected_data_type = DataType.P3
            else:
                detected_data_type = DataType.P1  # 預設為P1

        # 7. 回傳驗證結果
        return {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
            "errors": self.errors,
            "sample_errors": self.get_sample_errors(10),
            "detected_data_type": detected_data_type.value,
            "detected_columns": detected_columns,
        }


# 建立全域驗證服務實例
file_validation_service = FileValidationService()
