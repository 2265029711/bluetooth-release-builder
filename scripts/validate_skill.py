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
from pycompat import print_text
from pycompat import read_text

EXPECTED_SKILL_NAME = "bluetooth-release-builder"
LEGACY_DIRECTORY_NAMES = set(["version-skills"])
ALLOWED_FRONTMATTER_KEYS = set(["name", "description"])
ALLOWED_CHANGE_ITEMS = set(["default-eq", "macro-toggle", "other-config"])
ALLOWED_INPUT_MODES = set(["needs-values", "fixed-target"])
REQUIRED_INTERFACE_FIELDS = ("display_name", "short_description", "default_prompt")
REQUIRED_REFERENCE_FILES = (
    "release-workflow.md",
    "change-catalog.md",
    "project-registry.json",
    "change-records.json",
)
REQUIRED_SCRIPT_FILES = (
    "bootstrap_context.py",
    "find_change_record.py",
    "pycompat.py",
    "resolve_release_bin.py",
    "save_project_preference.py",
    "save_change_record.py",
    "validate_skill.py",
)
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def is_non_empty_string(value):
    return isinstance(value, STRING_TYPES) and bool(value)


def extract_frontmatter(text):
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 必须以 YAML frontmatter 开头。")
    return match.group(1)


def parse_simple_frontmatter(block):
    data = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            raise ValueError(u"frontmatter 行格式无效：{}".format(raw_line))

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(u"frontmatter 行格式无效：{}".format(raw_line))

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        data[key] = value

    return data


def validate_skill_md(skill_dir):
    errors = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        return [u"缺少 SKILL.md。"], None

    text = read_text(skill_md, encoding="utf-8")
    try:
        frontmatter = parse_simple_frontmatter(extract_frontmatter(text))
    except ValueError as exc:
        return [u"{}".format(exc)], None

    unexpected = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    if unexpected:
        errors.append(u"SKILL.md frontmatter 包含未允许的键：" + ", ".join(unexpected) + u"。")

    name = frontmatter.get("name", "").strip()
    if not name:
        errors.append(u"SKILL.md frontmatter 必须包含非空的 name。")
    elif not re.match(r"^[a-z0-9-]+\Z", name):
        errors.append(u"skill 名称必须使用小写连字符格式。")
    elif name.startswith("-") or name.endswith("-") or "--" in name:
        errors.append(u"skill 名称不能以连字符开头或结尾，也不能包含连续的 '--'。")
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(
            u"skill 名称过长：{} 个字符（上限 {}）。".format(len(name), MAX_NAME_LENGTH)
        )
    elif name != EXPECTED_SKILL_NAME:
        errors.append(u"skill 名称必须是 '{}'。".format(EXPECTED_SKILL_NAME))

    directory_name = os.path.basename(os.path.normpath(skill_dir))
    if directory_name != EXPECTED_SKILL_NAME and directory_name not in LEGACY_DIRECTORY_NAMES:
        errors.append(
            u"目录名必须是 '{}'，或临时兼容旧目录名；当前是 '{}'。".format(
                EXPECTED_SKILL_NAME,
                directory_name,
            )
        )

    description = frontmatter.get("description", "").strip()
    if not description:
        errors.append(u"SKILL.md frontmatter 必须包含非空的 description。")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            u"description 过长：{} 个字符（上限 {}）。".format(
                len(description),
                MAX_DESCRIPTION_LENGTH,
            )
        )
    elif "<" in description or ">" in description:
        errors.append(u"description 不能包含尖括号。")

    if "[TODO" in text:
        errors.append(u"SKILL.md 仍包含 TODO 占位内容。")
    if "$bluetooth-release-builder" not in text:
        errors.append(u"SKILL.md 应包含 $bluetooth-release-builder。")

    return errors, name or None


