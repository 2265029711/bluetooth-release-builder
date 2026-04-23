# 发布流程

这个 skill 固定服务于“通过差异配置产出不同版本 bin”的流程，适用于蓝牙嵌入式工程。

## 初始化规则

首次调用时，先检查 `references/project-registry.json`：

1. 若不存在默认项目，或默认项目缺少 `build_command`、默认版本目录、默认源 bin 等关键信息，必须先初始化。
2. 初始化提问必须全程使用中文。
3. 不要要求用户理解 `project_id` 这类内部字段；应询问“工程名称”“编译命令”“常用版本目录”等用户能直接回答的信息。
4. 用户回答后，立刻调用 `scripts/save_project_preference.py` 存入 `references/project-registry.json`。
5. 只要用户不要求更改，后续默认读取上次保存的首选项。

## 建议询问内容

- 这个工程我怎么称呼？
- 标准编译命令发我一下。
- 常用版本目录是哪个？例如 `DPD2603A`
- 默认源 bin 是哪个？不确定的话编译后我再问。

## 修改类型判断

所有修改先分成两类：

1. `needs-values`
   - 需要用户贴本次具体参数。
   - 典型场景：default EQ、一组结构体参数、数组参数、长配置块。
   - 若用户首条消息已经贴了参数，就直接使用，不要重复追问。
   - 若用户没贴，就只问一句：
     - `请把这次要改的完整参数贴给我，按代码格式直接发就行。`

2. `fixed-target`
   - 不需要用户再贴整块参数。
   - 典型场景：单改宏、把某个开关改成固定值、把日志改成明文。
   - 如果记录里已有固定目标，或用户消息里已写明目标值，就直接进入定位和确认步骤。
   - 示例：
     - `帮我改成明文 log，只用把 VIVO_ID_LOG = 0 即可`

## 标准顺序

1. 先读取默认项目与默认版本。
2. 若用户本次指定了新的版本目录，则用本次输入覆盖默认版本。
3. 确认本次修改项 `change_item`，首版固定为 `default-eq`、`macro-toggle`、`other-config`。
4. 先查询 `references/change-records.json`：
   - 先查 `(project_id, variant_key, change_item)`
   - 再查 `(project_id, common, change_item)`
5. 若无记录，搜索源码并整理候选位置、符号、修改理由，再请求用户确认。
6. 用户确认后再修改代码。
7. 读取 `references/project-registry.json` 中该工程的 `build_command`，确认是否可直接执行。
8. 若记录的 `input_mode` 是 `needs-values`，先确认本次参数是否已经拿到；没拿到就用一句中文短问补齐。
9. 编译后定位 `out/<variant_key>/`。
10. 若 `source_bin_name` 已登记，直接使用该源 bin；若未登记，列出候选 `.bin` 并请求用户首次确认。
11. 按 `variant_key + change_tags + MMDD` 生成发布名建议。
12. 用户确认最终文件名后，对源 bin 执行原地重命名。
13. 将确认后的修改位置、版本信息、源 bin 信息和说明更新到记录中。

## 确认点

- 记录未命中时，必须先问用户，不允许猜测修改位置。
- 第一次确认某个版本目录的源 bin 时，必须记录到 `project-registry.json`。
- 最终发布文件名必须由用户确认。
- 若同一次发布包含多个修改项，文件名短标签按确认顺序拼接。
- 只要用户没有说“改掉默认值”，就继续复用已保存首选项。
- `needs-values` 类型不得默认沿用上次参数，除非用户明确要求“按上次参数”。

## 命名规则

- 单项修改示例：`DPD2603A_default_eq_0423.bin`
- 多项修改示例：`DPD2603A_default_eq_macro_0423.bin`
- 日期默认使用 `MMDD`。

## 记录回写原则

- 只记录“已经被用户确认”的位置与命名。
- `change-records.json` 记录机器可检索结构。
- `change-catalog.md` 记录人工可读摘要和经验说明。
- `project-registry.json` 维护默认项目、默认版本、构建入口和默认源 bin。
