"""tests rio_stac.stac raster extension."""

import os
import sys
import warnings

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

from rio_stac.stac import create_stac_item, get_raster_info

from .conftest import PREFIX, _memfile, input_date


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


def test_negative_nodata():
    """Make sure we catch valid nodata (issue 33)."""
    src_path = os.path.join(PREFIX, "dataset_int16_nodata.tif")
    item = create_stac_item(
        src_path, input_datetime=input_date, with_raster=True, with_proj=True
    )
    item_dict = item.to_dict()
    assert item_dict["assets"]["asset"]["nodata"] == -9999


def test_bits_per_sample_and_resolution():
    """`raster:bits_per_sample` from NBITS; resolution and gsd in meters, shared on the asset."""
    with _memfile(nbits=12) as memfile, memfile.open() as src_dst:
        item = create_stac_item(src_dst, input_datetime=input_date, with_raster=True)
    assert item.validate()
    asset = item.to_dict()["assets"]["asset"]
    assert asset["raster:bits_per_sample"] == 12
    # 10 x 20 m pixels: the average is 15 m
    assert asset["raster:spatial_resolution"] == 15.0
    assert item.properties["gsd"] == 15.0

    # No NBITS: no bits_per_sample. Degrees (0.001 near the equator) are converted to meters
    with (
        _memfile(crs="EPSG:4326", transform=from_origin(11, 1, 0.001, 0.001)) as memfile,
        memfile.open() as src_dst,
    ):
        item = create_stac_item(src_dst, input_datetime=input_date, with_raster=True)
    asset = item.to_dict()["assets"]["asset"]
    assert "raster:bits_per_sample" not in asset
    assert asset["raster:spatial_resolution"] == pytest.approx(111, rel=0.01)
    assert item.properties["gsd"] == asset["raster:spatial_resolution"]

    # No CRS: no resolution or gsd
    with _memfile(crs=None) as memfile, memfile.open() as src_dst:
        item = create_stac_item(src_dst, input_datetime=input_date, with_raster=True)
    assert "raster:spatial_resolution" not in item.to_dict()["assets"]["asset"]
    assert "gsd" not in item.properties


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
