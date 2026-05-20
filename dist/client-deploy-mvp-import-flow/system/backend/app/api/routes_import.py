"""
資料匯入 API 路由

提供將驗證通過的資料匯入到系統的 API 端點。
"""

import time
import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.core.tenant import Tenant
from app.models.p3_item import P3Item
from app.models.p3_item_v2 import P3ItemV2
from app.models.p3_record import P3Record
from app.models.record import Record
from app.models.upload_job import JobStatus, UploadJob
from app.schemas.import_data import ImportErrorResponse, ImportRequest, ImportResponse
from app.services.production_date_extractor import production_date_extractor
from app.utils.normalization import NormalizationError, normalize_lot_no

# 獲取日誌記錄器
logger = get_logger(__name__)

# 建立路由器
router = APIRouter()


def _pick_first_non_empty(row: dict, keys: list[str]):
    for k in keys:
        if k in row and row[k] is not None and str(row[k]).strip() != "":
            return row[k]
    return None


def _parse_int_like(value) -> int | None:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if s == "":
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _extract_production_lot(row: dict) -> int | None:
    raw = _pick_first_non_empty(
        row,
        ["lot", "Lot", "LOT", "Production Lot", "production_lot"],
    )
    return _parse_int_like(raw)


def _compose_p3_product_id(
    production_date,
    machine_no,
    mold_no,
    production_lot: int | None,
) -> str | None:
    if production_date is None or machine_no is None or mold_no is None:
        return None
    if production_lot is None:
        return None
    machine = str(machine_no).strip()
    mold = str(mold_no).strip()
    if not machine or not mold:
        return None
    return (
        f"{production_date.strftime('%Y%m%d')}_{machine}_{mold}_{int(production_lot)}"
    )


