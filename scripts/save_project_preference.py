#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pycompat import JSONDecodeError
from pycompat import load_json_file
from pycompat import normalize_namespace
from pycompat import print_json
from pycompat import print_text
from pycompat import reference_path
from pycompat import resolve_cli_path
from pycompat import write_json_file


def load_registry(path):
    if not os.path.exists(path):
        return {"version": 2, "default_project_id": None, "projects": []}
    return load_json_file(path)


def normalize_project_id(raw_value):
    normalized = raw_value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def make_unique_project_id(base_id, projects):
    existing = set()
    for project in projects:
        project_id = project.get("project_id")
        if project_id:
            existing.add(project_id)

    if base_id not in existing:
        return base_id

    counter = 2
    while "{}-{}".format(base_id, counter) in existing:
        counter += 1
    return "{}-{}".format(base_id, counter)


def derive_project_id(display_name, root_hint, projects):
    for project in projects:
        if display_name and project.get("display_name") == display_name:
            return project["project_id"]
        if root_hint and project.get("root_hint") == root_hint:
            return project["project_id"]

    candidates = [
        display_name or "",
        os.path.basename(os.path.normpath(root_hint or ".")),
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


def find_project(projects, project_id):
    for project in projects:
        if project.get("project_id") == project_id:
            return project
    return None


def find_variant(project, variant_key):
    for variant in project.get("variants", []):
        if variant.get("variant_key") == variant_key:
            return variant
    return None


def default_artifact_dir(artifact_root, variant_key):
    return artifact_root.rstrip("/\\") + "/" + variant_key


def main():
    parser = argparse.ArgumentParser(description=u"保存或更新项目首选项。")
    parser.add_argument("--display-name", help=u"工程显示名称，例如我的蓝牙工程。")
    parser.add_argument("--project-id", help=u"内部项目标识；通常可不传，由脚本自动生成。")
    parser.add_argument("--root-hint", default=".", help=u"工程根目录提示，默认是当前目录。")
    parser.add_argument("--build-command", help=u"完整编译命令。")
    parser.add_argument("--artifact-root", default="out", help=u"输出根目录，默认是 out。")
    parser.add_argument(
        "--variant-key",
        "--preferred-variant-key",
        dest="variant_key",
        help=u"默认版本目录，例如 DPD2603A。",
    )
    parser.add_argument("--artifact-dir", help=u"版本目录输出路径；不传时默认 artifact_root/variant_key。")
    parser.add_argument("--source-bin-name", help=u"该版本默认源 bin 名称。")
    parser.add_argument("--notes", help=u"补充说明。")
    parser.add_argument(
        "--registry",
        default=None,
        help=u"project-registry.json 的路径。",
    )
    parser.add_argument(
        "--set-default",
        action="store_true",
        help=u"将本次项目设置为默认项目。",
    )
    args = normalize_namespace(parser.parse_args())

    registry_path = resolve_cli_path(
        args.registry,
        reference_path("project-registry.json"),
    )
    try:
        registry = load_registry(registry_path)
    except (IOError, OSError, JSONDecodeError) as exc:
        print_text(u"读取项目注册表失败：{}".format(exc))
        return 1

    projects = registry.setdefault("projects", [])
    if not isinstance(projects, list):
        print_text(u"读取项目注册表失败：projects 字段必须是列表。")
        return 1

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
            "display_name": args.display_name or u"未命名工程",
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
            project.setdefault("variants", []).append(variant)
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
    write_json_file(registry_path, registry)

    print_json(
        {
            "status": "ok",
            "project_id": project_id,
            "default_project_id": registry.get("default_project_id"),
            "created_project": created_project,
            "created_variant": created_variant,
            "preferred_variant_key": project.get("preferred_variant_key"),
            "saved_source_bin_name": variant.get("source_bin_name") if variant else None,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
