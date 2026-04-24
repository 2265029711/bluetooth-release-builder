#!/usr/bin/env python3
"""
功能:
    按项目、版本和修改项查找结构化修改记录。

说明:
    查找顺序固定为:
    1. 精确命中 `(project_id, variant_key, change_item)`
    2. 通用回退 `(project_id, common, change_item)`

    脚本输出一个小型 JSON 结果，供 skill 判断是否可以直接修改，
    还是需要继续搜索源码并向用户确认位置。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Tuple


def load_json(path: Path) -> dict:
    """读取 JSON 文件。

    参数:
        path: JSON 文件路径。

    返回:
        解析后的字典对象。

    异常:
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path: Path) -> list[dict]:
    """读取修改记录列表。

    参数:
        path: `change-records.json` 文件路径。

    返回:
        记录列表。

    异常:
        ValueError: `records` 字段不是列表时抛出。
    """
    data = load_json(path)
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("records 字段必须是列表。")
    return records


def resolve_default_project_id(registry_path: Path, project_id: Optional[str]) -> str:
    """解析项目标识。

    参数:
        registry_path: 项目注册表路径。
        project_id: 命令行显式传入的项目标识。

    返回:
        显式项目标识，或注册表中的默认项目标识。

    异常:
        ValueError: 未传入项目标识且注册表中也没有默认项目时抛出。
    """
    if project_id:
        return project_id

    registry = load_json(registry_path)
    default_project_id = registry.get("default_project_id")
    if not isinstance(default_project_id, str) or not default_project_id:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")
    return default_project_id


def resolve_variant_key(registry_path: Path, project_id: str, variant_key: Optional[str]) -> str:
    """解析版本目录键。

    参数:
        registry_path: 项目注册表路径。
        project_id: 当前项目标识。
        variant_key: 命令行显式传入的版本目录键。

    返回:
        显式版本目录键，或项目中保存的默认版本目录键。

    异常:
        ValueError: 未传入版本目录键且项目中也没有默认版本时抛出。
    """
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
    """判断记录是否与查询键完全匹配。

    参数:
        record: 单条记录。
        project_id: 项目标识。
        variant_key: 版本目录键。
        change_item: 修改项。

    返回:
        完全匹配时返回 True，否则返回 False。
    """
    return (
        record.get("project_id") == project_id
        and record.get("variant_key") == variant_key
        and record.get("change_item") == change_item
    )


def find_record(
    records: list[dict],
    project_id: str,
    variant_key: str,
    change_item: str,
) -> Optional[Tuple[str, dict]]:
    """查找记录。

    参数:
        records: 修改记录列表。
        project_id: 项目标识。
        variant_key: 版本目录键。
        change_item: 修改项。

    返回:
        若命中，返回 `(匹配类型, 记录字典)`；
        若未命中，返回 None。
    """
    for record in records:
        if match_record(record, project_id, variant_key, change_item):
            return "exact", record
    for record in records:
        if match_record(record, project_id, "common", change_item):
            return "fallback-common", record
    return None


def main() -> int:
    """命令行入口函数。

    返回:
        0 表示命中记录。
        1 表示读取失败或参数解析失败。
        2 表示未命中记录。
    """
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
        resolved_variant_key = resolve_variant_key(
            registry_path,
            resolved_project_id,
            args.variant_key,
        )
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
                    "change_item": args.change_item,
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
