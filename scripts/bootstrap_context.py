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
from pycompat import STRING_TYPES
from pycompat import load_json_file
from pycompat import normalize_namespace
from pycompat import print_json
from pycompat import reference_path
from pycompat import resolve_cli_path


def load_json(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise IOError(path)
    return load_json_file(path)


def resolve_default_project_id(registry, project_id):
    if project_id:
        return project_id

    value = registry.get("default_project_id")
    if isinstance(value, STRING_TYPES) and value:
        return value
    return None


def resolve_project(registry, project_id):
    if not project_id:
        return None

    for project in registry.get("projects", []):
        if project.get("project_id") == project_id:
            return project
    return None


def resolve_variant_key(project, variant_key):
    if variant_key:
        return variant_key

    if not project:
        return None

    value = project.get("preferred_variant_key")
    if isinstance(value, STRING_TYPES) and value:
        return value
    return None


def find_record(records, project_id, variant_key, change_item):
    if not project_id or not change_item:
        return None

    if variant_key:
        for record in records:
            if (
                record.get("project_id") == project_id
                and record.get("variant_key") == variant_key
                and record.get("change_item") == change_item
            ):
                return "exact", record

    for record in records:
        if (
            record.get("project_id") == project_id
            and record.get("variant_key") == "common"
            and record.get("change_item") == change_item
        ):
            return "fallback-common", record

    return None


def infer_change_item(request_text):
    text = request_text.lower()

    if any(
        token in text
        for token in [
            u"default eq",
            u"defaulteq",
            u"default-eq",
            u"audio_eq_standard_default_cfg",
            u"eq参数",
            u"eq 参数",
        ]
    ):
        return "default-eq"

    if any(
        token in text
        for token in [
            u"#define",
            u"宏",
            u"开关",
            u"明文log",
            u"明文 log",
            u"vivo_id_log",
            u"macro",
        ]
    ):
        return "macro-toggle"

    if any(token in text for token in [u"配置", u"config", u"默认值", u"路径切换"]):
        return "other-config"

    return None


def looks_like_complete_value_block(request_text):
    if "```" in request_text:
        return True

    if re.search(r"\.[A-Za-z_]\w*\s*=", request_text):
        return True

    if request_text.count("=") >= 2:
        return True

    if "(" in request_text and ")" in request_text and "=" in request_text:
        return True

    return False


def looks_like_explicit_target_value(request_text):
    lowered = request_text.lower()

    if re.search(r"[A-Za-z_]\w*\s*=\s*[^,\n]+", request_text):
        return True

    if re.search(u"(改成|设为|置为)\\s*[01]\\b", request_text):
        return True

    if any(token in request_text for token in [u"打开", u"关闭", u"使能", u"禁用"]):
        return True

    if any(token in lowered for token in [u"enable", u"disable"]):
        return True

    return False


def missing_project_fields(project):
    if not project:
        return ["display_name", "build_command", "preferred_variant_key"]

    missing = []
    if not project.get("display_name"):
        missing.append("display_name")
    if not project.get("build_command"):
        missing.append("build_command")
    if not project.get("preferred_variant_key"):
        missing.append("preferred_variant_key")
    return missing


def decide_action(request_text, project, project_id, variant_key, change_item, record_match):
    missing_fields = missing_project_fields(project)
    if missing_fields:
        return {
            "action": "need_project_init",
            "reason": "missing_project_preferences",
            "message_cn": u"缺少默认项目配置，需要先补齐工程名称、编译命令或默认版本。",
            "missing_fields": missing_fields,
        }

    if not change_item:
        return {
            "action": "need_change_item",
            "reason": "change_item_unknown",
            "message_cn": u"还没识别出这次修改项，需要先说明是改 EQ、宏开关还是其他配置。",
        }

    if record_match is None:
        return {
            "action": "need_location_confirmation",
            "reason": "record_not_found",
            "message_cn": u"没有命中历史记录，需要先搜索源码并确认修改位置。",
        }

    match_type, record = record_match
    input_mode = record.get("input_mode")

    if input_mode == "fixed-target":
        if looks_like_explicit_target_value(request_text) or record.get("fixed_change_hint"):
            return {
                "action": "direct_apply_and_build",
                "reason": "record_matched_and_target_clear",
                "message_cn": u"记录已命中且目标值明确，可以直接修改并编译。",
                "match_type": match_type,
                "record": record,
            }

        return {
            "action": "need_target_value",
            "reason": "target_value_missing",
            "message_cn": u"记录已命中，但目标值还不够明确，需要补一句目标值。",
            "match_type": match_type,
            "record": record,
        }

    if input_mode == "needs-values":
        if looks_like_complete_value_block(request_text):
            return {
                "action": "direct_apply_and_build",
                "reason": "record_matched_and_values_complete",
                "message_cn": u"记录已命中且参数已给全，可以直接修改并编译。",
                "match_type": match_type,
                "record": record,
            }

        return {
            "action": "need_value_input",
            "reason": "values_missing",
            "message_cn": u"记录已命中，但这次参数还不完整，需要先补参数。",
            "match_type": match_type,
            "record": record,
        }

    return {
        "action": "need_location_confirmation",
        "reason": "record_input_mode_unknown",
        "message_cn": u"记录命中了，但输入模式不完整，建议先确认修改位置和目标。",
        "match_type": match_type,
        "record": record,
    }


def main():
    parser = argparse.ArgumentParser(description=u"快速判断 skill 下一步动作。")
    parser.add_argument("--request-text", required=True, help=u"用户本次请求文本。")
    parser.add_argument("--change-item", help=u"可选，手动指定 change_item。")
    parser.add_argument("--project-id", help=u"可选，手动指定项目标识。")
    parser.add_argument(
        "--variant-key",
        "--preferred-variant-key",
        dest="variant_key",
        help=u"可选，手动指定版本目录。",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help=u"project-registry.json 路径。",
    )
    parser.add_argument(
        "--records",
        default=None,
        help=u"change-records.json 路径。",
    )
    args = normalize_namespace(parser.parse_args())

    registry_path = resolve_cli_path(
        args.registry,
        reference_path("project-registry.json"),
    )
    records_path = resolve_cli_path(
        args.records,
        reference_path("change-records.json"),
    )

    try:
        registry = load_json(
            registry_path,
            {"version": 2, "default_project_id": None, "projects": []},
        )
        records_data = load_json(
            records_path,
            {"version": 2, "records": []},
        )
        records = records_data.get("records", [])
        if not isinstance(records, list):
            raise ValueError("records 字段必须是列表。")
    except (IOError, OSError, ValueError, JSONDecodeError) as exc:
        print_json(
            {
                "status": "error",
                "reason": "load_failed",
                "message_cn": u"读取配置失败：{}".format(exc),
            }
        )
        return 1

    request_text = args.request_text.strip()
    project_id = resolve_default_project_id(registry, args.project_id)
    project = resolve_project(registry, project_id)
    variant_key = resolve_variant_key(project, args.variant_key)
    change_item = args.change_item or infer_change_item(request_text)
    record_match = find_record(records, project_id, variant_key, change_item)
    decision = decide_action(
        request_text,
        project,
        project_id,
        variant_key,
        change_item,
        record_match,
    )

    result = {
        "status": "ok",
        "project_id": project_id,
        "variant_key": variant_key,
        "change_item": change_item,
        "has_project": project is not None,
        "record_found": record_match is not None,
    }
    result.update(decision)

    print_json(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
