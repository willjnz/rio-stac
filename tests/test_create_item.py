"""test media type functions."""

import datetime
import json
import os
import sys
import warnings

import numpy
import pystac
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from rio_stac.stac import create_stac_item, get_bands_info, get_raster_info

from .conftest import requires_hdf4, requires_hdf5

PREFIX = os.path.join(os.path.dirname(__file__), "fixtures")
input_date = datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.parametrize(
    "file",
    [
        "dataset_nodata_nan.tif",
        "dataset_nodata_and_nan.tif",
        "dataset_cog.tif",
        "dataset_gdalcog.tif",
        "dataset_geo.tif",
        "dataset.tif",
        "dataset.jp2",
        "dataset.jpg",
        "dataset.png",
        "dataset.webp",
        "dataset_gcps.tif",
        "issue_22.tif",
        "dataset_dateline.tif",
        "dataset_int16_nodata.tif",
    ],
)
def test_create_item(file):
    """Should run without exceptions."""
    src_path = os.path.join(PREFIX, file)
    with rasterio.open(src_path) as src_dst:
        assert create_stac_item(
            src_dst, input_datetime=input_date, with_raster=True
        ).validate()


@requires_hdf4
def test_hdf4():
    """Test hdf4."""
    src_path = os.path.join(PREFIX, "dataset.hdf")
    with rasterio.open(src_path) as src_dst:
        assert create_stac_item(src_dst, input_datetime=input_date).validate()


@requires_hdf5
def test_hdf5():
    """Test hdf5."""
    src_path = os.path.join(PREFIX, "dataset.h5")
    with rasterio.open(src_path) as src_dst:
        assert create_stac_item(src_dst, input_datetime=input_date).validate()


def test_create_item_options():
    """Should return the correct mediatype."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")

    # pass string
    assert create_stac_item(src_path, input_datetime=input_date).validate()

    # default COG
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        asset_media_type=pystac.MediaType.COG,
        with_proj=False,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["assets"]["asset"]["type"] == pystac.MediaType.COG
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == []
    assert list(item_dict["properties"]) == ["datetime"]

    # additional extensions and properties
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        extensions=["https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
        properties={"sci:citation": "A nice image"},
        with_proj=False,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ]
    assert "datetime" in item_dict["properties"]
    assert "proj:code" not in item_dict["properties"]
    assert "sci:citation" in item_dict["properties"]

    # additional extensions and properties
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        extensions=["https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
        properties={"sci:citation": "A nice image"},
        with_proj=True,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
    ]
    assert "datetime" in item_dict["properties"]
    assert item_dict["properties"]["proj:code"] == "EPSG:32621"
    assert "proj:epsg" not in item_dict["properties"]
    assert "proj:wkt2" not in item_dict["properties"]
    assert "proj:projjson" not in item_dict["properties"]
    assert "sci:citation" in item_dict["properties"]

    # external assets
    assets = {"cog": pystac.Asset(href=src_path)}
    item = create_stac_item(
        src_path, input_datetime=input_date, assets=assets, with_proj=False
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["assets"]["cog"]
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == []
    assert "datetime" in item_dict["properties"]

    # collection
    item = create_stac_item(
        src_path, input_datetime=input_date, collection="mycollection", with_proj=False
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"][0]["href"] == "mycollection"
    assert item_dict["stac_extensions"] == []
    assert "datetime" in item_dict["properties"]
    assert item_dict["collection"] == "mycollection"

    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        collection="mycollection",
        collection_url="https://stac.somewhere.io/mycollection.json",
        with_proj=False,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"][0]["href"] == "https://stac.somewhere.io/mycollection.json"
    assert item_dict["stac_extensions"] == []
    assert "datetime" in item_dict["properties"]
    assert item_dict["collection"] == "mycollection"


def test_proj_without_proj():
    """Use the Proj extension without proj info."""
    src_path = os.path.join(PREFIX, "dataset.tif")

    # additional extensions and properties
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        with_proj=True,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
    ]
    assert "datetime" in item_dict["properties"]
    # No CRS: no code, and not WGS84 so `proj:bbox` is kept
    assert item_dict["properties"]["proj:code"] is None
    with rasterio.open(src_path) as src_dst:
        assert item_dict["properties"]["proj:bbox"] == list(src_dst.bounds)


def test_proj_wgs84():
    """`proj:bbox` and `proj:geometry` are omitted when the CRS is WGS84. bbox and geometry are kept."""
    src_path = os.path.join(PREFIX, "dataset_nodata_nan.tif")
    item = create_stac_item(src_path, input_datetime=input_date, with_proj=True)
    assert item.validate()
    properties = item.to_dict()["properties"]
    assert properties["proj:code"] == "EPSG:4326"
    assert "proj:bbox" not in properties
    assert "proj:geometry" not in properties
    assert properties["proj:shape"] == [341, 316]
    with rasterio.open(src_path) as src_dst:
        assert item.bbox == list(src_dst.bounds)


def test_create_item_raster():
    """Should return a valid item with raster properties."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        with_raster=True,
        raster_max_size=128,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"] == []
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
    ]
    # A single band is written directly on the asset
    assert "bands" not in item_dict["assets"]["asset"]
    assert "name" not in item_dict["assets"]["asset"]
    assert item_dict["assets"]["asset"]["data_type"] == "uint16"

    # Nodata=None not in the properties
    assert "nodata" not in item_dict["assets"]["asset"]

    # Unit=None not in the properties
    assert "unit" not in item_dict["assets"]["asset"]

    assert item_dict["assets"]["asset"]["raster:sampling"] == "point"

    src_path = os.path.join(PREFIX, "dataset_nodata_nan.tif")
    item = create_stac_item(src_path, input_datetime=input_date, with_raster=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
    ]

    assert item_dict["assets"]["asset"]["nodata"] == "nan"

    src_path = os.path.join(PREFIX, "dataset_with_offsets.tif")
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        with_raster=True,
    )
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
    ]
    assert item_dict["assets"]["asset"]["raster:scale"] == 0.0001
    assert item_dict["assets"]["asset"]["raster:offset"] == 1000.0


