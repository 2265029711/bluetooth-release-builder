---
name: "bluetooth-release-builder"
description: "用于蓝牙嵌入式工程的版本释放与差异配置处理。适用于首次用中文初始化项目偏好、持久化保存默认项目与默认版本、区分需要贴参数值和固定目标修改两类变更、按最小改动原则只修改明确指定的参数、完整读取目标源码文件、查找 default EQ 与宏开关等修改位置、确认 out 下对应版本目录的 bin 文件、只给出发布命名建议，并在结束时汇总修改位置与修改内容。"
---

# 蓝牙版本发布助手

处理蓝牙嵌入式项目中“同一工程、不同版本释放”的常见动作：自动初始化项目偏好、中文询问缺失信息、区分“需要贴参数”和“固定目标修改”、按最小改动原则只修改明确指定的参数、记住默认项目和默认版本、完整读取目标源码文件、找修改点、确认差异配置、编译、定位 `out/<variant_key>/` 下的目标 bin、只生成发布名建议，并在确认后更新记录。

## 快速开始

1. 用户显式调用 `$bluetooth-release-builder` 时，先读取 `references/project-registry.json`。
2. 若没有默认项目，或默认项目缺少 `build_command`、默认版本等必要信息，只问缺失项，且必须用中文询问。
3. 询问完成后，立刻用 `scripts/save_project_preference.py` 持久化保存，并把这次确认的项目设为默认项目。
4. 后续再次调用时，优先复用已经保存的默认项目、默认版本目录、默认源 bin；除非用户明确要求变更。
5. 修改分两类：
   - `needs-values`：必须拿到用户给的参数块或参数值后才能改，例如 default EQ。
   - `fixed-target`：只要记录里已有固定目标，或用户已在话里说清目标值，就不要再追问参数块，例如 `VIVO_ID_LOG = 0`。
6. 始终遵循“最小改动”原则：只修改用户明确要求的参数或目标值，不改其它字段，不动注释，不顺手整理格式，不扩散到无关逻辑。
7. 只有在用户确认后，才执行代码修改、编译、写回记录；不要主动改发布 bin 文件名。

## 工作流程

1. 启动时先检查 `references/project-registry.json` 是否已有默认项目。
2. 若缺少默认项目或关键信息，只用中文问缺的内容，建议短句：
   - 这个工程我怎么称呼？
   - 标准编译命令发我一下。
   - 常用版本目录是哪个？例如 `DPD2603A`
   - 默认源 bin 是哪个？不确定的话编译后我再问。
3. 不要求用户理解 `project_id`；内部 `project_id` 由脚本自动生成并持久化。
4. 用 `scripts/save_project_preference.py` 保存用户输入，并把当前项目设为默认首选项。
5. 查修改记录时，优先读取默认项目和默认版本；若用户本次指定了新版本，则用本次版本覆盖。
6. 用 `scripts/find_change_record.py` 查询 `(project_id, variant_key, change_item)`；若未命中，再回退到 `(project_id, common, change_item)`。
7. 若仍未命中，搜索工程源码并把候选位置与理由交给用户确认。
8. 命中记录后，先看记录里的 `input_mode`：
   - `needs-values`：如果用户这次已经贴了参数，就直接使用；如果没贴，就只问一句“请把这次要改的完整参数贴给我，按代码格式直接发就行。”
   - `fixed-target`：如果记录里已有 `fixed_change_hint`，或用户消息里已经写了目标值，就不要再追问参数块。
9. 用户确认后再执行修改。
10. 找到候选文件后，必须读取完整文件内容；如果文件很长，可以分段继续读取，但必须一直读到文件结尾，不要只看前 1000 行或第一个片段。
11. 编译完成后，用 `scripts/resolve_release_bin.py` 读取默认项目、默认版本和默认源 bin；若缺失，再用中文询问并确认。
12. 若首次确认了默认源 bin，立刻再次调用 `scripts/save_project_preference.py` 写回 `source_bin_name`，作为后续默认值。
13. 根据 `variant_key + change_tags + MMDD` 生成发布名建议，例如 `DPD2603A_default_eq_0423.bin`。
14. 只给出建议文件名，不主动重命名 bin。
15. 把已确认的修改位置写入 `references/change-records.json`；优先使用 `scripts/save_change_record.py` 持久化，不要只停留在对话里。
16. 若用户只要求改某个字段，就只改那个字段；例如 bypass 只需把 `.num = 0`，就不要顺带改 `.param` 或其它 EQ 字段。
17. 最终回复必须附上“修改位置 + 修改内容摘要”，至少包含文件路径、符号/函数名、修改了什么。

## 确认规则

- 所有向用户的提问都必须使用中文。
- 若用户不知道 `project_id`，不要反问这个字段；应改问工程名称，由脚本自动生成内部 `project_id`。
- 若用户不知道 `build_command`，就直接用中文问“标准编译命令是什么”。
- 问题尽量短，一次只问当前真正缺的内容。
- 不要在记录缺失时直接猜测修改点。
- 不要在用户未确认前修改代码、运行编译。
- 不要把 `out/` 根目录直接当作 bin 文件目录；先定位 `out/<variant_key>/`。
- 默认源 bin 首次确认后再登记，后续才能直接复用。
- 只要用户没有明确要求更改，已保存的默认项目、默认版本、默认源 bin 都视为首选项并自动复用。
- 对 `needs-values` 类型修改，不要用历史值替代这次用户输入；除非用户明确说“按上次参数”。
- 不要主动改发布 bin 文件名；只输出建议名供用户决定。
- 不要只看文件前半段；定位到目标文件后必须确认已经读到完整文件。
- 结束时必须列出修改位置以及每处改了什么，不能只说“已修改完成”。
- 只改用户明确指定的参数或值，不要顺手改相邻字段。
- 除非用户明确要求，否则不要改注释、空行、缩进、字段顺序或其它与本次修改无关的内容。

## 资源说明

- `references/release-workflow.md`: 详细流程、确认点、命名规则。
- `references/change-catalog.md`: 人工可读的常见修改项与示例。
- `references/project-registry.json`: 项目、构建入口、版本输出目录、默认源 bin。
- `references/change-records.json`: 版本差异修改位置的结构化记录。
- `scripts/save_project_preference.py`: 保存或更新默认项目、默认版本、默认源 bin。
- `scripts/save_change_record.py`: 保存或更新已确认的修改位置记录。
- `scripts/find_change_record.py`: 查询精确记录与 `common` 回退记录。
- `scripts/resolve_release_bin.py`: 定位版本目录中的默认源 bin，并生成发布名建议。
- `scripts/validate_skill.py`: 校验 skill 结构、JSON 索引和 `$bluetooth-release-builder` 引用。
