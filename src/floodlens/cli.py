from __future__ import annotations

import argparse
import json
from pathlib import Path

from .satellite.models import AOI, SatelliteSearchRequest
from .satellite.service import SatelliteService
from .satellite.stac import CDSEStacProvider
from .raster import inspect_raster, qc_report, write_preview
from .ml.data import dataset_manifest, write_manifest
from .ml.inference import infer_geotiff
from .connectivity import BlockedRoadSet, ConnectivityConfig, analyze_connectivity
from .models import Point, Road


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rescuex", description="RescueX satellite acquisition tools")
    commands = parser.add_subparsers(dest="command", required=True)
    satellite = commands.add_parser("satellite", help="discover and inspect satellite scenes")
    satellite_commands = satellite.add_subparsers(dest="satellite_command", required=True)
    search = satellite_commands.add_parser("search", help="search CDSE STAC and select a pair")
    search.add_argument("--aoi", required=True, type=Path, help="GeoJSON geometry file")
    search.add_argument("--date", required=True, help="event date, YYYY-MM-DD")
    search.add_argument("--sensor", choices=("sentinel-1", "sentinel-2"), required=True)
    search.add_argument("--before-days", type=int, default=30)
    search.add_argument("--after-days", type=int, default=30)
    search.add_argument("--max-cloud-percentage", type=float)
    raster = commands.add_parser("raster", help="inspect and quality-check georeferenced rasters")
    raster_commands = raster.add_subparsers(dest="raster_command", required=True)
    inspect = raster_commands.add_parser("inspect", help="inspect raster metadata")
    inspect.add_argument("--input", required=True, type=Path)
    qc = raster_commands.add_parser("qc", help="write raster QC JSON")
    qc.add_argument("--input", required=True, type=Path)
    qc.add_argument("--preview", type=Path)
    dataset = commands.add_parser("dataset", help="prepare dataset metadata")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_inspect = dataset_commands.add_parser("inspect", help="write a dataset manifest without downloading")
    dataset_inspect.add_argument("--dataset", choices=("kuro-siwo", "sen1floods11"), required=True)
    dataset_inspect.add_argument("--root", default="data/raw/datasets")
    model = commands.add_parser("model", help="run trained model inference")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    infer = model_commands.add_parser("infer", help="write georeferenced probability and binary masks")
    infer.add_argument("--input", required=True, type=Path)
    infer.add_argument("--checkpoint", required=True, type=Path)
    infer.add_argument("--probability-output", required=True, type=Path)
    infer.add_argument("--mask-output", required=True, type=Path)
    infer.add_argument("--threshold", type=float, default=0.5)
    connectivity = commands.add_parser("connectivity", help="analyze road-network access")
    connectivity_commands = connectivity.add_subparsers(dest="connectivity_command", required=True)
    analyze = connectivity_commands.add_parser("analyze", help="run before/after connectivity analysis")
    analyze.add_argument("--input", required=True, type=Path, help="JSON connectivity input")
    analyze.add_argument("--output", type=Path, help="optional JSON result path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "satellite" and args.satellite_command == "search":
        geometry = json.loads(args.aoi.read_text(encoding="utf-8"))
        request = SatelliteSearchRequest(
            aoi=AOI(geometry=geometry),
            event_date=args.date,
            sensor=args.sensor,
            search_window_before_days=args.before_days,
            search_window_after_days=args.after_days,
            max_cloud_percentage=args.max_cloud_percentage,
        )
        result = SatelliteService(CDSEStacProvider()).search(request)
        print(result.model_dump_json(indent=2))
        return 0
    if args.command == "raster" and args.raster_command == "inspect":
        print(json.dumps(inspect_raster(args.input).__dict__, indent=2, default=str))
        return 0
    if args.command == "raster" and args.raster_command == "qc":
        report = qc_report(args.input)
        print(json.dumps(report.__dict__, indent=2, default=str))
        if args.preview:
            write_preview(args.input, args.preview)
        return 0
    if args.command == "dataset" and args.dataset_command == "inspect":
        path = Path(args.root) / args.dataset.replace("-", "_")
        manifest = dataset_manifest(args.dataset, str(path), enabled=False)
        write_manifest(Path("data/manifests") / f"{args.dataset}.json", manifest)
        print(manifest)
        return 0
    if args.command == "model" and args.model_command == "infer":
        print(infer_geotiff(
            args.input, args.checkpoint, args.probability_output, args.mask_output, args.threshold
        ))
        return 0
    if args.command == "connectivity" and args.connectivity_command == "analyze":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = analyze_connectivity(
            [Road.model_validate(item) for item in payload["roads"]],
            [Point.model_validate(item) for item in payload.get("settlements", [])],
            [Point.model_validate(item) for item in payload.get("towns", [])],
            [Point.model_validate(item) for item in payload.get("hospitals", [])],
            BlockedRoadSet.model_validate(payload.get("blocked", {})),
            ConnectivityConfig.model_validate(payload["config"]),
            phase4_source=payload.get("phase4_source", "fixture"),
        )
        serialized = result.model_dump_json(indent=2)
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
        print(serialized)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
