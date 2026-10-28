import json
import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils  # noqa: E402
import request_by_inchikey  # noqa: E402


def make_response(status_code, body=None, headers=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body if body is not None else {}).encode()
    response.headers.update(headers or {})
    response.url = "http://example.org"
    return response


class RequestWithRetryTest(unittest.TestCase):
    def setUp(self):
        sleep_patcher = mock.patch("utils.time.sleep")
        self.sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)
        session_patcher = mock.patch.object(utils.session, "request")
        self.request = session_patcher.start()
        self.addCleanup(session_patcher.stop)

    def test_structure_query_success_after_temporary_500(self):
        self.request.side_effect = [make_response(500), make_response(500), make_response(200, {"id": 42})]

        with self.assertLogs("classyfire", level="WARNING"):
            self.assertEqual(utils.structure_query("CCO"), 42)

        self.assertEqual(self.request.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        method, called_url = self.request.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(called_url, f"{utils.url}/queries.json")
        self.assertEqual(self.request.call_args.kwargs["timeout"], utils.TIMEOUT)

    def test_backoff_is_exponential_with_jitter(self):
        self.request.side_effect = [make_response(503)] * 4 + [make_response(200, {"id": 1})]

        with mock.patch("utils.random.uniform", return_value=0.5), self.assertLogs("classyfire", level="WARNING"):
            utils.request_with_retry("GET", "http://example.org", backoff_initial=1.0, backoff_max=60.0)

        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1.5, 2.5, 4.5, 8.5])

    def test_permanent_500_raises_after_max_attempts(self):
        self.request.return_value = make_response(500, {"error": "Internal Server Error"})

        with self.assertLogs("classyfire", level="ERROR") as logs:
            with self.assertRaises(utils.ClassyFireRequestError) as ctx:
                utils.structure_query("CCO")

        self.assertEqual(self.request.call_count, 5)
        self.assertEqual(self.sleep.call_count, 4)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.attempts, 5)
        self.assertIsInstance(ctx.exception, requests.exceptions.RequestException)
        message = logs.output[-1]
        self.assertIn("queries.json", message)
        self.assertIn("HTTP 500", message)
        self.assertIn("5 attempts", message)
        self.assertIn("Internal Server Error", message)

    def test_timeout_is_retried_and_finally_raises(self):
        self.request.side_effect = requests.exceptions.ReadTimeout("read timed out")

        with self.assertLogs("classyfire", level="ERROR"):
            with self.assertRaises(utils.ClassyFireRequestError) as ctx:
                utils.get_results(1)

        self.assertEqual(self.request.call_count, 5)
        self.assertIsNone(ctx.exception.status_code)

    def test_success_after_connection_error(self):
        self.request.side_effect = [requests.exceptions.ConnectionError("reset"), make_response(200, {"a": 1})]

        with self.assertLogs("classyfire", level="WARNING"):
            self.assertEqual(json.loads(utils.get_results(1)), {"a": 1})

        self.assertEqual(self.request.call_count, 2)

    def test_429_is_retried_and_honours_retry_after(self):
        self.request.side_effect = [make_response(429, headers={"Retry-After": "7"}), make_response(200, {"id": 3})]

        with self.assertLogs("classyfire", level="WARNING"):
            self.assertEqual(utils.structure_query("CCO"), 3)

        self.assertEqual(self.request.call_count, 2)
        self.assertGreaterEqual(self.sleep.call_args.args[0], 7)

    def test_4xx_is_not_retried(self):
        for status in (400, 401, 403, 404, 422):
            with self.subTest(status=status):
                self.request.reset_mock()
                self.sleep.reset_mock()
                self.request.side_effect = None
                self.request.return_value = make_response(status)

                with self.assertLogs("classyfire", level="ERROR"):
                    with self.assertRaises(utils.ClassyFireRequestError) as ctx:
                        utils.structure_query("CCO")

                self.assertEqual(self.request.call_count, 1)
                self.sleep.assert_not_called()
                self.assertEqual(ctx.exception.status_code, status)
                self.assertEqual(ctx.exception.attempts, 1)

    def test_entity_lookup_returns_none_on_404(self):
        self.request.return_value = make_response(404)

        self.assertIsNone(request_by_inchikey.get_entity_by_inchikey("XXX"))
        self.assertEqual(self.request.call_count, 1)

    def test_entity_lookup_retries_on_502(self):
        self.request.side_effect = [make_response(502), make_response(200, {"smiles": "CCO"})]

        with self.assertLogs("classyfire", level="WARNING"):
            self.assertEqual(request_by_inchikey.get_entity_by_inchikey("XXX"), {"smiles": "CCO"})


if __name__ == "__main__":
    unittest.main()
