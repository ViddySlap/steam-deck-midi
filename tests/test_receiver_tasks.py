"""ReceiverTaskQueue and its drain inside serve_forever."""

from __future__ import annotations

import socket
import threading
import unittest

from tests.test_receiver import FakeMidiOut
from windows.receiver import ActionReceiver, serve_forever
from windows.receiver_tasks import ReceiverTaskQueue, ReceiverTaskTimeout


class ReceiverTaskQueueTests(unittest.TestCase):
    def test_run_returns_the_result_computed_on_the_draining_thread(self):
        tasks = ReceiverTaskQueue()
        stop = threading.Event()
        idents = []

        def loop():
            idents.append(threading.get_ident())
            while not stop.is_set():
                tasks.drain()
                stop.wait(0.001)

        thread = threading.Thread(target=loop)
        thread.start()
        try:
            self.assertEqual(tasks.run(threading.get_ident), idents[0])
            with self.assertRaisesRegex(KeyError, "boom"):
                tasks.run(lambda: {}["boom"])
        finally:
            stop.set()
            thread.join(5)

    def test_a_task_not_started_in_time_is_cancelled_and_never_runs(self):
        tasks = ReceiverTaskQueue()
        ran = []
        with self.assertRaises(ReceiverTaskTimeout):
            tasks.run(lambda: ran.append(1), start_timeout=0.05)
        self.assertEqual(tasks.drain(), 0)
        self.assertEqual(ran, [])


class ServeForeverDrainTests(unittest.TestCase):
    def test_serve_forever_runs_queued_tasks_on_its_own_thread(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        receiver = ActionReceiver(FakeMidiOut(), {})
        tasks = ReceiverTaskQueue()
        serve_ident = []

        def serve():
            serve_ident.append(threading.get_ident())
            serve_forever("127.0.0.1", port, receiver, poll_interval=0.01, receiver_tasks=tasks)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            ran_on = tasks.run(threading.get_ident, start_timeout=3.0)
        finally:
            receiver.request_shutdown()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(ran_on, serve_ident[0])


if __name__ == "__main__":
    unittest.main()
