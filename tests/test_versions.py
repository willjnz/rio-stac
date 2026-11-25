"""test STAC and extension version resolution."""

import warnings

import pystac
import pytest
import rasterio

from rio_stac.stac import (
    UnsupportedSTACVersionError,
    _projection_fields,
    _resolve_versions,
)


@pytest.mark.parametrize(
    "stac_version,expected",
    [("1.0.0", ("v1.1.0", "v1.1.0")), ("1.1.0", ("v2.1.0", "v1.1.0"))],
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
        ValueError,
        match="projection_extension_version.*Allowed values: v1.1.0, v2.0.0, v2.1.0",
    ):
        _resolve_versions(True, False, False, projection_extension_version=version)

    with pytest.raises(
        ValueError, match="raster_and_eo_extension_version.*Allowed values: v1.1.0"
    ):
        _resolve_versions(False, True, False, raster_and_eo_extension_version=version)


@pytest.mark.parametrize("projection", ["v1.1.0", "v2.0.0", "v2.1.0"])
def test_explicit_default_or_newer_does_not_warn(stac_version, projection):
    """An explicit choice of the default version (v1.1.0), or a newer one, does not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, False, projection, "v1.1.0") == (
            projection,
            "v1.1.0",
        )


PROJ_INFO = {
    "epsg": 32621,
    "geometry": {"type": "Polygon", "coordinates": []},
    "bbox": [0, 0, 1, 1],
    "shape": [1, 1],
    "transform": [1, 0, 0, 0, -1, 1, 0, 0, 1],
}
UTM = rasterio.crs.CRS.from_epsg(32621)
WGS84 = rasterio.crs.CRS.from_epsg(4326)


def test_projection_fields_v1():
    """v1.1.0 output is unchanged: `proj:epsg`, including None."""
    assert _projection_fields(PROJ_INFO, UTM, "v1.1.0") == {
        "proj:epsg": 32621,
        "proj:geometry": {"type": "Polygon", "coordinates": []},
        "proj:bbox": [0, 0, 1, 1],
        "proj:shape": [1, 1],
        "proj:transform": [1, 0, 0, 0, -1, 1, 0, 0, 1],
    }
    no_epsg = {**PROJ_INFO, "epsg": None, "wkt2": "WKT"}
    assert _projection_fields(no_epsg, None, "v1.1.0") == {
        "proj:epsg": None,
        "proj:geometry": {"type": "Polygon", "coordinates": []},
        "proj:bbox": [0, 0, 1, 1],
        "proj:shape": [1, 1],
        "proj:transform": [1, 0, 0, 0, -1, 1, 0, 0, 1],
        "proj:wkt2": "WKT",
    }
    # WGS 84 keeps `proj:bbox` and `proj:geometry` in v1.1.0
    wgs84_fields = _projection_fields({**PROJ_INFO, "epsg": 4326}, WGS84, "v1.1.0")
    assert wgs84_fields["proj:bbox"] == [0, 0, 1, 1]
    assert wgs84_fields["proj:geometry"] == {"type": "Polygon", "coordinates": []}


@pytest.mark.parametrize("version", ["v2.0.0", "v2.1.0"])
def test_projection_fields_v2(version):
    """v2.x writes `proj:code` instead of `proj:epsg`, or None with the wkt2 fallback."""
    assert _projection_fields(PROJ_INFO, UTM, version) == {
        "proj:code": "EPSG:32621",
        "proj:geometry": PROJ_INFO["geometry"],
        "proj:bbox": PROJ_INFO["bbox"],
        "proj:shape": PROJ_INFO["shape"],
        "proj:transform": PROJ_INFO["transform"],
    }

    no_epsg = {**PROJ_INFO, "epsg": None, "wkt2": "WKT"}
    fields = _projection_fields(no_epsg, None, version)
    assert fields["proj:code"] is None
    assert fields["proj:wkt2"] == "WKT"
    assert "proj:epsg" not in fields
    assert "proj:bbox" in fields  # no CRS: not WGS 84, so kept
    # input is not modified
    assert "epsg" in no_epsg


def test_projection_fields_wgs84():
    """v2.1.0 omits `proj:bbox` and `proj:geometry` for WGS 84; v2.0.0 keeps them."""
    crs = WGS84
    info = {**PROJ_INFO, "epsg": 4326}
    assert _projection_fields(info, crs, "v2.1.0") == {
        "proj:code": "EPSG:4326",
        "proj:shape": PROJ_INFO["shape"],
        "proj:transform": PROJ_INFO["transform"],
    }

    fields = _projection_fields(info, crs, "v2.0.0")
    assert fields["proj:bbox"] == PROJ_INFO["bbox"]
    assert fields["proj:geometry"] == PROJ_INFO["geometry"]
