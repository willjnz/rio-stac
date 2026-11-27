"""tests rio_stac.stac eo extension."""

import os

import rasterio

from rio_stac.stac import create_stac_item

from .conftest import PREFIX, _memfile, input_date


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
    # eo:common_name from the RGB colorinterp
    assert item_dict["assets"]["asset"]["bands"] == [
        {"name": "b1", "description": "red", "eo:common_name": "red"},
        {"name": "b2", "description": "green", "eo:common_name": "green"},
        {"name": "b3", "description": "blue", "eo:common_name": "blue"},
    ]


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
