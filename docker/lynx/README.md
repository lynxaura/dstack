# Lynx dstack 部署说明

这个目录用于保存 Lynx 环境部署 dstack 时使用的 Docker 镜像定义和部署说明。

## 这个 fork 改了什么

当前 Lynx fork 给 Vast.ai backend 的 profile options 增加了可配置的 `extra_filters`。

这些额外过滤条件会在 dstack 原有的 Vast.ai offer filters 基础上继续追加，并最终传给 `gpuhunt.VastAIProvider`。目前支持的 Vast.ai 字段包括 `storage_cost`、`inet_down_cost`、`inet_up`、`static_ip`、`gpu_arch`、`pci_gen`、`host_id` 等，比较操作符支持 `lt`、`lte`、`eq`、`gte` 和 `gt`。

当多个 profile 合并时，下界条件会取更大的值，上界条件会取更小的值。如果同一个字段出现互相冲突的 `eq` 值，会直接抛出 `CombineError`。对于已经由 dstack 自己管理的字段，例如 `verified`、`inet_down`、`gpu_name` 和 `dph_total`，不允许通过 `extra_filters` 覆盖。

这个改动只发生在 server 端，不需要为 worker 单独构建自定义镜像。

## 为什么单独放一个 Dockerfile

`docker/lynx/Dockerfile` 会直接基于当前 checkout 的源码构建 dstack server，而不是从 PyPI 安装已经发布的 dstack 版本，因此可以直接包含当前分支里尚未发布的修改。

这个镜像也会同时构建 `frontend/` 管理界面，并把产物放到 dstack server 的静态资源目录中。部署后直接访问 server 的根地址即可打开管理界面，不需要额外部署前端服务。

相比上游的 staging Dockerfile，这个 Dockerfile 还做了以下调整：

- 使用 DaoCloud 的 Python 镜像源，避免部署链路无法访问 Docker Hub 时构建失败；
- 使用 Node 22 构建 `frontend/`，并把 `frontend/build/` 打进 server 镜像；
- 额外复制 `skills/` 和 `examples/plugins/example_plugin_server/`，满足当前 package/uv 配置的要求；
- 使用 `uv sync --extra all --no-dev`，不安装开发和测试依赖；
- 把 `/dstack-server/.venv/bin` 加入 `PATH`，这样 entrypoint 可以直接执行 `dstack server`。

## 本地构建镜像

内部部署统一使用固定的 `dstack-lynx:latest` tag。每次发布直接覆盖这个 tag，避免长期保留大量按 commit 区分的镜像。

构建时明确指定 `linux/amd64`：

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t dstack-lynx:latest \
  -f docker/lynx/Dockerfile \
  .
```

构建完成后可以检查镜像架构：

```bash
docker image inspect dstack-lynx:latest \
  --format '{{.RepoTags}} arch={{.Architecture}} id={{.Id}}'
```

## 传镜像到 prod-2

`prod-2` 不需要从 registry 拉这个自定义 dstack 镜像，可以直接从本机构建机通过 SSH 传过去：

```bash
docker save dstack-lynx:latest | gzip -1 | \
  ssh prod-2 'gzip -d | docker load'
```

如果 `prod-2` 上还没有 `postgres:16`，也可以用同样的方法传过去。比如本地 Docker Hub 不可用时，可以先从 DaoCloud 镜像源拉取：

```bash
docker pull --platform linux/amd64 docker.m.daocloud.io/library/postgres:16
docker tag docker.m.daocloud.io/library/postgres:16 postgres:16

docker save postgres:16 | gzip -1 | \
  ssh prod-2 'gzip -d | docker load'
```

## prod-2 部署方式

线上部署目录固定为：

```text
/root/deployments/dstack
```

目前只需要两个服务：

- dstack server；
- PostgreSQL 16。

当前不部署 SSH proxy。

最小的 `docker-compose.yaml` 可以写成：

```yaml
name: dstack

services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DSTACK_POSTGRES_USER:-dstack}
      POSTGRES_PASSWORD: ${DSTACK_POSTGRES_PASSWORD}
      POSTGRES_DB: ${DSTACK_POSTGRES_DB:-dstack}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10

  server:
    image: dstack-lynx:latest
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DSTACK_DATABASE_URL: postgresql+asyncpg://${DSTACK_POSTGRES_USER:-dstack}:${DSTACK_POSTGRES_PASSWORD}@postgres:5432/${DSTACK_POSTGRES_DB:-dstack}
      DSTACK_SERVER_LOG_FORMAT: rich
    volumes:
      - server-data:/root/.dstack/server
    ports:
      - "172.31.22.121:3000:3000"

volumes:
  postgres-data:
  server-data:
```

第一次部署时，在 `prod-2` 上创建部署目录和私有 `.env` 文件：

```bash
ssh prod-2
mkdir -p /root/deployments/dstack
cd /root/deployments/dstack
umask 077
cat > .env <<EOF
DSTACK_POSTGRES_USER=dstack
DSTACK_POSTGRES_DB=dstack
DSTACK_POSTGRES_PASSWORD=$(openssl rand -hex 24)
EOF
chmod 600 .env
```

把 `docker-compose.yaml` 放到这个目录以后，启动或更新服务：

```bash
cd /root/deployments/dstack
docker compose up -d --force-recreate
```

检查部署状态：

```bash
docker compose ps
docker compose logs --tail=100 server
curl -I http://172.31.22.121:3000/
```

`prod-2` 上只把 dstack 的 `3000` 端口绑定到内网 IP `172.31.22.121`，不要使用 `3000:3000` 让 Docker 监听所有网卡。

## 升级

升级时，在本地重新构建 `dstack-lynx:latest` 并传到 `prod-2`，然后重新创建 server 容器：

```bash
cd /root/deployments/dstack
docker compose up -d --force-recreate server
```

因为固定使用 `latest`，不需要修改 `docker-compose.yaml` 的镜像 tag。

如果确认有旧的 dangling dstack 镜像需要清理，可以在部署完成并验证服务正常后执行：

```bash
docker image prune -f
```

如果需要回滚，则在本地 checkout 到目标旧 commit，重新构建同一个 `dstack-lynx:latest`，传到 `prod-2` 后再次重建 server 容器即可。

这个过程不会重建 PostgreSQL 和 `server-data` 对应的数据卷，所以数据库和 dstack server 的持久化数据都会保留。
