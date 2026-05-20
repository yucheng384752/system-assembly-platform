from sqlalchemy import Index, UniqueConstraint

from app.core.database import Base
from app.models.base_record import BaseRecordMixin


class P1Record(BaseRecordMixin, Base):
    __tablename__ = "p1_records"

    __table_args__ = (
        UniqueConstraint("tenant_id", "lot_no_norm", name="uq_p1_tenant_lot_norm"),
        Index("ix_p1_tenant_lot_norm", "tenant_id", "lot_no_norm"),
    )
