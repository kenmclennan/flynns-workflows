import io
import os
import socket
import sys
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

import scout_fetch


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class StubOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)


def http_error(code):
    return urllib.error.HTTPError("https://x.example/", code, "err", {}, None)


class FetchRetryTests(unittest.TestCase):
    def setUp(self):
        previous = scout_fetch.RETRY_PAUSE
        scout_fetch.RETRY_PAUSE = 0
        self.addCleanup(setattr, scout_fetch, "RETRY_PAUSE", previous)

    def fetch(self, *outcomes):
        opener = StubOpener(*outcomes)
        return scout_fetch.fetch("https://x.example/", opener=opener), opener.calls

    def test_retries_once_after_a_transient_failure(self):
        transient = [
            socket.timeout("timed out"),
            ConnectionResetError("reset"),
            urllib.error.URLError(socket.gaierror("dns")),
            http_error(502),
            http_error(503),
            http_error(504),
        ]
        for failure in transient:
            with self.subTest(failure=repr(failure)):
                self.assertEqual(self.fetch(failure, b"ok"), ("ok", 2))

    def test_gives_up_after_one_retry(self):
        self.assertEqual(self.fetch(http_error(503), http_error(503)), (None, 2))

    def test_does_not_retry_a_404(self):
        self.assertEqual(self.fetch(http_error(404), b"ok"), (None, 1))


if __name__ == "__main__":
    unittest.main()
