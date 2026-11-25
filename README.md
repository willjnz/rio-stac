# rio-stac

<p align="center">
  <img src="https://user-images.githubusercontent.com/10407788/111794250-696da080-889c-11eb-9043-5bdc3aadb8bf.png" alt="rio-stac"></a>
</p>
<p align="center">
  <em>Create STAC Items from raster datasets.</em>
</p>
<p align="center">
  <a href="https://github.com/developmentseed/rio-stac/actions?query=workflow%3ACI" target="_blank">
      <img src="https://github.com/developmentseed/rio-stac/workflows/CI/badge.svg" alt="Test">
  </a>
  <a href="https://codecov.io/gh/developmentseed/rio-stac" target="_blank">
      <img src="https://codecov.io/gh/developmentseed/rio-stac/branch/main/graph/badge.svg" alt="Coverage">
  </a>
  <a href="https://pypi.org/project/rio-stac" target="_blank">
      <img src="https://img.shields.io/pypi/v/rio-stac?color=%2334D058&label=pypi%20package" alt="Package version">
  </a>
  <a href="https://pypistats.org/packages/rio-stac" target="_blank">
      <img src="https://img.shields.io/pypi/dm/rio-stac.svg" alt="Downloads">
  </a>
  <a href="https://github.com/developmentseed/rio-stac/blob/main/LICENSE" target="_blank">
      <img src="https://img.shields.io/github/license/developmentseed/rio-stac.svg" alt="Downloads">
  </a>
</p>

---

**Documentation**: <a href="https://developmentseed.github.io/rio-stac/" target="_blank">https://developmentseed.github.io/rio-stac/</a>

**Source Code**: <a href="https://github.com/developmentseed/rio-stac" target="_blank">https://github.com/developmentseed/rio-stac</a>

---

