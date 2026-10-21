"""Upload DATANORM files to an S3-compatible object store (e.g. Garage).

boto3 is imported lazily, so the rest of the package works without the
optional ``s3`` extra installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

# The bucket is meant to be shared by several suppliers' DATANORM archives;
# this client files its deliveries under its own supplier prefix.
DEFAULT_PREFIX = "fega"

_CONTENT_TYPES = {".zip": "application/zip"}


@dataclass(frozen=True)
class S3Config:
    endpoint_url: str
    bucket: str
    access_key_id: str
    secret_access_key: str = field(repr=False)
    region: str = "garage"


def default_object_key(path: Path, prefix: str = DEFAULT_PREFIX, delivery_date: date | None = None) -> str:
    """``<prefix>/<YYYY-MM-DD>/<file name>``.

    Without ``delivery_date`` the file's modification date is used: unzip keeps
    the timestamps FEGA put into the archive, so the extracted files carry the
    delivery date rather than the date they were unpacked.
    """
    if delivery_date is None:
        delivery_date = datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
    parts = [prefix.strip("/"), delivery_date.isoformat(), path.name]
    return "/".join(p for p in parts if p)


def make_client(config: S3Config) -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("Für den S3-Upload wird boto3 benötigt: pip install 'fega-schmitt-client[s3]'") from exc

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name=config.region,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=Config(
            # Garage serves buckets only path-style, not as <bucket>.<host>.
            s3={"addressing_style": "path"},
            # botocore >= 1.36 adds CRC checksums to every upload by default,
            # which not every S3-compatible store accepts.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def upload_file(path: Path, key: str, config: S3Config, client: Any = None) -> str:
    """Upload ``path`` to ``s3://<bucket>/<key>`` and return that URI.

    Large files go up as multipart uploads (boto3's transfer manager).
    ``client`` is for tests; by default one is built from ``config``.
    """
    if client is None:
        client = make_client(config)
    content_type = _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    client.upload_file(str(path), config.bucket, key, ExtraArgs={"ContentType": content_type})
    return f"s3://{config.bucket}/{key}"
