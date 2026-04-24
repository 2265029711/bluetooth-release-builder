# bluetooth-release-builder

> Note: the scripts now support both `python` 2.7 and 3.x runtimes.

面向蓝牙嵌入式版本出具流程的 Skill。

这个 skill 主要解决同一套蓝牙固件工程因默认 EQ、宏开关、配置差异而需要反复出不同版本包的问题。它会优先复用已经保存的项目首选项和历史修改记录，在信息足够明确时直接修改并编译；在信息不完整时，只用中文补问当前真正缺失的那一项。

## 适用场景

- 修改 `default eq` 一类需要整组参数输入的配置。
- 修改宏开关一类目标明确、不需要额外解释的配置。
- 对同一项目的不同版本目录，例如 `out/DPD2603A/`，持续复用默认设置。
- 记录“某类修改通常改哪个文件、哪个符号、怎么改”，减少重复确认。

## 核心能力

- 自动初始化项目首选项，例如项目名称、编译命令、默认版本目录。
- 区分“需要用户贴参数值”和“固定目标修改”两种输入模式。
- 优先命中历史记录，缺记录时再搜索源码并询问用户确认。
- 定位目标文件后读取完整内容，不只看前面一小段。
- 同一文件内的多处目标一次性合并修改，避免逐条确认。
- 编译结束后输出修改位置、修改内容和编译结果。
- 仅提供发布文件名建议，不自动重命名产物。

## 目录结构

```text
bluetooth-release-builder/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── change-catalog.md
│   ├── change-records.json
│   ├── project-registry.json
│   └── release-workflow.md
└── scripts/
    ├── bootstrap_context.py
    ├── find_change_record.py
    ├── pycompat.py
    ├── resolve_release_bin.py
    ├── save_change_record.py
    ├── save_project_preference.py
    └── validate_skill.py
```

## 文件说明

### Skill 元信息

- `SKILL.md`
  - skill 的主说明文件，定义触发条件、工作流程和确认规则。
- `agents/openai.yaml`
  - skill 在 agent 界面里的展示信息，例如名称、简介和默认提示词。

### references

- `references/project-registry.json`
  - 保存默认项目、编译命令、默认版本目录、默认源 bin 等首选项。
- `references/change-records.json`
  - 保存已经确认过的修改位置、符号、修改意图和输入模式。
- `references/change-catalog.md`
  - 人工可读的常见修改项汇总。
- `references/release-workflow.md`
  - 更详细的发布流程说明。

### scripts

- `scripts/bootstrap_context.py`
  - 启动阶段的快速判断脚本，用来决定这次请求是直接修改还是先补问信息。
- `scripts/find_change_record.py`
  - 按项目、版本、修改项查找历史修改记录。
- `scripts/save_project_preference.py`
  - 保存或更新默认项目、默认版本、默认源 bin 等首选项。
- `scripts/save_change_record.py`
  - 保存已经确认过的修改位置记录。
- `scripts/resolve_release_bin.py`
  - 在版本目录下定位候选 `.bin`，并生成发布文件名建议。
- `scripts/validate_skill.py`
  - 校验 skill 结构、JSON 文件结构和元信息是否完整。

## 使用方式

在 agent 中直接调用：

```text
@bluetooth-release-builder
```

或者按当前环境支持的调用格式：

```text
$bluetooth-release-builder
```

## 典型流程

1. 首次调用时，skill 会先检查是否已经保存默认项目信息。
2. 如果还没有，就用中文询问你最少必要的信息：
   - 工程怎么称呼
   - 编译命令是什么
   - 默认版本目录是什么，例如 `DPD2603A`
3. 这些信息会写入 `references/project-registry.json`，后续默认直接复用。
4. 每次收到新请求时，先由 `scripts/bootstrap_context.py` 判断属于哪类修改：
   - `default-eq`
   - `macro-toggle`
   - `other-config`
5. 如果历史记录已命中，而且你给的信息已经足够明确，就直接修改并编译。
6. 如果是 EQ 这类需要参数的修改，但你还没贴参数，就只补问参数。
7. 如果是宏这类固定目标修改，而且目标值已经明确，例如 `ID_LOG = 0`，就不再重复确认。
8. 修改结束后，skill 会输出：
   - 改了哪些文件
   - 对应改了哪些符号、宏或配置块
   - 每一处具体改了什么
   - 编译是否成功

## 输入示例

### 需要贴参数的修改

```text
帮我修改 default eq，参数如下：
.gain1 = xx
.num = xx
param = (...)
```

### 不需要额外补值的修改

```text
帮我改成明文 log，只用把 VIVO_ID_LOG = 0 即可
```

## 数据持久化

skill 会把用户确认过的信息持久化到 `references/` 目录下：

- 项目首选项保存在 `project-registry.json`
- 修改位置记录保存在 `change-records.json`

只要你不主动修改，后续都会默认按这些首选项继续工作。

## 校验命令

校验 skill 结构：

```bash
python scripts/validate_skill.py .
```

检查 Python 语法：

```bash
python -m py_compile scripts/pycompat.py scripts/bootstrap_context.py scripts/find_change_record.py scripts/resolve_release_bin.py scripts/save_change_record.py scripts/save_project_preference.py scripts/validate_skill.py
```

## 说明

- `__pycache__` 是 Python 运行时自动生成的缓存目录，不属于 skill 必需内容，可以删除。
- 所有 JSON 文件建议使用 UTF-8 编码保存。
- 如果你要发布到 GitHub，建议再补一个开源许可证文件。
