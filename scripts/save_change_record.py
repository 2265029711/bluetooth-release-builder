#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pycompat import JSONDecodeError
from pycompat import STRING_TYPES
from pycompat import load_json_file
from pycompat import normalize_namespace
from pycompat import print_json
from pycompat import print_text
from pycompat import write_json_file


def load_json(path, default):
    if not os.path.exists(path):
        return default
    return load_json_file(path)


def resolve_project_id(registry, project_id):
    resolved = project_id or registry.get("default_project_id")
    if not isinstance(resolved, STRING_TYPES) or not resolved:
        raise ValueError("未提供 project_id，且当前没有已保存的默认项目。")
    return resolved


def resolve_variant_key(registry, project_id, variant_key, match_scope):
    if match_scope == "common":
        return "common"

    if variant_key:
        return variant_key

    for project in registry.get("projects", []):
        if project.get("project_id") != project_id:
            continue

        preferred_variant_key = project.get("preferred_variant_key")
        if isinstance(preferred_variant_key, STRING_TYPES) and preferred_variant_key:
            return preferred_variant_key
        break

    raise ValueError("未提供 variant_key，且当前项目没有已保存的默认版本目录。")


def main():
    parser = argparse.ArgumentParser(description=u"保存或更新修改记录。")
    parser.add_argument("--change-item", required=True, help=u"修改项，例如 default-eq。")
    parser.add_argument("--project-id", help=u"项目标识；不传时自动使用默认项目。")
    parser.add_argument("--variant-key", help=u"版本目录；不传时自动使用默认版本。")
    parser.add_argument(
        "--match-scope",
        default="variant",
        choices=["variant", "common"],
        help=u"记录作用域，默认是 variant。",
    )
    parser.add_argument("--files", nargs="+", required=True, help=u"确认修改的文件路径列表。")
    parser.add_argument("--symbols", nargs="+", required=True, help=u"确认修改的符号或配置项列表。")
    parser.add_argument("--edit-intent", required=True, help=u"本次修改意图说明。")
    parser.add_argument("--change-tags", nargs="+", required=True, help=u"发布文件名使用的标签列表。")
    parser.add_argument(
        "--input-mode",
        choices=["needs-values", "fixed-target"],
        help=u"输入模式：需要用户贴参数，或固定目标修改。",
    )
    parser.add_argument("--value-prompt", help=u"缺参数时对用户的中文提问模板。")
    parser.add_argument("--value-format-hint", help=u"参数格式提示，例如按代码格式直接粘贴。")
    parser.add_argument("--fixed-change-hint", help=u"固定目标修改说明，例如 VIVO_ID_LOG = 0。")
    parser.add_argument("--last-value-text", help=u"最近一次用户确认的原始参数文本。")
    parser.add_argument("--confirmation-note", required=True, help=u"确认说明。")
    parser.add_argument(
        "--last-confirmed-at",
        default=str(date.today()),
        help=u"确认日期，默认使用今天。",
    )
    parser.add_argument(
        "--records",
        default="references/change-records.json",
        help=u"change-records.json 的路径。",
    )
    parser.add_argument(
        "--registry",
        default="references/project-registry.json",
        help=u"project-registry.json 的路径。",
    )
    args = normalize_namespace(parser.parse_args())

    records_path = os.path.abspath(args.records)
    registry_path = os.path.abspath(args.registry)

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
    except (IOError, OSError, ValueError, JSONDecodeError) as exc:
        print_text(u"读取记录失败：{}".format(exc))
        return 1

    records = records_data.setdefault("records", [])
    if not isinstance(records, list):
        print_text(u"读取记录失败：records 字段必须是列表。")
        return 1

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
    write_json_file(records_path, records_data)

    print_json(
        {
            "status": "ok",
            "created": created,
            "project_id": project_id,
            "variant_key": variant_key,
            "change_item": args.change_item,
            "input_mode": existing.get("input_mode"),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
