"""tests rio_stac.cli."""

import json
import os

import pystac

from rio_stac.scripts.cli import stac

PREFIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_rio_stac_cli(runner):
    """Should work as expected."""
    with runner.isolated_filesystem():
        src_path = os.path.join(PREFIX, "dataset_cog.tif")
        result = runner.invoke(stac, [src_path])
        assert not result.exception
        assert result.exit_code == 0
        stac_item = json.loads(result.output)
        assert stac_item["type"] == "Feature"
        assert stac_item["assets"]["asset"]
        assert stac_item["assets"]["asset"]["href"] == src_path
        assert stac_item["links"] == []
        assert stac_item["stac_extensions"] == [
            "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
        ]
        assert "datetime" in stac_item["properties"]
        assert "proj:epsg" in stac_item["properties"]
        assert "raster:bands" in stac_item["assets"]["asset"]
        assert "eo:bands" in stac_item["assets"]["asset"]

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
        assert stac_item["assets"]["asset"]
        assert stac_item["links"] == []
        assert stac_item["stac_extensions"] == [
            "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
        ]
        assert "datetime" in stac_item["properties"]
        assert "proj:epsg" in stac_item["properties"]
        assert "raster:bands" in stac_item["assets"]["asset"]

        with runner.isolated_filesystem():
            src_path = os.path.join(PREFIX, "dataset_nocrs.tif")
            result = runner.invoke(stac, [src_path])
            assert not result.exception
            assert result.exit_code == 0
            stac_item = json.loads(result.output)
            assert stac_item["type"] == "Feature"
            assert stac_item["assets"]["asset"]
            assert stac_item["assets"]["asset"]["href"] == src_path
            assert stac_item["links"] == []
            assert stac_item["stac_extensions"] == [
                "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
                "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
                "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
            ]
            assert "datetime" in stac_item["properties"]
            assert "proj:epsg" in stac_item["properties"]
            assert "proj:projjson" not in stac_item["properties"]
            assert "raster:bands" in stac_item["assets"]["asset"]
            assert "eo:bands" in stac_item["assets"]["asset"]


def test_rio_stac_cli_extension_versions(runner):
    """Extension version options are validated and listed in --help."""
    src_path = os.path.join(PREFIX, "dataset_cog.tif")

    result = runner.invoke(stac, ["--help"])
    assert "--projection-extension-version [v1.1.0|v2.0.0|v2.1.0]" in result.output
    assert "--raster-and-eo-extension-version [v1.1.0]" in result.output

    # The CLI writes the STAC version pystac is set to
    for version in ["1.0.0", "1.1.0"]:
        result = runner.invoke(
            stac, [src_path], env={"PYSTAC_STAC_VERSION_OVERRIDE": version}
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["stac_version"] == version

    # The option is passed through: v2.1.0 writes `proj:code`, not the default `proj:epsg`
    result = runner.invoke(stac, [src_path, "--projection-extension-version", "v2.1.0"])
    assert result.exit_code == 0
    stac_item = json.loads(result.output)
    assert (
        "https://stac-extensions.github.io/projection/v2.1.0/schema.json"
        in stac_item["stac_extensions"]
    )
    assert stac_item["properties"]["proj:code"] == "EPSG:32621"
    assert "proj:epsg" not in stac_item["properties"]

    # Error for an unknown STAC version
    result = runner.invoke(stac, [src_path, "--projection-extension-version", "v3.0.0"])
    assert result.exit_code == 2

    result = runner.invoke(
        stac, [src_path], env={"PYSTAC_STAC_VERSION_OVERRIDE": "3.0.0"}
    )
    assert result.exit_code == 2
    assert "pystac is writing STAC 3.0.0" in result.output
