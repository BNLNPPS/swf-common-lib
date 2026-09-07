"""The stop path is bounded whatever a doer is doing.

Exercises BaseAgent._stop_and_drain on a bare agent (no broker, no monitor):
a background task blocked in a subprocess that would run for minutes is
ended at the drain limit, the worker thread returns, and the call comes back
inside the limit plus the grace period. A second stop signal cuts the drain
short. No work in flight returns at once.
"""
import logging
import subprocess
import threading
import time

from swf_common_lib.base_agent import BaseAgent


def _bare_agent(drain_limit_s=2, grace_s=2):
    """A BaseAgent with only the stop path's state, so the test needs no
    broker connection, configuration file, or monitor."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.agent_type = 'TEST'
    agent.agent_name = 'test-stop'
    agent.logger = logging.getLogger('test-stop')
    agent.conn = None
    agent.mq_connected = False
    agent.operational_state = 'READY'
    agent._bg_executor = None
    agent._bg_max_workers = 2
    agent._bg_lock = threading.Lock()
    agent._bg_inflight = 0
    agent._bg_keys = set()
    agent._stopping = True
    agent._stop_now = False
    agent._deliberate = False
    agent._drain_limit_s = drain_limit_s
    agent._stop_grace_s = grace_s
    agent.report_agent_status = lambda *a, **k: None
    agent.set_processing = lambda: None
    agent.set_ready = lambda: None
    return agent


def _sleep_child(holder):
    proc = subprocess.Popen(['sleep', '300'])
    holder['pid'] = proc.pid
    proc.wait()
    holder['rc'] = proc.returncode


def _wait_until(predicate, limit_s=5):
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _alive(pid):
    try:
        with open(f'/proc/{pid}/status') as handle:
            return 'zombie' not in handle.read()
    except OSError:
        return False


def test_no_work_returns_at_once():
    agent = _bare_agent()
    started = time.monotonic()
    agent._stop_and_drain()
    assert time.monotonic() - started < 1


def test_long_doer_is_ended_at_the_drain_limit():
    agent = _bare_agent(drain_limit_s=2, grace_s=2)
    holder = {}
    assert agent.run_in_background(_sleep_child, holder, label='sleep')
    assert _wait_until(lambda: 'pid' in holder)
    started = time.monotonic()
    agent._stop_and_drain()
    elapsed = time.monotonic() - started
    # The limit, the grace to end the child, the grace for the thread.
    assert elapsed < 2 + 2 + 2 + 1, elapsed
    assert _wait_until(lambda: agent._bg_inflight == 0)
    assert holder.get('rc') is not None and holder['rc'] < 0   # ended by signal
    assert not _alive(holder['pid'])


def test_second_stop_signal_cuts_the_drain_short():
    agent = _bare_agent(drain_limit_s=30, grace_s=2)
    holder = {}
    assert agent.run_in_background(_sleep_child, holder, label='sleep')
    assert _wait_until(lambda: 'pid' in holder)
    agent._stop_now = True
    started = time.monotonic()
    agent._stop_and_drain()
    assert time.monotonic() - started < 6
    assert _wait_until(lambda: agent._bg_inflight == 0)
    assert not _alive(holder['pid'])
