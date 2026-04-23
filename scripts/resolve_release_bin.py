#!/usr/bin/env python3
"""
功能:
    定位某个版本目录下的源 `.bin` 文件，并给出发布文件名建议。

说明:
    脚本会读取项目注册表，根据项目和版本信息执行以下操作:
    1. 优先复用已登记的源 `.bin` 文件名。
    2. 若尚未登记，则列出当前版本目录下所有候选 `.bin` 文件。
    3. 根据版本键、修改标签和日期拼接建议发布文件名。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def load_registry(path: Path) -> dict:
    """读取项目注册表。

    参数:
        path: `project-registry.json` 文件路径。

    返回:
        解析后的项目注册表字典。

    异常:
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_project(registry: dict, project_id: str | None) -> dict:
    """解析目标项目配置。

    参数:
        registry: 项目注册表内容。
        project_id: 命令行显式传入的项目标识。

    返回:
        命中的项目配置字典。

    异常:
        ValueError: 未提供项目标识且不存在默认项目，或项目未找到时抛出。
    """
    resolved_project_id = project_id or registry.get("default_project_id")
    if not isinstance(resolved_project_id, str) or not resolved_project_id:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")

    for project in registry.get("projects", []):
        if project.get("project_id") == resolved_project_id:
            return project
    raise ValueError(f"未找到项目：{resolved_project_id}")


def resolve_variant(project: dict, variant_key: str | None) -> dict:
    """解析目标版本配置。

    参数:
        project: 当前项目配置。
        variant_key: 命令行显式传入的版本目录键。

    返回:
        命中的版本配置字典。

    异常:
        ValueError: 未提供版本目录键且不存在默认版本，或版本未找到时抛出。
    """
    resolved_variant_key = variant_key or project.get("preferred_variant_key")
    if not isinstance(resolved_variant_key, str) or not resolved_variant_key:
        raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")

    for variant in project.get("variants", []):
        if variant.get("variant_key") == resolved_variant_key:
            return variant
    raise ValueError(f"项目 {project.get('project_id')} 下未找到版本：{resolved_variant_key}")


def build_release_name(variant_key: str, change_tags: list[str], date_mmdd: str) -> str:
    """生成建议发布文件名。

    参数:
        variant_key: 版本目录键。
        change_tags: 修改标签列表。
        date_mmdd: `MMDD` 格式日期字符串。

    返回:
        形如 `DPD2603A_default_eq_0423.bin` 的建议文件名。
    """
    tags = [tag for tag in change_tags if tag]
    parts = [variant_key]
    if tags:
        parts.extend(tags)
    parts.append(date_mmdd)
    return "_".join(parts) + ".bin"


def collect_candidates(artifact_dir: Path) -> list[Path]:
    """收集候选 `.bin` 文件。

    参数:
        artifact_dir: 版本产物目录。

    返回:
        按最后修改时间倒序排列的 `.bin` 文件路径列表。
    """
    return sorted(
        (path for path in artifact_dir.glob("*.bin") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def main() -> int:
    """命令行入口函数。

    返回:
        0 表示成功输出结果。
        1 表示读取失败、配置缺失或目录异常。
    """
    parser = argparse.ArgumentParser(description="定位某个版本目录对应的发布源 bin。")
    parser.add_argument("--project-id", help="项目标识；不传时自动使用默认项目。")
    parser.add_argument("--variant-key", help="版本键，例如 DPD2603A；不传时自动使用默认版本。")
    parser.add_argument(
        "--registry",
        default="references/project-registry.json",
        help="project-registry.json 的路径。",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="工作区根目录，用于解析 root_hint 和产物路径。",
    )
    parser.add_argument(
        "--change-tags",
        nargs="*",
        default=[],
        help="用于拼接发布文件名的修改标签。",
    )
    parser.add_argument(
        "--date-mmdd",
        default=datetime.now().strftime("%m%d"),
        help="用于生成发布文件名的 MMDD 日期字符串。",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve()
    if not registry_path.exists():
        print(f"未找到项目注册表：{registry_path}")
        return 1

    try:
        registry = load_registry(registry_path)
        project = resolve_project(registry, args.project_id)
        variant = resolve_variant(project, args.variant_key)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"读取项目注册表失败：{exc}")
        return 1

    workspace_root = Path(args.workspace_root).resolve()
    root_hint = project.get("root_hint") or "."
    project_root = (workspace_root / root_hint).resolve()
    artifact_dir_value = variant.get("artifact_dir")
    if not isinstance(artifact_dir_value, str) or not artifact_dir_value.strip():
        print("版本配置缺少 artifact_dir。")
        return 1

    artifact_dir = (project_root / artifact_dir_value).resolve()
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        print(f"未找到产物目录：{artifact_dir}")
        return 1

    source_bin_name = variant.get("source_bin_name")
    candidates = collect_candidates(artifact_dir)
    candidate_names = [path.name for path in candidates]
    source_bin_path = None
    requires_confirmation = False

    if isinstance(source_bin_name, str) and source_bin_name.strip():
        expected_path = artifact_dir / source_bin_name
        if not expected_path.exists():
            print(f"已登记的源 bin 不存在：{expected_path}")
            return 1
        source_bin_path = expected_path
    else:
        requires_confirmation = True
        if not candidates:
            print(f"产物目录中未找到 .bin 文件：{artifact_dir}")
            return 1

    result = {
        "project_id": project.get("project_id"),
        "variant_key": variant.get("variant_key"),
        "artifact_dir": str(artifact_dir),
        "source_bin_name": source_bin_name,
        "source_bin_path": str(source_bin_path) if source_bin_path else None,
        "candidates": candidate_names,
        "requires_confirmation": requires_confirmation,
        "suggested_release_name": build_release_name(
            variant.get("variant_key"),
            args.change_tags,
            args.date_mmdd,
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
