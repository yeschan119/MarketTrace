"""Disclosure ingest — persist a RawDocument into the DB and object store.

Idempotent: re-ingesting the same content returns the existing Document
without creating a duplicate row (dedup via content_hash unique constraint).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from markettrace.db.models import Document
from markettrace.providers.base import RawDocument
from markettrace.storage.object_store import ObjectStore

__all__ = ["ingest_document"]


def ingest_document(
    session: Session,
    store: ObjectStore,
    raw: RawDocument,
) -> Document:
    """Persist ``raw`` and return the corresponding ``Document`` ORM object.

    If a ``Document`` with the same ``content_hash`` already exists the
    existing row is returned unchanged (idempotent / dedup).

    Parameters
    ----------
    session:
        An open SQLAlchemy ``Session``; the caller is responsible for committing.
    store:
        Object store used to persist the raw bytes.
    raw:
        The raw document fetched from a provider.
    """
    content_bytes: bytes = (
        raw.content_bytes if raw.content_bytes is not None else raw.content.encode()
    )
    content_hash = store.hash_content(content_bytes)

    existing = session.query(Document).filter_by(content_hash=content_hash).first()
    if existing is not None:
        return existing

    raw_object_key = store.put(content_bytes)

    ref = raw.ref
    doc = Document(
        source=ref.source,
        external_id=ref.external_id,
        url=ref.url,
        title=ref.title,
        raw_object_key=raw_object_key,
        content_hash=content_hash,
        market=ref.market,
        occurred_at=ref.occurred_at,
        published_at=ref.published_at,
        first_seen_at=raw.fetched_at,
    )
    session.add(doc)
    session.flush()
    return doc
