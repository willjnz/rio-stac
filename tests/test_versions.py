"""test STAC and extension version resolution."""

import warnings

import pystac
import pytest

from rio_stac.stac import UnsupportedSTACVersionError, _resolve_versions


@pytest.mark.parametrize(
    "stac_version,expected",
    [("1.0.0", ("v1.1.0", "v1.1.0")), ("1.1.0", ("v1.1.0", "v1.1.0"))],
    indirect=["stac_version"],
)
def test_defaults(stac_version, expected):
    """Defaults follow the STAC version pystac writes, without warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, True) == expected


def test_not_requested(stac_version):
    """Extensions not requested resolve to None and their argument is ignored."""
    assert _resolve_versions(False, False, False) == (
        None,
        None,
    )  # No extensions = nothing to resolve
    # TODO: Should the next 2 assertions error even though they are not used?
    assert (
        _resolve_versions(True, False, False, None, "v9.9.9")[1] is None
    )  # Only proj so bad eo version is ignored
    assert (
        _resolve_versions(False, True, False, "v9.9.9", None)[0] is None
    )  # Same as above but for proj
    assert (
        _resolve_versions(False, False, True)[1] == "v1.1.0"
    )  # Just eo returns the shared eo/raster version


# rio-stac doesn't know how to write >=1.2.0 so it explicitly raises
@pytest.mark.parametrize("version", ["1.2.0", "3.0.0"])
def test_unknown_stac_version(version):
    """Unknown STAC versions raise, with or without extensions."""
    pystac.set_stac_version(version)
    for flags in [(False, False, False), (True, False, False), (False, True, False)]:
        with pytest.raises(
            UnsupportedSTACVersionError, match=f"STAC {version}.*1.0.0, 1.1.0"
        ):
            _resolve_versions(*flags)


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


# This test is weak, but will become stronger when STAC version v1.1 is supported properly
def test_explicit_default_does_not_warn(stac_version):
    """An explicit choice of the default version does not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, False, "v1.1.0", "v1.1.0") == (
            "v1.1.0",
            "v1.1.0",
        )
