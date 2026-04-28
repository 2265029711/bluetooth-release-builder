---
name: "bluetooth-release-builder"
description: "用于蓝牙嵌入式工程的版本释放与差异配置处理。适用于首次用中文初始化项目偏好、持久化保存默认项目与默认版本、区分需要贴参数值和固定目标修改两类变更、按最小改动原则只修改明确指定的参数、优先用 scripts/bootstrap_context.py 快速判断是否可直接修改并编译、同一文件内合并处理多处目标、完整读取目标源码文件、查找 default EQ 与宏开关等修改位置，并在结束时汇总修改位置与修改内容。"
---

# 蓝牙版本发布助手

处理蓝牙嵌入式项目中“同一工程、不同版本释放”的常见动作：自动初始化项目偏好、中文询问缺失信息、区分“需要贴参数”和“固定目标修改”、按最小改动原则只修改明确指定的参数、优先用 skill 自身目录下的 `scripts/bootstrap_context.py` 快速判断下一步动作、在信息充分时直接修改并编译、同一文件内合并处理多处目标、记住默认项目和默认版本、完整读取目标源码文件、找修改点，并在结束时汇总修改位置与修改内容。

## 路径规则
1. 当前工作目录通常是用户工程目录，不是 skill 目录。
2. 运行任何 bundled Python 脚本时，必须使用 skill 自身目录下的绝对路径；skill 根目录就是当前这个 `SKILL.md` 所在目录。
3. 不要在工程目录里直接执行 `python scripts/bootstrap_context.py`、`python scripts/save_project_preference.py` 这类相对路径命令，因为那会指向工程自己的 `scripts/`。
4. 推荐写法：
   - `python "<skill-root>/scripts/bootstrap_context.py" --request-text "<用户原话>"`
   - `python "<skill-root>/scripts/save_project_preference.py" ...`
   - `python "<skill-root>/scripts/find_change_record.py" ...`
   - `python "<skill-root>/scripts/save_change_record.py" ...`
   - `python "<skill-root>/scripts/resolve_release_bin.py" ...`

## 快速开始

1. 用户显式调用 `$bluetooth-release-builder` 时，先运行 skill 自身目录下的 `scripts/bootstrap_context.py`，把这次请求一次性判断成：
   - `need_project_init`
   - `need_change_item`
   - `need_location_confirmation`
   - `need_value_input`
   - `need_target_value`
   - `direct_apply_and_build`
2. 若返回 `direct_apply_and_build`，直接修改并编译，不再额外确认。
3. 若返回其它动作，只补问当前真正缺的一项信息，而且必须用中文短句。
4. 后续再次调用时，优先复用已经保存的默认项目、默认版本目录、默认源 bin；除非用户明确要求变更。
5. 始终遵循“最小改动”原则：只修改用户明确要求的参数或目标值，不改其它字段，不动注释，不顺手整理格式，不扩散到无关逻辑。
6. 如果同一次请求命中了同一个文件内的多处修改点，先按文件合并处理，再一次性修改，不要按行或按宏逐条打断。

## 工作流程

1. 启动时优先调用：
   - `python "<skill-root>/scripts/bootstrap_context.py" --request-text "<用户原话>"`
2. 若返回 `need_project_init`，只补问缺失项，建议短句：
   - 这个工程我怎么称呼？
   - 标准编译命令发我一下。
   - 常用版本目录是哪个？例如 `DPD2603A`
3. 用 skill 自身目录下的 `scripts/save_project_preference.py` 保存用户输入，并把当前项目设为默认首选项。
4. 若返回 `need_change_item`，只问这次是改 EQ、宏开关还是其它配置。
5. 若返回 `need_location_confirmation`，才搜索工程源码并把候选位置与理由交给用户确认。
6. 若返回 `need_value_input`，只补问一次参数。
7. 若返回 `need_target_value`，只补问一次目标值。
8. 若返回 `direct_apply_and_build`：
   - 读取目标文件完整内容
   - 同一文件内多处修改一次性完成
   - 直接执行编译
   - 最后汇总修改位置和编译结果
9. 找到目标文件后，必须读取完整文件内容；如果文件很长，可以分段继续读取，但必须一直读到文件结尾，不要只看前 1000 行或第一个片段。
10. 编译完成后，默认只汇总：
   - 修改文件路径
   - 对应符号、宏名或函数
   - 改了什么值
   - 编译是否成功
11. 只有当用户明确要求发布命名、源 bin、出版本文件名时，才继续执行 skill 自身目录下的 `scripts/resolve_release_bin.py` 和命名建议流程。
12. 把已确认的修改位置写入 `references/change-records.json`；优先使用 skill 自身目录下的 `scripts/save_change_record.py` 持久化，不要只停留在对话里。

## 确认规则

- 所有向用户的提问都必须使用中文。
- 若 `bootstrap_context.py` 已返回 `direct_apply_and_build`，不要重复确认。
- 不要在记录缺失时直接猜测修改点。
- 不要把 `out/` 根目录直接当作 bin 文件目录；先定位 `out/<variant_key>/`。
- 对 `needs-values` 类型修改，不要用历史值替代这次用户输入；除非用户明确说“按上次参数”。
- 不要只看文件前半段；定位到目标文件后必须确认已经读到完整文件。
- 结束时必须列出修改位置以及每处改了什么，不能只说“已修改完成”。
- 只改用户明确指定的参数或值，不要顺手改相邻字段。
- 除非用户明确要求，否则不要改注释、空行、缩进、字段顺序或其它与本次修改无关的内容。
- 若同一文件内有多处已确认修改，必须一次性落代码，不要分多轮修改同一文件。
- 只有在位置不明确、候选冲突、参数不完整时，才允许进入确认分支。

## 资源说明

- `scripts/bootstrap_context.py`: 快速判断当前请求是否可直接修改并编译。
- `references/release-workflow.md`: 详细流程、确认点、命名规则。
- `references/change-catalog.md`: 人工可读的常见修改项与示例。
- `references/project-registry.json`: 项目、构建入口、版本输出目录、默认源 bin。
- `references/change-records.json`: 版本差异修改位置的结构化记录。
- `scripts/save_project_preference.py`: 保存或更新默认项目、默认版本、默认源 bin。
- `scripts/save_change_record.py`: 保存或更新已确认的修改位置记录。
- `scripts/find_change_record.py`: 查询精确记录与 `common` 回退记录。
- `scripts/resolve_release_bin.py`: 定位版本目录中的默认源 bin，并生成发布名建议。
- `scripts/validate_skill.py`: 校验 skill 结构、JSON 索引和 `$bluetooth-release-builder` 引用。
