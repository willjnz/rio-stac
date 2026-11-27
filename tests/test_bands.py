"""tests rio_stac.stac STAC 1.1 bands."""

import os

import pystac
import pytest

from rio_stac.stac import create_stac_item, get_bands_info

from .conftest import PREFIX


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
