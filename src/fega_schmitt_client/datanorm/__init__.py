"""DATANORM deliveries from FEGA & Schmitt.

For now only archiving: a delivered file (``datanorm.zip`` or one of the
extracted ``datanorm.001``/``datanorm.wrg``/``datpreis.001``) is uploaded to an
S3-compatible store. Parsing is planned, see DATANORM.md.

Needs the optional ``s3`` extra (``pip install fega-schmitt-client[s3]``).
"""

from .s3 import S3Config, default_object_key, upload_file

__all__ = ["S3Config", "default_object_key", "upload_file"]
