"""Create STAC Item from a rasterio dataset."""

import datetime
import math
import os
import warnings
from contextlib import ExitStack
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy
import pystac
import rasterio
from pystac.extensions.eo import Band as EOBand
from pystac.utils import str_to_datetime
from rasterio import transform, warp
from rasterio.features import bounds as feature_bounds
from rasterio.io import DatasetReader, DatasetWriter, MemoryFile
from rasterio.vrt import WarpedVRT

# pystac's extensions for raster and eo v2.0.0 are not yet available
# Need https://github.com/stac-utils/pystac/pull/1829 released
# rio-stac writes the fields as plain dicts until the updated extension classes are available
PROJECTION_EXT_VERSION = "v2.1.0"
RASTER_EXT_VERSION = "v2.0.0"
EO_EXT_VERSION = "v2.0.0"

# Only these band fields deduplicate up to the asset when all bands have the same value
# Any other field (e.g. `name`, `description`, `statistics`, `raster:histogram`) describes one band and stays in `bands`
# Ref: https://github.com/radiantearth/stac-spec/blob/v1.1.0/best-practices.md#multiple-bands
_SHAREABLE = {
    "data_type",
    "nodata",
    "unit",
    "raster:scale",
    "raster:offset",
    "raster:sampling",
}

EPSG_4326 = rasterio.crs.CRS.from_epsg(4326)


def _extension_url(name: str, version: str) -> str:
    """Get a STAC extension schema URL."""
    return f"https://stac-extensions.github.io/{name}/{version}/schema.json"


# Field prefix of each extension rio-stac writes
_PREFIXES = {
    _extension_url("projection", PROJECTION_EXT_VERSION): "proj",
    _extension_url("raster", RASTER_EXT_VERSION): "raster",
    _extension_url("eo", EO_EXT_VERSION): "eo",
}


def _field_keys(objects: List[Dict]) -> Set[str]:
    """Get the field names of STAC objects (e.g. properties or asset fields) and of their `bands`."""
    return {
        key
        for fields in objects
        for band in [fields, *fields.get("bands", [])]
        for key in band
    }