def test_create_item_raster_with_gcps():
    """Should return a valid item with raster properties."""
    src_path = os.path.join(PREFIX, "dataset_gcps.tif")
    item = create_stac_item(
        src_path, input_datetime=input_date, with_raster=True, with_proj=True
    )
    assert item.validate()


@pytest.mark.xfail
def test_dateline_polygon_split():
    """make sure we return a multipolygon."""
    src_path = os.path.join(PREFIX, "dataset_dateline.tif")
    item = create_stac_item(
        src_path, input_datetime=input_date, with_raster=True, with_proj=True
    )
    item_dict = item.to_dict()
    assert item_dict["geometry"]["type"] == "MultiPolygon"


def test_negative_nodata():
    """Make sure we catch valid nodata (issue 33)."""
    src_path = os.path.join(PREFIX, "dataset_int16_nodata.tif")
    item = create_stac_item(
        src_path, input_datetime=input_date, with_raster=True, with_proj=True
    )
    item_dict = item.to_dict()
    assert item_dict["assets"]["asset"]["nodata"] == -9999


def test_create_item_eo():
    """Band names and descriptions are core `bands` fields; eo is declared for eo:* fields."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["links"] == []
    # no eo:* field (no cloud cover), so no eo extension
    assert item_dict["stac_extensions"] == []
    assert item_dict["assets"]["asset"]["description"] == "gray"
    assert "bands" not in item_dict["assets"]["asset"]

    src_path = os.path.join(PREFIX, "dataset_description.tif")
    item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["assets"]["asset"]["description"] == "b1"

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="FALSE"):
        src_path = os.path.join(PREFIX, "dataset_cloud_date_metadata.tif")
        item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["stac_extensions"] == [
        "https://stac-extensions.github.io/eo/v2.0.0/schema.json",
    ]
    assert item_dict["properties"]["eo:cloud_cover"] == 2
    assert item_dict["assets"]["asset"]["bands"] == [
        {"name": "b1", "description": "red"},
        {"name": "b2", "description": "green"},
        {"name": "b3", "description": "blue"},
    ]


def _memfile(**imagery):
    """A 2 band uint16 GeoTIFF in memory, with optional IMAGERY tags."""
    memfile = MemoryFile()
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "count": 2,
        "width": 4,
        "height": 4,
        "crs": "EPSG:32621",
        "transform": from_origin(373185, 8286015, 10, 20),
    }
    with memfile.open(**profile) as dst:
        dst.write(numpy.arange(32, dtype="uint16").reshape(2, 4, 4))
        if imagery:
            dst.update_tags(ns="IMAGERY", **imagery)
    return memfile


def test_cloud_cover_not_available():
    """Cloud cover outside 0-100 (e.g. GDAL's 999, not available) is not written."""
    for cloudcover in [999, 120, -1, 100.4]:
        with _memfile(CLOUDCOVER=cloudcover) as memfile, memfile.open() as src_dst:
            item = create_stac_item(src_dst, input_datetime=input_date, with_eo=True)
        assert "eo:cloud_cover" not in item.properties

    # Decimal values are rounded to an int
    for cloudcover, expected in [(40, 40), ("40.0", 40), (40.6, 41)]:
        with _memfile(CLOUDCOVER=cloudcover) as memfile, memfile.open() as src_dst:
            item = create_stac_item(src_dst, input_datetime=input_date, with_eo=True)
        assert item.properties["eo:cloud_cover"] == expected


def test_datetime_now_warning():
    """A warning is raised when no datetime is found and the current time is used."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    with pytest.warns(UserWarning, match="the current time"):
        create_stac_item(src_path)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        create_stac_item(src_path, input_datetime=input_date)


def test_create_item_datetime():
    """Should return a valid item with datetime from IMD."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="FALSE"):
        src_path = os.path.join(PREFIX, "dataset_cloud_date_metadata.tif")
        item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["properties"]["datetime"] == "2011-05-01T13:00:00Z"

    src_path = os.path.join(PREFIX, "dataset_tiff_datetime.tif")
    item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert item_dict["properties"]["datetime"] == "2023-10-30T11:37:13Z"


def test_densify_geom():
    """Should run without exceptions."""
    src_path = os.path.join(PREFIX, "dataset_geom.tif")

    item = create_stac_item(src_path, with_eo=True)
    assert item.validate()
    item_dict = item.to_dict()

    item_dens = create_stac_item(src_path, geom_densify_pts=21)
    assert item_dens.validate()
    item_dens_dict = item_dens.to_dict()

    assert item_dict["bbox"] != item_dens_dict["bbox"]


def test_mars_dataset():
    """Test with Mars Dataset."""
    MARS2000_SPHERE = rasterio.crs.CRS.from_proj4("+proj=longlat +R=3396190 +no_defs")
    src_path = os.path.join(PREFIX, "dataset_mars.tif")

    item = create_stac_item(src_path, geographic_crs=MARS2000_SPHERE, with_proj=True)
    assert item.validate()
    item_dict = item.to_dict()

    # No EPSG code: `proj:code` is None and the CRS is written as `proj:wkt2`
    assert item_dict["properties"]["proj:code"] is None
    with rasterio.open(src_path) as src_dst:
        assert (
            rasterio.crs.CRS.from_wkt(item_dict["properties"]["proj:wkt2"]) == src_dst.crs
        )


def test_json_serialization():
    """Test JSON serialization"""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(src_path, with_raster=True)
    assert item.validate()
    item_dict = item.to_dict()
    assert json.dumps(item_dict)


@pytest.mark.xfail(sys.version_info < (3, 10), reason="Old numpy do not raise error")
def test_stats_unique_values():
    """issue 68 -
    ref: https://github.com/developmentseed/rio-stac/issues/68
    """
    src_path = os.path.join(
        PREFIX, "S2A_MSIL2A_20220722T105631_N0400_R094_T31TCN_20220722T171159.tif"
    )
    with pytest.warns(UserWarning):
        item = create_stac_item(src_path, with_raster=True)
    assert item.validate()
    item_dict = item.to_dict()
    stats = item_dict["assets"]["asset"]["bands"][9]["raster:histogram"]
    assert len(stats["buckets"]) == 3

    # Should not raise warnings when bins is good
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        item = create_stac_item(
            src_path,
            input_datetime=input_date,
            with_raster=True,
            histogram_bins=3,
        )

    with pytest.raises(ValueError):
        create_stac_item(
            src_path, with_raster=True, histogram_bins=3, histogram_range=(0, -1)
        )

    with pytest.raises(ValueError):
        create_stac_item(src_path, with_raster=True, histogram_range=(0, -1))


def test_create_item_raster_custom_histogram():
    """Should return a valid item with raster properties."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(
        src_path,
        input_datetime=input_date,
        with_raster=True,
        raster_max_size=128,
        histogram_bins=5,
        histogram_range=[0, 10],
    )
    assert item.validate()
    item_dict = item.to_dict()
    stats = item_dict["assets"]["asset"]["raster:histogram"]
    assert len(stats["buckets"]) == 5
    assert stats["max"] == 10
    assert stats["min"] == 0


def test_stats_with_nan_missing_nodata():
    """Stats should ignore nan/inf values.

    Ref: https://github.com/developmentseed/rio-stac/issues/70
    """
    src_path = os.path.join(PREFIX, "dataset_missing_nodata_nan.tif")
    with rasterio.open(src_path) as src:
        arr = src.read(masked=True)
        assert numpy.isnan(arr.max().item())

        info = get_raster_info(src)
        assert info[0]["statistics"]["minimum"] > 0
        assert info[0]["statistics"]["maximum"] > 0


def test_get_bands_info():
    """raster and eo band metadata is merged into STAC 1.1 `bands`."""
    raster = [
        {
            "data_type": "uint8",
            "raster:scale": 1.0,
            "raster:offset": 0.0,
            "raster:sampling": "area",
            "nodata": 0,
            "unit": "m",
            "statistics": {"minimum": 0},
            "raster:histogram": {"count": 10},
        }
    ]
    eo = [{"name": "b1", "description": "red"}]
    # A single band is written directly on the asset, without `name`
    assert get_bands_info(raster, eo) == {
        "description": "red",
        "data_type": "uint8",
        "raster:scale": 1.0,
        "raster:offset": 0.0,
        "raster:sampling": "area",
        "nodata": 0,
        "unit": "m",
        "statistics": {"minimum": 0},
        "raster:histogram": {"count": 10},
    }
    assert get_bands_info([], []) == {}


def test_get_bands_info_shared_values():
    """Values shared by all bands move to the asset; per-band values stay in `bands`."""
    raster = [
        {
            "data_type": "uint8",
            "raster:scale": 1.0,
            "unit": unit,
            "statistics": {"minimum": 0},
        }
        for unit in ["m", "m", "cm"]
    ]
    eo = [{"name": f"b{ix}", "description": "same"} for ix in range(1, 4)]
    assert get_bands_info(raster, eo) == {
        "data_type": "uint8",
        "raster:scale": 1.0,
        "bands": [
            # name, description and statistics always stay per band
            {
                "name": "b1",
                "description": "same",
                "unit": "m",
                "statistics": {"minimum": 0},
            },
            {
                "name": "b2",
                "description": "same",
                "unit": "m",
                "statistics": {"minimum": 0},
            },
            {
                "name": "b3",
                "description": "same",
                "unit": "cm",
                "statistics": {"minimum": 0},
            },
        ],
    }
    # raster only: bands are named b1, b2
    assert [band["name"] for band in get_bands_info(raster[:2], [])["bands"]] == [
        "b1",
        "b2",
    ]


def test_create_item_assets_no_band_extensions():
    """When `assets` is passed, no band fields are written, so raster and eo are not declared."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(
        src_path,
        assets={"cog": pystac.Asset(href=src_path)},
        with_raster=True,
        with_eo=True,
    )
    assert item.validate()
    assert item.to_dict()["stac_extensions"] == []


