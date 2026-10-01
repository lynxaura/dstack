# Lynx dstack 部署

[`Dockerfile`](Dockerfile) 使用官方 Node 22 和 Python 3.11 镜像，从当前源码构建 dstack server 和管理界面。Lynx fork 的功能说明见[项目 README](../../README.md#lynx-fork)。

## AWS us-east-1

部署文件是 [`docker-compose.ec2.yaml`](docker-compose.ec2.yaml)，在 EC2 上放置于 `/home/ec2-user/deployments/dstack/docker-compose.yaml`。同目录的私有 `.env` 需设置 `DSTACK_POSTGRES_PASSWORD`；可选设置 `DSTACK_POSTGRES_USER` 和 `DSTACK_POSTGRES_DB`。不要提交 `.env`。

PostgreSQL 和 server 数据分别保存在部署目录的 `data/postgres/`、`data/server/`。Server 只监听 EC2 本机的 `127.0.0.1:3000`；DNS 和反向代理独立配置。Compose 已指定美东 CDN 的 runner、shim 下载地址。

### 构建并发布镜像

在仓库根目录运行；发布新版本时更换 `IMAGE_TAG`，并同步更新 Compose 中的镜像 tag：

```bash
IMAGE_TAG=$(git rev-parse HEAD | cut -c1-8)
ECR=806758135039.dkr.ecr.us-east-1.amazonaws.com/dstack-lynx

docker buildx build --platform linux/amd64 --load \
  -t "$ECR:$IMAGE_TAG" -f docker/lynx/Dockerfile .
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 806758135039.dkr.ecr.us-east-1.amazonaws.com
docker push "$ECR:$IMAGE_TAG"
```

### GitHub Actions 构建

将修改提交并推送到 `lynx` 分支后，**Build Lynx dstack server** 自动触发；也可在 Actions 中点击 **Run workflow** 并选择 `lynx`。该工作流只允许在 `lynx` 分支执行，从对应 commit 构建 `linux/amd64` 镜像并推送到上面的 ECR；tag 固定为 commit SHA 前 8 位，不自动部署 EC2。

仓库需要配置 Actions secret `AWS_ROLE_ARN`，用于 GitHub OIDC 认证。AWS 角色的信任策略应仅允许 subject `repo:lynxaura/dstack:ref:refs/heads/lynx`，audience 为 `sts.amazonaws.com`；角色需允许 `ecr:GetAuthorizationToken`，以及对 `dstack-lynx` 仓库执行 `ecr:BatchCheckLayerAvailability`、`ecr:GetDownloadUrlForLayer`、`ecr:BatchGetImage`、`ecr:InitiateLayerUpload`、`ecr:UploadLayerPart`、`ecr:CompleteLayerUpload`、`ecr:PutImage`。

`push` 触发无需合入默认分支；Actions 页面的手动触发入口需要默认分支包含该工作流。构建成功后，Summary 会显示完整镜像地址；将 EC2 Compose 的 server image 更新为该地址，再执行下面的更新命令。

### 在 EC2 更新和检查

```bash
cd /home/ec2-user/deployments/dstack
docker compose pull server
docker compose up -d
docker compose ps
curl -I http://127.0.0.1:3000/
```

更新前确认新版本的 runner、shim 与 Compose 中的下载地址兼容。