def bbox_to_geom(bbox: Tuple[float, float, float, float]) -> Dict:
    """Return a geojson geometry from a bbox."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
                [bbox[0], bbox[1]],
            ]
        ],
    }


def get_dataset_geom(
    src_dst: Union[DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
    densify_pts: int = 0,
    precision: int = -1,
    geographic_crs: rasterio.crs.CRS = EPSG_4326,
) -> Dict:
    """Get Raster Footprint."""
    if densify_pts < 0:
        raise ValueError("`densify_pts` must be positive")

    if src_dst.crs is not None:
        # 1. Create Polygon from raster bounds
        geom = bbox_to_geom(src_dst.bounds)

        # 2. Densify the Polygon geometry
        if src_dst.crs != geographic_crs and densify_pts:
            # Derived from code found at
            # https://stackoverflow.com/questions/64995977/generating-equidistance-points-along-the-boundary-of-a-polygon-but-cw-ccw
            coordinates = numpy.asarray(geom["coordinates"][0])

            densified_number = len(coordinates) * densify_pts
            existing_indices = numpy.arange(0, densified_number, densify_pts)
            interp_indices = numpy.arange(existing_indices[-1] + 1)
            interp_x = numpy.interp(interp_indices, existing_indices, coordinates[:, 0])
            interp_y = numpy.interp(interp_indices, existing_indices, coordinates[:, 1])
            geom = {
                "type": "Polygon",
                "coordinates": [[(x, y) for x, y in zip(interp_x, interp_y)]],
            }

        # 3. Reproject the geometry to "epsg:4326"
        geom = warp.transform_geom(src_dst.crs, geographic_crs, geom, precision=precision)
        bbox = feature_bounds(geom)

    else:
        warnings.warn(
            "Input file doesn't have CRS information, setting geometry and bbox to (-180,-90,180,90)."
        )
        bbox = (-180.0, -90.0, 180.0, 90.0)
        geom = bbox_to_geom(bbox)

    return {"bbox": list(bbox), "footprint": geom}


def get_projection_info(
    src_dst: Union[DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
) -> Dict:
    """Get projection metadata.

    The STAC projection extension allows for three different ways to describe the coordinate reference system
    associated with a raster :
    - code (`"EPSG:<code>"`, or None when there is no EPSG code)
    - WKT2
    - PROJJSON

    The EPSG code is used if available, otherwise WKT2, or PROJJSON if WKT2 fails.

    `bbox` and `geometry` are omitted when the CRS is WGS84 as per v2.1.0.

    see: https://github.com/stac-extensions/projection

    """

    epsg = None
    if src_dst.crs is not None:
        # EPSG
        epsg = src_dst.crs.to_epsg() if src_dst.crs.is_epsg_code else None

    meta = {
        "code": f"EPSG:{epsg}" if epsg else None,
        "geometry": bbox_to_geom(src_dst.bounds),
        "bbox": list(src_dst.bounds),
        "shape": [src_dst.height, src_dst.width],
        "transform": list(src_dst.transform),
    }

    if src_dst.crs == EPSG_4326:
        del meta["bbox"], meta["geometry"]

    if not epsg and src_dst.crs:
        # WKT2
        try:
            meta["wkt2"] = src_dst.crs.to_wkt()
        except Exception as ex:
            warnings.warn(f"Could not get WKT2 from dataset : {ex}")
            # PROJJSON
            try:
                meta["projjson"] = src_dst.crs.to_dict(projjson=True)
            except (AttributeError, TypeError) as ex:
                warnings.warn(f"Could not get PROJJSON from dataset : {ex}")

    return meta


def get_band_names(
    src_dst: Union[DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
) -> List[Dict]:
    """Get the `name`, `description` and `eo:common_name` of each band.

    `name` is the band index (e.g. `b1`), `description` the band description, and `eo:common_name` the
    color interpretation when it is an eo common band name (e.g. `red`).

    see:
    - https://github.com/radiantearth/stac-spec/blob/v1.1.0/commons/common-metadata.md#bands
    - https://github.com/stac-extensions/eo/tree/v2.0.0#common-band-names

    """
    bands = []
    for i, description, color in zip(
        src_dst.indexes, src_dst.descriptions, src_dst.colorinterp
    ):
        band = {"name": f"b{i}"}
        if description:
            band["description"] = description

        # GDAL color interpretations: https://gdal.org/en/stable/user/raster_data_model.html#raster-band
        # pystac's eo:common_name list is v1.1.0 until https://github.com/stac-utils/pystac/pull/1829 upgrades it
        # v2.0.0's adds `green05` and `rededge071/075/078`, none of which are written by GDAL
        # GDAL's `yellow` is the CMYK print color, not the eo `yellow` band.
        if color.name != "yellow" and EOBand.band_range(color.name):
            band["eo:common_name"] = color.name

        bands.append(band)

    return bands


# The band dicts match `pystac.Band.to_dict()` from https://github.com/stac-utils/pystac/pull/1829
# Once that is released we can migrate to `pystac.Band.from_dict(band)` and `pystac.Asset(bands=...)` for typed objects
def merge_band_fields(raster_bands: List[Dict], band_names: List[Dict]) -> Dict:
    """Get the STAC v1.1.0 `bands` asset field from `get_raster_info` and `get_band_names` output.

    raster and eo v2.0.0 write band metadata in the STAC 1.1 core `bands` array.

    Following the STAC best practices, values shared by all bands are written on the asset, and a single
    band is written directly on the asset (without `name`).

    see:
    - https://github.com/radiantearth/stac-spec/blob/v1.1.0/commons/common-metadata.md#bands
    - https://github.com/radiantearth/stac-spec/blob/v1.1.0/best-practices.md#bands

    """
    # `with_raster` and `with_eo` are both off
    if not raster_bands and not band_names:
        return {}

    # One list is empty when `with_raster` or `with_eo` is off
    count = max(len(raster_bands), len(band_names))
    bands = [
        {
            "name": f"b{i + 1}",
            **(band_names[i] if band_names else {}),
            **(raster_bands[i] if raster_bands else {}),
        }
        for i in range(count)
    ]

    # A single band goes on the asset without `name`
    if len(bands) == 1:
        bands[0].pop("name")
        return bands[0]

    # Fields with the same value in every band are written once on the asset
    shared = {
        key: value
        for key, value in bands[0].items()
        if key in _SHAREABLE and all(band.get(key) == value for band in bands)
    }
    bands = [{k: v for k, v in band.items() if k not in shared} for band in bands]

    # Shared fields are included at the top level, remaining band-specific fields go under "bands"
    return {**shared, "bands": bands}


def _get_stats(
    arr: numpy.ma.MaskedArray,
    bins: Union[int, str, Sequence] = 10,
    range: Optional[Tuple[float, float]] = None,
) -> Dict:
    """Calculate array statistics."""
    # Avoid non masked nan/inf values
    arr = numpy.ma.fix_invalid(arr, copy=True)

    stats = {
        "statistics": {
            "mean": arr.mean().item(),
            "minimum": arr.min().item(),
            "maximum": arr.max().item(),
            "stddev": arr.std().item(),
            "valid_percent": float(
                numpy.count_nonzero(~arr.mask) / float(arr.data.size) * 100
            ),
        }
    }

    try:
        sample, edges = numpy.histogram(arr[~arr.mask], bins=bins, range=range)

    except ValueError as e:
        if "Too many bins for data range." in str(e):
            _, counts = numpy.unique(arr[~arr.mask], return_counts=True)
            warnings.warn(
                f"Could not calculate the histogram, fall back to automatic bin={len(counts) + 1}.",
                UserWarning,
            )
            sample, edges = numpy.histogram(arr[~arr.mask], bins=len(counts) + 1)
        else:
            raise e

    stats["raster:histogram"] = {
        "count": len(edges),
        "min": float(edges.min()),
        "max": float(edges.max()),
        "buckets": sample.tolist(),
    }

    return stats


def get_raster_info(
    src_dst: Union[DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
    max_size: int = 1024,
    histogram_bins: Union[int, str, Sequence] = 10,
    histogram_range: Optional[Tuple[float, float]] = None,
) -> List[Dict]:
    """Get raster band metadata (STAC 1.1 core and raster v2.0.0 fields).

    `data_type`, `nodata`, `unit` and `statistics` are STAC 1.1 core fields; the other fields get the
    `raster:` prefix.

    see: https://github.com/stac-extensions/raster/tree/v2.0.0

    """
    height = src_dst.height
    width = src_dst.width
    if max_size and max(width, height) > max_size:
        ratio = height / width
        if ratio > 1:
            height = max_size
            width = math.ceil(height / ratio)
        else:
            height = math.ceil(max_size * ratio)
            width = max_size

    meta: List[Dict] = []

    area_or_point = src_dst.tags().get("AREA_OR_POINT", "").lower()

    # Missing `bits_per_sample` and `spatial_resolution`
    for band in src_dst.indexes:
        value = {
            "data_type": src_dst.dtypes[band - 1],
            "raster:scale": src_dst.scales[band - 1],
            "raster:offset": src_dst.offsets[band - 1],
        }
        if area_or_point:
            value["raster:sampling"] = area_or_point

        # If the Nodata is not set we don't forward it. JSON has no nan/inf, so they are "nan", "inf" and "-inf".
        if src_dst.nodata is not None:
            nodata = src_dst.nodata
            value["nodata"] = nodata if math.isfinite(nodata) else str(nodata)

        if src_dst.units[band - 1] is not None:
            value["unit"] = src_dst.units[band - 1]

        value.update(
            _get_stats(
                src_dst.read(indexes=band, out_shape=(height, width), masked=True),
                bins=histogram_bins,
                range=histogram_range,
            )
        )
        meta.append(value)

    return meta


def _get_band_extensions(objects: List[Dict]) -> List[str]:
    """Get the raster and eo extension URLs for the `raster:*` and `eo:*` fields in assets or properties.

    To be valid, an extension is declared only when one of its fields is written.

    """
    keys = _field_keys(objects)
    if keys & {"raster:bands", "eo:bands"}:
        warnings.warn(
            "`raster:bands` and `eo:bands` are replaced by `bands` in STAC 1.1 (raster and eo v2.0.0)."
        )

    return [
        _extension_url(name, version)
        for name, version in [("raster", RASTER_EXT_VERSION), ("eo", EO_EXT_VERSION)]
        if any(key.startswith(f"{name}:") for key in keys)
    ]


def get_media_type(
    src_dst: Union[DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
) -> Optional[pystac.MediaType]:
    """Find MediaType for a raster dataset."""
    driver = src_dst.driver

    if driver == "GTiff":
        if src_dst.crs:
            return pystac.MediaType.GEOTIFF
        else:
            return pystac.MediaType.TIFF

    elif driver in [
        "JP2ECW",
        "JP2KAK",
        "JP2LURA",
        "JP2MrSID",
        "JP2OpenJPEG",
        "JPEG2000",
    ]:
        return pystac.MediaType.JPEG2000

    elif driver in ["HDF4", "HDF4Image"]:
        return pystac.MediaType.HDF

    elif driver in ["HDF5", "HDF5Image"]:
        return pystac.MediaType.HDF5

    elif driver == "JPEG":
        return pystac.MediaType.JPEG

    elif driver == "PNG":
        return pystac.MediaType.PNG

    warnings.warn("Could not determine the media type from GDAL driver.", UserWarning)
    return None


def create_stac_item(
    source: Union[str, DatasetReader, DatasetWriter, WarpedVRT, MemoryFile],
    input_datetime: Optional[datetime.datetime] = None,
    extensions: Optional[List[str]] = None,
    collection: Optional[str] = None,
    collection_url: Optional[str] = None,
    properties: Optional[Dict] = None,
    id: Optional[str] = None,
    assets: Optional[Dict[str, pystac.Asset]] = None,
    asset_name: str = "asset",
    asset_roles: Optional[List[str]] = None,
    asset_media_type: Optional[Union[str, pystac.MediaType]] = "auto",
    asset_href: Optional[str] = None,
    with_proj: bool = False,
    with_raster: bool = False,
    with_eo: bool = False,
    raster_max_size: int = 1024,
    geom_densify_pts: int = 0,
    geom_precision: int = -1,
    geographic_crs: rasterio.crs.CRS = EPSG_4326,
    histogram_bins: Union[int, str, Sequence] = 10,
    histogram_range: Optional[Tuple[float, float]] = None,
) -> pystac.Item:
    """Create a Stac Item.

    Args:
        source (str or opened rasterio dataset): input path or rasterio dataset.
        input_datetime (datetime.datetime, optional): datetime associated with the item.
        extensions (list of str): input list of extensions to use in the item.
        collection (str, optional): name of collection the item belongs to.
        collection_url (str, optional): Link to the STAC Collection.
        properties (dict, optional): additional properties to add in the item.
        id (str, optional): id to assign to the item (default to the source basename).
        assets (dict, optional): Assets to set in the item. If set we won't create one from the source.
        asset_name (str, optional): asset name in the Assets object.
        asset_roles (list of str, optional): list of str | list of asset's roles.
        asset_media_type (str or pystac.MediaType, optional): asset's media type.
        asset_href (str, optional): asset's URI (default to input path).
        with_proj (bool): Add the `projection` extension and properties (default to False).
        with_raster (bool): Add the `raster` extension and properties (default to False).
        with_eo (bool): Add the `eo` extension and properties (default to False).
        raster_max_size (int): Limit array size from which to get the raster statistics. Defaults to 1024.
        geom_densify_pts (int): Number of points to add to each edge to account for nonlinear edges transformation (Note: GDAL uses 21).
        geom_precision (int): If >= 0, geometry coordinates will be rounded to this number of decimal.

    Returns:
        pystac.Item: valid STAC Item.

    """
    properties = properties or {}
    extensions = list(extensions or [])
    asset_roles = asset_roles or []

    with ExitStack() as ctx:
        if isinstance(source, (DatasetReader, DatasetWriter, WarpedVRT)):
            dataset = source
        else:
            dataset = ctx.enter_context(rasterio.open(source))

        if dataset.gcps[0]:
            src_dst = ctx.enter_context(
                WarpedVRT(
                    dataset,
                    src_crs=dataset.gcps[1],
                    src_transform=transform.from_gcps(dataset.gcps[0]),
                )
            )
        else:
            src_dst = dataset

        dataset_geom = get_dataset_geom(
            src_dst,
            densify_pts=geom_densify_pts,
            precision=geom_precision,
            geographic_crs=geographic_crs,
        )

        media_type = (
            get_media_type(dataset) if asset_media_type == "auto" else asset_media_type
        )

        if "start_datetime" not in properties and "end_datetime" not in properties:
            # Try to get datetime from https://gdal.org/user/raster_data_model.html#imagery-domain-remote-sensing
            acq_date = src_dst.get_tag_item("ACQUISITIONDATETIME", "IMAGERY")
            tiff_date = src_dst.get_tag_item("TIFFTAG_DATETIME")
            dst_date = acq_date or tiff_date
            try:
                dst_datetime = str_to_datetime(dst_date) if dst_date else None
            except ValueError as err:
                warnings.warn(f"Could not get parse date: {dst_date}: {err}")
                dst_datetime = None

            input_datetime = (
                input_datetime
                or dst_datetime
                or datetime.datetime.now(datetime.timezone.utc)
            )

        # add projection properties
        if with_proj:
            extensions.append(_extension_url("projection", PROJECTION_EXT_VERSION))

            properties.update(
                {
                    f"proj:{name}": value
                    for name, value in get_projection_info(src_dst).items()
                }
            )

        if with_eo:
            cloudcover = src_dst.get_tag_item("CLOUDCOVER", "IMAGERY")
            if cloudcover is not None:
                properties.update({"eo:cloud_cover": int(cloudcover)})

        # Band fields are only written on the asset rio-stac creates. User input parameter `assets` are written as-is.
        band_fields = {}
        if not assets:
            band_fields = merge_band_fields(
                get_raster_info(
                    dataset,
                    max_size=raster_max_size,
                    histogram_bins=histogram_bins,
                    histogram_range=histogram_range,
                )
                if with_raster
                else [],
                get_band_names(src_dst) if with_eo else [],
            )
        asset_fields = (
            [asset.extra_fields for asset in assets.values()] if assets else [band_fields]
        )
        extensions += _get_band_extensions([*asset_fields, properties if with_eo else {}])

    # item
    item = pystac.Item(
        id=id or os.path.basename(dataset.name),
        geometry=dataset_geom["footprint"],
        bbox=dataset_geom["bbox"],
        collection=collection,
        stac_extensions=list(dict.fromkeys(extensions)),  # unique, in order
        datetime=input_datetime,
        properties=properties,
    )

    # if we add a collection we MUST add a link
    if collection:
        # TODO: Error if collection but no collection_url?
        item.add_link(
            pystac.Link(
                pystac.RelType.COLLECTION,
                collection_url or collection,
                media_type=pystac.MediaType.JSON,
            )
        )

    # item.assets
    if assets:
        for key, asset in assets.items():
            item.add_asset(key=key, asset=asset)

    else:
        item.add_asset(
            key=asset_name,
            asset=pystac.Asset(
                href=asset_href or dataset.name,
                media_type=media_type,
                # TODO: pystac will (hopefully soon) release Asset.bands
                extra_fields=band_fields,
                roles=asset_roles,
            ),
        )

    return item
