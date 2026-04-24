#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import os
import sys

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


def load_records(path):
    data = load_json_file(path)
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("records 字段必须是列表。")
    return records


def resolve_default_project_id(registry_path, project_id):
    if project_id:
        return project_id

    registry = load_json_file(registry_path)
    default_project_id = registry.get("default_project_id")
    if not isinstance(default_project_id, STRING_TYPES) or not default_project_id:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")
    return default_project_id


def resolve_variant_key(registry_path, project_id, variant_key):
    if variant_key:
        return variant_key

    registry = load_json_file(registry_path)
    projects = registry.get("projects", [])
    for project in projects:
        if project.get("project_id") != project_id:
            continue

        preferred_variant_key = project.get("preferred_variant_key")
        if isinstance(preferred_variant_key, STRING_TYPES) and preferred_variant_key:
            return preferred_variant_key
        break

    raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")


def match_record(record, project_id, variant_key, change_item):
    return (
        record.get("project_id") == project_id
        and record.get("variant_key") == variant_key
        and record.get("change_item") == change_item
    )


def find_record(records, project_id, variant_key, change_item):
    for record in records:
        if match_record(record, project_id, variant_key, change_item):
            return "exact", record

    for record in records:
        if match_record(record, project_id, "common", change_item):
            return "fallback-common", record

    return None


def main():
    parser = argparse.ArgumentParser(description=u"查询版本发布修改记录。")
    parser.add_argument("--project-id", help=u"项目标识；不传时自动使用默认项目。")
    parser.add_argument(
        "--variant-key",
        "--preferred-variant-key",
        dest="variant_key",
        help=u"版本目录键；不传时自动使用默认版本。",
    )
    parser.add_argument("--change-item", required=True, help=u"修改项，例如 default-eq。")
    parser.add_argument(
        "--records",
        default=None,
        help=u"change-records.json 的路径。",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help=u"project-registry.json 的路径。",
    )
    args = normalize_namespace(parser.parse_args())

    records_path = resolve_cli_path(
        args.records,
        reference_path("change-records.json"),
    )
    registry_path = resolve_cli_path(
        args.registry,
        reference_path("project-registry.json"),
    )

    if not os.path.exists(records_path):
        print_text(u"未找到记录文件：{}".format(records_path))
        return 1

    if not os.path.exists(registry_path):
        print_text(u"未找到项目注册表：{}".format(registry_path))
        return 1

    try:
        resolved_project_id = resolve_default_project_id(registry_path, args.project_id)
        resolved_variant_key = resolve_variant_key(
            registry_path,
            resolved_project_id,
            args.variant_key,
        )
        records = load_records(records_path)
    except (IOError, OSError, ValueError, JSONDecodeError) as exc:
        print_text(u"读取记录失败：{}".format(exc))
        return 1

    result = find_record(records, resolved_project_id, resolved_variant_key, args.change_item)
    if result is None:
        print_json(
            {
                "status": "not_found",
                "project_id": resolved_project_id,
                "variant_key": resolved_variant_key,
                "change_item": args.change_item,
            }
        )
        return 2

    match_type, record = result
    print_json(
        {
            "status": "ok",
            "match_type": match_type,
            "project_id": resolved_project_id,
            "variant_key": resolved_variant_key,
            "record": record,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
