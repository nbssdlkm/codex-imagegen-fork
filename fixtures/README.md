# Fixtures — B skill (codex-imagegen-fork)

最小 adversarial sample JSON,**用于安装后自检 + 第三方审计**。每份文件聚焦一个边界条件。

跑法:`python ../scripts/batch_runner.py <fixture>.json --dry-run` 或 真跑(去掉 `--dry-run`)。

## 期望行为对照表

| 文件 | 期望 |
|---|---|
| `good_minimal_text2im.json` | ✅ runner 通过 + dry-run 显示走 `generate` 子命令(0 图 text2im,B 独有能力) |
| `good_minimal_edit.json` | ✅ runner 通过 + dry-run 显示走 `edit` 子命令(注意 `./fixtures/sample_ref.png` 是占位,真跑前替换) |
| `bad_empty_prompt.json` | ❌ exit 2 + 报 "prompt 不能空" |
| `bad_wrong_skill.json` | ❌ exit 2 + 报 "config.skill = 'a',本 runner 只跑 skill='b'" + 指向 A 的 runner |
| `bad_missing_path.json` | ❌ exit 2 + 报 "参考图不存在 — ./not_exists/nowhere.png" |

## 注意

- B 跟 A 不同:**0 图合法**(走 `generate` 子命令),所以没有 `bad_empty_refs.json` 这条
- 所有 `out_dir` 都用 `~/Desktop/...` 占位,跨 OS 安全
- `good_minimal_edit.json` 的 `reference_images` 是相对路径占位,真跑必须替换成有效绝对路径
- 这些是用来验证 runner / form 自身行为的最小集
