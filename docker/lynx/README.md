# Lynx dstack 部署

[`Dockerfile`](Dockerfile) 使用官方 Node 22 和 Python 3.11 镜像，从当前源码构建 dstack server 和管理界面。Lynx fork 的功能说明见[项目 README](../../README.md#lynx-fork)。

## AWS us-east-1

部署文件是 [`docker-compose.ec2.yaml`](docker-compose.ec2.yaml)，在 EC2 上放置于 `/home/ec2-user/deployments/dstack/docker-compose.yaml`。同目录的私有 `.env` 需设置 `DSTACK_POSTGRES_PASSWORD`；可选设置 `DSTACK_POSTGRES_USER` 和 `DSTACK_POSTGRES_DB`。不要提交 `.env`。

PostgreSQL 和 server 数据分别保存在部署目录的 `data/postgres/`、`data/server/`。Server 只监听 EC2 本机的 `127.0.0.1:3000`；DNS 和反向代理独立配置。Compose 已指定美东 CDN 的 runner、shim 下载地址。

### 构建并发布镜像

在仓库根目录运行；发布新版本时更换 `IMAGE_TAG`，并同步更新 Compose 中的镜像 tag：

```bash
IMAGE_TAG=78c0c808b-ec2
ECR=806758135039.dkr.ecr.us-east-1.amazonaws.com/dstack-lynx

docker buildx build --platform linux/amd64 --load \
  -t "$ECR:$IMAGE_TAG" -f docker/lynx/Dockerfile .
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 806758135039.dkr.ecr.us-east-1.amazonaws.com
docker push "$ECR:$IMAGE_TAG"
```

### 在 EC2 更新和检查

```bash
cd /home/ec2-user/deployments/dstack
docker compose pull server
docker compose up -d
docker compose ps
curl -I http://127.0.0.1:3000/
```

更新前确认新版本的 runner、shim 与 Compose 中的下载地址兼容。
