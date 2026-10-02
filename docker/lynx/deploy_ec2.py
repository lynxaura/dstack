"""Deploy the checked-out Compose configuration and built image using AWS SSM."""

import base64
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

DEPLOY_DIR = "/home/ec2-user/deployments/dstack"


def main():
    instance_id = os.environ["EC2_INSTANCE_ID"]
    image = os.environ["DSTACK_SERVER_IMAGE"]
    compose = Path(__file__).with_name("docker-compose.ec2.yaml").read_bytes()
    command_id = aws_json(
        "send-command",
        "--instance-ids",
        instance_id,
        "--document-name",
        "AWS-RunShellScript",
        "--timeout-seconds",
        "60",
        "--parameters",
        json.dumps(
            {
                "commands": [deployment_command(image, compose)],
                "executionTimeout": ["1200"],
            }
        ),
    )["Command"]["CommandId"]
    print(f"SSM command: {command_id}", flush=True)
    for _ in range(126):
        result = subprocess.run(
            [
                "aws",
                "ssm",
                "get-command-invocation",
                "--command-id",
                command_id,
                "--instance-id",
                instance_id,
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            if "InvocationDoesNotExist" not in result.stderr:
                raise RuntimeError(result.stderr)
        else:
            invocation = json.loads(result.stdout)
            status = invocation["Status"]
            if status not in {"Pending", "InProgress", "Delayed"}:
                print(invocation.get("StandardOutputContent", ""))
                print(invocation.get("StandardErrorContent", ""))
                if status != "Success":
                    raise RuntimeError(f"SSM deployment failed: {status}")
                summary = os.environ.get("GITHUB_STEP_SUMMARY")
                if summary:
                    with open(summary, "a") as file:
                        file.write(
                            f"### EC2 deployment\nInstance: `{instance_id}`\n\nImage: `{image}`\n"
                        )
                return
        time.sleep(10)
    raise TimeoutError(f"SSM command {command_id} did not finish; check its status in AWS")


def aws_json(*args):
    result = subprocess.run(
        ["aws", "ssm", *args, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def deployment_command(image, compose):
    encoded_compose = base64.b64encode(compose).decode()
    script = f"""set -euo pipefail
cd {shlex.quote(DEPLOY_DIR)}
exec 9>.deploy.lock
flock -n 9
test -s .env
docker compose version
export DSTACK_SERVER_IMAGE={shlex.quote(image)}
candidate=$(mktemp .docker-compose.ci.XXXXXX.yaml)
trap 'rm -f "$candidate"' EXIT
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 806758135039.dkr.ecr.us-east-1.amazonaws.com
printf '%s' {shlex.quote(encoded_compose)} | base64 --decode > "$candidate"
docker compose --env-file .env -f "$candidate" config --quiet
# Pull before changing the running deployment or its saved configuration.
docker compose --env-file .env -f "$candidate" pull server
mv "$candidate" docker-compose.yaml
printf 'DSTACK_SERVER_IMAGE=%s\\n' "$DSTACK_SERVER_IMAGE" > .server-image.env
docker compose --env-file .env --env-file .server-image.env up -d --wait --wait-timeout 300
docker compose --env-file .env --env-file .server-image.env ps
curl --fail --silent --output /dev/null --max-time 10 http://127.0.0.1:3000/
"""
    encoded_script = base64.b64encode(script.encode()).decode()
    return f"printf '%s' {shlex.quote(encoded_script)} | base64 --decode | bash"


if __name__ == "__main__":
    main()
