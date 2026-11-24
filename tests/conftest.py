"""``pytest`` configuration."""

import pystac
import pytest
import rasterio

with rasterio.Env() as env:
    drivers = env.drivers()


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


@pytest.fixture(autouse=True)
def _pystac_stac_version(monkeypatch):
    """Reset pystac's process-wide STAC version around every test."""
    monkeypatch.delenv("PYSTAC_STAC_VERSION_OVERRIDE", raising=False)
    yield
    pystac.set_stac_version(None)


@pytest.fixture(params=["1.0.0", "1.1.0"])
def stac_version(request):
    """Run a test once for each STAC version rio-stac supports."""
    pystac.set_stac_version(request.param)
    return request.param
