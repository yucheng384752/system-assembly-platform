"""
生產日期提取器

根據不同的資料類型（P1/P2/P3）從不同的欄位提取生產日期：
- P1: 從 "Production Date" 欄位提取
- P2: 從 "分條時間" 欄位提取（民國年格式）
- P3: 從 "year-month-day" 欄位提取（民國年格式）

所有日期統一轉換為西元年 YYYY-MM-DD 格式
"""

import re
from datetime import date, datetime
from typing import Any


class ProductionDateExtractor:
    """生產日期提取器"""

    # P1 可能的生產日期欄位名稱
    P1_DATE_FIELD_NAMES = [
        "Production Date",
        "production_date",
        "ProductionDate",
        "生產日期",
        "Date",
    ]

    # P2 可能的分條時間欄位名稱
    P2_DATE_FIELD_NAMES = [
        "分條時間",
        "Slitting Time",
        "slitting_time",
        "SlittingTime",
        "日期",
    ]

    # P3 可能的日期欄位名稱
    P3_DATE_FIELD_NAMES = ["year-month-day", "Year-Month-Day", "Date", "年月日", "日期"]

    def extract_production_date(
        self, row_data: dict[str, Any], data_type: str
    ) -> date | None:
        """
        根據資料類型提取生產日期

        Args:
            row_data: 行資料（包含 additional_data）
            data_type: 資料類型 (P1/P2/P3)

        Returns:
            Optional[date]: 生產日期，如果無法提取則返回 None
        """
        additional_data = row_data.get("additional_data", {})

        if data_type == "P1":
            return self._extract_p1_date(additional_data)
        elif data_type == "P2":
            return self._extract_p2_date(additional_data)
        elif data_type == "P3":
            return self._extract_p3_date(additional_data)

        return None

    def _extract_p1_date(self, data: dict[str, Any]) -> date | None:
        """
        從 P1 資料中提取生產日期

        P1 的 Production Date 可能格式：
        - YYYY-MM-DD (標準格式)
        - YYMMDD (6位數字)
        - YY-MM-DD

        Args:
            data: additional_data 字典

        Returns:
            Optional[date]: 生產日期
        """
        date_value = self._find_field_value(data, self.P1_DATE_FIELD_NAMES)
        if not date_value:
            return None

        return self._parse_date_string(str(date_value))

    def _extract_p2_date(self, data: dict[str, Any]) -> date | None:
        """
        從 P2 資料中提取分條時間

        P2 的分條時間通常是民國年格式：
        - YYY/MM/DD (如: 114/09/02)
        - YYY-MM-DD
        - YYYMMDD (6位數字)

        Args:
            data: additional_data 字典

        Returns:
            Optional[date]: 生產日期
        """
        date_value = self._find_field_value(data, self.P2_DATE_FIELD_NAMES)
        if not date_value:
            return None

        date_str = str(date_value).strip()

        # 嘗試解析民國年格式
        parsed_date = self._parse_roc_date(date_str)
        if parsed_date:
            return parsed_date

        # 如果不是民國年，嘗試標準格式
        return self._parse_date_string(date_str)

    def _extract_p3_date(self, data: dict[str, Any]) -> date | None:
        """
        從 P3 資料中提取 year-month-day

        P3 的 year-month-day 格式：
        - "114年09月02日" (民國年中文格式)
        - "114/09/02"
        - "114-09-02"

        Args:
            data: additional_data 字典

        Returns:
            Optional[date]: 生產日期
        """
        date_value = self._find_field_value(data, self.P3_DATE_FIELD_NAMES)
        if not date_value:
            return None

        date_str = str(date_value).strip()

        # 嘗試解析中文格式：114年09月02日
        chinese_match = re.match(r"(\d{3})年(\d{1,2})月(\d{1,2})日", date_str)
        if chinese_match:
            roc_year = int(chinese_match.group(1))
            month = int(chinese_match.group(2))
            day = int(chinese_match.group(3))
            ad_year = roc_year + 1911
            try:
                return date(ad_year, month, day)
            except ValueError:
                return None

        # 嘗試解析民國年格式
        parsed_date = self._parse_roc_date(date_str)
        if parsed_date:
            return parsed_date

        # 如果不是民國年，嘗試標準格式
        return self._parse_date_string(date_str)

    def _find_field_value(self, data: dict[str, Any], field_names: list) -> Any | None:
        """
        從多個可能的欄位名稱中找到值

        Args:
            data: 資料字典
            field_names: 可能的欄位名稱列表

        Returns:
            Optional[Any]: 找到的值
        """
        for field_name in field_names:
            if field_name in data:
                value = data[field_name]
                if value is not None and str(value).strip():
                    return value
        return None

    def _parse_roc_date(self, date_str: str) -> date | None:
        """
        解析民國年日期

        支援格式：
        - YYY/MM/DD (如: 114/09/02)
        - YYY-MM-DD
        - YYYMMDD (6位數字，如: 1140902)

        Args:
            date_str: 日期字串

        Returns:
            Optional[date]: 解析後的日期
        """
        # 格式1: YYY/MM/DD 或 YYY-MM-DD
        slash_match = re.match(r"^(\d{3})[\/-](\d{1,2})[\/-](\d{1,2})$", date_str)
        if slash_match:
            roc_year = int(slash_match.group(1))
            month = int(slash_match.group(2))
            day = int(slash_match.group(3))
            ad_year = roc_year + 1911
            try:
                return date(ad_year, month, day)
            except ValueError:
                return None

        # 格式2: YYYMMDD (6位數字)
        if date_str.isdigit() and len(date_str) == 7:
            try:
                roc_year = int(date_str[:3])
                month = int(date_str[3:5])
                day = int(date_str[5:7])
                ad_year = roc_year + 1911
                return date(ad_year, month, day)
            except (ValueError, IndexError):
                return None

        return None

    def _parse_date_string(self, date_str: str) -> date | None:
        """
        解析標準日期字串

        支援格式：
        - YYYY-MM-DD (標準格式)
        - YYMMDD (6位數字，自動加上 20 前綴)
        - YY-MM-DD

        Args:
            date_str: 日期字串

        Returns:
            Optional[date]: 解析後的日期
        """
        date_str = str(date_str).strip()

        # 格式1: YYYY-MM-DD 或 YYYY/MM/DD
        try:
            if "-" in date_str:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            elif "/" in date_str:
                return datetime.strptime(date_str, "%Y/%m/%d").date()
        except ValueError:
            pass

        # 格式2: YYMMDD (6位數字)
        if date_str.isdigit() and len(date_str) == 6:
            try:
                year = int(date_str[:2]) + 2000  # 25 -> 2025
                month = int(date_str[2:4])
                day = int(date_str[4:6])
                return date(year, month, day)
            except ValueError:
                return None

        # 格式3: YY-MM-DD
        yy_match = re.match(r"^(\d{2})-(\d{2})-(\d{2})$", date_str)
        if yy_match:
            try:
                year = int(yy_match.group(1)) + 2000
                month = int(yy_match.group(2))
                day = int(yy_match.group(3))
                return date(year, month, day)
            except ValueError:
                return None

        return None


# 創建單例實例
production_date_extractor = ProductionDateExtractor()