`rio-stac` is a simple [rasterio](https://github.com/mapbox/rasterio) plugin for creating valid STAC items from a raster dataset. The library is built on top of [pystac](https://github.com/stac-utils/pystac) to make sure we follow the STAC specification.

## Installation

```bash
$ pip install pip -U

# From Pypi
$ pip install rio-stac

# Or from source
$ pip install git+http://github.com/developmentseed/rio-stac
```

### Example

```json
// rio stac tests/fixtures/dataset_cog.tif --datetime 2026-01-01 | jq
{
  "type": "Feature",
  "stac_version": "1.1.0",
  "stac_extensions": [
    "https://stac-extensions.github.io/projection/v2.1.0/schema.json",
    "https://stac-extensions.github.io/raster/v2.0.0/schema.json"
  ],
  "id": "dataset_cog.tif",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [
          -60.72634617297825,
          72.23689137791739
        ],
        [
          -52.91627525610924,
          72.22979795551834
        ],
        [
          -52.301598718454485,
          74.61378388950398
        ],
        [
          -61.28762442711404,
          74.62204314252978
        ],
        [
          -60.72634617297825,
          72.23689137791739
        ]
      ]
    ]
  },
  "bbox": [
    -61.28762442711404,
    72.22979795551834,
    -52.301598718454485,
    74.62204314252978
  ],
  "properties": {
    "proj:code": "EPSG:32621",
    "proj:geometry": {
      "type": "Polygon",
      "coordinates": [
        [
          [
            373185.0,
            8019284.949381611
          ],
          [
            639014.9492102272,
            8019284.949381611
          ],
          [
            639014.9492102272,
            8286015.0
          ],
          [
            373185.0,
            8286015.0
          ],
          [
            373185.0,
            8019284.949381611
          ]
        ]
      ]
    },
    "proj:bbox": [
      373185.0,
      8019284.949381611,
      639014.9492102272,
      8286015.0
    ],
    "proj:shape": [
      2667,
      2658
    ],
    "proj:transform": [
      100.01126757344893,
      0.0,
      373185.0,
      0.0,
      -100.01126757344893,
      8286015.0,
      0.0,
      0.0,
      1.0
    ],
    "datetime": "2026-01-01T00:00:00Z"
  },
  "links": [],
  "assets": {
    "asset": {
      "href": "/Users/wj/Projects/rio-stac/tests/fixtures/dataset_cog.tif",
      "description": "gray",
      "data_type": "uint16",
      "raster:scale": 1.0,
      "raster:offset": 0.0,
      "raster:sampling": "point",
      "statistics": {
        "mean": 2107.524612053134,
        "minimum": 1,
        "maximum": 7872,
        "stddev": 2271.006553785732,
        "valid_percent": 9.564764936336924e-05
      },
      "raster:histogram": {
        "count": 11,
        "min": 1.0,
        "max": 7872.0,
        "buckets": [
          503460,
          0,
          0,
          161792,
          283094,
          0,
          0,
          0,
          87727,
          9431
        ]
      },
      "roles": []
    }
  }
}
```

### STAC and extension versions

rio-stac writes the STAC version that [pystac](https://github.com/stac-utils/pystac) writes: pystac 1.12 and later write STAC 1.1.0, older versions write STAC 1.0.0. To choose the version, call `pystac.set_stac_version()` or set `PYSTAC_STAC_VERSION_OVERRIDE`. Other STAC versions raise an error. rio-stac has no `stac_version` option because pystac applies its version to the whole process when an item is serialized ([`pystac.set_stac_version`](https://github.com/stac-utils/pystac/blob/924560a62579c0e84584fab198f96bdb56ad2547/core/pystac/version.py#L6)), so an option could only produce items whose `stac_version` disagrees with their fields.

The extension versions default to the version matching the STAC version, and can be chosen with `projection_extension_version` / `--projection-extension-version` and `raster_and_eo_extension_version` / `--raster-and-eo-extension-version`:

| Extension | Allowed | Default with STAC 1.0.0 | Default with STAC 1.1.0 |
| --- | --- | --- | --- |
| [projection](https://github.com/stac-extensions/projection) | `v1.1.0`, `v2.0.0`, `v2.1.0` | `v1.1.0` | `v2.1.0` |
| [raster](https://github.com/stac-extensions/raster) and [eo](https://github.com/stac-extensions/eo) | `v1.1.0`, `v2.0.0` (STAC 1.1.0 only, falls back to `v1.1.0` with a warning under STAC 1.0.0) | `v1.1.0` | `v2.0.0` |

Only released versions that rio-stac writes exactly are accepted. Choosing a version older than the default for the STAC version warns.

| Environment | `stac_version` | Projection | Band metadata |
| --- | --- | --- | --- |
| pystac >= 1.12 (default) | `1.1.0` | `"proj:code": "EPSG:32621"`, no `proj:bbox`/`proj:geometry` for WGS 84 | `bands` (shared values on the asset), or directly on the asset for a single band |
| pystac >= 1.12 with `PYSTAC_STAC_VERSION_OVERRIDE=1.0.0`, or pystac <= 1.11 | `1.0.0` | `"proj:epsg": 32621` | `raster:bands`, `eo:bands` (same as rio-stac 0.12) |

An extension is only declared when one of its fields is written. With raster/eo `v2.0.0`, the band `name` and `description` are STAC 1.1 core fields, so eo is only declared when an `eo:*` field such as `eo:cloud_cover` is written.

To get the same output as rio-stac 0.12, write STAC 1.0:

```bash
$ PYSTAC_STAC_VERSION_OVERRIDE=1.0.0 rio stac tests/fixtures/dataset_cog.tif
```

URLs passed with `--extension` / `extensions` are added as given and are not checked against these versions.

See https://developmentseed.org/rio-stac/intro/ for more.

## Contribution & Development

See [CONTRIBUTING.md](https://github.com/developmentseed/rio-stac/blob/main/CONTRIBUTING.md)

## Authors

See [contributors](https://github.com/developmentseed/rio-stac/graphs/contributors)

## Changes

See [CHANGES.md](https://github.com/developmentseed/rio-stac/blob/main/CHANGES.md).

## License

See [LICENSE](https://github.com/developmentseed/rio-stac/blob/main/LICENSE)
