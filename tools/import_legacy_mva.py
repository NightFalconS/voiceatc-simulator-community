#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_ROOT = ROOT.parent / "Project-Emerald-Upgrade" / "resources" / "mva"

DESTINATIONS = {
    "EHAM": Path("E/EH/EHAA/AMSTERDAM_TMA/mva.json"),
    "LEBB": Path("L/LE/LECM/LECM_R1/BILBAO_TMA/mva.json"),
    "LEBL": Path("L/LE/LECB/LECB_W/BARCELONA_TMA/mva.json"),
    "LEMD": Path("L/LE/LECM/LECM_R2/MADRID_TMA/mva.json"),
    "LEMG": Path("L/LE/LECM/LECS/MALAGA_TMA/mva.json"),
    "LEPA": Path("L/LE/LECB/LECB_E/PALMA_TMA/mva.json"),
}


def parse_coordinate_flexible(coord: str) -> float:
    coord = coord.strip()
    if not coord:
        return math.nan

    if len(coord) <= 5 and "." not in coord and coord.isalpha():
        return math.nan

    coord_sign = 1.0
    first_char = coord[0]
    if first_char in ("N", "E"):
        coord = coord[1:]
    elif first_char in ("S", "W"):
        coord_sign = -1.0
        coord = coord[1:]

    if len(coord) >= 9 and "." not in coord and coord.isdigit():
        return parse_compressed_coordinate(coord, coord_sign)

    if coord.count(".") >= 2:
        return parse_dms_coordinate(coord, coord_sign)

    try:
        return coord_sign * float(coord)
    except ValueError:
        return math.nan


def parse_compressed_coordinate(coord: str, sign: float) -> float:
    is_longitude = len(coord) >= 10
    if is_longitude:
        degrees = float(coord[0:3])
        minutes = float(coord[3:5])
        seconds = float(coord[5:7])
    else:
        degrees = float(coord[0:2])
        minutes = float(coord[2:4])
        seconds = float(coord[4:6])
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


def parse_dms_coordinate(coord: str, sign: float) -> float:
    parts = coord.split(".")
    if len(parts) < 3:
        return math.nan
    degrees = float(parts[0])
    minutes = float(parts[1])
    if len(parts) >= 4:
        seconds = float(parts[2]) + float(f"0.{parts[3]}")
    else:
        seconds = float(parts[2])
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


def parse_altitude_flexible(alt_str: str) -> int:
    alt_str = alt_str.strip()
    if not alt_str:
        return 0

    if "FL" in alt_str.upper():
        fl_part = alt_str.upper().replace("FL", "").strip()
        if "(" in fl_part:
            fl_part = fl_part.split("(", 1)[0].strip()
        if fl_part.isdigit():
            return int(fl_part) * 100

    if "(" in alt_str:
        main_value = alt_str.split("(", 1)[0].strip()
        if main_value.isdigit():
            value = int(main_value)
            return value * 100 if value < 100 else value

    if alt_str.count(".") == 1:
        left, right = alt_str.split(".", 1)
        if left.isdigit() and right.isdigit():
            left_value = int(left)
            right_value = int(right)
            if left_value >= 100 and right_value >= 100:
                return min(left_value, right_value)
            try:
                return int(float(alt_str) * 1000)
            except ValueError:
                pass

    if alt_str.isdigit():
        value = int(alt_str)
        return value * 100 if value < 100 else value

    try:
        return int(float(alt_str) * 1000)
    except ValueError:
        return 0


def normalize_point(lat: float, lon: float) -> list[float]:
    return [round(lat, 9), round(lon, 9)]


def normalize_label_area_id(area_id: str) -> str:
    normalized = area_id.strip()
    if normalized.endswith("ADD"):
        return normalized[:-3]
    return normalized


