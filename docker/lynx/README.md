# Lynx dstack 部署

[`Dockerfile`](Dockerfile) 使用官方 Node 22 和 Python 3.11 镜像，从当前源码构建 dstack server 和管理界面。Lynx fork 的功能说明见[项目 README](../../README.md#lynx-fork)。

## AWS us-east-1

部署目录为 `/home/ec2-user/deployments/dstack`。首次部署先在 EC2 创建该目录及私有 `.env`，设置 `DSTACK_POSTGRES_PASSWORD`；可选设置 `DSTACK_POSTGRES_USER` 和 `DSTACK_POSTGRES_DB`。不要提交 `.env`。CI 将 [`docker-compose.ec2.yaml`](docker-compose.ec2.yaml) 同步为部署目录中的 `docker-compose.yaml`。

PostgreSQL 和 server 数据分别保存在部署目录的 `data/postgres/`、`data/server/`。Server 只监听 EC2 本机的 `127.0.0.1:3000`；DNS 和反向代理独立配置。Compose 已指定美东 CDN 的 runner、shim 下载地址。

## GitHub Actions 发布和部署

将修改推送到 `lynx` 分支后，**Build and deploy Lynx dstack server** 自动构建 `linux/amd64` 镜像并发布到 `806758135039.dkr.ecr.us-east-1.amazonaws.com/dstack-lynx:<commit SHA 前 8 位>`。构建和部署均通过 GitHub OIDC 获取 AWS 权限，无需长期 AWS 密钥。

配置以下 GitHub Actions 设置：

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Repository variable | `EC2_INSTANCE_ID` | 美东部署目标实例 ID；未设置时只发布镜像 |
| Repository secret | `AWS_ROLE_ARN` | 通过 GitHub OIDC 获取 ECR 发布和 SSM 部署权限 |

当前目标为 `i-04b02d6bd3a829418`（`lynx-test`，`us-east-1d`），配置在仓库变量 `EC2_INSTANCE_ID` 中。

设置实例 ID 后，每次 push 在镜像发布成功后自动部署。手动 **Run workflow** 选择 `lynx`，取消 `deploy` 可只构建镜像；保留勾选则构建并部署。手动入口需要默认分支包含该工作流。整个构建和部署流程串行执行，避免同时更新同一实例。

部署 job 验证 AWS 账号为 `806758135039`，通过 SSM `AWS-RunShellScript` 同步本次提交的 Compose 文件。EC2 使用实例角色登录 ECR，拉取本次构建的 **8 位 commit tag**，执行 `docker compose up -d --wait` 并检查 HTTP。实例 ID、镜像地址和部署结果会写入 Actions Summary；SSM 命令失败或健康检查超时会令 job 失败。

### EC2 和 IAM 前置配置

- 实例必须是 `us-east-1` 中的 Linux x86_64，安装 Docker、Compose（支持 `--wait`）、AWS CLI、curl 和 flock。
- 实例需运行 SSM Agent，实例角色包含 `AmazonSSMManagedInstanceCore`，并能连接 SSM 服务及 ECR；无需开放 SSH 入站端口。
- GitHub OIDC 角色信任策略仅允许此仓库 `lynx` 分支，audience 为 `sts.amazonaws.com`。当前仓库 subject 为 `repo:lynxaura@220947976/dstack@1392219201:ref:refs/heads/lynx`。
- CI 角色允许 `ecr:GetAuthorizationToken`，并允许对 `dstack-lynx` 仓库执行 `ecr:BatchCheckLayerAvailability`、`ecr:GetDownloadUrlForLayer`、`ecr:BatchGetImage`、`ecr:InitiateLayerUpload`、`ecr:UploadLayerPart`、`ecr:CompleteLayerUpload`、`ecr:PutImage`。
- CI 角色允许对目标实例 ARN 和 `arn:aws:ssm:us-east-1::document/AWS-RunShellScript` 执行 `ssm:SendCommand`，允许对 `*` 执行 `ssm:GetCommandInvocation`。
- EC2 角色允许 `ecr:GetAuthorizationToken`，并允许对 `dstack-lynx` 仓库执行 `ecr:BatchCheckLayerAvailability`、`ecr:GetDownloadUrlForLayer`、`ecr:BatchGetImage`。现有实例角色已包含 ECR 权限。

部署保留 `.env` 和 `data/`，镜像拉取成功后才更新 Compose 和 `.server-image.env`。失败时检查 SSM 输出及 EC2 容器状态；不会自动回滚数据库迁移。更新前确认 runner、shim 与 Compose 中的下载地址兼容。

## 部署入口

EC2 server 更新统一通过本工作流执行。首次准备好部署目录和 `.env` 后，由 CI 同步 Compose 和镜像版本；无需在 EC2 手动 pull 或重启。发布或重试时在 Actions 中选择 `lynx` 并运行工作流，保留 `deploy` 勾选。

SSM 部署机制见 [AWS Run Command 文档](https://docs.aws.amazon.com/systems-manager/latest/userguide/walkthrough-cli.html)。