def test_create_item_eo_properties():
    """The eo extension is declared for eo:* properties passed by the user."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(src_path, properties={"eo:snow_cover": 10}, with_eo=True)
    assert item.validate()
    assert item.to_dict()["stac_extensions"] == [
        "https://stac-extensions.github.io/eo/v2.0.0/schema.json",
    ]

    # without `with_eo`, rio-stac doesn't declare it (pass it in `extensions`)
    item = create_stac_item(src_path, properties={"eo:snow_cover": 10})
    assert item.to_dict()["stac_extensions"] == []


def test_create_item_shared_band_values():
    """Multi-band rasters: shared values are on the asset, per-band values in `bands`."""
    src_path = os.path.join(
        PREFIX, "S2A_MSIL2A_20220722T105631_N0400_R094_T31TCN_20220722T171159.tif"
    )
    with pytest.warns(UserWarning):
        item = create_stac_item(src_path, with_raster=True, with_eo=True)
    assert item.validate()
    asset = item.to_dict()["assets"]["asset"]
    assert asset["data_type"] == "float32"
    assert asset["nodata"] == "nan"
    assert len(asset["bands"]) == 14
    for ix, band in enumerate(asset["bands"], 1):
        assert band["name"] == f"b{ix}"
        assert "data_type" not in band
        assert "nodata" not in band
        assert "statistics" in band
