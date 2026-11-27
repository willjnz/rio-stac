"""test media type functions."""

import json
import os
import warnings

import pystac
import pytest
import rasterio

from rio_stac.stac import create_stac_item

from .conftest import PREFIX, input_date, requires_hdf4, requires_hdf5


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
    # gsd is core metadata, the average pixel size in meters
    assert list(item_dict["properties"]) == ["gsd", "datetime"]
    assert item_dict["properties"]["gsd"] == 100.01126757344893

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
