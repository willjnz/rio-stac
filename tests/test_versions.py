"""test STAC and extension version resolution."""

import os
import warnings

import pystac
import pytest
import rasterio

from rio_stac.stac import (
    EXTENSION_VERSIONS,
    UnsupportedSTACVersionError,
    _band_fields,
    _projection_fields,
    _resolve_versions,
    create_stac_item,
)

from .conftest import stac_1_1

PREFIX = os.path.join(os.path.dirname(__file__), "fixtures")


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
        ValueError,
        match="raster_and_eo_extension_version.*Allowed values: v1.1.0, v2.0.0",
    ):
        _resolve_versions(False, True, False, raster_and_eo_extension_version=version)


@pytest.mark.parametrize(
    "stac_version,projection,bands",
    [
        ("1.0.0", "v1.1.0", "v1.1.0"),
        ("1.0.0", "v2.0.0", "v1.1.0"),
        ("1.0.0", "v2.1.0", "v1.1.0"),
        ("1.1.0", "v2.1.0", "v1.1.0"),
        ("1.1.0", "v2.1.0", "v2.0.0"),
    ],
    indirect=["stac_version"],
)
def test_explicit_default_or_newer_does_not_warn(stac_version, projection, bands):
    """An explicit choice of the default version, or a newer one, does not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _resolve_versions(True, True, False, projection, bands) == (
            projection,
            bands,
        )


def test_bands_v2_falls_back_under_stac_1_0():
    """raster and eo v2.0.0 fall back to v1.1.0 under STAC 1.0, with a warning linking the spec."""
    pystac.set_stac_version("1.0.0")
    for flags in [(False, True, False), (False, False, True)]:
        with pytest.warns(UserWarning, match="STAC 1.1 `bands` field") as record:
            versions = _resolve_versions(*flags, raster_and_eo_extension_version="v2.0.0")
        assert versions == (None, "v1.1.0")
        assert len(record) == 1
        message = str(record[0].message)
        assert "rio-stac writes 'v1.1.0' instead" in message
        assert "common-metadata.md#bands" in message
        assert "best-practices.md#band-migration" in message


@stac_1_1
@pytest.mark.parametrize("version", ["v1.1.0", "v2.0.0"])
def test_explicit_older_projection_warns(stac_version, version):
    """Under STAC 1.1, an explicit projection version older than v2.1.0 warns."""
    with pytest.warns(
        UserWarning, match=r"older than the default \(v2.1.0\) for STAC 1.1.0"
    ):
        versions = _resolve_versions(
            True, False, False, projection_extension_version=version
        )
    assert versions == (version, None)


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


def _raster_band(**kwargs):
    band = {
        "data_type": "uint8",
        "scale": 1.0,
        "offset": 0.0,
        "sampling": "area",
        "nodata": 0,
        "statistics": {"minimum": 0},
        "histogram": {"count": 11},
    }
    band.update(kwargs)
    return band


def test_band_fields_v1():
    """v1.1.0 writes `raster:bands` and `eo:bands` as given."""
    raster = [_raster_band()]
    eo = [{"name": "b1", "description": "gray"}]
    assert _band_fields(raster, eo, "v1.1.0") == {
        "raster:bands": raster,
        "eo:bands": eo,
    }
    assert _band_fields(raster, [], "v1.1.0") == {"raster:bands": raster}
    assert _band_fields([], [], "v1.1.0") == {}


def test_band_fields_v2_single_band():
    """v2.0.0 writes a single band directly on the asset, without `name`."""
    fields = _band_fields(
        [_raster_band()], [{"name": "b1", "description": "gray"}], "v2.0.0"
    )
    assert fields == {
        "description": "gray",
        "data_type": "uint8",
        "raster:scale": 1.0,
        "raster:offset": 0.0,
        "raster:sampling": "area",
        "nodata": 0,
        "statistics": {"minimum": 0},
        "raster:histogram": {"count": 11},
    }


def test_band_fields_v2_multiple_bands():
    """v2.0.0 moves values shared by all bands to the asset."""
    raster = [_raster_band(unit="m"), _raster_band(unit="m"), _raster_band(unit="cm")]
    eo = [{"name": f"b{ix}", "description": "same"} for ix in range(1, 4)]
    fields = _band_fields(raster, eo, "v2.0.0")

    assert fields["data_type"] == "uint8"
    assert fields["nodata"] == 0
    assert fields["raster:scale"] == 1.0
    assert fields["raster:sampling"] == "area"
    assert "unit" not in fields
    assert "scale" not in fields
    assert "statistics" not in fields
    assert "description" not in fields

    assert [band["name"] for band in fields["bands"]] == ["b1", "b2", "b3"]
    assert [band["unit"] for band in fields["bands"]] == ["m", "m", "cm"]
    for band in fields["bands"]:
        assert set(band) == {
            "name",
            "description",
            "unit",
            "statistics",
            "raster:histogram",
        }


def test_band_fields_v2_without_eo():
    """v2.0.0 names bands even when eo is off."""
    fields = _band_fields([_raster_band(), _raster_band()], [], "v2.0.0")
    assert [band["name"] for band in fields["bands"]] == ["b1", "b2"]

    fields = _band_fields([], [{"name": "b1"}, {"name": "b2"}], "v2.0.0")
    assert fields == {"bands": [{"name": "b1"}, {"name": "b2"}]}


@pytest.mark.parametrize("raster_and_eo", EXTENSION_VERSIONS["raster_and_eo"])
@pytest.mark.parametrize("projection", EXTENSION_VERSIONS["projection"])
def test_version_matrix(stac_version, projection, raster_and_eo):
    """Every STAC and extension version combination writes a valid item with matching fields."""
    # raster and eo v2.0.0 fall back to v1.1.0 under STAC 1.0
    bands = "v1.1.0" if stac_version == "1.0.0" else raster_and_eo
    with warnings.catch_warnings():
        # older-version and fallback warnings are tested above
        warnings.simplefilter("ignore", UserWarning)
        item = create_stac_item(
            os.path.join(PREFIX, "dataset_cog.tif"),
            properties={"eo:cloud_cover": 10},
            with_proj=True,
            with_raster=True,
            with_eo=True,
            projection_extension_version=projection,
            raster_and_eo_extension_version=raster_and_eo,
        )
    item.validate()
    item_dict = item.to_dict()
    assert item_dict["stac_version"] == stac_version
    assert item_dict["stac_extensions"] == [
        f"https://stac-extensions.github.io/projection/{projection}/schema.json",
        f"https://stac-extensions.github.io/raster/{bands}/schema.json",
        f"https://stac-extensions.github.io/eo/{bands}/schema.json",
    ]

    properties = item_dict["properties"]
    if projection == "v1.1.0":
        assert properties["proj:epsg"] == 32621
        assert "proj:code" not in properties
    else:
        assert properties["proj:code"] == "EPSG:32621"
        assert "proj:epsg" not in properties

    asset = item_dict["assets"]["asset"]
    if bands == "v1.1.0":
        assert "raster:bands" in asset
        assert "eo:bands" in asset
        assert "data_type" not in asset
    else:
        assert asset["data_type"] == "uint16"
        assert "raster:bands" not in asset
        assert "eo:bands" not in asset
