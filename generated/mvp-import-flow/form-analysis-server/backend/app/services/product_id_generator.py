"""Product ID 產生器服務

唯一格式（canonical）：YYYYMMDD_machine_mold_lot
範例：20250902_P24_238-2_301

設計重點：
- 只允許用底線分隔日期/機台/模具/批號，避免模具號碼本身含 '-' 時造成歧義。
- 可允許尾端附加後綴（例如 `_dup9`）以處理去重。
"""

from datetime import date, datetime


class ProductIDGenerator:
    """
    Product ID 產生與解析服務

    Product ID 格式（唯一）: YYYYMMDD_machine_mold_lot
    - YYYYMMDD: 生產日期（8位數字）
    - machine: 機台編號（如 P24）
    - mold: 模具號碼（如 238-2）
    - lot: 批號（整數，如 301）

    範例:
    >>> generator = ProductIDGenerator()
    >>> product_id = generator.generate(
    ...     production_date=date(2025, 9, 2),
    ...     machine_no="P24",
    ...     mold_no="238-2",
    ...     production_lot=301
    ... )
    >>> print(product_id)
    20250902_P24_238-2_301

    >>> parsed = generator.parse(product_id)
    >>> print(parsed)
    {
        'production_date': datetime.date(2025, 9, 2),
        'machine_no': 'P24',
        'mold_no': '238-2',
        'production_lot': 301
    }
    """

    def generate(
        self, production_date: date, machine_no: str, mold_no: str, production_lot: int
    ) -> str:
        """
        產生 Product ID

        Args:
            production_date: 生產日期（date 物件）
            machine_no: 機台編號（如 "P24"）
            mold_no: 模具號碼（如 "238-2"）
            production_lot: 批號（整數，如 301）

        Returns:
            Product ID 字串，格式: YYYYMMDD_machine_mold_lot

        Raises:
            ValueError: 如果參數格式不正確

        Examples:
            >>> gen = ProductIDGenerator()
            >>> gen.generate(date(2025, 9, 2), "P24", "238-2", 301)
            '20250902_P24_238-2_301'
        """
        # 驗證參數
        if not isinstance(production_date, date):
            raise ValueError(
                f"production_date 必須是 date 物件: {type(production_date)}"
            )

        if not machine_no or not isinstance(machine_no, str):
            raise ValueError(f"machine_no 必須是非空字串: {machine_no}")

        if not mold_no or not isinstance(mold_no, str):
            raise ValueError(f"mold_no 必須是非空字串: {mold_no}")

        if not isinstance(production_lot, int) or production_lot < 0:
            raise ValueError(f"production_lot 必須是非負整數: {production_lot}")

        # 格式化日期為 YYYYMMDD
        date_str = production_date.strftime("%Y%m%d")

        # 組合 Product ID（唯一格式：底線分隔）
        product_id = f"{date_str}_{machine_no}_{mold_no}_{production_lot}"

        return product_id

    def generate_from_strings(
        self,
        production_date_str: str,
        machine_no: str,
        mold_no: str,
        production_lot: int,
    ) -> str:
        """
        從字串日期產生 Product ID

        Args:
            production_date_str: 生產日期字串（可接受多種格式）
            machine_no: 機台編號
            mold_no: 模具號碼
            production_lot: 批號

        Returns:
            Product ID 字串

        Examples:
            >>> gen = ProductIDGenerator()
            >>> gen.generate_from_strings("2025-09-02", "P24", "238-2", 301)
            '20250902_P24_238-2_301'
            >>> gen.generate_from_strings("20250902", "P24", "238-2", 301)
            '20250902_P24_238-2_301'
        """
        # 解析日期字串
        production_date = self._parse_date(production_date_str)

        # 使用標準產生方法
        return self.generate(production_date, machine_no, mold_no, production_lot)

    def parse(self, product_id: str) -> dict[str, any]:
        """
        解析 Product ID，取得原始資料

        Args:
            product_id: Product ID 字串

        Returns:
            包含以下欄位的字典:
            - production_date: date 物件
            - machine_no: 機台編號字串
            - mold_no: 模具號碼字串
            - production_lot: 批號整數

        Raises:
            ValueError: 如果 Product ID 格式不正確

        Examples:
            >>> gen = ProductIDGenerator()
            >>> result = gen.parse("20250902_P24_238-2_301")
            >>> result['production_date']
            datetime.date(2025, 9, 2)
            >>> result['machine_no']
            'P24'
            >>> result['production_lot']
            301
        """
        if not product_id or not isinstance(product_id, str):
            raise ValueError(f"product_id 必須是非空字串: {product_id}")

        # 分割 Product ID（唯一格式：底線分隔）
        # 允許尾端附加額外片段（例如去重後的 suffix: _dup9）
        if "_" not in product_id:
            raise ValueError(
                f"Product ID 格式錯誤：只接受底線格式 'YYYYMMDD_machine_mold_lot'，但收到: {product_id}"
            )

        parts = product_id.split("_")

        if len(parts) < 4:
            raise ValueError(
                f"Product ID 格式錯誤，應為 'YYYYMMDD_machine_mold_lot'，但收到: {product_id}"
            )

        # 解析：date (1) - machine (1) - mold (1+) - lot (1) [- suffix (optional)]
        # 前兩個固定是日期和機台，最後一個是批號（可能後面還有 dup 等後綴），中間的都是模具號碼
        date_str = parts[0]
        machine_no = parts[1]

        # 找到批號位置（排除 dup 等後綴）
        # 從倒數找第一個可以轉換成整數的部分
        lot_idx = -1
        for i in range(len(parts) - 1, 1, -1):  # 從後往前，但不包括前2個（日期和機台）
            try:
                int(parts[i])
                lot_idx = i
                break
            except ValueError:
                continue  # 這部分不是數字，可能是 dup9 之類的後綴

        if lot_idx == -1:
            raise ValueError(f"無法找到有效的批號（整數）: {product_id}")

        lot_str = parts[lot_idx]

        # 中間的部分組成模具號碼（模具本身可包含 '-'，不影響解析）
        if lot_idx > 2:
            mold_no = "_".join(parts[2:lot_idx])
        else:
            mold_no = parts[2]

        # 解析日期
        try:
            production_date = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError as e:
            raise ValueError(f"日期格式錯誤，應為 YYYYMMDD，但收到: {date_str}") from e

        # 解析批號
        try:
            production_lot = int(lot_str)
        except ValueError as e:
            raise ValueError(f"批號必須是整數，但收到: {lot_str}") from e

        return {
            "production_date": production_date,
            "machine_no": machine_no,
            "mold_no": mold_no,
            "production_lot": production_lot,
        }

    def validate(self, product_id: str) -> tuple[bool, str | None]:
        """
        驗證 Product ID 格式是否正確

        Args:
            product_id: 要驗證的 Product ID

        Returns:
            (是否有效, 錯誤訊息) 的元組
            如果有效，錯誤訊息為 None

        Examples:
            >>> gen = ProductIDGenerator()
            >>> gen.validate("20250902_P24_238-2_301")
            (True, None)
            >>> gen.validate("invalid_id")
            (False, 'Product ID 格式錯誤...')
        """
        try:
            self.parse(product_id)
            return (True, None)
        except ValueError as e:
            return (False, str(e))

    def _parse_date(self, date_str: str) -> date:
        """
        解析多種日期格式

        支援格式:
        - YYYY-MM-DD (ISO 8601)
        - YYYYMMDD (8位數字)
        - YYYY/MM/DD
        - DD/MM/YYYY
        - MM/DD/YYYY

        Args:
            date_str: 日期字串

        Returns:
            date 物件

        Raises:
            ValueError: 如果無法解析日期
        """
        # 移除空白
        date_str = date_str.strip()

        # 嘗試各種格式
        formats = [
            "%Y-%m-%d",  # 2025-09-02
            "%Y%m%d",  # 20250902
            "%Y/%m/%d",  # 2025/09/02
            "%d/%m/%Y",  # 02/09/2025
            "%m/%d/%Y",  # 09/02/2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # 所有格式都失敗
        raise ValueError(
            f"無法解析日期: {date_str}，支援格式: YYYY-MM-DD, YYYYMMDD, YYYY/MM/DD"
        )


# 單例實例
product_id_generator = ProductIDGenerator()


# 快捷函數，方便直接匯入使用
def generate_product_id(
    production_date: date, machine_no: str, mold_no: str, production_lot: int
) -> str:
    """
    快捷函數: 產生 Product ID

    Examples:
        >>> from app.services.product_id_generator import generate_product_id
        >>> from datetime import date
        >>> generate_product_id(date(2025, 9, 2), "P24", "238-2", 301)
        '20250902_P24_238-2_301'
    """
    return product_id_generator.generate(
        production_date, machine_no, mold_no, production_lot
    )


def parse_product_id(product_id: str) -> dict[str, any]:
    """
    快捷函數: 解析 Product ID

    Examples:
        >>> from app.services.product_id_generator import parse_product_id
        >>> parse_product_id("20250902_P24_238-2_301")
        {'production_date': datetime.date(2025, 9, 2), 'machine_no': 'P24', ...}
    """
    return product_id_generator.parse(product_id)


def validate_product_id(product_id: str) -> tuple[bool, str | None]:
    """
    快捷函數: 驗證 Product ID

    Examples:
        >>> from app.services.product_id_generator import validate_product_id
        >>> validate_product_id("20250902_P24_238-2_301")
        (True, None)
    """
    return product_id_generator.validate(product_id)
