"""DATANORM deliveries from FEGA & Schmitt.

A delivery (``datanorm.zip`` or the extracted ``datanorm.001``/``datanorm.wrg``/
``datpreis.001``) can be loaded into SQLite with :func:`import_delivery` and
archived to an S3-compatible store with :func:`upload_file`. Field meanings
are derived from real deliveries, see DATANORM.md.

The S3 upload needs the optional ``s3`` extra (``pip install fega-schmitt-client[s3]``).
"""

from ._parser import DatanormFormatError
from .db import Changes, ImportResult, default_db_path, import_delivery
from .s3 import S3Config, default_object_key, upload_file

__all__ = [
    "Changes",
    "DatanormFormatError",
    "ImportResult",
    "S3Config",
    "default_db_path",
    "default_object_key",
    "import_delivery",
    "upload_file",
]
