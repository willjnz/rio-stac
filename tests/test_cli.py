"""tests rio_stac.cli."""

import json
import os

import pystac

from rio_stac.scripts.cli import stac

PREFIX = os.path.join(os.path.dirname(__file__), "fixtures")


def check_asset(asset, data_type, sampling):
    """Single band fields are written directly on the asset."""
    assert asset["data_type"] == data_type
    # `gray` color interpretation is not an eo common band name
    assert "description" not in asset
    assert "eo:common_name" not in asset
    assert asset["raster:scale"] == 1.0
    assert asset["raster:offset"] == 0.0
    assert asset["raster:sampling"] == sampling
    assert set(asset["statistics"]) == {
        "mean",
        "minimum",
        "maximum",
        "stddev",
        "valid_percent",
    }
    assert set(asset["raster:histogram"]) == {"count", "min", "max", "buckets"}
    assert "bands" not in asset
    assert "name" not in asset


def test_rio_stac_cli(runner):
    """Should work as expected."""
    with runner.isolated_filesystem():
        src_path = os.path.join(PREFIX, "dataset_cog.tif")
        result = runner.invoke(stac, [src_path])
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["type"] == "Feature"
        assert stac_item["assets"]["asset"]["href"] == src_path
        assert stac_item["links"] == []
        assert stac_item["stac_extensions"] == [
            "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
            "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
        ]
        assert "datetime" in stac_item["properties"]
        assert stac_item["properties"]["proj:code"] == "EPSG:32621"
        check_asset(stac_item["assets"]["asset"], "uint16", "point")

        result = runner.invoke(
            stac,
            [
                src_path,
                "--without-proj",
                "--without-raster",
                "--without-eo",
                "--datetime",
                "2010-01-01",
                "--id",
                "000001",
            ],
        )
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["stac_extensions"] == []
        assert stac_item["id"] == "000001"
        assert "datetime" in stac_item["properties"]
        assert stac_item["properties"]["datetime"] == "2010-01-01T00:00:00Z"

        result = runner.invoke(
            stac,
            [
                src_path,
                "--without-proj",
                "--without-raster",
                "--without-eo",
                "--datetime",
                "2010-01-01/2010-01-02",
            ],
        )
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["stac_extensions"] == []
        assert "datetime" in stac_item["properties"]
        assert not stac_item["properties"]["datetime"]
        assert stac_item["properties"]["start_datetime"] == "2010-01-01T00:00:00Z"
        assert stac_item["properties"]["end_datetime"] == "2010-01-02T00:00:00Z"

        result = runner.invoke(stac, [src_path, "--asset-mediatype", "COG"])
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["assets"]["asset"]["type"] == pystac.MediaType.COG

        result = runner.invoke(stac, [src_path, "--asset-mediatype", "auto"])
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["assets"]["asset"]["type"] == pystac.MediaType.GEOTIFF

        result = runner.invoke(stac, [src_path, "--property", "comment:name=something"])
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["properties"]["comment:name"] == "something"

        result = runner.invoke(stac, [src_path, "--property", "comment:something"])
        assert result.exception
        assert result.exit_code == 2

        result = runner.invoke(stac, [src_path, "-o", "item.json"])
        assert not result.exception
        assert result.exit_code == 0
        with open("item.json", "r") as f:
            stac_item = json.loads(f.read())
        assert stac_item["type"] == "Feature"
        assert stac_item["links"] == []
        assert stac_item["stac_extensions"] == [
            "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
            "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
        ]
        assert "datetime" in stac_item["properties"]
        assert stac_item["properties"]["proj:code"] == "EPSG:32621"
        check_asset(stac_item["assets"]["asset"], "uint16", "point")

        with runner.isolated_filesystem():
            src_path = os.path.join(PREFIX, "dataset_nocrs.tif")
            result = runner.invoke(stac, [src_path])
            assert not result.exception
            assert result.exit_code == 0
            stac_item = json.loads(result.output)
            assert stac_item["type"] == "Feature"
            assert stac_item["assets"]["asset"]["href"] == src_path
            assert stac_item["links"] == []
            assert stac_item["stac_extensions"] == [
                "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
                "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
            ]
            assert "datetime" in stac_item["properties"]
            assert stac_item["properties"]["proj:code"] == "EPSG:3035"
            assert "proj:projjson" not in stac_item["properties"]
            check_asset(stac_item["assets"]["asset"], "float32", "area")
            assert stac_item["assets"]["asset"]["nodata"] == -3.3999999521443642e38
