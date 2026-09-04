# 协作交接记录

本文件是 ChatGPT（决策与审查入口）、Codex（实现与验证）和 GitHub（分支、commit、Draft PR 中转）之间的长期交接记录。每个可独立验证的步骤完成测试后更新本文件。

## 当前基线

- 仓库：`https://github.com/zys1544526484/video-extractor-miniprogram`
- 目标基线：`main`
- 任务分支：`codex/bootstrap-github-handoff`
- `main` 已推送的基线 commit：`dd74b10e90396740599135a0b55c696533c5a6c8`
- 小程序安全检查点：`42334a8bc2a9478bd6926789157494cec23f6d66`
- Draft PR：由本分支 push 后创建，地址以最终任务报告为准

## 长期工作规则

1. ChatGPT 负责拆分任务、审查范围、确认风险和决定是否允许合并。
2. Codex 在一个独立的 `codex/` 分支上实现；不得直接在 `main` 开发。
3. 每个可独立验证的小步骤都要先运行相关测试，再单独 commit 并立即 push。
4. 不使用 force push；push 失败立即停止并报告真实错误。
5. 不提交 `.env`、Token、密钥、密码、账号信息、完整 Authorization、Cookie、缓存或临时文件。
6. 未经用户明确允许，不合并到 `main`，不替用户作最终合并决策。
7. 每次交接报告都要包含仓库、分支、commit SHA、PR 地址、测试结果和下一步建议。

## 本次初始化记录

### 步骤一：现有小程序修改安全检查点

- 范围：19 个小程序页面、服务、存储、工具和测试文件。
- 处理：保留工作区已有修改，未覆盖、删除或还原；未将其他目录内容带入 commit。
- 敏感检查：变更路径未发现 `.env`、缓存或临时文件；未提交凭据、Token、密钥或账号信息。
- 验证：`npm test` 通过（30/30）；`npm run validate:miniprogram` 通过（74 个文件）。
- commit：`42334a8bc2a9478bd6926789157494cec23f6d66`
- push：已成功推送到 `origin/codex/bootstrap-github-handoff`。

### 步骤二：协作机制文件

- 本步骤创建或更新根目录 `AGENTS.md`、本文件和 `.github/pull_request_template.md`。
- 验证：`npm test` 通过（30/30）；`npm run validate:miniprogram` 通过（74 个文件）；`git diff --check` 通过。
- 状态：待 commit、push 和 Draft PR 创建后补充最终链接与结果。

## 未验证项

- 未进行微信开发者工具真机验证。
- 未进行部署验证，未使用真实生产凭证。
- 因此当前产品状态仍为 `NOT VERIFIED`。

## 下一步

完成本步骤的文档检查后，创建第二个独立 commit 并立即 push；随后以 `main` 为目标创建 Draft PR。保持 Draft 状态，等待 ChatGPT 审查和用户明确的合并决定。
