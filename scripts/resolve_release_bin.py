#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import glob
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pycompat import JSONDecodeError
from pycompat import STRING_TYPES
from pycompat import load_json_file
from pycompat import normalize_namespace
from pycompat import print_json
from pycompat import print_text
from pycompat import reference_path
from pycompat import resolve_cli_path


def resolve_project(registry, project_id):
    resolved_project_id = project_id or registry.get("default_project_id")
    if not isinstance(resolved_project_id, STRING_TYPES) or not resolved_project_id:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")

    for project in registry.get("projects", []):
        if project.get("project_id") == resolved_project_id:
            return project

    raise ValueError(u"未找到项目：{}".format(resolved_project_id))


def resolve_variant(project, variant_key):
    resolved_variant_key = variant_key or project.get("preferred_variant_key")
    if not isinstance(resolved_variant_key, STRING_TYPES) or not resolved_variant_key:
        raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")

    for variant in project.get("variants", []):
        if variant.get("variant_key") == resolved_variant_key:
            return variant

    raise ValueError(
        u"项目 {} 下未找到版本：{}".format(project.get("project_id"), resolved_variant_key)
    )


def build_release_name(variant_key, change_tags, date_mmdd):
    tags = [tag for tag in change_tags if tag]
    parts = [variant_key]
    if tags:
        parts.extend(tags)
    parts.append(date_mmdd)
    return "_".join(parts) + ".bin"


def collect_candidates(artifact_dir):
    pattern = os.path.join(artifact_dir, "*.bin")
    candidates = [path for path in glob.glob(pattern) if os.path.isfile(path)]
    return sorted(candidates, key=os.path.getmtime, reverse=True)


def main():
    parser = argparse.ArgumentParser(description=u"定位某个版本目录对应的发布源 bin。")
    parser.add_argument("--project-id", help=u"项目标识；不传时自动使用默认项目。")
    parser.add_argument(
        "--variant-key",
        "--preferred-variant-key",
        dest="variant_key",
        help=u"版本键；不传时自动使用默认版本。",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help=u"project-registry.json 的路径。",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help=u"工作区根目录，用于解析 root_hint 和产物路径。",
    )
    parser.add_argument(
        "--change-tags",
        nargs="*",
        default=[],
        help=u"用于拼接发布文件名的修改标签。",
    )
    parser.add_argument(
        "--date-mmdd",
        default=datetime.now().strftime("%m%d"),
        help=u"用于生成发布文件名的 MMDD 日期字符串。",
    )
    args = normalize_namespace(parser.parse_args())

    registry_path = resolve_cli_path(
        args.registry,
        reference_path("project-registry.json"),
    )
    if not os.path.exists(registry_path):
        print_text(u"未找到项目注册表：{}".format(registry_path))
        return 1

    try:
        registry = load_json_file(registry_path)
        project = resolve_project(registry, args.project_id)
        variant = resolve_variant(project, args.variant_key)
    except (IOError, OSError, ValueError, JSONDecodeError) as exc:
        print_text(u"读取项目注册表失败：{}".format(exc))
        return 1

    workspace_root = os.path.abspath(args.workspace_root)
    root_hint = project.get("root_hint") or "."
    project_root = os.path.abspath(os.path.join(workspace_root, root_hint))
    artifact_dir_value = variant.get("artifact_dir")
    if not isinstance(artifact_dir_value, STRING_TYPES) or not artifact_dir_value.strip():
        print_text(u"版本配置缺少 artifact_dir。")
        return 1

    artifact_dir = os.path.abspath(os.path.join(project_root, artifact_dir_value))
    if not os.path.isdir(artifact_dir):
        print_text(u"未找到产物目录：{}".format(artifact_dir))
        return 1

    source_bin_name = variant.get("source_bin_name")
    candidates = collect_candidates(artifact_dir)
    candidate_names = [os.path.basename(path) for path in candidates]
    source_bin_path = None
    requires_confirmation = False

    if isinstance(source_bin_name, STRING_TYPES) and source_bin_name.strip():
        expected_path = os.path.join(artifact_dir, source_bin_name)
        if not os.path.exists(expected_path):
            print_text(u"已登记的源 bin 不存在：{}".format(expected_path))
            return 1
        source_bin_path = expected_path
    else:
        requires_confirmation = True
        if not candidates:
            print_text(u"产物目录中未找到 .bin 文件：{}".format(artifact_dir))
            return 1

    print_json(
        {
            "project_id": project.get("project_id"),
            "variant_key": variant.get("variant_key"),
            "artifact_dir": artifact_dir,
            "source_bin_name": source_bin_name,
            "source_bin_path": source_bin_path,
            "candidates": candidate_names,
            "requires_confirmation": requires_confirmation,
            "suggested_release_name": build_release_name(
                variant.get("variant_key"),
                args.change_tags,
                args.date_mmdd,
            ),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
