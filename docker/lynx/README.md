# Lynx dstack deployment

This directory contains the Docker image definition used for Lynx deployments of dstack.

## What this fork changes

The current Lynx fork adds configurable `extra_filters` to the Vast.ai backend profile options.

The extra filters are appended to dstack's existing Vast.ai offer filters and are passed to `gpuhunt.VastAIProvider`. They support Vast.ai fields such as `storage_cost`, `inet_down_cost`, `inet_up`, `static_ip`, `gpu_arch`, `pci_gen`, and `host_id`, with the comparison operators `lt`, `lte`, `eq`, `gte`, and `gt`.

When multiple profiles are combined, lower-bound filters are tightened to the larger value and upper-bound filters are tightened to the smaller value. Conflicting `eq` values raise `CombineError`. Fields already managed by dstack itself, such as `verified`, `inet_down`, `gpu_name`, and `dph_total`, cannot be overridden through `extra_filters`.

This is a server-side change. No custom worker image is required for this feature.

## Why this Dockerfile exists

`docker/lynx/Dockerfile` builds the dstack server directly from the current checkout instead of installing a released dstack package from PyPI.

Compared with the upstream staging Dockerfile, it also:

- uses the DaoCloud Python mirror because Docker Hub may be unavailable from our deployment path;
- copies `skills/` and `examples/plugins/example_plugin_server/`, which are required by the current package/uv configuration;
- installs only non-development dependencies with `uv sync --extra all --no-dev`;
- puts `/dstack-server/.venv/bin` on `PATH`, so the entrypoint can execute `dstack server` directly.

## Build

Build an amd64 image locally and tag it with the Git commit being deployed:

```bash
SHA=$(git rev-parse --short=10 HEAD)
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t dstack-prod2:${SHA} \
  -f docker/lynx/Dockerfile \
  .
```

Verify the resulting architecture:

```bash
docker image inspect dstack-prod2:${SHA} \
  --format '{{.RepoTags}} arch={{.Architecture}} id={{.Id}}'
```

## Transfer to prod-2

`prod-2` does not need to pull the custom dstack image from a registry. Transfer it directly from the build machine:

```bash
docker save dstack-prod2:${SHA} | gzip -1 | \
  ssh prod-2 'gzip -d | docker load'
```

If `postgres:16` is not already present on `prod-2`, it can be transferred the same way. For example, when Docker Hub is unavailable locally:

```bash
docker pull --platform linux/amd64 docker.m.daocloud.io/library/postgres:16
docker tag docker.m.daocloud.io/library/postgres:16 postgres:16

docker save postgres:16 | gzip -1 | \
  ssh prod-2 'gzip -d | docker load'
```

## prod-2 deployment

The deployment lives at:

```text
/root/deployments/dstack
```

Only two services are required for this deployment:

- dstack server;
- PostgreSQL 16.

SSH proxy is intentionally not deployed.

A minimal `docker-compose.yaml` is:

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
    image: dstack-prod2:<git-sha>
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
      - "3000:3000"

volumes:
  postgres-data:
  server-data:
```

Create the deployment directory and a private `.env` file once:

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

After placing `docker-compose.yaml` in that directory, start or update the deployment with:

```bash
cd /root/deployments/dstack
docker compose up -d --force-recreate
```

Check the deployment with:

```bash
docker compose ps
docker compose logs --tail=100 server
curl -I http://127.0.0.1:3000/
```

## Upgrade and rollback

For an upgrade, build and transfer a new image tagged with the new Git SHA, update only the `server.image` value in `docker-compose.yaml`, then run:

```bash
cd /root/deployments/dstack
docker compose up -d --force-recreate server
```

Do not prune the previous dstack image immediately. To roll back, restore the previous image tag in `docker-compose.yaml` and recreate the server container. The PostgreSQL and server-data volumes are not recreated during this process.
