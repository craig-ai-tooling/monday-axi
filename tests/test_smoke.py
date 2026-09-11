"""Smoke tests — no network, no credentials, no dependence on the host's real
1Password login (op is force-mocked "absent" so these are deterministic on any
machine, including one where `op` happens to already be signed in).

Confirms the package imports, __version__ exists, and doctor never crashes and
never reports success (exit 0) when a required connector is unreachable, which
is the state of any box without MONDAY_TOKEN and without a working `op`.
"""
import argparse
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import monday_axi
from monday_axi import cli


def _run_doctor(as_json=False):
    """Run cmd_doctor with no credentials and `op` treated as not on PATH —
    fully offline and deterministic regardless of the host environment."""
    env = dict(os.environ)
    env.pop("MONDAY_TOKEN", None)
    args = argparse.Namespace(json=as_json)
    buf = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch.object(cli.shutil, "which", return_value=None), \
         redirect_stdout(buf):
        code = cli.cmd_doctor(args)
    return code, buf.getvalue()


class VersionTest(unittest.TestCase):
    def test_version_string(self):
        self.assertTrue(monday_axi.__version__)
        self.assertRegex(monday_axi.__version__, r"^\d+\.\d+\.\d+$")


class DoctorTest(unittest.TestCase):
    def test_doctor_runs_and_fails_closed_without_credentials(self):
        code, out = _run_doctor(as_json=False)
        self.assertNotEqual(code, 0)
        self.assertIn("connectors[", out)
        self.assertIn("config[", out)

    def test_doctor_json_is_valid_and_never_raises(self):
        code, out = _run_doctor(as_json=True)
        payload = json.loads(out)
        self.assertIn("connectors", payload)
        self.assertIn("config", payload)
        self.assertIsInstance(code, int)
        self.assertNotEqual(code, 0)
        names = {row["name"] for row in payload["connectors"]}
        self.assertEqual(names, {"onepassword", "monday-api"})


if __name__ == "__main__":
    unittest.main()