def extract_interface_value(text, field):
    patterns = [
        r'(?m)^\s{{2}}{}:\s+"([^"]+)"\s*$'.format(re.escape(field)),
        r"(?m)^\s{{2}}{}:\s+'([^']+)'\s*$".format(re.escape(field)),
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def validate_openai_yaml(skill_dir, skill_name):
    errors = []
    openai_yaml = os.path.join(skill_dir, "agents", "openai.yaml")
    if not os.path.exists(openai_yaml):
        return [u"缺少 agents/openai.yaml。"]

    text = read_text(openai_yaml, encoding="utf-8")
    if not re.search(r"(?m)^interface:\s*$", text):
        errors.append(u"agents/openai.yaml 必须包含 interface 段。")

    values = {}
    for field in REQUIRED_INTERFACE_FIELDS:
        value = extract_interface_value(text, field)
        if value is None:
            errors.append(u"缺少带引号的 interface 字段：{}。".format(field))
            continue
        values[field] = value

    short_description = values.get("short_description")
    if short_description is not None and not (25 <= len(short_description) <= 64):
        errors.append(u"short_description 长度必须在 25 到 64 个字符之间。")

    default_prompt = values.get("default_prompt")
    if skill_name and default_prompt and ("${}".format(skill_name) not in default_prompt):
        errors.append(u"default_prompt 必须以 ${} 的形式提到 skill 名。".format(skill_name))

    return errors


def validate_project_registry(skill_dir):
    path = os.path.join(skill_dir, "references", "project-registry.json")
    try:
        data = load_json_file(path)
    except (IOError, OSError, JSONDecodeError) as exc:
        return [u"project-registry.json 读取失败：{}".format(exc)]

    errors = []
    if not isinstance(data.get("version"), int):
        errors.append(u"project-registry.json 必须包含整数类型的 version。")

    default_project_id = data.get("default_project_id")
    if default_project_id is not None and not is_non_empty_string(default_project_id):
        errors.append(u"project-registry.json 的 default_project_id 必须是字符串或 null。")

    projects = data.get("projects")
    if not isinstance(projects, list):
        return errors + [u"project-registry.json 必须包含 projects 列表。"]

    for index, project in enumerate(projects):
        label = u"project-registry.json projects[{}]".format(index)
        if not isinstance(project, dict):
            errors.append(u"{} 必须是对象。".format(label))
            continue

        for key in (
            "project_id",
            "display_name",
            "root_hint",
            "build_command",
            "artifact_root",
            "variants",
        ):
            if key not in project:
                errors.append(u"{} 缺少键：{}。".format(label, key))

        if not is_non_empty_string(project.get("project_id")):
            errors.append(u"{} 的 project_id 必须是非空字符串。".format(label))
        if not is_non_empty_string(project.get("artifact_root")):
            errors.append(u"{} 的 artifact_root 必须是非空字符串。".format(label))

        preferred_variant_key = project.get("preferred_variant_key")
        if preferred_variant_key is not None and not is_non_empty_string(preferred_variant_key):
            errors.append(u"{} 的 preferred_variant_key 必须是字符串或 null。".format(label))

        variants = project.get("variants")
        if not isinstance(variants, list):
            errors.append(u"{} 的 variants 必须是列表。".format(label))
            continue

        for variant_index, variant in enumerate(variants):
            variant_label = u"{} variants[{}]".format(label, variant_index)
            if not isinstance(variant, dict):
                errors.append(u"{} 必须是对象。".format(variant_label))
                continue

            for key in ("variant_key", "artifact_dir", "source_bin_name"):
                if key not in variant:
                    errors.append(u"{} 缺少键：{}。".format(variant_label, key))

            if not is_non_empty_string(variant.get("variant_key")):
                errors.append(u"{} 的 variant_key 必须是非空字符串。".format(variant_label))
            if not is_non_empty_string(variant.get("artifact_dir")):
                errors.append(u"{} 的 artifact_dir 必须是非空字符串。".format(variant_label))

            source_bin_name = variant.get("source_bin_name")
            if source_bin_name is not None and not isinstance(source_bin_name, STRING_TYPES):
                errors.append(u"{} 的 source_bin_name 必须是字符串或 null。".format(variant_label))

    return errors


def validate_change_records(skill_dir):
    path = os.path.join(skill_dir, "references", "change-records.json")
    try:
        data = load_json_file(path)
    except (IOError, OSError, JSONDecodeError) as exc:
        return [u"change-records.json 读取失败：{}".format(exc)]

    errors = []
    if not isinstance(data.get("version"), int):
        errors.append(u"change-records.json 必须包含整数类型的 version。")

    records = data.get("records")
    if not isinstance(records, list):
        return errors + [u"change-records.json 必须包含 records 列表。"]

    for index, record in enumerate(records):
        label = u"change-records.json records[{}]".format(index)
        if not isinstance(record, dict):
            errors.append(u"{} 必须是对象。".format(label))
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
                errors.append(u"{} 缺少键：{}。".format(label, key))

        if record.get("change_item") not in ALLOWED_CHANGE_ITEMS:
            errors.append(
                u"{} 的 change_item 必须是以下之一：{}。".format(
                    label,
                    ", ".join(sorted(ALLOWED_CHANGE_ITEMS)),
                )
            )
        if record.get("match_scope") not in set(["variant", "common"]):
            errors.append(u"{} 的 match_scope 必须是 'variant' 或 'common'。".format(label))

        for list_key in ("files", "symbols", "change_tags"):
            value = record.get(list_key)
            if not isinstance(value, list) or not value:
                errors.append(u"{} 的 {} 必须是非空字符串列表。".format(label, list_key))
                continue

            if not all(is_non_empty_string(item) for item in value):
                errors.append(u"{} 的 {} 必须是非空字符串列表。".format(label, list_key))

        for text_key in (
            "project_id",
            "variant_key",
            "edit_intent",
            "last_confirmed_at",
            "confirmation_note",
        ):
            if not is_non_empty_string(record.get(text_key)):
                errors.append(u"{} 的 {} 必须是非空字符串。".format(label, text_key))

        input_mode = record.get("input_mode")
        if input_mode is not None and input_mode not in ALLOWED_INPUT_MODES:
            errors.append(
                u"{} 的 input_mode 必须是以下之一：{}。".format(
                    label,
                    ", ".join(sorted(ALLOWED_INPUT_MODES)),
                )
            )

        for optional_text_key in (
            "value_prompt",
            "value_format_hint",
            "fixed_change_hint",
            "last_value_text",
        ):
            value = record.get(optional_text_key)
            if value is not None and not is_non_empty_string(value):
                errors.append(
                    u"{} 的 {} 必须是非空字符串或不提供。".format(label, optional_text_key)
                )

        if input_mode == "needs-values" and not is_non_empty_string(record.get("value_prompt")):
            errors.append(u"{} 在 input_mode 为 needs-values 时必须提供 value_prompt。".format(label))

    return errors


def validate_file_layout(skill_dir):
    errors = []
    for filename in REQUIRED_REFERENCE_FILES:
        path = os.path.join(skill_dir, "references", filename)
        if not os.path.exists(path):
            errors.append(u"缺少 references/{}。".format(filename))

    for filename in REQUIRED_SCRIPT_FILES:
        path = os.path.join(skill_dir, "scripts", filename)
        if not os.path.exists(path):
            errors.append(u"缺少 scripts/{}。".format(filename))

    return errors


def main():
    parser = argparse.ArgumentParser(description=u"校验蓝牙版本发布 skill。")
    parser.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help=u"skill 根目录路径，默认是当前目录。",
    )
    args = normalize_namespace(parser.parse_args())

    skill_dir = os.path.abspath(args.skill_dir)
    if not os.path.exists(skill_dir):
        print_text(u"未找到 skill 目录：{}".format(skill_dir))
        return 1

    if not os.path.isdir(skill_dir):
        print_text(u"路径不是目录：{}".format(skill_dir))
        return 1

    skill_errors, skill_name = validate_skill_md(skill_dir)
    errors = []
    errors.extend(skill_errors)
    errors.extend(validate_openai_yaml(skill_dir, skill_name))
    errors.extend(validate_file_layout(skill_dir))

    references_dir = os.path.join(skill_dir, "references")
    if os.path.exists(references_dir):
        errors.extend(validate_project_registry(skill_dir))
        errors.extend(validate_change_records(skill_dir))

    if errors:
        print_text(u"Skill 结构校验失败：")
        for error in errors:
            print_text(u"- {}".format(error))
        return 1

    print_text(u"Skill 结构合法：{}".format(skill_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