def parse_legacy_mva(path: Path) -> dict[str, object]:
    airport = path.stem.upper()
    areas: list[dict[str, object]] = []
    labels_by_area: dict[str, list[dict[str, object]]] = {}
    altitude_by_area: dict[str, int] = {}
    current_area: dict[str, object] | None = None
    current_area_id = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        elements = [part.strip() for part in line.split(";")]
        if len(elements) < 4:
            continue

        row_type = elements[0]
        area_id = elements[1]
        lat = parse_coordinate_flexible(elements[2])
        lon = parse_coordinate_flexible(elements[3])
        if math.isnan(lat) or math.isnan(lon):
            continue

        if row_type == "T":
            if area_id != current_area_id:
                if any(existing["area_id"] == area_id for existing in areas):
                    raise ValueError(f"{path}: duplicate polygon group '{area_id}'")
                current_area = {
                    "area_id": area_id,
                    "polygon": [],
                }
                areas.append(current_area)
                current_area_id = area_id
            assert current_area is not None
            current_area["polygon"].append(normalize_point(lat, lon))
            continue

        if row_type not in ("L", "LADD"):
            continue

        normalized_area_id = normalize_label_area_id(area_id)
        altitude_text = elements[4] if len(elements) > 4 else ""
        altitude_ft = parse_altitude_flexible(altitude_text)
        if altitude_ft <= 0:
            raise ValueError(f"{path}: invalid altitude '{altitude_text}' for area '{normalized_area_id}'")

        previous_altitude = altitude_by_area.get(normalized_area_id)
        if previous_altitude is not None and previous_altitude != altitude_ft:
            raise ValueError(
                f"{path}: conflicting label altitudes for '{normalized_area_id}' ({previous_altitude} vs {altitude_ft})"
            )
        altitude_by_area[normalized_area_id] = altitude_ft
        labels_by_area.setdefault(normalized_area_id, []).append(
            {
                "text": altitude_text,
                "position": normalize_point(lat, lon),
            }
        )

    if not areas:
        raise ValueError(f"{path}: no polygon areas found")

    exported_areas: list[dict[str, object]] = []
    for area in areas:
        area_id = str(area["area_id"])
        polygon = area["polygon"]
        if len(polygon) < 3:
            raise ValueError(f"{path}: area '{area_id}' has fewer than 3 polygon points")

        if area_id not in altitude_by_area:
            raise ValueError(f"{path}: area '{area_id}' is missing label altitude data")

        entry = {
            "area_id": area_id,
            "minimum_altitude_ft": altitude_by_area[area_id],
            "polygon": polygon,
        }
        labels = labels_by_area.get(area_id, [])
        if labels:
            entry["labels"] = labels
        exported_areas.append(entry)

    return {
        "schema_version": 1,
        "airport": airport,
        "mva_areas": exported_areas,
    }


def destination_airports(selected_airports: list[str] | None) -> list[str]:
    if not selected_airports:
        return sorted(DESTINATIONS.keys())
    airports = []
    for airport in selected_airports:
        normalized = airport.strip().upper()
        if normalized not in DESTINATIONS:
            raise ValueError(f"unsupported airport '{airport}'")
        airports.append(normalized)
    return sorted(set(airports))


def import_airports(source_root: Path, airports: list[str], root: Path = ROOT) -> list[Path]:
    written_paths: list[Path] = []
    for airport in airports:
        source_path = source_root / f"{airport}.MVA"
        if not source_path.exists():
            raise FileNotFoundError(f"missing legacy source file: {source_path}")

        payload = parse_legacy_mva(source_path)
        destination_path = root / DESTINATIONS[airport]
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written_paths.append(destination_path)
    return written_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert legacy Project Emerald .MVA files into community mva.json files.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT, help="Path to legacy .MVA files")
    parser.add_argument("--airport", action="append", help="Airport ICAO to import (repeatable)")
    args = parser.parse_args()

    try:
        airports = destination_airports(args.airport)
        written_paths = import_airports(args.source_root.resolve(), airports)
    except Exception as exc:
        print(str(exc))
        return 1

    for path in written_paths:
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
