"""tests rio_stac.stac projection extension."""

import os

import numpy
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from rio_stac.stac import _get_centroid, create_stac_item

from .conftest import PREFIX, input_date


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
    # No CRS: no code, no centroid, and not WGS84 so `proj:bbox` is kept
    assert item_dict["properties"]["proj:code"] is None
    assert "proj:centroid" not in item_dict["properties"]
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


def test_proj_centroid():
    """`proj:centroid` is the center of the raster bounds, in lat/lon."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")
    item = create_stac_item(src_path, input_datetime=input_date, with_proj=True)
    assert item.validate()
    assert item.properties["proj:centroid"] == {
        "lat": 73.4675735659621,
        "lon": -56.80794728322342,
    }

    # 0 to 360 longitudes are wrapped to -180/180: lon 190 is -170
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            dtype="uint8",
            count=1,
            width=20,
            height=20,
            crs="EPSG:4326",
            transform=from_origin(180, 10, 1, 1),
        ) as dst:
            dst.write(numpy.zeros((1, 20, 20), dtype="uint8"))
        with memfile.open() as src_dst:
            assert _get_centroid(src_dst) == (-170.0, 0.0)
