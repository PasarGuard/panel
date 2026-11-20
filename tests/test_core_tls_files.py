"""Core config TLS files: allowed directories, PEM key check and soft loading of saved cores."""

import ntpath
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core import xray
from app.core.xray import _read_tls_file


def _write_key(path):
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )


@pytest.fixture
def tls_dirs(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setattr(
        xray, "server_settings", SimpleNamespace(tls_files_allowed_dirs=f" {allowed} ,", ssl_keyfile=None)
    )
    return allowed, outside


def test_tls_file_outside_allowed_dirs_is_refused(tls_dirs):
    _, outside = tls_dirs
    secret = outside / "panel.env"
    secret.write_text("SQLALCHEMY_DATABASE_URL=postgresql://user:password@db/pasarguard\n")

    with pytest.raises(ValueError, match="outside the directories allowed") as error:
        xray._read_tls_file(str(secret), private_key=True)
    assert "password" not in str(error.value)


def test_tls_file_dotdot_and_symlink_escapes_are_refused(tls_dirs):
    allowed, outside = tls_dirs
    _write_key(outside / "other.key")

    with pytest.raises(ValueError, match="outside"):
        xray._read_tls_file(str(allowed / ".." / "outside" / "other.key"), private_key=True)

    link = allowed / "link.key"
    try:
        link.symlink_to(outside / "other.key")
    except OSError:
        pytest.skip("symlinks are not available on this system")
    with pytest.raises(ValueError, match="outside"):
        xray._read_tls_file(str(link), private_key=True)


def test_key_file_must_be_a_pem_private_key(tls_dirs):
    allowed, _ = tls_dirs
    not_a_key = allowed / "notes.txt"
    not_a_key.write_text("root:$6$hash:19000:0:99999:7:::\n")

    with pytest.raises(ValueError, match="not an unencrypted PEM private key") as error:
        xray._read_tls_file(str(not_a_key), private_key=True)
    assert "root:" not in str(error.value)


def test_key_file_inside_allowed_dir_is_read(tls_dirs):
    allowed, _ = tls_dirs
    key = allowed / "certs" / "privkey.pem"
    key.parent.mkdir()
    _write_key(key)

    assert xray._read_tls_file(str(key), private_key=True).startswith(b"-----BEGIN PRIVATE KEY-----")


def test_panel_own_tls_key_inside_allowed_dir_is_accepted(tls_dirs, monkeypatch):
    """One domain for the panel and the inbounds: the inbound may reuse the panel's HTTPS key."""
    allowed, _ = tls_dirs
    key = allowed / "panel.key"
    _write_key(key)
    monkeypatch.setattr(
        xray, "server_settings", SimpleNamespace(tls_files_allowed_dirs=str(allowed), ssl_keyfile=str(key))
    )

    assert xray._read_tls_file(str(key), private_key=True).startswith(b"-----BEGIN PRIVATE KEY-----")


def test_strict_mode_checks_the_directory_before_touching_the_file(tls_dirs, monkeypatch):
    """A missing and an existing file outside the allowed dirs get the same error, and neither is stat-ed."""
    _, outside = tls_dirs
    existing = outside / "shadow"
    existing.write_text("root:$6$hash:19000:0:99999:7:::\n")
    missing = outside / "missing"

    def must_not_touch(*args, **kwargs):
        raise AssertionError("the file system was touched before the directory check")

    monkeypatch.setattr(xray.os.path, "isfile", must_not_touch)
    monkeypatch.setattr(xray.os.path, "getsize", must_not_touch)
    errors = []
    for path in (existing, missing):
        with pytest.raises(ValueError, match="outside the directories allowed") as error:
            xray._read_tls_file(str(path), private_key=True)
        errors.append(str(error.value).replace(str(path), "<path>"))
    assert errors[0] == errors[1]
    assert "root:" not in errors[0]


def test_unc_path_is_refused_in_strict_mode_without_resolving_it(tls_dirs, monkeypatch):
    def must_not_resolve(*args, **kwargs):
        raise AssertionError("the UNC path was resolved")

    allowed_dirs = xray._allowed_tls_dirs()
    monkeypatch.setattr(xray, "_allowed_tls_dirs", lambda: allowed_dirs)
    # Windows path semantics on any OS: there realpath of a UNC path would open an SMB connection.
    monkeypatch.setattr(xray.os.path, "splitdrive", ntpath.splitdrive)
    monkeypatch.setattr(xray.os.path, "realpath", must_not_resolve)

    with pytest.raises(ValueError, match="outside the directories allowed"):
        xray._read_tls_file(r"\\host\share\cert.pem")


def test_soft_mode_reads_a_file_outside_allowed_dirs(tls_dirs):
    _, outside = tls_dirs
    key = outside / "privkey.pem"
    _write_key(key)

    assert xray._read_tls_file(str(key), private_key=True, strict=False).startswith(b"-----BEGIN PRIVATE KEY-----")


def test_soft_mode_keeps_the_base_checks(tls_dirs):
    _, outside = tls_dirs
    not_a_key = outside / "shadow"
    not_a_key.write_text("root:$6$hash:19000:0:99999:7:::\n")

    with pytest.raises(ValueError, match="not an unencrypted PEM private key") as error:
        xray._read_tls_file(str(not_a_key), private_key=True, strict=False)
    assert "root:" not in str(error.value)
    with pytest.raises(ValueError, match="not a regular certificate file"):
        xray._read_tls_file(str(outside), strict=False)
    big = outside / "big.pem"
    big.write_bytes(b"x" * (xray.MAX_TLS_FILE_SIZE + 1))
    with pytest.raises(ValueError, match="too large"):
        xray._read_tls_file(str(big), strict=False)


def _tls_core_config(cert_path: str, key_path: str) -> dict:
    from tests.test_xray_tls_fallback import _config, _parent_inbound

    return _config([_parent_inbound([{"certificateFile": cert_path, "keyFile": key_path}], [])])


def test_xray_config_is_strict_by_default_and_soft_on_request(tls_dirs):
    from tests.test_xray_tls_fallback import _write_self_signed

    _, outside = tls_dirs
    cert_path, key_path = _write_self_signed(outside)
    config = _tls_core_config(cert_path, key_path)

    with pytest.raises(ValueError, match="outside the directories allowed"):
        xray.XRayConfig(config)

    loaded = xray.XRayConfig(config, strict_tls_paths=False)
    assert "vless-tls" in loaded.inbounds_by_tag
    assert loaded.tls_files_outside_allowed_dirs == [cert_path, key_path]


@pytest.mark.asyncio
async def test_saved_core_with_tls_files_outside_allowed_dirs_loads_on_startup(tls_dirs, monkeypatch):
    """After the upgrade a core saved with /root/certs-like paths keeps its inbounds and logs a warning."""
    from app.core.manager import CoreManager
    from app.db.models import CoreType
    from tests.test_xray_tls_fallback import _write_self_signed

    _, outside = tls_dirs
    cert_path, key_path = _write_self_signed(outside)
    saved = SimpleNamespace(
        id=7,
        name="main",
        type=CoreType.xray,
        config=_tls_core_config(cert_path, key_path),
        exclude_inbound_tags=set(),
        fallbacks_inbound_tags=set(),
    )

    async def fake_get_core_configs(db, query):
        return [saved], 1

    async def noop_persist():
        return None

    manager = CoreManager()
    manager._nats_enabled = False
    warnings = []
    monkeypatch.setattr(manager._logger, "warning", lambda message, *args: warnings.append(message % args))
    monkeypatch.setattr("app.core.manager.get_core_configs", fake_get_core_configs)
    monkeypatch.setattr(manager, "_persist_state", noop_persist)

    await manager.initialize(db=None)

    assert "vless-tls" in (await manager.get_cores())[7].inbounds_by_tag
    assert any("id=7" in w and "'main'" in w and cert_path in w and "TLS_FILES_ALLOWED_DIRS" in w for w in warnings)
    assert any(key_path in w for w in warnings)


@pytest.mark.asyncio
async def test_core_update_from_another_worker_is_loaded_softly(tls_dirs, monkeypatch):
    """A NATS update carries a config another worker already saved; it must not be dropped here."""
    from app.core.manager import CoreManager
    from app.db.models import CoreType
    from tests.test_xray_tls_fallback import _write_self_signed

    _, outside = tls_dirs
    cert_path, key_path = _write_self_signed(outside)
    manager = CoreManager()
    manager._nats_enabled = False

    async def noop_persist():
        return None

    monkeypatch.setattr(manager, "_persist_state", noop_persist)

    await manager._apply_core_payload({"id": 3, "type": CoreType.xray, "config": _tls_core_config(cert_path, key_path)})

    assert "vless-tls" in (await manager.get_cores())[3].inbounds_by_tag


def test_default_allowed_dirs_are_the_data_dir_and_letsencrypt():
    from config import ServerSettings

    assert ServerSettings.model_fields["tls_files_allowed_dirs"].default == "/var/lib/pasarguard,/etc/letsencrypt"


def test_tls_file_reader_only_accepts_regular_files(tmp_path, monkeypatch):
    monkeypatch.setattr(xray.server_settings, "tls_files_allowed_dirs", str(tmp_path))
    cert = tmp_path / "cert.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----")

    assert _read_tls_file(str(cert)) == b"-----BEGIN CERTIFICATE-----"
    with pytest.raises(ValueError):
        _read_tls_file("/proc/self/environ")
    with pytest.raises(ValueError):
        _read_tls_file(str(tmp_path))
