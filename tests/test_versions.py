"""test STAC and extension version resolution."""

import logging
import warnings

import pystac
import pytest

from rio_stac.stac import (
    DEFAULT_EXTENSION_VERSIONS,
    UnsupportedSTACVersionError,
    _resolve_versions,
)


def test_defaults(stac_version):
    """Defaults follow the STAC version pystac writes."""
    defaults = DEFAULT_EXTENSION_VERSIONS[stac_version]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, True) == (
            defaults["projection"],
            defaults["raster_and_eo"],
        )


def test_not_requested(stac_version):
    """Extensions not requested resolve to None and their argument is ignored."""
    assert _resolve_versions(False, False, False) == (None, None)
    assert _resolve_versions(True, False, False, None, "v9.9.9")[1] is None
    assert _resolve_versions(False, True, False, "v9.9.9", None)[0] is None
    assert _resolve_versions(False, False, True)[1] is not None


@pytest.mark.parametrize("version", ["1.2.0", "3.0.0"])
def test_unknown_stac_version(version):
    """Unknown STAC versions raise only when an extension is requested."""
    pystac.set_stac_version(version)
    assert _resolve_versions(False, False, False) == (None, None)
    with pytest.raises(
        UnsupportedSTACVersionError, match=f"STAC {version}.*1.0.0, 1.1.0"
    ):
        _resolve_versions(True, False, False)


def test_unknown_stac_version_env(monkeypatch):
    """The error names the environment variable when it is set."""
    monkeypatch.setenv("PYSTAC_STAC_VERSION_OVERRIDE", "3.0.0")
    with pytest.raises(
        UnsupportedSTACVersionError, match="PYSTAC_STAC_VERSION_OVERRIDE=3.0.0"
    ):
        _resolve_versions(False, True, False)


@pytest.mark.parametrize("version", ["v3.0.0", "1.1.0", "v2.0.0-beta.1"])
def test_unknown_extension_version(stac_version, version):
    """Unknown, unprefixed or pre-release extension versions raise."""
    with pytest.raises(
        ValueError, match="projection_extension_version.*Allowed values: v1.1.0"
    ):
        _resolve_versions(True, False, False, projection_extension_version=version)

    with pytest.raises(
        ValueError, match="raster_and_eo_extension_version.*Allowed values: v1.1.0"
    ):
        _resolve_versions(False, True, False, raster_and_eo_extension_version=version)


def test_explicit_latest_does_not_warn(stac_version):
    """An explicit choice of the latest version does not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, False, "v1.1.0", "v1.1.0") == (
            "v1.1.0",
            "v1.1.0",
        )


def test_debug_log(caplog, stac_version):
    """The pystac version and STAC version are logged at DEBUG."""
    caplog.set_level(logging.DEBUG, logger="rio_stac.stac")
    _resolve_versions(True, False, False)
    assert pystac.__version__ in caplog.text
    assert f"STAC {stac_version}" in caplog.text
