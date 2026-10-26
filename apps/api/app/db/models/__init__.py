"""ORM models. Importing this package registers every table on ``Base.metadata``
(Alembic's ``target_metadata``), so import order here matters — keep all models listed.
"""
from app.db.base import Base
from app.db.models.api_key import APIKey, KeyScope
from app.db.models.audit import AuditLog
from app.db.models.case import Case, CaseMember
from app.db.models.edge import Edge
from app.db.models.entity import Entity
from app.db.models.job import Job
from app.db.models.note import Note
from app.db.models.provenance import Provenance
from app.db.models.report import Report, ReportStatus
from app.db.models.user import User

__all__ = [
    "Base",
    "User",
    "Case",
    "CaseMember",
    "Entity",
    "Edge",
    "Provenance",
    "Job",
    "APIKey",
    "KeyScope",
    "Note",
    "AuditLog",
    "Report",
    "ReportStatus",
]
