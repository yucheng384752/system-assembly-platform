"""
驗證結果查詢 API 路由

提供查詢上傳工作驗證結果的 API 端點。
"""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.upload_error import UploadError
from app.models.upload_job import UploadJob
from app.schemas.validate import (
    ErrorItem,
    ErrorNotFoundResponse,
    ValidateResult,
)

# 建立路由器
router = APIRouter()


@router.get(
    "/validate",
    response_model=ValidateResult,
    summary="查詢驗證結果",
    description="""
    根據 process_id 查詢上傳工作的驗證結果。
    
    ## 功能說明
    
    - 查詢指定 process_id 的上傳工作資訊
    - 取得工作的統計資料（總行數、有效行數、錯誤行數）
    - 分頁顯示所有驗證錯誤項目
    - 提供完整的錯誤詳細資訊
    
    ## 回傳內容
    
    - **工作資訊**: process_id、檔案名稱、狀態、建立時間
    - **統計資料**: 總行數、有效行數、無效行數
    - **錯誤列表**: 每個錯誤的行號、欄位、錯誤程式碼和訊息
    - **分頁資訊**: 當前頁數、每頁項目數、總頁數等
    
    ## 使用範例
    
    ```bash
    # 查詢第一頁錯誤，每頁20筆
    GET /api/validate?process_id=550e8400-e29b-41d4-a716-446655440000
    
    # 查詢第二頁錯誤，每頁10筆
    GET /api/validate?process_id=550e8400-e29b-41d4-a716-446655440000&page=2&page_size=10
    ```
    """,
    responses={
        200: {"description": "成功取得驗證結果", "model": ValidateResult},
        404: {
            "description": "找不到指定的上傳工作",
            "model": ErrorNotFoundResponse,
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
        422: {
            "description": "參數驗證錯誤",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "uuid_parsing",
                                "loc": ["query", "process_id"],
                                "msg": "Input should be a valid UUID",
                                "input": "invalid-uuid",
                            }
                        ]
                    }
                }
            },
        },
    },
    tags=["驗證結果查詢"],
)
async def get_validate_result(
    process_id: UUID = Query(
        ...,
        description="處理流程識別碼",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    ),
    page: int = Query(
        default=1, description="頁碼（從1開始）", ge=1, examples=[1, 2, 3]
    ),
    page_size: int = Query(
        default=20, description="每頁項目數量", ge=1, le=100, examples=[10, 20, 50]
    ),
    db: AsyncSession = Depends(get_db),
) -> ValidateResult:
    """
    查詢驗證結果

    Args:
        process_id: 處理流程識別碼
        page: 頁碼，從1開始
        page_size: 每頁項目數量，限制1-100
        db: 資料庫會話

    Returns:
        ValidateResult: 驗證結果資料

    Raises:
        HTTPException: 當找不到指定工作時拋出 404 錯誤
    """

    # 查詢上傳工作
    stmt = select(UploadJob).where(UploadJob.process_id == process_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "detail": "找不到指定的上傳工作",
                "process_id": str(process_id),
                "error_code": "JOB_NOT_FOUND",
            },
        )

    # 查詢錯誤總數
    count_stmt = select(func.count(UploadError.id)).where(UploadError.job_id == job.id)
    count_result = await db.execute(count_stmt)
    total_errors = count_result.scalar() or 0

    # 計算分頁資訊
    total_pages = math.ceil(total_errors / page_size) if total_errors > 0 else 1
    offset = (page - 1) * page_size

    # 查詢當前頁的錯誤項目
    errors_stmt = (
        select(UploadError)
        .where(UploadError.job_id == job.id)
        .order_by(UploadError.row_index, UploadError.field)
        .offset(offset)
        .limit(page_size)
    )
    errors_result = await db.execute(errors_stmt)
    errors = errors_result.scalars().all()

    # 轉換為回應模型
    error_items = [
        ErrorItem(
            row_index=error.row_index + 1,  # 轉換為從1開始的行號（不包含標題）
            field=error.field,
            error_code=error.error_code,
            message=error.message,
        )
        for error in errors
    ]

    # 建立統計資訊
    statistics = {
        "total_rows": job.total_rows or 0,
        "valid_rows": job.valid_rows or 0,
        "invalid_rows": job.invalid_rows or 0,
    }

    # 建立分頁資訊
    pagination = {
        "page": page,
        "page_size": page_size,
        "total_errors": total_errors,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    return ValidateResult(
        job_id=job.id,
        process_id=job.process_id,
        filename=job.filename,
        status=job.status.value,
        created_at=job.created_at,
        statistics=statistics,
        errors=error_items,
        pagination=pagination,
    )
