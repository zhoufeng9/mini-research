# 第一次使用 Git 与 GitHub

Git 和 GitHub 不是同一个东西：

- **Git** 是本机版本管理工具；没有网络也能使用；
- **GitHub** 是保存 Git 仓库的远程平台；
- 只有执行 `git push`，本机提交才会上传。

## 四个核心动作

| 命令 | 含义 | 是否上传 |
|---|---|---|
| `git init` | 在当前目录建立隐藏的 `.git` 历史数据库 | 否 |
| `git add` | 选择下一次提交包含哪些改动，放进“暂存区” | 否 |
| `git commit` | 在本机保存一个带说明的版本快照 | 否 |
| `git push` | 把本机提交发送到 GitHub | **是** |

你平时编辑的文件叫**工作区**；`git add` 后等待提交的内容叫**暂存区**；`git commit`
保存后的快照叫**本地仓库历史**；GitHub 上的副本叫**远程仓库**。

## 第 0 步：先做安全检查

无论公开还是私有仓库，都不能提交真实密钥。首次建库前确认：

1. 已暴露的旧密钥已在服务后台撤销；
2. 新密钥只写在 `.env`；
3. `.env.example` 只有占位符；
4. 旧 Notebook、缓存和大文件已清理；
5. `.gitignore` 包含 `.env`、虚拟环境和缓存规则。

## 第 1 步：初始化本地仓库

在项目根目录执行：

```bash
git init -b main
```

- `init` 创建本地历史数据库；
- `-b main` 把第一条分支明确命名为 `main`；
- 这一步不需要 GitHub 账号，也不会上传文件。

查看当前状态：

```bash
git status
```

## 第 2 步：确认 `.env` 一定被忽略

```bash
git check-ignore -v .env
```

正确结果会显示是哪一条 `.gitignore` 规则忽略了 `.env`。如果没有输出，先停止，不要
继续 `git add`。

也可以同时查看被忽略文件：

```bash
git status --short --ignored
```

其中：

- `??` 表示未跟踪、尚未加入版本管理；
- `!!` 表示已被忽略；
- `.env` 应该显示为 `!! .env`。

## 第 3 步：把安全文件放入暂存区

```bash
git add .
```

这仍然没有上传。现在最重要的是审查“下一次提交究竟包含什么”：

```bash
git status
git diff --cached --stat
git diff --cached --name-status
git diff --cached --check
```

- `--stat` 显示文件和行数概览；
- `--name-status` 显示新增、修改、删除了哪些文件；
- `--check` 检查冲突标记和常见空白错误。

首次提交前还应执行只返回可疑**文件名**的密钥扫描：

```bash
git grep --cached -I -l -E \
'(sk-(proj-)?[[:alnum:]_-]{20,}|tvly-[[:alnum:]_-]{20,}|lsv2_[[:alnum:]_-]{20,}|github_pat_[[:alnum:]_]{20,}|gh[pousr]_[[:alnum:]]{20,}|(AKIA|ASIA)[[:upper:][:digit:]]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)'
```

预期没有输出。如果输出任何文件名，先检查并清理，不要提交。

如果误把某个文件加入暂存区，首次提交前可以执行：

```bash
git rm --cached -- 文件路径
```

`--cached` 只把文件移出 Git 暂存区，不会删除本机文件。然后把对应规则加入
`.gitignore`。

## 第 4 步：确认提交身份

每个提交都会记录作者姓名和邮箱：

```bash
git config user.name
git config user.email
```

如果命令没有输出，可以只为当前项目配置：

```bash
git config user.name "你的显示名称"
git config user.email "你的邮箱或 GitHub noreply 邮箱"
```

不加 `--global`，设置就只影响当前仓库。如果在意邮箱隐私，先在 GitHub 邮箱设置页面
取得 GitHub 提供的 `noreply` 地址，不要猜测地址格式。

## 第 5 步：创建第一个本地提交

确认暂存内容安全后：

```bash
git commit -m "chore: initialize mini research project"
```

查看刚保存的本地历史：

```bash
git log --oneline --decorate -n 3
git status
```

正常情况下，`git status` 会显示工作区干净。到这里仍然没有上传。

## 第 6 步：创建 GitHub 私有仓库

初学测试推荐先使用 **Private** 仓库。私有只限制访问者，不代表可以存密钥。

### 方式 A：GitHub CLI

本机尚未安装 `gh` 时，可先安装并通过浏览器登录：

```bash
brew install gh
gh auth login --web --git-protocol https
gh auth status
```

在项目目录创建并上传私有仓库：

```bash
gh repo create mini-research \
  --private \
  --source=. \
  --remote=origin \
  --push
```

这个命令会在当前 GitHub 账号下创建仓库，把远程地址命名为 `origin`，并执行第一次
`push`。

### 方式 B：先在 GitHub 网页创建空仓库

在 GitHub 新建私有仓库时，不要勾选自动创建 README、`.gitignore` 或 License；本地
已经有这些文件，保持远程为空可以避免两套初始历史冲突。

创建后在本机执行：

```bash
git remote add origin https://github.com/YOUR_GITHUB_NAME/mini-research.git
git remote -v
git push -u origin main
```

- `origin` 是远程仓库的惯用别名；
- `-u` 建立本地 `main` 与远程 `main` 的跟踪关系；
- 以后在这个分支通常只需运行 `git push`。

GitHub 官方参考：

- [创建新仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [GitHub 身份认证](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)
- [GitHub CLI `gh repo create`](https://cli.github.com/manual/gh_repo_create)

## 第 7 步：上传后验证

```bash
git status
git remote -v
git branch -vv
git ls-files
```

再在 GitHub 网页确认：

- 仓库显示为 Private；
- README、`src/`、`tests/` 正常显示；
- 没有 `.env`；
- `.env.example` 只有占位符；
- 提交作者信息符合预期。

## 以后最常用的日常流程

```bash
git status
git diff
git add 具体文件
git diff --cached
git commit -m "说明这次完成了什么"
git push
```

建议一次提交只表达一个清楚目的。这样下一阶段实验失败时，才能准确比较和回退。
