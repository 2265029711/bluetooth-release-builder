#!/usr/bin/env python3
"""
先查精确版本记录，再回退到 common 通用记录。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path: Path) -> list[dict]:
    data = load_json(path)
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("records 字段必须是列表。")
    return records


def resolve_default_project_id(registry_path: Path, project_id: str | None) -> str:
    if project_id:
        return project_id

    registry = load_json(registry_path)
    default_project_id = registry.get("default_project_id")
    if not isinstance(default_project_id, str) or not default_project_id:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")
    return default_project_id


def resolve_variant_key(registry_path: Path, project_id: str, variant_key: str | None) -> str:
    if variant_key:
        return variant_key

    registry = load_json(registry_path)
    projects = registry.get("projects", [])
    for project in projects:
        if project.get("project_id") != project_id:
            continue
        preferred_variant_key = project.get("preferred_variant_key")
        if isinstance(preferred_variant_key, str) and preferred_variant_key:
            return preferred_variant_key
        break
    raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")


def match_record(record: dict, project_id: str, variant_key: str, change_item: str) -> bool:
    return (
        record.get("project_id") == project_id
        and record.get("variant_key") == variant_key
        and record.get("change_item") == change_item
    )


def find_record(records: list[dict], project_id: str, variant_key: str, change_item: str) -> tuple[str, dict] | None:
    for record in records:
        if match_record(record, project_id, variant_key, change_item):
            return "exact", record
    for record in records:
        if match_record(record, project_id, "common", change_item):
            return "fallback-common", record
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="查询版本发布修改记录。")
    parser.add_argument("--project-id", help="项目标识；不传时自动使用默认项目。")
    parser.add_argument("--variant-key", help="版本目录键，例如 DPD2603A；不传时自动使用默认版本。")
    parser.add_argument("--change-item", required=True, help="修改项，例如 default-eq。")
    parser.add_argument(
        "--records",
        default="references/change-records.json",
        help="change-records.json 的路径。",
    )
    parser.add_argument(
        "--registry",
        default="references/project-registry.json",
        help="project-registry.json 的路径。",
    )
    args = parser.parse_args()

    records_path = Path(args.records).resolve()
    registry_path = Path(args.registry).resolve()

    if not records_path.exists():
        print(f"未找到记录文件：{records_path}")
        return 1
    if not registry_path.exists():
        print(f"未找到项目注册表：{registry_path}")
        return 1

    try:
        resolved_project_id = resolve_default_project_id(registry_path, args.project_id)
        resolved_variant_key = resolve_variant_key(registry_path, resolved_project_id, args.variant_key)
        records = load_records(records_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"读取记录失败：{exc}")
        return 1

    result = find_record(records, resolved_project_id, resolved_variant_key, args.change_item)
    if result is None:
        print(
            json.dumps(
                {
                    "status": "not_found",
                    "project_id": resolved_project_id,
                    "variant_key": resolved_variant_key,
                    "change_item": args.change_item
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    match_type, record = result
    print(
        json.dumps(
            {
                "status": "ok",
                "match_type": match_type,
                "project_id": resolved_project_id,
                "variant_key": resolved_variant_key,
                "record": record,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
