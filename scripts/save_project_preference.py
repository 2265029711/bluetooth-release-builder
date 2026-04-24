#!/usr/bin/env python3
"""
功能:
    保存或更新项目级首选项。

说明:
    这个脚本用于持久化 skill 所依赖的默认项目、默认版本目录、
    编译命令、产物目录以及默认源 bin 信息。保存后，后续调用可
    以减少初始化提问次数。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


def load_registry(path: Path) -> dict:
    """读取项目注册表。

    参数:
        path: `project-registry.json` 文件路径。

    返回:
        解析后的注册表字典；若文件不存在，则返回空的默认结构。

    异常:
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    if not path.exists():
        return {"version": 2, "default_project_id": None, "projects": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_registry(path: Path, data: dict) -> None:
    """写入项目注册表。

    参数:
        path: 目标 JSON 文件路径。
        data: 待写入的数据字典。
    """
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_project_id(raw_value: str) -> str:
    """将自由文本规范化为项目标识。

    参数:
        raw_value: 原始项目名称或目录名。

    返回:
        仅包含小写字母、数字和连字符的项目标识字符串。
    """
    normalized = raw_value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def make_unique_project_id(base_id: str, projects: list[dict]) -> str:
    """为项目标识生成不冲突的唯一值。

    参数:
        base_id: 基础项目标识。
        projects: 现有项目列表。

    返回:
        不与现有项目冲突的项目标识。
    """
    existing = {project.get("project_id") for project in projects}
    if base_id not in existing:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing:
        counter += 1
    return f"{base_id}-{counter}"


def derive_project_id(
    display_name: Optional[str],
    root_hint: Optional[str],
    projects: list[dict],
) -> str:
    """推导项目标识。

    参数:
        display_name: 工程显示名称。
        root_hint: 工程根目录提示。
        projects: 现有项目列表。

    返回:
        已存在项目的项目标识，或新生成的不冲突项目标识。
    """
    for project in projects:
        if display_name and project.get("display_name") == display_name:
            return project["project_id"]
        if root_hint and project.get("root_hint") == root_hint:
            return project["project_id"]

    candidates = [
        display_name or "",
        Path(root_hint or ".").name,
        "bluetooth-project",
    ]
    base_id = ""
    for candidate in candidates:
        base_id = normalize_project_id(candidate)
        if base_id:
            break
    if not base_id:
        base_id = "bluetooth-project"
    return make_unique_project_id(base_id, projects)


def find_project(projects: list[dict], project_id: str) -> Optional[dict]:
    """查找项目配置。

    参数:
        projects: 项目列表。
        project_id: 目标项目标识。

    返回:
        命中的项目配置字典；未命中时返回 None。
    """
    for project in projects:
        if project.get("project_id") == project_id:
            return project
    return None


def find_variant(project: dict, variant_key: str) -> Optional[dict]:
    """查找版本配置。

    参数:
        project: 当前项目配置。
        variant_key: 目标版本目录键。

    返回:
        命中的版本配置字典；未命中时返回 None。
    """
    for variant in project.get("variants", []):
        if variant.get("variant_key") == variant_key:
            return variant
    return None


def default_artifact_dir(artifact_root: str, variant_key: str) -> str:
    """拼接默认产物目录。

    参数:
        artifact_root: 产物根目录。
        variant_key: 版本目录键。

    返回:
        默认版本产物目录路径字符串。
    """
    return artifact_root.rstrip("/\\") + "/" + variant_key


def main() -> int:
    """命令行入口函数。

    返回:
        0 表示写入成功。
        1 表示读取失败或参数不合法。
    """
    parser = argparse.ArgumentParser(description="保存或更新项目首选项。")
    parser.add_argument("--display-name", help="工程显示名称，例如 我的蓝牙工程。")
    parser.add_argument("--project-id", help="内部项目标识；通常可不传，由脚本自动生成。")
    parser.add_argument("--root-hint", default=".", help="工程根目录提示，默认为当前目录。")
    parser.add_argument("--build-command", help="完整编译命令。")
    parser.add_argument("--artifact-root", default="out", help="输出根目录，默认是 out。")
    parser.add_argument("--variant-key", help="默认版本目录，例如 DPD2603A。")
    parser.add_argument("--artifact-dir", help="版本目录输出路径；不传时默认 artifact_root/variant_key。")
    parser.add_argument("--source-bin-name", help="该版本默认源 bin 名称。")
    parser.add_argument("--notes", help="补充说明。")
    parser.add_argument(
        "--registry",
        default="references/project-registry.json",
        help="project-registry.json 的路径。",
    )
    parser.add_argument(
        "--set-default",
        action="store_true",
        help="将本次项目设置为默认项目。",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve()
    try:
        registry = load_registry(registry_path)
    except json.JSONDecodeError as exc:
        print(f"读取项目注册表失败：{exc}")
        return 1

    projects = registry.setdefault("projects", [])
    project_id = args.project_id or derive_project_id(
        args.display_name,
        args.root_hint,
        projects,
    )
    project = find_project(projects, project_id)
    created_project = False

    if project is None:
        project = {
            "project_id": project_id,
            "display_name": args.display_name or "未命名工程",
            "root_hint": args.root_hint,
            "build_command": args.build_command or "",
            "artifact_root": args.artifact_root,
            "preferred_variant_key": None,
            "variants": [],
        }
        projects.append(project)
        created_project = True

    if args.display_name is not None:
        project["display_name"] = args.display_name
    if args.root_hint is not None:
        project["root_hint"] = args.root_hint
    if args.build_command is not None:
        project["build_command"] = args.build_command
    if args.artifact_root is not None:
        project["artifact_root"] = args.artifact_root

    created_variant = False
    variant = None
    if args.variant_key:
        project["preferred_variant_key"] = args.variant_key
        variant = find_variant(project, args.variant_key)
        if variant is None:
            variant = {
                "variant_key": args.variant_key,
                "artifact_dir": args.artifact_dir
                or default_artifact_dir(project["artifact_root"], args.variant_key),
                "source_bin_name": None,
                "notes": "",
            }
            project["variants"].append(variant)
            created_variant = True

        if args.artifact_dir is not None:
            variant["artifact_dir"] = args.artifact_dir
        if args.source_bin_name is not None:
            variant["source_bin_name"] = args.source_bin_name
        if args.notes is not None:
            variant["notes"] = args.notes

    if args.set_default or not registry.get("default_project_id"):
        registry["default_project_id"] = project_id

    registry["version"] = 2
    write_registry(registry_path, registry)

    result = {
        "status": "ok",
        "project_id": project_id,
        "default_project_id": registry.get("default_project_id"),
        "created_project": created_project,
        "created_variant": created_variant,
        "preferred_variant_key": project.get("preferred_variant_key"),
        "saved_source_bin_name": variant.get("source_bin_name") if variant else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
