import base64
import json
import os
import shlex
import subprocess
import unittest
from unittest.mock import patch

import deploy_ec2


class TestMain(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "EC2_INSTANCE_ID": "i-test",
                "DSTACK_SERVER_IMAGE": "example.ecr/dstack:12345678",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def invocation(self, status):
        return subprocess.CompletedProcess([], 0, json.dumps({"Status": status}), "")

    def test_waits_for_invocation_and_completion(self):
        with (
            patch.object(
                deploy_ec2, "aws_json", return_value={"Command": {"CommandId": "cmd"}}
            ) as aws,
            patch.object(deploy_ec2.subprocess, "run") as run,
            patch.object(deploy_ec2.time, "sleep") as sleep,
        ):
            run.side_effect = [
                subprocess.CompletedProcess([], 255, "", "InvocationDoesNotExist"),
                self.invocation("InProgress"),
                self.invocation("Success"),
            ]
            deploy_ec2.main()
        self.assertEqual(sleep.call_count, 2)
        args = aws.call_args.args
        self.assertEqual(args[0], "send-command")
        self.assertEqual(args[args.index("--instance-ids") + 1], "i-test")
        parameters = json.loads(args[args.index("--parameters") + 1])
        script = decode_command(parameters["commands"][0])
        self.assertIn("DSTACK_SERVER_IMAGE=example.ecr/dstack:12345678", script)

    def test_failed_remote_deployment_fails_ci(self):
        with (
            patch.object(deploy_ec2, "aws_json", return_value={"Command": {"CommandId": "cmd"}}),
            patch.object(deploy_ec2.subprocess, "run", return_value=self.invocation("Failed")),
            patch.object(deploy_ec2.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "SSM deployment failed: Failed"):
                deploy_ec2.main()
        sleep.assert_not_called()

    def test_api_error_is_not_retried_as_a_pending_command(self):
        with (
            patch.object(deploy_ec2, "aws_json", return_value={"Command": {"CommandId": "cmd"}}),
            patch.object(
                deploy_ec2.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 255, "", "AccessDenied"),
            ),
            patch.object(deploy_ec2.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
                deploy_ec2.main()
        sleep.assert_not_called()

    def test_timeout_fails_ci_without_waiting_on_real_time(self):
        with (
            patch.object(deploy_ec2, "aws_json", return_value={"Command": {"CommandId": "cmd"}}),
            patch.object(deploy_ec2.subprocess, "run", return_value=self.invocation("InProgress")),
            patch.object(deploy_ec2.time, "sleep"),
        ):
            with self.assertRaises(TimeoutError):
                deploy_ec2.main()


class TestDeploymentCommand(unittest.TestCase):
    def test_preserves_compose_and_quotes_shell_arguments(self):
        compose = b"name: dstack\nservices: {}\n"
        image = "example.ecr/dstack:12345678; echo unexpected"
        script = decode_command(deploy_ec2.deployment_command(image, compose))
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)
        self.assertIn(f"export DSTACK_SERVER_IMAGE={shlex.quote(image)}", script)
        self.assertIn(base64.b64encode(compose).decode(), script)
        self.assertLess(script.index("pull server"), script.index('mv "$candidate"'))
        self.assertIn("--wait --wait-timeout 300", script)
        self.assertIn("set -euo pipefail", script)


def decode_command(command):
    return base64.b64decode(shlex.split(command)[2]).decode()


if __name__ == "__main__":
    unittest.main()