def _build_p3_extras_rows(all_rows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for r in all_rows:
        rows.append(
            {
                "lot": _pick_first_non_empty(
                    r, ["lot", "Lot", "LOT", "Production Lot", "production_lot"]
                ),
                "produce_no": _pick_first_non_empty(
                    r,
                    [
                        "Produce_No.",
                        "Produce No.",
                        "Produce_No",
                        "Produce No",
                        "ProduceNo",
                        "produce_no",
                    ],
                ),
                "adjustment_record": _pick_first_non_empty(
                    r,
                    [
                        "AdjustmentRecord",
                        "Adjustment Record",
                        "adjustment_record",
                        "Adjustment",
                    ],
                ),
                "finish": _pick_first_non_empty(r, ["Finish", "finish"]),
                "operator": _pick_first_non_empty(r, ["operator", "Operator", "OP"]),
                "specification": _pick_first_non_empty(
                    r, ["Specification", "specification", "Spec", "規格"]
                ),
                "source_winder": _pick_first_non_empty(
                    r,
                    [
                        "source_winder",
                        "Source Winder",
                        "Source winder",
                        "source winder",
                        "Winder number",
                        "winder number",
                        "Winder",
                        "winder",
                        "收卷機",
                        "收卷機編號",
                        "捲收機號碼",
                    ],
                ),
            }
        )
    return rows


async def _resolve_tenant_for_analytics(
    db: AsyncSession, http_request: Request
) -> Tenant | None:
    from app.core.tenant_resolver import resolve_tenant_or_none

    x_tenant_id = http_request.headers.get("X-Tenant-Id")
    tenant = await resolve_tenant_or_none(db=db, x_tenant_id=x_tenant_id)

    # Preserve legacy behavior: log only for invalid UUID format.
    if x_tenant_id and tenant is None:
        try:
            UUID(x_tenant_id)
        except ValueError:
            logger.warning(
                "Invalid X-Tenant-Id format; skip p3_records sync",
                x_tenant_id=x_tenant_id,
            )

    return tenant


async def _upsert_p3_record_for_analytics(
    db: AsyncSession,
    tenant: Tenant,
    lot_no_raw: str,
    production_date,
    first_row: dict,
    all_rows: list[dict],
):
    try:
        lot_no_norm = normalize_lot_no(lot_no_raw)
    except NormalizationError:
        lot_no_norm = 0

    prod_date = production_date
    if prod_date is None:
        from datetime import date as _date

        prod_date = _date.today()
    production_date_yyyymmdd = (
        prod_date.year * 10000 + prod_date.month * 100 + prod_date.day
    )

    machine_no = _pick_first_non_empty(
        first_row, ["Machine NO", "Machine No", "Machine", "machine_no", "machine"]
    )
    mold_no = _pick_first_non_empty(
        first_row, ["Mold NO", "Mold No", "Mold", "mold_no", "mold"]
    )
    machine_no_str = str(machine_no).strip() if machine_no is not None else "UNKNOWN"
    mold_no_str = str(mold_no).strip() if mold_no is not None else "UNKNOWN"

    lot_part = _extract_production_lot(first_row) or 0
    product_id = f"{production_date_yyyymmdd}-{machine_no_str}-{mold_no_str}-{lot_part}"

    specification = _pick_first_non_empty(
        first_row, ["Specification", "specification", "規格", "Spec"]
    )
    bottom_tape = _pick_first_non_empty(
        first_row,
        [
            "Bottom Tape",
            "bottom tape",
            "Bottom Tape LOT",
            "BottomTape",
            "bottom_tape",
            "下膠編號",
            "下膠",
        ],
    )

    extras_rows = _build_p3_extras_rows(all_rows)
    new_extras = {
        "machine_no": machine_no_str,
        "mold_no": mold_no_str,
        "specification": str(specification).strip()
        if specification is not None
        else None,
        "bottom_tape": str(bottom_tape).strip() if bottom_tape is not None else None,
        "rows": extras_rows,
    }

    existing_stmt = select(P3Record).where(
        P3Record.tenant_id == tenant.id,
        P3Record.lot_no_norm == lot_no_norm,
        P3Record.production_date_yyyymmdd == production_date_yyyymmdd,
        P3Record.machine_no == machine_no_str,
        P3Record.mold_no == mold_no_str,
    )
    existing_result = await db.execute(existing_stmt)
    p3_record = existing_result.scalar_one_or_none()

    if not p3_record:
        p3_record = P3Record(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            lot_no_raw=str(lot_no_raw).strip(),
            lot_no_norm=lot_no_norm,
            schema_version_id=None,
            production_date_yyyymmdd=production_date_yyyymmdd,
            machine_no=machine_no_str,
            mold_no=mold_no_str,
            product_id=product_id,
            extras=new_extras,
        )
        db.add(p3_record)
    else:
        p3_record.lot_no_raw = str(lot_no_raw).strip()
        p3_record.product_id = product_id
        p3_record.extras = {**(p3_record.extras or {}), **new_extras}

    # Keep p3_records <-> p3_items_v2 consistent for v2 query / traceability.
    # Legacy import writes into records/p3_items, then we sync normalized tables for analytics.
    await db.execute(delete(P3ItemV2).where(P3ItemV2.p3_record_id == p3_record.id))
    await db.flush()

    for row_no, row in enumerate(all_rows, start=1):
        if not isinstance(row, dict):
            continue

        item_production_lot = _extract_production_lot(row)

        item_source_winder_raw = _pick_first_non_empty(
            row,
            [
                "source_winder",
                "Source Winder",
                "Source winder",
                "source winder",
                "Winder number",
                "winder number",
                "Winder",
                "winder",
                "收卷機",
                "收卷機編號",
                "捲收機號碼",
            ],
        )
        try:
            item_source_winder = (
                int(float(item_source_winder_raw))
                if item_source_winder_raw is not None
                else None
            )
        except (ValueError, TypeError):
            item_source_winder = None

        item_specification = _pick_first_non_empty(
            row, ["Specification", "specification", "規格", "Spec"]
        )
        item_bottom_tape = _pick_first_non_empty(
            row,
            [
                "Bottom Tape",
                "bottom tape",
                "Bottom Tape LOT",
                "BottomTape",
                "bottom_tape",
                "下膠編號",
                "下膠",
            ],
        )

        item_machine_no = _pick_first_non_empty(
            row, ["Machine NO", "Machine No", "Machine", "machine_no", "machine"]
        )
        item_mold_no = _pick_first_non_empty(
            row, ["Mold NO", "Mold No", "Mold", "mold_no", "mold"]
        )
        item_product_id_s = _compose_p3_product_id(
            prod_date,
            item_machine_no or machine_no_str,
            item_mold_no or mold_no_str,
            item_production_lot,
        )

        db.add(
            P3ItemV2(
                id=uuid.uuid4(),
                p3_record_id=p3_record.id,
                tenant_id=tenant.id,
                row_no=row_no,
                product_id=item_product_id_s,
                lot_no=str(lot_no_raw).strip(),
                production_date=prod_date,
                machine_no=machine_no_str,
                mold_no=mold_no_str,
                production_lot=item_production_lot,
                source_winder=item_source_winder,
                specification=str(item_specification).strip()
                if item_specification is not None
                else None,
                bottom_tape_lot=str(item_bottom_tape).strip()
                if item_bottom_tape is not None
                else None,
                row_data=row,
            )
        )


@router.post(
    "/import",
    response_model=ImportResponse,
    summary="匯入驗證通過的資料",
    description="""
    將指定上傳工作中驗證通過的有效資料匯入到系統中。
    
    ## 功能說明
    
    - 檢查指定的上傳工作是否存在且已完成驗證
    - 重新讀取原始檔案並驗證資料
    - 將所有有效的資料行匯入到 records 表
    - 更新工作狀態為 IMPORTED
    - 回傳匯入統計資訊
    
    ## 前置條件
    
    - 上傳工作必須存在
    - 工作狀態必須為 VALIDATED（已驗證）
    - 不可重複匯入同一工作
    
    ## 匯入過程
    
    1. 驗證工作狀態
    2. 重新解析並驗證檔案內容
    3. 批次匯入所有有效資料行
    4. 更新工作狀態
    5. 回傳統計結果
    
    ## 使用範例
    
    ```bash
    # 匯入指定工作的有效資料
    curl -X POST "http://localhost:8000/api/import" \\
         -H "Content-Type: application/json" \\
         -d '{"process_id": "550e8400-e29b-41d4-a716-446655440000"}'
    ```
    """,
    responses={
        200: {"description": "資料匯入成功", "model": ImportResponse},
        404: {
            "description": "找不到指定的上傳工作",
            "model": ImportErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "找不到指定的上傳工作",
                        "process_id": "550e8400-e29b-41d4-a716-446655440000",
                        "error_code": "JOB_NOT_FOUND",
                    }
                }
            },
        },
        400: {
            "description": "工作狀態不允許匯入",
            "model": ImportErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "not_validated": {
                            "summary": "工作尚未驗證",
                            "value": {
                                "detail": "工作尚未完成驗證，無法匯入資料",
                                "process_id": "550e8400-e29b-41d4-a716-446655440000",
                                "error_code": "JOB_NOT_READY",
                            },
                        },
                        "already_imported": {
                            "summary": "工作已經匯入",
                            "value": {
                                "detail": "資料已經匯入，不可重複操作",
                                "process_id": "550e8400-e29b-41d4-a716-446655440000",
                                "error_code": "JOB_ALREADY_IMPORTED",
                            },
                        },
                    }
                }
            },
        },
    },
    tags=["資料匯入"],
)
async def import_data(
    request: ImportRequest, http_request: Request, db: AsyncSession = Depends(get_db)
) -> ImportResponse:
    """
    匯入驗證通過的資料

    Args:
        request: 匯入請求，包含 process_id
        db: 資料庫會話

    Returns:
        ImportResponse: 匯入結果統計

    Raises:
        HTTPException: 當工作不存在、狀態不正確或其他錯誤時拋出
    """

    start_time = time.time()

    if get_settings().multi_tenant_enabled:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "detail": "Legacy import endpoint is disabled in multi-tenant mode.",
                "hint": "Use v2 import pipeline: POST /api/v2/import/jobs then POST /api/v2/import/jobs/{id}/commit.",
                "error_code": "LEGACY_IMPORT_DISABLED",
            },
        )

    logger.info("開始資料匯入", process_id=str(request.process_id))

    # 1. 查詢上傳工作
    stmt = select(UploadJob).where(UploadJob.process_id == request.process_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        logger.error("匯入失敗：找不到上傳工作", process_id=str(request.process_id))
        raise HTTPException(
            status_code=404,
            detail={
                "detail": "找不到指定的上傳工作",
                "process_id": str(request.process_id),
                "error_code": "JOB_NOT_FOUND",
            },
        )

    # 2. 檢查工作狀態
    if job.status == JobStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "工作尚未完成驗證，無法匯入資料",
                "process_id": str(request.process_id),
                "error_code": "JOB_NOT_READY",
            },
        )

    if job.status == JobStatus.IMPORTED:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "資料已經匯入，不可重複操作",
                "process_id": str(request.process_id),
                "error_code": "JOB_ALREADY_IMPORTED",
            },
        )

    try:
        # 3. 重新讀取並處理檔案內容
        logger.info("開始處理檔案內容以進行匯入", process_id=str(request.process_id))

        # 重要：我們需要從上傳工作中重新讀取原始檔案內容
        # 在這個版本中，我們先實作基於檔案名稱的重讀邏輯

        import io
        from datetime import date

        import pandas as pd

        from app.models.record import DataType

        # 檢查是否有儲存的檔案內容
        if not job.file_content:
            raise HTTPException(
                status_code=400,
                detail={
                    "detail": "找不到上傳檔案內容，無法進行匯入",
                    "process_id": str(request.process_id),
                    "error_code": "FILE_CONTENT_MISSING",
                },
            )

        logger.info(
            "開始讀取並解析檔案內容",
            process_id=str(request.process_id),
            filename=job.filename,
            file_size=len(job.file_content),
        )

        # 使用 pandas 讀取 CSV 檔案內容
        try:
            # 讀取檔案內容
            df = pd.read_csv(
                io.BytesIO(job.file_content),
                encoding="utf-8-sig",  # 處理 BOM
            )

            # 排除整行空白/全空白字元的列（常見於尾端填充）
            df = df.replace(r"^\s*$", pd.NA, regex=True)
            df = df.dropna(how="all")

            if df.empty:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "detail": "檔案內容為空，無法匯入",
                        "process_id": str(request.process_id),
                        "error_code": "EMPTY_FILE",
                    },
                )

            logger.info(
                "成功讀取CSV檔案",
                process_id=str(request.process_id),
                rows=len(df),
                columns=list(df.columns),
            )

        except Exception as e:
            logger.error(
                "讀取檔案內容失敗", process_id=str(request.process_id), error=str(e)
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "detail": f"無法讀取檔案內容：{str(e)}",
                    "process_id": str(request.process_id),
                    "error_code": "FILE_READ_ERROR",
                },
            )

        # 從檔案名稱確定資料類型
        filename = job.filename
        filename_lower = filename.lower()

        if filename_lower.startswith("p1_"):
            data_type = DataType.P1
        elif filename_lower.startswith("p2_"):
            data_type = DataType.P2
        elif filename_lower.startswith("p3_"):
            data_type = DataType.P3
        else:
            data_type = DataType.P1  # 預設為P1

        # 4. 解析批號
        lot_no = None

        if data_type in [DataType.P1, DataType.P2]:
            # P1/P2 檔案：從檔案名稱提取 lot_no
            parts = filename.replace(".csv", "").replace(".xlsx", "").split("_")
            if len(parts) >= 3:
                lot_no = f"{parts[1]}_{parts[2]}"
        elif data_type == DataType.P3:
            # P3 檔案：支援新舊兩種格式
            # 1. 新格式：從 "lot no" 欄位提取（優先）
            # 2. 舊格式：從 "P3_No." 欄位提取

            if "lot no" in df.columns and not df["lot no"].empty:
                # 新格式：直接從 "lot no" 欄位讀取
                first_lot_no = str(df["lot no"].iloc[0]).strip()

                # 正規化批號（支援 7+2+2 或更多段格式，自動截取前 9 碼）
                import re

                flexible_pattern = re.compile(r"^(\d{7}_\d{2})(?:_.+)?$")
                match = flexible_pattern.match(first_lot_no)
                if match:
                    lot_no = match.group(1)  # 提取前 9 碼
                else:
                    lot_no = first_lot_no  # 如果不符合格式，保留原值讓驗證處理

            elif "P3_No." in df.columns and not df["P3_No."].empty:
                # 舊格式：從 P3_No. 欄位提取前 9 碼
                first_p3_no = str(df["P3_No."].iloc[0])
                if len(first_p3_no) >= 10:
                    lot_no = first_p3_no[:10]  # 提取前10碼 (7數字_2數字)

            if not lot_no:
                logger.warning(
                    "無法從P3檔案提取lot_no",
                    process_id=str(request.process_id),
                    filename=filename,
                )

        # 如果無法提取批號，使用預設值或報錯
        if not lot_no:
            logger.warning(
                "無法提取有效的批號",
                process_id=str(request.process_id),
                filename=filename,
                data_type=data_type.value,
            )
            # 使用檔案名稱的一部分作為預設批號
            lot_no = "0000000_00"

        # 5. 批量匯入資料
        imported_rows = 0
        skipped_rows = 0

        logger.info(
            "開始處理CSV資料行",
            process_id=str(request.process_id),
            total_rows=len(df),
            lot_no=lot_no,
            data_type=data_type.value,
        )

        # P2 特殊處理：父子表結構（Record + P2Items）
        if data_type == DataType.P2:
            try:
                from app.models.p2_item import P2Item

                # 1. 準備資料
                all_rows = []
                for index, row in df.iterrows():
                    row_dict = row.to_dict()
                    cleaned_row = {
                        k: (v if pd.notna(v) else None) for k, v in row_dict.items()
                    }
                    all_rows.append(cleaned_row)

                # 2. 檢查或創建父記錄
                existing_stmt = (
                    select(Record)
                    .where(Record.lot_no == lot_no, Record.data_type == data_type)
                    .options(selectinload(Record.p2_items))
                )
                existing_result = await db.execute(existing_stmt)
                existing_record = existing_result.scalar_one_or_none()

                # 提取生產日期
                production_date = (
                    production_date_extractor.extract_production_date(
                        row_data={"additional_data": all_rows[0] if all_rows else {}},
                        data_type=data_type.value,
                    )
                    or date.today()
                )

                if existing_record:
                    # 更新現有記錄 - 採用嚴格的去重模式
                    # 1. 處理 P2Items (嚴格去重)
                    # 獲取現有的 P2Items，建立 winder_number -> item 的映射
                    existing_items_map = {}
                    if existing_record.p2_items:
                        for item in existing_record.p2_items:
                            existing_items_map[item.winder_number] = item

                    # 定義 helper functions
                    def get_float(row_d, key):
                        val = row_d.get(key)
                        try:
                            return float(val) if val is not None else None
                        except (ValueError, TypeError):
                            return None

                    def get_int_or_status(row_d, key):
                        val = row_d.get(key)
                        if val == "OK":
                            return 1
                        if val == "NG":
                            return 0
                        try:
                            return int(float(val)) if val is not None else None
                        except (ValueError, TypeError):
                            return None

                    # 處理每一行資料
                    processed_winders = set()

                    for index, row_data in enumerate(all_rows):
                        # 嘗試從資料中獲取 winder_number
                        winder_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row_data and row_data[key] is not None:
                                try:
                                    winder_val = int(float(row_data[key]))
                                    break
                                except (ValueError, TypeError):
                                    pass

                        # 如果資料中沒有 winder_number，則使用 (index + 1)
                        # 注意：這裡假設如果檔案中沒有 winder 欄位，則檔案是完整的且從 1 開始
                        # 如果是追加模式且沒有 winder 欄位，這可能會導致問題，但在嚴格模式下，我們優先信任檔案內容
                        target_winder = (
                            winder_val if winder_val is not None else (index + 1)
                        )

                        processed_winders.add(target_winder)

                        if target_winder in existing_items_map:
                            # 更新現有 item
                            item = existing_items_map[target_winder]
                            item.sheet_width = get_float(row_data, "Sheet Width(mm)")
                            item.thickness1 = get_float(row_data, "Thicknessss1(μm)")
                            item.thickness2 = get_float(row_data, "Thicknessss2(μm)")
                            item.thickness3 = get_float(row_data, "Thicknessss3(μm)")
                            item.thickness4 = get_float(row_data, "Thicknessss4(μm)")
                            item.thickness5 = get_float(row_data, "Thicknessss5(μm)")
                            item.thickness6 = get_float(row_data, "Thicknessss6(μm)")
                            item.thickness7 = get_float(row_data, "Thicknessss7(μm)")
                            item.appearance = get_int_or_status(row_data, "Appearance")
                            item.rough_edge = get_int_or_status(row_data, "rough edge")
                            item.slitting_result = get_int_or_status(
                                row_data, "Slitting Result"
                            )
                            item.row_data = row_data
                        else:
                            # 新增 item
                            p2_item = P2Item(
                                record_id=existing_record.id,
                                winder_number=target_winder,
                                sheet_width=get_float(row_data, "Sheet Width(mm)"),
                                thickness1=get_float(row_data, "Thicknessss1(μm)"),
                                thickness2=get_float(row_data, "Thicknessss2(μm)"),
                                thickness3=get_float(row_data, "Thicknessss3(μm)"),
                                thickness4=get_float(row_data, "Thicknessss4(μm)"),
                                thickness5=get_float(row_data, "Thicknessss5(μm)"),
                                thickness6=get_float(row_data, "Thicknessss6(μm)"),
                                thickness7=get_float(row_data, "Thicknessss7(μm)"),
                                appearance=get_int_or_status(row_data, "Appearance"),
                                rough_edge=get_int_or_status(row_data, "rough edge"),
                                slitting_result=get_int_or_status(
                                    row_data, "Slitting Result"
                                ),
                                row_data=row_data,
                            )
                            db.add(p2_item)

                    # 2. 更新 additional_data['rows']
                    # 我們需要確保 additional_data['rows'] 與 p2_items 保持一致
                    # 策略：讀取所有最新的 p2_items (包含剛更新/新增的)，重新構建 rows
                    # 由於 db.add() 尚未 commit，我們手動維護一個 rows 列表

                    # 獲取舊的 rows (轉為 dict 以便更新)
                    current_data = existing_record.additional_data or {}
                    current_rows = current_data.get("rows", [])

                    # 建立 winder -> row 的映射
                    rows_map = {}

                    # 先載入舊資料
                    for row in current_rows:
                        w_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row:
                                try:
                                    w_val = int(float(row[key]))
                                    break
                                except:
                                    pass

                        # 如果舊資料沒有 winder 欄位，這會很難對應。
                        # 暫時假設舊資料也有 winder 欄位，或者我們依賴 p2_items 的更新
                        if w_val is not None:
                            rows_map[w_val] = row

                    # 使用新資料更新/新增
                    for row in all_rows:
                        w_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row:
                                try:
                                    w_val = int(float(row[key]))
                                    break
                                except:
                                    pass

                        # 如果新資料沒有 winder 欄位，嘗試使用 index+1 (與上面邏輯一致)
                        if w_val is None:
                            # 這裡比較麻煩，因為我們在迴圈中無法輕易得知 index
                            # 但我們可以假設 all_rows 的順序就是 1, 2, 3...
                            # 為了簡化，我們直接使用上面處理 p2_items 時的邏輯：
                            # 如果檔案中沒有 winder，我們就覆蓋整個 rows 列表，或者追加
                            pass

                    # 簡化策略：直接將 additional_data['rows'] 更新為 "舊資料(未被更新的) + 新資料"
                    # 但為了避免複雜的合併邏輯導致錯誤，且考慮到 P2 通常是整批匯入
                    # 我們採取：如果新資料包含 winder 資訊，則精確更新；否則追加

                    # 實作：
                    # 1. 建立一個以 winder 為 key 的 map，包含所有舊資料
                    # 2. 遍歷新資料，更新 map
                    # 3. 將 map 轉回 list

                    # 注意：如果舊資料沒有 winder 欄位，可能會被遺失或重複。
                    # 但在嚴格模式下，我們假設資料完整性較高。

                    # 重新構建 rows_map (包含舊資料)
                    # 為了安全，如果舊資料沒有 winder，我們保留它
                    final_rows = []
                    rows_map_by_winder = {}
                    rows_without_winder = []

                    for row in current_rows:
                        w_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row:
                                try:
                                    w_val = int(float(row[key]))
                                    break
                                except:
                                    pass

                        if w_val is not None:
                            rows_map_by_winder[w_val] = row
                        else:
                            rows_without_winder.append(row)

                    # 更新 map
                    for index, row in enumerate(all_rows):
                        w_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row:
                                try:
                                    w_val = int(float(row[key]))
                                    break
                                except:
                                    pass

                        if w_val is not None:
                            rows_map_by_winder[w_val] = row
                        else:
                            # 如果新資料沒有 winder，且我們在嚴格模式
                            # 我們假設它是 winder = index + 1
                            target_winder = index + 1
                            rows_map_by_winder[target_winder] = row
                            # 同時，我們應該移除 rows_without_winder 中可能對應的舊資料嗎？
                            # 這很難判斷。為了安全，我們只更新有明確 winder 的。
                            # 但如果依賴 index，則會覆蓋 map 中的 entry

                    # 重組 final_rows
                    # 先放入沒有 winder 的舊資料 (雖然這在 P2 中很少見)
                    final_rows.extend(rows_without_winder)

                    # 再放入 map 中的資料 (按 winder 排序)
                    for winder in sorted(rows_map_by_winder.keys()):
                        final_rows.append(rows_map_by_winder[winder])

                    existing_record.additional_data = {
                        **current_data,
                        "rows": final_rows,
                    }

                    # 更新生產日期（如果新的有效）
                    new_production_date = (
                        production_date_extractor.extract_production_date(
                            row_data={
                                "additional_data": all_rows[0] if all_rows else {}
                            },
                            data_type=data_type.value,
                        )
                    )
                    if new_production_date:
                        existing_record.production_date = new_production_date

                else:
                    # 創建新記錄
                    existing_record = Record(
                        lot_no=lot_no,
                        data_type=data_type,
                        production_date=production_date,
                        additional_data={"rows": all_rows},
                    )
                    db.add(existing_record)
                    await db.flush()  # 獲取 ID

                    # 3. 創建 P2Items (新記錄)
                    for index, row_data in enumerate(all_rows):
                        # 嘗試從資料中獲取 winder_number
                        winder_val = None
                        for key in [
                            "Winder number",
                            "winder number",
                            "Winder",
                            "winder",
                            "收卷機",
                            "收卷機編號",
                            "捲收機號碼",
                        ]:
                            if key in row_data and row_data[key] is not None:
                                try:
                                    winder_val = int(float(row_data[key]))
                                    break
                                except (ValueError, TypeError):
                                    pass

                        # 如果資料中沒有 winder_number，則使用 (index + 1)
                        target_winder = (
                            winder_val if winder_val is not None else (index + 1)
                        )

                        # 定義 helper functions (複製自上面)
                        def get_float(key):
                            val = row_data.get(key)
                            try:
                                return float(val) if val is not None else None
                            except (ValueError, TypeError):
                                return None

                        def get_int_or_status(key):
                            val = row_data.get(key)
                            if val == "OK":
                                return 1
                            if val == "NG":
                                return 0
                            try:
                                return int(float(val)) if val is not None else None
                            except (ValueError, TypeError):
                                return None

                        p2_item = P2Item(
                            record_id=existing_record.id,
                            winder_number=target_winder,
                            sheet_width=get_float("Sheet Width(mm)"),
                            thickness1=get_float("Thicknessss1(μm)"),
                            thickness2=get_float("Thicknessss2(μm)"),
                            thickness3=get_float("Thicknessss3(μm)"),
                            thickness4=get_float("Thicknessss4(μm)"),
                            thickness5=get_float("Thicknessss5(μm)"),
                            thickness6=get_float("Thicknessss6(μm)"),
                            thickness7=get_float("Thicknessss7(μm)"),
                            appearance=get_int_or_status("Appearance"),
                            rough_edge=get_int_or_status("rough edge"),
                            slitting_result=get_int_or_status("Slitting Result"),
                            row_data=row_data,
                        )
                        db.add(p2_item)

                imported_rows = len(all_rows)
                logger.info(
                    "P2資料匯入完成",
                    lot_no=lot_no,
                    total_winders=imported_rows,
                    record_id=str(existing_record.id),
                )

            except Exception as e:
                logger.error(
                    "處理P2資料失敗",
                    error=str(e),
                    lot_no=lot_no,
                    process_id=str(request.process_id),
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "detail": f"處理P2資料失敗：{str(e)}",
                        "process_id": str(request.process_id),
                        "error_code": "IMPORT_ERROR",
                    },
                )

        # P3 特殊處理：將多行資料合併為單一記錄
        elif data_type == DataType.P3:
            try:
                # 將所有行轉換為列表存入 additional_data
                all_rows = []
                for index, row in df.iterrows():
                    row_dict = row.to_dict()
                    # 清理 NaN 值
                    cleaned_row = {
                        k: (v if pd.notna(v) else None) for k, v in row_dict.items()
                    }
                    all_rows.append(cleaned_row)

                # 取第一列作為代表（P2/P3 合併為單一記錄時，用於填充可檢索欄位）
                first_row = all_rows[0] if all_rows else {}

                # 檢查是否已存在相同的 lot_no + data_type 記錄
                existing_stmt = (
                    select(Record)
                    .where(Record.lot_no == lot_no, Record.data_type == data_type)
                    .options(selectinload(Record.p3_items))
                )
                existing_result = await db.execute(existing_stmt)
                existing_record = existing_result.scalar_one_or_none()

                if existing_record:
                    # 更新現有記錄 - 採用嚴格的去重模式
                    # 1. 合併 additional_data['rows']
                    current_data = existing_record.additional_data or {}
                    current_rows = current_data.get("rows", [])

                    # 建立 product_id -> row 的映射 (如果可能)
                    # 或者使用 row_data 的內容雜湊來去重
                    import hashlib
                    import json

                    def get_row_hash(r):
                        # 移除可能變動的欄位或不重要的欄位
                        # 這裡簡單地將整個 dict 轉為 json string 並 hash
                        # 注意：key 的順序可能會影響，所以要 sort_keys=True
                        return hashlib.md5(
                            json.dumps(r, sort_keys=True, default=str).encode()
                        ).hexdigest()

                    existing_hashes = set()
                    for r in current_rows:
                        existing_hashes.add(get_row_hash(r))

                    # 過濾掉已存在的 rows
                    new_unique_rows = []
                    for r in all_rows:
                        h = get_row_hash(r)
                        if h not in existing_hashes:
                            new_unique_rows.append(r)
                            existing_hashes.add(h)  # 防止本次匯入內部的重複

                    # 合併
                    merged_rows = current_rows + new_unique_rows
                    existing_record.additional_data = {
                        **current_data,
                        "rows": merged_rows,
                    }

                    # 更新生產日期（如果新的有效）
                    new_production_date = (
                        production_date_extractor.extract_production_date(
                            row_data={
                                "additional_data": all_rows[0] if all_rows else {}
                            },
                            data_type=data_type.value,
                        )
                    )
                    if new_production_date:
                        existing_record.production_date = new_production_date

                    # P3：同步填充可檢索欄位（避免只存在 JSON 內造成欄位全為 NULL）
                    if data_type == DataType.P3 and first_row:
                        # ... (保留原有邏輯)
                        machine_no_val = (
                            first_row.get("Machine NO")
                            or first_row.get("Machine No")
                            or first_row.get("Machine")
                            or first_row.get("machine_no")
                            or first_row.get("machine")
                        )
                        mold_no_val = (
                            first_row.get("Mold NO")
                            or first_row.get("Mold No")
                            or first_row.get("Mold")
                            or first_row.get("mold_no")
                            or first_row.get("mold")
                        )

                        production_lot_val = _extract_production_lot(first_row)

                        existing_record.machine_no = machine_no_val
                        existing_record.mold_no = mold_no_val
                        existing_record.production_lot = production_lot_val

                        # 寫入 P3 明細項目子表 - 採用嚴格去重模式
                        # 獲取現有的 P3Items，建立 product_id -> item 的映射 (如果 product_id 存在)
                        existing_items_map = {}
                        if existing_record.p3_items:
                            for item in existing_record.p3_items:
                                if item.product_id:
                                    existing_items_map[item.product_id] = item

                        # 避免 product_id 重複造成 UNIQUE constraint 失敗
                        reserved_product_ids = set(existing_items_map.keys())

                        # 計算目前的 row_no 起始點 (如果是追加)
                        current_max_row = 0
                        if existing_record.p3_items:
                            current_max_row = max(
                                [item.row_no for item in existing_record.p3_items],
                                default=0,
                            )

                        # 為每一行創建或更新 P3Item
                        for row_no, row_data in enumerate(all_rows, start=1):
                            # 提取欄位
                            # row_data['lot'] 是生產序號 (production_lot)，批號應使用父表 lot_no
                            item_lot_no = lot_no
                            item_production_lot = _extract_production_lot(row_data)
                            item_machine_no = (
                                row_data.get("Machine NO")
                                or row_data.get("Machine No")
                                or row_data.get("Machine")
                                or row_data.get("machine_no")
                                or row_data.get("machine")
                            )

                            # 如果無法從內容提取機台編號，嘗試從檔案名稱提取
                            if not item_machine_no:
                                parts = (
                                    filename.replace(".csv", "")
                                    .replace(".xlsx", "")
                                    .split("_")
                                )
                                if len(parts) >= 3:
                                    # 假設格式為 P3_Date_Machine... (例如 P3_0902_P24)
                                    item_machine_no = (
                                        parts[2].replace(" copy", "").strip()
                                    )

                            item_mold_no = (
                                row_data.get("Mold NO")
                                or row_data.get("Mold No")
                                or row_data.get("Mold")
                                or row_data.get("mold_no")
                                or row_data.get("mold")
                            )
                            item_specification = (
                                row_data.get("Specification")
                                or row_data.get("specification")
                                or row_data.get("規格")
                                or row_data.get("Spec")
                            )
                            item_bottom_tape = (
                                row_data.get("Bottom Tape")
                                or row_data.get("bottom tape")
                                or row_data.get("Bottom Tape LOT")
                                or row_data.get("下膠編號")
                                or row_data.get("下膠")
                            )

                            # 以 row_data 為優先推導此 item 的生產日期；若無法推導則 fallback 到 record.production_date
                            item_date = None
                            if not item_date:
                                try:
                                    item_date = production_date_extractor.extract_production_date(
                                        {"additional_data": row_data}, DataType.P3.value
                                    )
                                except Exception:
                                    item_date = None
                            if not item_date:
                                item_date = existing_record.production_date

                            item_product_id = _compose_p3_product_id(
                                item_date,
                                item_machine_no,
                                item_mold_no,
                                item_production_lot,
                            )

                            # 檢查是否已存在 (透過 product_id)
                            if (
                                item_product_id
                                and item_product_id in existing_items_map
                            ):
                                # 更新現有 item
                                item = existing_items_map[item_product_id]
                                item.lot_no = (
                                    str(item_lot_no).strip() if item_lot_no else None
                                )
                                item.production_lot = item_production_lot
                                item.production_date = item_date
                                item.machine_no = (
                                    str(item_machine_no).strip()
                                    if item_machine_no
                                    else None
                                )
                                item.mold_no = (
                                    str(item_mold_no).strip() if item_mold_no else None
                                )
                                item.specification = (
                                    str(item_specification).strip()
                                    if item_specification
                                    else None
                                )
                                item.bottom_tape_lot = (
                                    str(item_bottom_tape).strip()
                                    if item_bottom_tape
                                    else None
                                )
                                item.row_data = row_data
                                # row_no 不更新，保持原樣
                            else:
                                # 新增 item
                                # row_no 接續在現有最大值之後
                                new_row_no = current_max_row + row_no

                                if item_product_id:
                                    candidate = item_product_id
                                    if candidate in reserved_product_ids:
                                        candidate = f"{candidate}_dup{new_row_no}"
                                    item_product_id = candidate
                                    reserved_product_ids.add(item_product_id)

                                p3_item = P3Item(
                                    record_id=existing_record.id,
                                    product_id=item_product_id,
                                    lot_no=str(item_lot_no).strip()
                                    if item_lot_no
                                    else None,
                                    production_lot=item_production_lot,
                                    production_date=item_date,
                                    machine_no=str(item_machine_no).strip()
                                    if item_machine_no
                                    else None,
                                    mold_no=str(item_mold_no).strip()
                                    if item_mold_no
                                    else None,
                                    specification=str(item_specification).strip()
                                    if item_specification
                                    else None,
                                    bottom_tape_lot=str(item_bottom_tape).strip()
                                    if item_bottom_tape
                                    else None,
                                    row_no=new_row_no,
                                    row_data=row_data,
                                )
                                db.add(p3_item)

                    # 同步寫入新表：p3_records（供追溯/analytics 使用）
                    tenant = await _resolve_tenant_for_analytics(db, http_request)
                    if tenant:
                        await _upsert_p3_record_for_analytics(
                            db=db,
                            tenant=tenant,
                            lot_no_raw=lot_no,
                            production_date=existing_record.production_date,
                            first_row=first_row,
                            all_rows=all_rows,
                        )
                    else:
                        logger.warning(
                            "Skip p3_records sync: cannot resolve tenant (set X-Tenant-Id or ensure single/default tenant)",
                            process_id=str(request.process_id),
                            lot_no=lot_no,
                        )

                    logger.info(
                        "更新現有P2/P3記錄",
                        lot_no=lot_no,
                        data_type=data_type.value,
                        rows_count=len(all_rows),
                        record_id=str(existing_record.id),
                        process_id=str(request.process_id),
                    )
                else:
                    # 創建新記錄
                    # 提取生產日期
                    production_date = (
                        production_date_extractor.extract_production_date(
                            row_data={
                                "additional_data": all_rows[0] if all_rows else {}
                            },
                            data_type=data_type.value,
                        )
                        or date.today()
                    )  # 如果提取失敗，fallback 到當前日期

                    record_kwargs = {
                        "lot_no": lot_no,
                        "data_type": data_type,
                        "production_date": production_date,
                        "additional_data": {"rows": all_rows},
                    }

                    # P3：同步填充可檢索欄位
                    if data_type == DataType.P3 and first_row:
                        machine_no_val = (
                            first_row.get("Machine NO")
                            or first_row.get("Machine No")
                            or first_row.get("Machine")
                            or first_row.get("machine_no")
                            or first_row.get("machine")
                        )
                        mold_no_val = (
                            first_row.get("Mold NO")
                            or first_row.get("Mold No")
                            or first_row.get("Mold")
                            or first_row.get("mold_no")
                            or first_row.get("mold")
                        )

                        production_lot_val = _extract_production_lot(first_row)

                        record_kwargs.update(
                            {
                                "machine_no": machine_no_val,
                                "mold_no": mold_no_val,
                                "production_lot": production_lot_val,
                            }
                        )

                    record = Record(**record_kwargs)
                    db.add(record)
                    await db.flush()  # 確保 record.id 可用

                    # 同步寫入新表：p3_records（供追溯/analytics 使用）
                    tenant = await _resolve_tenant_for_analytics(db, http_request)
                    if tenant:
                        await _upsert_p3_record_for_analytics(
                            db=db,
                            tenant=tenant,
                            lot_no_raw=lot_no,
                            production_date=production_date,
                            first_row=first_row,
                            all_rows=all_rows,
                        )
                    else:
                        logger.warning(
                            "Skip p3_records sync: cannot resolve tenant (set X-Tenant-Id or ensure single/default tenant)",
                            process_id=str(request.process_id),
                            lot_no=lot_no,
                        )

                    # P3：寫入明細項目子表
                    if data_type == DataType.P3:
                        reserved_product_ids = set()
                        for row_no, row_data in enumerate(all_rows, start=1):
                            # 提取其他欄位
                            # row_data['lot'] 是生產序號 (production_lot)，批號應使用父表 lot_no
                            item_lot_no = lot_no
                            item_production_lot = _extract_production_lot(row_data)
                            item_machine_no = (
                                row_data.get("Machine NO")
                                or row_data.get("Machine No")
                                or row_data.get("Machine")
                                or row_data.get("machine_no")
                                or row_data.get("machine")
                            )

                            # 如果無法從內容提取機台編號，嘗試從檔案名稱提取
                            if not item_machine_no:
                                parts = (
                                    filename.replace(".csv", "")
                                    .replace(".xlsx", "")
                                    .split("_")
                                )
                                if len(parts) >= 3:
                                    # 假設格式為 P3_Date_Machine... (例如 P3_0902_P24)
                                    item_machine_no = (
                                        parts[2].replace(" copy", "").strip()
                                    )

                            item_mold_no = (
                                row_data.get("Mold NO")
                                or row_data.get("Mold No")
                                or row_data.get("Mold")
                                or row_data.get("mold_no")
                                or row_data.get("mold")
                            )
                            item_specification = (
                                row_data.get("Specification")
                                or row_data.get("specification")
                                or row_data.get("規格")
                                or row_data.get("Spec")
                            )
                            item_bottom_tape = (
                                row_data.get("Bottom Tape")
                                or row_data.get("bottom tape")
                                or row_data.get("Bottom Tape LOT")
                                or row_data.get("下膠編號")
                                or row_data.get("下膠")
                            )

                            # 動態產生 Product ID
                            # 規則：YYYYMMDD_Machine_Mold_Lot
                            item_product_id = None

                            # 優先從 row_data 提取日期
                            item_date = None
                            try:
                                # 使用 production_date_extractor 提取日期
                                # 注意：extract_production_date 預期輸入格式為 {'additional_data': row_data}
                                item_date = (
                                    production_date_extractor.extract_production_date(
                                        {"additional_data": row_data}, DataType.P3.value
                                    )
                                )
                            except Exception:
                                pass

                            # 如果無法從 row_data 提取，則使用 Record 的日期
                            if not item_date:
                                item_date = record.production_date

                            item_product_id = _compose_p3_product_id(
                                item_date,
                                item_machine_no,
                                item_mold_no,
                                item_production_lot,
                            )

                            if item_product_id:
                                candidate = item_product_id
                                if candidate in reserved_product_ids:
                                    candidate = f"{candidate}_dup{row_no}"
                                item_product_id = candidate
                                reserved_product_ids.add(item_product_id)

                            p3_item = P3Item(
                                record_id=record.id,
                                product_id=item_product_id,
                                lot_no=str(item_lot_no).strip()
                                if item_lot_no
                                else None,
                                production_lot=item_production_lot,
                                production_date=item_date,
                                machine_no=str(item_machine_no).strip()
                                if item_machine_no
                                else None,
                                mold_no=str(item_mold_no).strip()
                                if item_mold_no
                                else None,
                                specification=str(item_specification).strip()
                                if item_specification
                                else None,
                                bottom_tape_lot=str(item_bottom_tape).strip()
                                if item_bottom_tape
                                else None,
                                row_no=row_no,
                                row_data=row_data,
                            )
                            db.add(p3_item)

                    logger.info(
                        "創建新P2/P3記錄",
                        lot_no=lot_no,
                        data_type=data_type.value,
                        rows_count=len(all_rows),
                        process_id=str(request.process_id),
                    )

                imported_rows = len(all_rows)

            except Exception as e:
                logger.error(
                    "處理P2/P3資料失敗",
                    error=str(e),
                    lot_no=lot_no,
                    data_type=data_type.value,
                    process_id=str(request.process_id),
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "detail": f"處理{data_type.value}資料失敗：{str(e)}",
                        "process_id": str(request.process_id),
                        "error_code": "IMPORT_ERROR",
                    },
                )

        # P1 處理：每一行作為獨立記錄
        elif data_type == DataType.P1:
            for index, row in df.iterrows():
                try:
                    # 轉換 pandas Series 為字典
                    row_dict = row.to_dict()

                    # 分離已知欄位和額外欄位
                    known_fields = {}
                    additional_fields = {}

                    # 設置批號（對所有類型都需要）
                    known_fields["lot_no"] = lot_no

                    # 提取已知的資料庫欄位
                    if "product_name" in row_dict and pd.notna(
                        row_dict["product_name"]
                    ):
                        known_fields["product_name"] = str(
                            row_dict["product_name"]
                        ).strip()

                    if "quantity" in row_dict and pd.notna(row_dict["quantity"]):
                        try:
                            known_fields["quantity"] = int(float(row_dict["quantity"]))
                        except (ValueError, TypeError):
                            pass

                    # 使用 production_date_extractor 提取日期
                    extracted_date = production_date_extractor.extract_production_date(
                        row_data={"additional_data": row_dict},
                        data_type=DataType.P1.value,
                    )
                    if extracted_date:
                        known_fields["production_date"] = extracted_date
                    elif "production_date" in row_dict and pd.notna(
                        row_dict["production_date"]
                    ):
                        # 保留原有的 fallback 邏輯，以防 extractor 失敗但欄位存在
                        try:
                            if isinstance(row_dict["production_date"], str):
                                known_fields["production_date"] = datetime.strptime(
                                    row_dict["production_date"], "%Y-%m-%d"
                                ).date()
                            else:
                                known_fields["production_date"] = row_dict[
                                    "production_date"
                                ]
                        except (ValueError, TypeError):
                            pass

                    if "notes" in row_dict and pd.notna(row_dict["notes"]):
                        known_fields["notes"] = str(row_dict["notes"]).strip()

                    # 將所有其他欄位存入 additional_data
                    for key, value in row_dict.items():
                        if key not in [
                            "lot_no",
                            "product_name",
                            "quantity",
                            "production_date",
                            "notes",
                        ] and pd.notna(value):
                            # 轉換 numpy 類型為 Python 原生類型
                            if pd.api.types.is_numeric_dtype(type(value)):
                                additional_fields[key] = (
                                    float(value)
                                    if isinstance(value, (int, float))
                                    else str(value)
                                )
                            else:
                                additional_fields[key] = str(value).strip()

                    # 設置預設生產日期（如果沒有提供）
                    if "production_date" not in known_fields:
                        known_fields["production_date"] = date.today()

                    # 檢查是否已存在相同的 lot_no + data_type 記錄
                    existing_stmt = select(Record).where(
                        Record.lot_no == known_fields["lot_no"],
                        Record.data_type == data_type,
                    )
                    existing_result = await db.execute(existing_stmt)
                    existing_record = existing_result.scalar_one_or_none()

                    if existing_record:
                        # 如果記錄已存在，更新它而不是創建新記錄
                        for field, value in known_fields.items():
                            if field != "lot_no":  # lot_no 不需要更新
                                setattr(existing_record, field, value)

                        existing_record.data_type = data_type
                        existing_record.additional_data = (
                            additional_fields if additional_fields else None
                        )

                        logger.info(
                            "更新現有P1記錄",
                            row_index=index,
                            lot_no=known_fields.get("lot_no"),
                            data_type=data_type.value,
                            record_id=str(existing_record.id),
                            process_id=str(request.process_id),
                        )
                    else:
                        # 創建新記錄
                        record = Record(
                            data_type=data_type,
                            additional_data=additional_fields
                            if additional_fields
                            else None,
                            **known_fields,
                        )

                        db.add(record)

                        if imported_rows <= 3:  # 只記錄前3筆的詳細資訊
                            logger.info(
                                "成功創建P1記錄",
                                row_index=index,
                                lot_no=known_fields.get("lot_no"),
                                data_type=data_type.value,
                                additional_fields_count=len(additional_fields),
                                additional_fields=list(additional_fields.keys())[:5],
                                process_id=str(request.process_id),
                            )

                    imported_rows += 1

                except Exception as e:
                    logger.error(
                        "處理P1記錄失敗",
                        error=str(e),
                        row_index=index,
                        process_id=str(request.process_id),
                    )
                    skipped_rows += 1
                    continue

        # 6. 更新工作狀態
        job.status = JobStatus.IMPORTED
        await db.commit()

        # 6. 計算耗時
        elapsed_ms = int((time.time() - start_time) * 1000)

        return ImportResponse(
            imported_rows=imported_rows,
            skipped_rows=skipped_rows,
            elapsed_ms=elapsed_ms,
            message=f"資料匯入完成：成功 {imported_rows} 筆，跳過 {skipped_rows} 筆",
            process_id=request.process_id,
        )

    except Exception as e:
        # 回滾事務
        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail={
                "detail": f"匯入過程發生錯誤：{str(e)}",
                "process_id": str(request.process_id),
                "error_code": "IMPORT_ERROR",
            },
        )
