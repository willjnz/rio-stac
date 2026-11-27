"""``pytest`` configuration."""

import datetime
import os

import numpy
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

with rasterio.Env() as env:
    drivers = env.drivers()


PREFIX = os.path.join(os.path.dirname(__file__), "fixtures")


input_date = datetime.datetime.now(datetime.timezone.utc)


def _memfile(
    nbits=None,
    crs="EPSG:32621",
    transform=from_origin(373185, 8286015, 10, 20),
    **imagery,
):
    """A 2 band uint16 GeoTIFF in memory, with optional NBITS and IMAGERY tags."""
    memfile = MemoryFile()
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "count": 2,
        "width": 4,
        "height": 4,
        "crs": crs,
        "transform": transform,
    }
    if nbits:
        profile["nbits"] = nbits
    with memfile.open(**profile) as dst:
        dst.write(numpy.arange(32, dtype="uint16").reshape(2, 4, 4))
        if imagery:
            dst.update_tags(ns="IMAGERY", **imagery)
    return memfile


requires_hdf5 = pytest.mark.skipif(
    "HDF5" not in drivers.keys(), reason="Only relevant if HDF5 drivers is supported"
)
requires_hdf4 = pytest.mark.skipif(
    "HDF4" not in drivers.keys(), reason="Only relevant if HDF4 drivers is supported"
)


@pytest.fixture
def runner():
    """CLI Runner fixture."""
    from click.testing import CliRunner

    return CliRunner()
