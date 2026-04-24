#!/usr/bin/env python3
"""
功能:
    保存或更新结构化修改记录。

说明:
    这个脚本用于持久化已经确认过的修改位置、符号、修改意图、
    输入模式等信息，方便后续版本修改时复用历史定位结果，减少
    重复搜索和重复确认。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional


def load_json(path: Path, default: dict) -> dict:
    """读取 JSON 文件。

    参数:
        path: JSON 文件路径。
        default: 文件不存在时返回的默认值。

    返回:
        解析后的字典对象；若文件不存在，则返回默认值。

    异常:
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """写入 JSON 文件。

    参数:
        path: 目标 JSON 文件路径。
        data: 待写入的数据字典。
    """
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_project_id(registry: dict, project_id: Optional[str]) -> str:
    """解析项目标识。

    参数:
        registry: 项目注册表内容。
        project_id: 命令行显式传入的项目标识。

    返回:
        显式项目标识，或注册表中的默认项目标识。

    异常:
        ValueError: 未传入项目标识且不存在默认项目时抛出。
    """
    resolved = project_id or registry.get("default_project_id")
    if not isinstance(resolved, str) or not resolved:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")
    return resolved


def resolve_variant_key(
    registry: dict,
    project_id: str,
    variant_key: Optional[str],
    match_scope: str,
) -> str:
    """解析版本目录键。

    参数:
        registry: 项目注册表内容。
        project_id: 当前项目标识。
        variant_key: 命令行显式传入的版本目录键。
        match_scope: 记录作用域，可能是 `variant` 或 `common`。

    返回:
        `common`，或显式版本目录键，或当前项目的默认版本目录键。

    异常:
        ValueError: 未传入版本目录键且项目中也没有默认版本时抛出。
    """
    if match_scope == "common":
        return "common"
    if variant_key:
        return variant_key

    for project in registry.get("projects", []):
        if project.get("project_id") != project_id:
            continue
        preferred_variant_key = project.get("preferred_variant_key")
        if isinstance(preferred_variant_key, str) and preferred_variant_key:
            return preferred_variant_key
        break
    raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")


def main() -> int:
    """命令行入口函数。

    返回:
        0 表示写入成功。
        1 表示读取失败或参数不合法。
    """
    parser = argparse.ArgumentParser(description="保存或更新修改记录。")
    parser.add_argument("--change-item", required=True, help="修改项，例如 default-eq。")
    parser.add_argument("--project-id", help="项目标识；不传时自动使用默认项目。")
    parser.add_argument("--variant-key", help="版本目录；不传时自动使用默认版本。")
    parser.add_argument(
        "--match-scope",
        default="variant",
        choices=["variant", "common"],
        help="记录作用域，默认是 variant。",
    )
    parser.add_argument("--files", nargs="+", required=True, help="确认修改的文件路径列表。")
    parser.add_argument("--symbols", nargs="+", required=True, help="确认修改的符号或配置项列表。")
    parser.add_argument("--edit-intent", required=True, help="本次修改意图说明。")
    parser.add_argument("--change-tags", nargs="+", required=True, help="发布文件名使用的标签列表。")
    parser.add_argument(
        "--input-mode",
        choices=["needs-values", "fixed-target"],
        help="输入模式：需要用户贴参数，或固定目标修改。",
    )
    parser.add_argument("--value-prompt", help="缺参数时对用户的中文提问模板。")
    parser.add_argument("--value-format-hint", help="参数格式提示，例如按代码格式直接粘贴。")
    parser.add_argument("--fixed-change-hint", help="固定目标修改说明，例如 VIVO_ID_LOG = 0。")
    parser.add_argument("--last-value-text", help="最近一次用户确认的原始参数文本。")
    parser.add_argument("--confirmation-note", required=True, help="确认说明。")
    parser.add_argument(
        "--last-confirmed-at",
        default=str(date.today()),
        help="确认日期，默认使用今天。",
    )
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

    try:
        registry = load_json(
            registry_path,
            {"version": 2, "default_project_id": None, "projects": []},
        )
        records_data = load_json(
            records_path,
            {"version": 2, "records": []},
        )
        project_id = resolve_project_id(registry, args.project_id)
        variant_key = resolve_variant_key(
            registry,
            project_id,
            args.variant_key,
            args.match_scope,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"读取记录失败：{exc}")
        return 1

    records = records_data.setdefault("records", [])
    existing = None
    for record in records:
        if (
            record.get("project_id") == project_id
            and record.get("variant_key") == variant_key
            and record.get("change_item") == args.change_item
        ):
            existing = record
            break

    created = False
    if existing is None:
        existing = {}
        records.append(existing)
        created = True

    existing.update(
        {
            "project_id": project_id,
            "variant_key": variant_key,
            "change_item": args.change_item,
            "match_scope": args.match_scope,
            "files": args.files,
            "symbols": args.symbols,
            "edit_intent": args.edit_intent,
            "change_tags": args.change_tags,
            "last_confirmed_at": args.last_confirmed_at,
            "confirmation_note": args.confirmation_note,
        }
    )
    optional_updates = {
        "input_mode": args.input_mode,
        "value_prompt": args.value_prompt,
        "value_format_hint": args.value_format_hint,
        "fixed_change_hint": args.fixed_change_hint,
        "last_value_text": args.last_value_text,
    }
    for key, value in optional_updates.items():
        if value is not None:
            existing[key] = value

    records_data["version"] = 2
    write_json(records_path, records_data)

    print(
        json.dumps(
            {
                "status": "ok",
                "created": created,
                "project_id": project_id,
                "variant_key": variant_key,
                "change_item": args.change_item,
                "input_mode": existing.get("input_mode"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
