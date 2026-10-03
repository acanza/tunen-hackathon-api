"""SoilGrids WCS adapter for the bounded M1 clay integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import io
import json
import math
from typing import Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as element_tree

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import bounds, geometry_mask
from rasterio.warp import transform_geom

from soil_api.domain import LayerRequest


SOILGRIDS_WCS_URL = "https://maps.isric.org/mapserv"
SOILGRIDS_FILES_URL = "https://files.isric.org/soilgrids/latest/data/clay"
SOURCE_CRS = "+proj=igh +datum=WGS84 +units=m +no_defs"
WCS_CRS = "http://www.opengis.net/def/crs/EPSG/0/152160"
DEPTH_COVERAGES = (
    ("clay_0-5cm_mean", 5),
    ("clay_5-15cm_mean", 10),
    ("clay_15-30cm_mean", 15),
)
SOURCE_NODATA = -32768.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
XML_NAMESPACES = {
    "wcs": "http://www.opengis.net/wcs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
}


class SoilGridsProviderError(RuntimeError):
    """A bounded provider request failed."""


class SoilGridsProviderTimeout(SoilGridsProviderError):
    """A provider request exceeded its configured timeout."""


@dataclass(frozen=True)
class SoilGridsRaster:
    """One native SoilGrids depth raster with its source metadata."""

    coverage_id: str
    values: np.ma.MaskedArray
    transform: rasterio.Affine
    crs: CRS
    nodata: float
    metadata: Mapping[str, str]


FetchBytes = Callable[[str, float, int], bytes]


def _default_fetch_bytes(url: str, timeout_seconds: float, max_bytes: int) -> bytes:
    request = Request(url, headers={"Accept": "application/octet-stream"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(max_bytes + 1)
    except TimeoutError as error:
        raise SoilGridsProviderTimeout(f"SoilGrids request timed out: {url}") from error
    except OSError as error:
        raise SoilGridsProviderError(f"SoilGrids request failed: {url}") from error
    if len(payload) > max_bytes:
        raise SoilGridsProviderError("SoilGrids response exceeds the 8 MiB budget")
    return payload


def _request_url(parameters: list[tuple[str, str]]) -> str:
    return SOILGRIDS_WCS_URL + "?" + urlencode(
        [("map", "/map/clay.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"), *parameters]
    )


def _parse_vrt(payload: bytes) -> tuple[CRS, float, dict[str, str]]:
    root = element_tree.fromstring(gzip.decompress(payload) if payload[:2] == b"\x1f\x8b" else payload)
    crs = CRS.from_wkt(root.findtext("SRS") or "")
    nodata = float(root.findtext("VRTRasterBand/NoDataValue") or SOURCE_NODATA)
    metadata = {
        node.attrib["key"]: node.text or ""
        for node in root.findall("Metadata/MDI")
        if "key" in node.attrib
    }
    return crs, nodata, metadata


class SoilGridsAdapter:
    """Retrieve and normalize SoilGrids clay depth rasters for one field."""

    def __init__(
        self,
        *,
        fetch_bytes: FetchBytes | None = None,
        timeout_seconds: float = 45.0,
        retry_attempts: int = 2,
    ) -> None:
        self._fetch_bytes = fetch_bytes or _default_fetch_bytes
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts

    def _fetch(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts + 1):
            try:
                return self._fetch_bytes(url, self._timeout_seconds, MAX_RESPONSE_BYTES)
            except SoilGridsProviderTimeout:
                raise
            except SoilGridsProviderError as error:
                last_error = error
                if attempt == self._retry_attempts:
                    break
        raise SoilGridsProviderError(str(last_error)) from last_error

    def retrieve(self, request: LayerRequest) -> tuple[list[SoilGridsRaster], dict[str, object]]:
        feature_geometry = transform_geom(
            "EPSG:4326", SOURCE_CRS, request.fields.features[0].geometry.model_dump()
        )
        capabilities_url = _request_url([("REQUEST", "GetCapabilities")])
        capabilities = element_tree.fromstring(self._fetch(capabilities_url))
        available = {
            node.text
            for node in capabilities.findall(".//wcs:CoverageId", XML_NAMESPACES)
        }
        coverage_ids = [coverage_id for coverage_id, _ in DEPTH_COVERAGES]
        if not set(coverage_ids).issubset(available):
            raise SoilGridsProviderError("SoilGrids does not advertise all clay depth coverages")

        description_url = _request_url(
            [("REQUEST", "DescribeCoverage"), ("COVERAGEID", ",".join(coverage_ids))]
        )
        description = element_tree.fromstring(self._fetch(description_url))
        origins = []
        for coverage_id in coverage_ids:
            coverage = next(
                node
                for node in description.findall("wcs:CoverageDescription", XML_NAMESPACES)
                if node.findtext("wcs:CoverageId", namespaces=XML_NAMESPACES) == coverage_id
            )
            grid = coverage.find("gml:domainSet/gml:RectifiedGrid", XML_NAMESPACES)
            origin = tuple(
                map(float, (grid.findtext("gml:origin/gml:Point/gml:pos", namespaces=XML_NAMESPACES) or "").split())
            )
            offsets = [
                tuple(map(float, node.text.split()))
                for node in grid.findall("gml:offsetVector", XML_NAMESPACES)
            ]
            if offsets != [(250.0, 0.0), (0.0, -250.0)]:
                raise SoilGridsProviderError("Unexpected SoilGrids grid orientation")
            origins.append(origin)
        if len(set(origins)) != 1:
            raise SoilGridsProviderError("SoilGrids depth grids are not aligned")

        west, south, east, north = bounds(feature_geometry)
        origin_x, origin_y = origins[0]
        edge_x, edge_y = origin_x - 125, origin_y - 125
        left = edge_x + math.floor((west - edge_x) / 250) * 250
        right = edge_x + math.ceil((east - edge_x) / 250) * 250
        bottom = edge_y + math.floor((south - edge_y) / 250) * 250
        top = edge_y + math.ceil((north - edge_y) / 250) * 250
        width, height = int((right - left) / 250), int((top - bottom) / 250)
        if width * height > 4096:
            raise SoilGridsProviderError("SoilGrids request exceeds the pixel budget")

        rasters: list[SoilGridsRaster] = []
        for coverage_id, _ in DEPTH_COVERAGES:
            vrt_url = f"{SOILGRIDS_FILES_URL}/{coverage_id}.vrt"
            source_crs, source_nodata, metadata = _parse_vrt(self._fetch(vrt_url))
            if source_nodata != SOURCE_NODATA:
                raise SoilGridsProviderError("Unexpected SoilGrids nodata convention")
            tiff_url = _request_url(
                [
                    ("REQUEST", "GetCoverage"),
                    ("COVERAGEID", coverage_id),
                    ("FORMAT", "image/tiff"),
                    ("SUBSETTINGCRS", WCS_CRS),
                    ("OUTPUTCRS", WCS_CRS),
                    ("SUBSET", f"X({left},{right})"),
                    ("SUBSET", f"Y({bottom},{top})"),
                ]
            )
            with rasterio.MemoryFile(self._fetch(tiff_url)) as memory_file:
                with memory_file.open() as dataset:
                    if dataset.count != 1 or dataset.width * dataset.height > 4096:
                        raise SoilGridsProviderError("Unexpected SoilGrids raster dimensions")
                    values = dataset.read(1, masked=True).astype(float)
                    if dataset.nodata is not None and dataset.nodata != source_nodata:
                        raise SoilGridsProviderError("Conflicting SoilGrids nodata metadata")
                    if dataset.res != (250, 250) or tuple(dataset.bounds) != (
                        left,
                        bottom,
                        right,
                        top,
                    ):
                        raise SoilGridsProviderError("Unexpected SoilGrids raster georeferencing")
                    outside = geometry_mask(
                        [feature_geometry], dataset.shape, dataset.transform, all_touched=False
                    )
                    values.mask = np.ma.getmaskarray(values) | outside | (values.data == source_nodata)
                    rasters.append(
                        SoilGridsRaster(
                            coverage_id=coverage_id,
                            values=values,
                            transform=dataset.transform,
                            crs=source_crs,
                            nodata=source_nodata,
                            metadata=metadata,
                        )
                    )
        return rasters, {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "dataset_version": "SoilGrids250m 2.0 / RUN10",
            "dataset_date": None,
            "source_url": SOILGRIDS_WCS_URL,
            "source_crs": SOURCE_CRS,
            "source_resolution_meters": 250,
            "original_unit": "g/kg",
            "attribution": "ISRIC — World Soil Information",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "depth_intervals_cm": [[0, 5], [5, 15], [15, 30]],
            "metadata": [dict(raster.metadata) for raster in rasters],
        }
