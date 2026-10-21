"""Tests for the DATANORM S3 upload and `fega datanorm upload`."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
from click.testing import CliRunner

from fega_schmitt_client import cli
from fega_schmitt_client.datanorm import S3Config, default_object_key, upload_file
from fega_schmitt_client.datanorm.s3 import make_client

S3_ENV = {
    "FEGA_S3_ENDPOINT_URL": "https://s3.example.test",
    "FEGA_S3_REGION": "garage",
    "FEGA_S3_BUCKET": "fega",
    "FEGA_S3_ACCESS_KEY_ID": "GKtest",
    "FEGA_S3_SECRET_ACCESS_KEY": "not-a-real-secret",
}


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str, dict]] = []

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict) -> None:
        self.uploads.append((filename, bucket, key, ExtraArgs))


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr(cli, "make_s3_client", lambda config: client)
    return client


@pytest.fixture
def delivery(tmp_path):
    path = tmp_path / "datanorm.zip"
    path.write_bytes(b"PK\x03\x04")
    # Midday UTC, so the local date is the 21st in any European time zone.
    mtime = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(path, (mtime, mtime))
    return path


def _config() -> S3Config:
    return S3Config(
        endpoint_url="https://s3.example.test",
        bucket="fega",
        access_key_id="GKtest",
        secret_access_key="not-a-real-secret",
    )


def test_default_object_key_uses_modification_date(delivery):
    assert default_object_key(delivery) == "datanorm/2026-10-21/datanorm.zip"


def test_default_object_key_with_explicit_date_and_prefix(delivery):
    assert default_object_key(delivery, "archiv/fega/", date(2026, 8, 10)) == "archiv/fega/2026-08-10/datanorm.zip"


def test_default_object_key_without_prefix(delivery):
    assert default_object_key(delivery, "") == "2026-10-21/datanorm.zip"


def test_upload_file_sets_content_type(delivery, tmp_path):
    client = FakeS3Client()
    other = tmp_path / "datpreis.001"
    other.write_bytes(b"P;")

    assert upload_file(delivery, "k/datanorm.zip", _config(), client=client) == "s3://fega/k/datanorm.zip"
    upload_file(other, "k/datpreis.001", _config(), client=client)

    assert client.uploads == [
        (str(delivery), "fega", "k/datanorm.zip", {"ContentType": "application/zip"}),
        (str(other), "fega", "k/datpreis.001", {"ContentType": "application/octet-stream"}),
    ]


def test_make_client_uses_path_style_and_endpoint():
    client = make_client(_config())

    assert client.meta.endpoint_url == "https://s3.example.test"
    assert client.meta.region_name == "garage"
    assert client.meta.config.s3["addressing_style"] == "path"


def test_secret_not_in_config_repr():
    assert "not-a-real-secret" not in repr(_config())


def test_cli_upload_from_env(fake_client, delivery):
    result = CliRunner().invoke(cli.main, ["datanorm", "upload", str(delivery)], env=S3_ENV)

    assert result.exit_code == 0, result.output
    assert fake_client.uploads[0][1:3] == ("fega", "datanorm/2026-10-21/datanorm.zip")
    assert "s3://fega/datanorm/2026-10-21/datanorm.zip" in result.output


def test_cli_upload_multiple_files_with_date(fake_client, delivery, tmp_path):
    other = tmp_path / "datanorm.wrg"
    other.write_bytes(b"S;")

    result = CliRunner().invoke(
        cli.main, ["datanorm", "upload", str(delivery), str(other), "--date", "2026-08-10"], env=S3_ENV
    )

    assert result.exit_code == 0, result.output
    assert [u[2] for u in fake_client.uploads] == [
        "datanorm/2026-08-10/datanorm.zip",
        "datanorm/2026-08-10/datanorm.wrg",
    ]


def test_cli_upload_explicit_key(fake_client, delivery):
    result = CliRunner().invoke(cli.main, ["datanorm", "upload", str(delivery), "--key", "x/y.zip"], env=S3_ENV)

    assert result.exit_code == 0, result.output
    assert fake_client.uploads[0][2] == "x/y.zip"


def test_cli_upload_key_rejects_multiple_files(fake_client, delivery):
    result = CliRunner().invoke(
        cli.main, ["datanorm", "upload", str(delivery), str(delivery), "--key", "x/y.zip"], env=S3_ENV
    )

    assert result.exit_code == 2
    assert fake_client.uploads == []


def test_cli_upload_requires_s3_settings(fake_client, delivery):
    env = {**S3_ENV, "FEGA_S3_BUCKET": "", "FEGA_S3_SECRET_ACCESS_KEY": ""}

    result = CliRunner().invoke(cli.main, ["datanorm", "upload", str(delivery)], env=env)

    assert result.exit_code == 2
    assert "--bucket" in result.output
    assert "--secret-access-key" in result.output
    assert fake_client.uploads == []


def test_cli_upload_reports_errors(monkeypatch, delivery):
    class FailingClient(FakeS3Client):
        def upload_file(self, *args, **kwargs):
            raise RuntimeError("Access Denied")

    monkeypatch.setattr(cli, "make_s3_client", lambda config: FailingClient())

    result = CliRunner().invoke(cli.main, ["datanorm", "upload", str(delivery)], env=S3_ENV)

    assert result.exit_code == 1
    assert "Access Denied" in result.output
