"""Tests for pyopenlab.utils.thread_utils locking / background decorators."""
import threading
import time

from pyopenlab.utils.thread_utils import background_action
from pyopenlab.utils.thread_utils import background_actions_running
from pyopenlab.utils.thread_utils import locked_action
from pyopenlab.utils.thread_utils import locked_action_decorator


def test_locked_action_is_mutually_exclusive():

    class Worker:

        def __init__(self):
            self.concurrent = 0
            self.max_concurrent = 0

        @locked_action
        def work(self):
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
            time.sleep(0.02)
            self.concurrent -= 1

    w = Worker()
    threads = [threading.Thread(target=w.work) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # The lock must serialise calls, so never more than one ran at once.
    assert w.max_concurrent == 1


def test_locked_action_is_reentrant():

    class Reentrant:

        @locked_action
        def outer(self):
            return self.inner() + 1

        @locked_action
        def inner(self):
            return 41

    # An RLock allows a locked method to call another on the same object.
    assert Reentrant().outer() == 42


def test_locked_action_no_wait_returns_false_when_busy():

    class NoWait:

        @locked_action_decorator(wait_for_lock=False)
        def maybe(self):
            return 'ran'

    n = NoWait()
    n._pyopenlab_action_lock = threading.RLock()

    acquired = threading.Event()
    release = threading.Event()

    def holder():
        n._pyopenlab_action_lock.acquire()
        acquired.set()
        release.wait()
        n._pyopenlab_action_lock.release()

    t = threading.Thread(target=holder)
    t.start()
    acquired.wait()
    try:
        # Lock held by another thread -> non-blocking acquire fails -> False.
        assert n.maybe() is False
    finally:
        release.set()
        t.join()
    # Once free, it runs normally.
    assert n.maybe() == 'ran'


def test_background_action_runs_in_thread_and_returns_value():

    class Bg:

        @background_action
        def compute(self, x):
            time.sleep(0.01)
            return x * 2

    b = Bg()
    t = b.compute(21)
    assert isinstance(t, threading.Thread)
    assert t.join_and_return_result() == 42


def test_background_actions_running_tracks_state():

    class Bg:

        @background_action
        def slow(self):
            time.sleep(0.05)
            return True

    b = Bg()
    assert background_actions_running(b) is False
    t = b.slow()
    assert background_actions_running(b) is True
    t.join_and_return_result()
    assert background_actions_running(b) is False
