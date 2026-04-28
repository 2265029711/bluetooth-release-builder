# 发布流程

这个 skill 固定服务于“通过差异配置产出不同版本 bin”的流程，适用于蓝牙嵌入式工程。

## 总入口

优先运行：

```bash
python "<skill-root>/scripts/bootstrap_context.py" --request-text "<用户原话>"
```

脚本会返回一个动作：

- `need_project_init`
- `need_change_item`
- `need_location_confirmation`
- `need_value_input`
- `need_target_value`
- `direct_apply_and_build`

## 初始化规则

1. 若返回 `need_project_init`，只补问缺失项。
2. 初始化提问必须全程使用中文。
3. 不要要求用户理解 `project_id` 这类内部字段；应询问“工程名称”“编译命令”“常用版本目录”等用户能直接回答的信息。
4. 用户回答后，立刻调用 skill 自身目录下的 `scripts/save_project_preference.py` 存入 `references/project-registry.json`。
5. 只要用户不要求更改，后续默认读取上次保存的首选项。

## 修改类型判断

1. `needs-values`
   - 需要用户贴本次具体参数。
   - 典型场景：default EQ、一组结构体参数、数组参数、长配置块。
   - 若用户首条消息已经贴了参数，就直接使用，不要重复追问。
   - 若用户已经明确给出字段和值，也视为输入充分。
   - 若本次参数不完整，才补问一次：
     - `请把这次要改的完整参数贴给我，按代码格式直接发就行。`

2. `fixed-target`
   - 不需要用户再贴整块参数。
   - 典型场景：单改宏、把某个开关改成固定值、把日志改成明文。
   - 如果记录里已有固定目标，或用户消息里已写明目标值，就直接进入修改和编译，不再确认。

## 标准顺序

1. 先读取默认项目与默认版本。
2. 若用户本次指定了新的版本目录，则用本次输入覆盖默认版本。
3. 确认本次修改项 `change_item`，首版固定为 `default-eq`、`macro-toggle`、`other-config`。
4. 先查询 `references/change-records.json`：
   - 先查 `(project_id, variant_key, change_item)`
   - 再查 `(project_id, common, change_item)`
5. 若 `bootstrap_context.py` 返回 `direct_apply_and_build`，直接修改代码并编译。
6. 若同一次请求在同一个文件中命中多处修改，先整理成一份同文件修改清单，再一次性修改，不逐条确认。
7. 若返回 `need_location_confirmation`，才搜索源码并整理候选位置、符号、修改理由，再请求用户确认。
8. 若返回 `need_value_input` 或 `need_target_value`，只补问一次最短问题。
9. 定位到待修改源码文件后，必须读取完整文件；若文件较长，可分段读取，但必须持续读取到 EOF，不能只停在前 1000 行。
10. 执行修改时遵循最小改动原则：
   - 只改用户明确要求的参数或目标值
   - 不改无关字段
   - 不改注释
   - 不做额外格式整理
   - 示例：bypass 若只需要 `.num = 0`，则不要改 `.param`
11. 同一文件内的多处已确认修改必须一次完成，不要改一条确认一条。
12. 编译后默认输出修改汇总和编译结果。
13. 只有当用户明确要求发布命名或源 bin 时，才继续定位 `out/<variant_key>/`、默认源 bin 和建议文件名。
14. 将确认后的修改位置、版本信息和说明更新到记录中。

## 确认点

- 记录命中且输入明确时，不要额外确认，直接执行。
- 记录未命中时，必须先问用户，不允许猜测修改位置。
- `needs-values` 类型只有在本次没给完整参数时才允许追问。
- 若同一文件内有多处已确认修改，先合并处理，再一次性修改。
- 查看源码时必须确认已经读完整个目标文件，而不是只看首段。
- 只改用户明确指定的字段或值；若没有明确要求，不得扩展修改范围。
- 注释属于禁止随手改动项，除非用户明确要求修改注释。
- 最终输出优先给出修改位置、修改内容和编译结果。

## 命名规则

- 单项修改示例：`DPD2603A_default_eq_0423.bin`
- 多项修改示例：`DPD2603A_default_eq_macro_0423.bin`
- 日期默认使用 `MMDD`。
- 仅当用户明确要求出版本文件名时再使用这些规则。
