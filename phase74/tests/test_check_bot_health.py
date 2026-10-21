"""Bot PC health alerts: no false alarms from sync lag, alert on real problems, one recovery message."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("check_bot_health", Path(__file__).resolve().parents[2] / "scripts" / "check_bot_health.py")
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

INFO = {"last_sync_et": "Wed 9:19 AM", "last_bar_et": "Wed 9:18 AM", "market_open": True}


class AlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp()) / "state.json"
        self.patch = mock.patch.object(chk, "STATE", self.state)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()

    def run_with(self, probs, info=INFO) -> dict:
        def fake(now):
            if probs == "fail":
                raise OSError("offline")
            return list(probs), dict(info)

        buf = io.StringIO()
        with mock.patch.object(chk, "problems", fake), redirect_stdout(buf):
            chk.main()
        return json.loads(buf.getvalue())

    def test_healthy_is_silent(self) -> None:
        self.assertFalse(self.run_with([])["notify"])

    def test_real_problem_alerts_once_then_waits(self) -> None:
        first = self.run_with(["BARS_STALE"])
        self.assertTrue(first["notify"])
        self.assertIn("no bars since", first["message"])
        self.assertFalse(self.run_with(["BARS_STALE"])["notify"])

    def test_recovery_sends_one_message(self) -> None:
        self.run_with(["BOT_NOT_RUNNING"])
        back = self.run_with([])
        self.assertTrue(back["notify"])
        self.assertIn("recovered", back["message"])
        self.assertFalse(self.run_with([])["notify"])

    def test_one_failed_github_check_is_not_an_alert(self) -> None:
        self.assertFalse(self.run_with("fail")["notify"])
        self.assertTrue(self.run_with("fail")["notify"])

    def test_bars_judged_by_the_pc_not_by_sync_lag(self) -> None:
        # The PC said OK at its last sync; a 25-minute-old newest bar on the Mac is just sync lag.
        health = {"bot_running": True, "problems": [], "last_bar_utc": "2026-10-21T12:18:00.0000000+00:00"}
        with mock.patch.object(chk, "git") as git:
            git.side_effect = lambda *a: {
                "fetch": "",
                "log": "2026-10-21T08:19:39-04:00",
                "show": json.dumps(health),
            }[a[0]]
            from datetime import datetime, timezone
            probs, _ = chk.problems(datetime(2026, 10, 21, 12, 44, tzinfo=timezone.utc))
        self.assertEqual(probs, [])


if __name__ == "__main__":
    unittest.main()
