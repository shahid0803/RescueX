from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodlens.raster import (
    align_before_after,
    clip_to_aoi,
    inspect_raster,
    qc_report,
    validate_raster_metadata,
    write_preview,
    choose_analysis_crs,
)
from floodlens.satellite.preprocessing import (
    PreprocessingConfig,
    sentinel1_metadata,
    sentinel2_cloud_mask,
    sentinel2_scale_reflectance,
)


def write_fixture(path: Path, values: np.ndarray, transform=None, crs="EPSG:32645", nodata=-9999):
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[1], width=values.shape[2],
        count=values.shape[0], dtype=values.dtype, crs=crs,
        transform=transform or from_origin(500000, 1000, 10, 10), nodata=nodata,
    ) as dataset:
        dataset.write(values)
        for index in range(values.shape[0]):
            dataset.set_band_description(index + 1, f"band_{index + 1}")


def test_metadata_and_qc_are_calculated(tmp_path):
    source = tmp_path / "source.tif"
    values = np.array([[[1, 2], [3, -9999]]], dtype="float32")
    write_fixture(source, values)
    metadata = inspect_raster(source)
    assert validate_raster_metadata(metadata)["valid"] is True
    report = qc_report(source, "fixture", "sentinel-1")
    assert report.nodata_fraction == pytest.approx(0.25)
    assert report.valid_pixel_fraction == pytest.approx(0.75)


def test_clip_preserves_georeferencing(tmp_path):
    source = tmp_path / "source.tif"
    clipped = tmp_path / "clipped.tif"
    write_fixture(source, np.ones((1, 10, 10), dtype="float32"))
    clip_to_aoi(
        source, clipped,
        {"type": "Polygon", "coordinates": [[[500020, 900], [500060, 900], [500060, 940], [500020, 940], [500020, 900]]]},
    )
    metadata = inspect_raster(clipped)
    assert metadata.crs == "EPSG:32645"
    assert metadata.width == 4 and metadata.height == 4
    assert metadata.bounds[0] == pytest.approx(500020)


def test_alignment_reprojects_and_uses_common_grid(tmp_path):
    before = tmp_path / "before.tif"
    after = tmp_path / "after.tif"
    before_out = tmp_path / "aligned_before.tif"
    after_out = tmp_path / "aligned_after.tif"
    write_fixture(before, np.ones((1, 5, 5), dtype="float32"))
    write_fixture(after, np.ones((1, 10, 10), dtype="float32"), from_origin(500000, 1000, 5, 5))
    result = align_before_after(before, after, before_out, after_out, "EPSG:32645", 10)
    assert result["same_crs"] is True
    assert result["same_transform"] is True
    assert inspect_raster(before_out).crs == "EPSG:32645"


def test_no_overlap_fails_explicitly(tmp_path):
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    write_fixture(first, np.ones((1, 2, 2), dtype="float32"))
    write_fixture(second, np.ones((1, 2, 2), dtype="float32"), from_origin(600000, 1000, 10, 10))
    with pytest.raises(ValueError, match="no spatial overlap"):
        align_before_after(first, second, tmp_path / "a.tif", tmp_path / "b.tif")


def test_sentinel2_mask_scaling_and_preview(tmp_path):
    assert sentinel2_cloud_mask(np.array([[3, 4, 9]])).tolist() == [[True, False, True]]
    assert sentinel2_scale_reflectance(np.array([[10000]], dtype="uint16"))[0, 0] == 1
    source = tmp_path / "source.tif"
    preview = tmp_path / "preview.png"
    write_fixture(source, np.arange(25, dtype="float32").reshape(1, 5, 5))
    write_preview(source, preview)
    assert preview.exists()
    assert sentinel1_metadata(PreprocessingConfig())["terrain_correction"] is False
    assert choose_analysis_crs(
        {"type": "Polygon", "coordinates": [[[85, 27], [85.1, 27], [85.1, 27.1], [85, 27.1], [85, 27]]]}
    ) == "EPSG:32645"
