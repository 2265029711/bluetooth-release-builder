#!/usr/bin/env python3
"""
功能:
    快速判断当前 skill 请求的下一步动作。

说明:
    这个脚本把 skill 启动阶段最常见的前置判断收敛到一次执行里，
    避免模型在对话中重复读取 JSON、重复推断修改类型、重复判断
    是否需要继续确认。

    脚本会综合以下信息输出一个小型 JSON 结果:
    1. 是否已存在默认项目配置。
    2. 当前请求最可能属于哪一种修改项。
    3. 是否命中历史修改记录。
    4. 当前输入是否已经足够直接执行“修改并编译”。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple


def load_json(path: Path, default: Optional[dict] = None) -> dict:
    """读取 JSON 文件。

    参数:
        path: 目标 JSON 文件路径。
        default: 文件不存在时返回的默认值；若为 None，则抛出异常。

    返回:
        解析后的字典对象。

    异常:
        FileNotFoundError: 文件不存在且未提供默认值时抛出。
        json.JSONDecodeError: 文件内容不是合法 JSON 时抛出。
    """
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_default_project_id(registry: dict, project_id: Optional[str]) -> Optional[str]:
    """解析项目标识。

    参数:
        registry: 项目注册表内容。
        project_id: 命令行显式传入的项目标识。

    返回:
        显式项目标识，或注册表中的默认项目标识；若都不存在则返回 None。
    """
    if project_id:
        return project_id
    value = registry.get("default_project_id")
    return value if isinstance(value, str) and value else None


def resolve_project(registry: dict, project_id: Optional[str]) -> Optional[dict]:
    """根据项目标识查找项目配置。

    参数:
        registry: 项目注册表内容。
        project_id: 目标项目标识。

    返回:
        命中的项目配置字典；未命中时返回 None。
    """
    if not project_id:
        return None
    for project in registry.get("projects", []):
        if project.get("project_id") == project_id:
            return project
    return None


def resolve_variant_key(project: Optional[dict], variant_key: Optional[str]) -> Optional[str]:
    """解析版本目录键。

    参数:
        project: 当前项目配置。
        variant_key: 命令行显式传入的版本目录键。

    返回:
        显式版本目录键，或项目中的默认版本目录键；若都不存在则返回 None。
    """
    if variant_key:
        return variant_key
    if not project:
        return None
    value = project.get("preferred_variant_key")
    return value if isinstance(value, str) and value else None


def find_record(
    records: list[dict],
    project_id: Optional[str],
    variant_key: Optional[str],
    change_item: Optional[str],
) -> Optional[Tuple[str, dict]]:
    """查找修改记录。

    参数:
        records: 所有修改记录列表。
        project_id: 当前项目标识。
        variant_key: 当前版本目录键。
        change_item: 当前修改项。

    返回:
        若命中，返回 `(匹配类型, 记录字典)`：
        - `exact`: 精确命中 `(project_id, variant_key, change_item)`
        - `fallback-common`: 回退命中 `(project_id, common, change_item)`
        若未命中则返回 None。
    """
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


def infer_change_item(request_text: str) -> Optional[str]:
    """从用户原话中推断修改项。

    参数:
        request_text: 用户本次原始请求文本。

    返回:
        命中的修改项：
        - `default-eq`
        - `macro-toggle`
        - `other-config`
        若无法识别则返回 None。
    """
    text = request_text.lower()

    if any(
        token in text
        for token in [
            "default eq",
            "defaulteq",
            "default-eq",
            "audio_eq_standard_default_cfg",
            "eq参数",
            "eq 参数",
        ]
    ):
        return "default-eq"
    if any(
        token in text
        for token in [
            "#define",
            "宏",
            "开关",
            "明文log",
            "明文 log",
            "vivo_id_log",
            "macro",
        ]
    ):
        return "macro-toggle"
    if any(token in text for token in ["配置", "config", "默认值", "路径切换"]):
        return "other-config"
    return None


def looks_like_complete_value_block(request_text: str) -> bool:
    """判断用户是否已经给出了可直接落代码的参数内容。

    参数:
        request_text: 用户本次原始请求文本。

    返回:
        若文本中已经包含完整参数块、结构体字段赋值或明显的代码片段，
        返回 True；否则返回 False。
    """
    text = request_text
    if "```" in text:
        return True
    if re.search(r"\.[A-Za-z_]\w*\s*=", text):
        return True
    if text.count("=") >= 2:
        return True
    if "(" in text and ")" in text and "=" in text:
        return True
    return False


def looks_like_explicit_target_value(request_text: str) -> bool:
    """判断用户是否已经明确给出了宏或目标值。

    参数:
        request_text: 用户本次原始请求文本。

    返回:
        若文本中已经包含明确的宏赋值、开关状态或目标值表达，
        返回 True；否则返回 False。
    """
    text = request_text
    if re.search(r"[A-Za-z_]\w*\s*=\s*[^,\n]+", text):
        return True
    if re.search(r"改[成为]\s*[01]\b", text):
        return True
    if any(token in text for token in ["打开", "关闭", "使能", "禁用"]):
        return True
    return False


def missing_project_fields(project: Optional[dict]) -> list[str]:
    """列出缺失的项目首选项字段。

    参数:
        project: 当前项目配置。

    返回:
        缺失字段名列表。
    """
    if not project:
        return ["display_name", "build_command", "preferred_variant_key"]

    missing: list[str] = []
    if not project.get("display_name"):
        missing.append("display_name")
    if not project.get("build_command"):
        missing.append("build_command")
    if not project.get("preferred_variant_key"):
        missing.append("preferred_variant_key")
    return missing


def decide_action(
    request_text: str,
    project: Optional[dict],
    project_id: Optional[str],
    variant_key: Optional[str],
    change_item: Optional[str],
    record_match: Optional[Tuple[str, dict]],
) -> dict:
    """根据上下文决定 skill 的下一步动作。

    参数:
        request_text: 用户本次原始请求文本。
        project: 当前项目配置。
        project_id: 当前项目标识。
        variant_key: 当前版本目录键。
        change_item: 当前修改项。
        record_match: 命中的记录结果，格式为 `(匹配类型, 记录字典)`。

    返回:
        一个可直接写入 JSON 输出的决策字典，至少包含:
        - action
        - reason
        - message_cn
    """
    missing_fields = missing_project_fields(project)
    if missing_fields:
        return {
            "action": "need_project_init",
            "reason": "missing_project_preferences",
            "message_cn": "缺少默认项目配置，需要先补齐工程名称、编译命令或默认版本。",
            "missing_fields": missing_fields,
        }

    if not change_item:
        return {
            "action": "need_change_item",
            "reason": "change_item_unknown",
            "message_cn": "还没识别出这次修改项，需要先说明是改 EQ、宏开关还是其它配置。",
        }

    if record_match is None:
        return {
            "action": "need_location_confirmation",
            "reason": "record_not_found",
            "message_cn": "没有命中历史记录，需要先搜索源码并确认修改位置。",
        }

    match_type, record = record_match
    input_mode = record.get("input_mode")

    if input_mode == "fixed-target":
        if looks_like_explicit_target_value(request_text) or record.get("fixed_change_hint"):
            return {
                "action": "direct_apply_and_build",
                "reason": "record_matched_and_target_clear",
                "message_cn": "记录已命中且目标值明确，可以直接修改并编译。",
                "match_type": match_type,
                "record": record,
            }
        return {
            "action": "need_target_value",
            "reason": "target_value_missing",
            "message_cn": "记录已命中，但目标值不够明确，需要补一句目标值。",
            "match_type": match_type,
            "record": record,
        }

    if input_mode == "needs-values":
        if looks_like_complete_value_block(request_text):
            return {
                "action": "direct_apply_and_build",
                "reason": "record_matched_and_values_complete",
                "message_cn": "记录已命中且参数已给全，可以直接修改并编译。",
                "match_type": match_type,
                "record": record,
            }
        return {
            "action": "need_value_input",
            "reason": "values_missing",
            "message_cn": "记录已命中，但这次参数还不完整，需要先补参数。",
            "match_type": match_type,
            "record": record,
        }

    return {
        "action": "need_location_confirmation",
        "reason": "record_input_mode_unknown",
        "message_cn": "记录命中了，但输入模式不完整，建议先确认修改位置和目标。",
        "match_type": match_type,
        "record": record,
    }


def main() -> int:
    """命令行入口函数。

    返回:
        0 表示判断成功并输出 JSON。
        1 表示读取配置失败或执行失败。
    """
    parser = argparse.ArgumentParser(description="快速判断 skill 下一步动作。")
    parser.add_argument("--request-text", required=True, help="用户本次请求文本。")
    parser.add_argument("--change-item", help="可选；手动指定 change_item。")
    parser.add_argument("--project-id", help="可选；手动指定项目标识。")
    parser.add_argument("--variant-key", help="可选；手动指定版本目录。")
    parser.add_argument(
        "--registry",
        default="references/project-registry.json",
        help="project-registry.json 路径。",
    )
    parser.add_argument(
        "--records",
        default="references/change-records.json",
        help="change-records.json 路径。",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve()
    records_path = Path(args.records).resolve()

    try:
        registry = load_json(
            registry_path,
            {"version": 2, "default_project_id": None, "projects": []},
        )
        records_data = load_json(
            records_path,
            {"version": 2, "records": []},
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "load_failed",
                    "message_cn": f"读取配置失败：{exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    request_text = args.request_text.strip()
    project_id = resolve_default_project_id(registry, args.project_id)
    project = resolve_project(registry, project_id)
    variant_key = resolve_variant_key(project, args.variant_key)
    change_item = args.change_item or infer_change_item(request_text)
    records = records_data.get("records", [])
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

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
