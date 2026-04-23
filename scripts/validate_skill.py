#!/usr/bin/env python3
"""
校验蓝牙版本发布 skill 的目录结构和索引文件。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_SKILL_NAME = "bluetooth-release-builder"
LEGACY_DIRECTORY_NAMES = {"version-skills"}
ALLOWED_FRONTMATTER_KEYS = {"name", "description"}
ALLOWED_CHANGE_ITEMS = {"default-eq", "macro-toggle", "other-config"}
ALLOWED_INPUT_MODES = {"needs-values", "fixed-target"}
REQUIRED_INTERFACE_FIELDS = ("display_name", "short_description", "default_prompt")
REQUIRED_REFERENCE_FILES = (
    "release-workflow.md",
    "change-catalog.md",
    "project-registry.json",
    "change-records.json",
)
REQUIRED_SCRIPT_FILES = (
    "validate_skill.py",
    "find_change_record.py",
    "resolve_release_bin.py",
    "save_project_preference.py",
    "save_change_record.py",
)
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def extract_frontmatter(text: str) -> str:
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 必须以 YAML frontmatter 开头。")
    return match.group(1)


def parse_simple_frontmatter(block: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter 行格式无效：{raw_line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"frontmatter 行格式无效：{raw_line}")
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        data[key] = value
    return data


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_skill_md(skill_dir: Path) -> tuple[list[str], str | None]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ["缺少 SKILL.md。"], None

    text = skill_md.read_text(encoding="utf-8")
    try:
        frontmatter = parse_simple_frontmatter(extract_frontmatter(text))
    except ValueError as exc:
        return [str(exc)], None

    unexpected = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    if unexpected:
        errors.append("SKILL.md frontmatter 包含未允许的键：" + ", ".join(unexpected) + "。")

    name = frontmatter.get("name", "").strip()
    if not name:
        errors.append("SKILL.md frontmatter 必须包含非空的 name。")
    elif not re.fullmatch(r"[a-z0-9-]+", name):
        errors.append("skill 名称必须使用小写连字符格式。")
    elif name.startswith("-") or name.endswith("-") or "--" in name:
        errors.append("skill 名称不能以连字符开头或结尾，也不能包含连续的 '--'。")
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(f"skill 名称过长：{len(name)} 个字符（上限 {MAX_NAME_LENGTH}）。")
    elif name != EXPECTED_SKILL_NAME:
        errors.append(f"skill 名称必须是 '{EXPECTED_SKILL_NAME}'。")

    directory_name = skill_dir.name
    if directory_name != EXPECTED_SKILL_NAME and directory_name not in LEGACY_DIRECTORY_NAMES:
        errors.append(
            f"目录名必须是 '{EXPECTED_SKILL_NAME}'，或临时兼容旧目录名；当前是 '{directory_name}'。"
        )

    description = frontmatter.get("description", "").strip()
    if not description:
        errors.append("SKILL.md frontmatter 必须包含非空的 description。")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"description 过长：{len(description)} 个字符（上限 {MAX_DESCRIPTION_LENGTH}）。"
        )
    elif "<" in description or ">" in description:
        errors.append("description 不能包含尖括号。")

    if "[TODO" in text:
        errors.append("SKILL.md 仍包含 TODO 占位内容。")
    if "$bluetooth-release-builder" not in text:
        errors.append("SKILL.md 应包含 $bluetooth-release-builder。")

    return errors, name or None


def extract_interface_value(text: str, field: str) -> str | None:
    patterns = [
        rf'(?m)^\s{{2}}{re.escape(field)}:\s+"([^"]+)"\s*$',
        rf"(?m)^\s{{2}}{re.escape(field)}:\s+'([^']+)'\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def validate_openai_yaml(skill_dir: Path, skill_name: str | None) -> list[str]:
    errors: list[str] = []
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        return ["缺少 agents/openai.yaml。"]

    text = openai_yaml.read_text(encoding="utf-8")
    if not re.search(r"(?m)^interface:\s*$", text):
        errors.append("agents/openai.yaml 必须包含 interface 段。")

    values: dict[str, str] = {}
    for field in REQUIRED_INTERFACE_FIELDS:
        value = extract_interface_value(text, field)
        if value is None:
            errors.append(f"缺少带引号的 interface 字段：{field}。")
            continue
        values[field] = value

    short_description = values.get("short_description")
    if short_description is not None and not (25 <= len(short_description) <= 64):
        errors.append("short_description 长度必须在 25 到 64 个字符之间。")

    default_prompt = values.get("default_prompt")
    if skill_name and default_prompt and f"${skill_name}" not in default_prompt:
        errors.append("default_prompt 必须以 $" + skill_name + " 的形式提到 skill 名。")

    return errors


def validate_project_registry(skill_dir: Path) -> list[str]:
    path = skill_dir / "references" / "project-registry.json"
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        return [f"project-registry.json 不是合法的 JSON：{exc}"]

    errors: list[str] = []
    if not isinstance(data.get("version"), int):
        errors.append("project-registry.json 必须包含整数类型的 version。")

    default_project_id = data.get("default_project_id")
    if default_project_id is not None and (not isinstance(default_project_id, str) or not default_project_id):
        errors.append("project-registry.json 的 default_project_id 必须是字符串或 null。")

    projects = data.get("projects")
    if not isinstance(projects, list):
        return errors + ["project-registry.json 必须包含 projects 列表。"]

    for index, project in enumerate(projects):
        label = f"project-registry.json projects[{index}]"
        if not isinstance(project, dict):
            errors.append(f"{label} 必须是对象。")
            continue
        for key in ("project_id", "display_name", "root_hint", "build_command", "artifact_root", "variants"):
            if key not in project:
                errors.append(f"{label} 缺少键：{key}。")
        if not isinstance(project.get("project_id"), str) or not project.get("project_id"):
            errors.append(f"{label} 的 project_id 必须是非空字符串。")
        if not isinstance(project.get("artifact_root"), str) or not project.get("artifact_root"):
            errors.append(f"{label} 的 artifact_root 必须是非空字符串。")
        preferred_variant_key = project.get("preferred_variant_key")
        if preferred_variant_key is not None and (
            not isinstance(preferred_variant_key, str) or not preferred_variant_key
        ):
            errors.append(f"{label} 的 preferred_variant_key 必须是字符串或 null。")
        variants = project.get("variants")
        if not isinstance(variants, list):
            errors.append(f"{label} 的 variants 必须是列表。")
            continue
        for variant_index, variant in enumerate(variants):
            variant_label = f"{label} variants[{variant_index}]"
            if not isinstance(variant, dict):
                errors.append(f"{variant_label} 必须是对象。")
                continue
            for key in ("variant_key", "artifact_dir", "source_bin_name"):
                if key not in variant:
                    errors.append(f"{variant_label} 缺少键：{key}。")
            if not isinstance(variant.get("variant_key"), str) or not variant.get("variant_key"):
                errors.append(f"{variant_label} 的 variant_key 必须是非空字符串。")
            if not isinstance(variant.get("artifact_dir"), str) or not variant.get("artifact_dir"):
                errors.append(f"{variant_label} 的 artifact_dir 必须是非空字符串。")
            source_bin_name = variant.get("source_bin_name")
            if source_bin_name is not None and not isinstance(source_bin_name, str):
                errors.append(f"{variant_label} 的 source_bin_name 必须是字符串或 null。")
    return errors


def validate_change_records(skill_dir: Path) -> list[str]:
    path = skill_dir / "references" / "change-records.json"
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        return [f"change-records.json 不是合法的 JSON：{exc}"]

    errors: list[str] = []
    if not isinstance(data.get("version"), int):
        errors.append("change-records.json 必须包含整数类型的 version。")

    records = data.get("records")
    if not isinstance(records, list):
        return errors + ["change-records.json 必须包含 records 列表。"]

    for index, record in enumerate(records):
        label = f"change-records.json records[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} 必须是对象。")
            continue
        for key in (
            "project_id",
            "variant_key",
            "change_item",
            "match_scope",
            "files",
            "symbols",
            "edit_intent",
            "change_tags",
            "last_confirmed_at",
            "confirmation_note",
        ):
            if key not in record:
                errors.append(f"{label} 缺少键：{key}。")
        if record.get("change_item") not in ALLOWED_CHANGE_ITEMS:
            errors.append(f"{label} 的 change_item 必须是以下之一：{', '.join(sorted(ALLOWED_CHANGE_ITEMS))}。")
        if record.get("match_scope") not in {"variant", "common"}:
            errors.append(f"{label} 的 match_scope 必须是 'variant' 或 'common'。")
        for list_key in ("files", "symbols", "change_tags"):
            value = record.get(list_key)
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                errors.append(f"{label} 的 {list_key} 必须是非空字符串列表。")
        for text_key in ("project_id", "variant_key", "edit_intent", "last_confirmed_at", "confirmation_note"):
            value = record.get(text_key)
            if not isinstance(value, str) or not value:
                errors.append(f"{label} 的 {text_key} 必须是非空字符串。")
        input_mode = record.get("input_mode")
        if input_mode is not None and input_mode not in ALLOWED_INPUT_MODES:
            errors.append(
                f"{label} 的 input_mode 必须是以下之一：{', '.join(sorted(ALLOWED_INPUT_MODES))}。"
            )
        for optional_text_key in ("value_prompt", "value_format_hint", "fixed_change_hint", "last_value_text"):
            value = record.get(optional_text_key)
            if value is not None and (not isinstance(value, str) or not value):
                errors.append(f"{label} 的 {optional_text_key} 必须是非空字符串或不提供。")
        if input_mode == "needs-values" and not isinstance(record.get("value_prompt"), str):
            errors.append(f"{label} 在 input_mode 为 needs-values 时必须提供 value_prompt。")
    return errors


def validate_file_layout(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    for filename in REQUIRED_REFERENCE_FILES:
        path = skill_dir / "references" / filename
        if not path.exists():
            errors.append(f"缺少 references/{filename}。")
    for filename in REQUIRED_SCRIPT_FILES:
        path = skill_dir / "scripts" / filename
        if not path.exists():
            errors.append(f"缺少 scripts/{filename}。")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="校验蓝牙版本发布 skill。")
    parser.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="skill 根目录路径，默认为当前目录。",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.exists():
        print(f"未找到 skill 目录：{skill_dir}")
        return 1
    if not skill_dir.is_dir():
        print(f"路径不是目录：{skill_dir}")
        return 1

    skill_errors, skill_name = validate_skill_md(skill_dir)
    errors = []
    errors.extend(skill_errors)
    errors.extend(validate_openai_yaml(skill_dir, skill_name))
    errors.extend(validate_file_layout(skill_dir))

    references_dir = skill_dir / "references"
    if references_dir.exists():
        errors.extend(validate_project_registry(skill_dir))
        errors.extend(validate_change_records(skill_dir))

    if errors:
        print("Skill 结构校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Skill 结构合法：{skill_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
