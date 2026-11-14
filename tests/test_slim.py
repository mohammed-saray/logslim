import unittest

from logslim.core import Options, collapse_repeats, collapse_stacks, fit_budget, slim
from logslim.tokens import estimate

PY_TRACE = """Traceback (most recent call last):
  File "/app/main.py", line 10, in <module>
    run()
  File "/usr/lib/python3.12/site-packages/click/core.py", line 1157, in __call__
    return self.main(*args, **kwargs)
  File "/usr/lib/python3.12/site-packages/click/core.py", line 1078, in main
    rv = self.invoke(ctx)
  File "/usr/lib/python3.12/site-packages/click/core.py", line 1434, in invoke
    return ctx.invoke(self.callback, **ctx.params)
  File "/usr/lib/python3.12/site-packages/click/core.py", line 783, in invoke
    return __callback(*args, **kwargs)
  File "/app/service.py", line 42, in run
    db.connect()
  File "/usr/lib/python3.12/site-packages/psycopg/connection.py", line 99, in connect
    raise e
psycopg.OperationalError: connection refused"""

JS_TRACE = """TypeError: Cannot read properties of undefined (reading 'id')
    at getUser (/app/src/users.js:12:18)
    at /app/node_modules/express/lib/router/layer.js:95:5
    at next (/app/node_modules/express/lib/router/route.js:149:13)
    at Route.dispatch (/app/node_modules/express/lib/router/route.js:119:3)
    at Layer.handle (/app/node_modules/express/lib/router/layer.js:95:5)
    at /app/node_modules/express/lib/router/index.js:284:15
    at Function.process_params (/app/node_modules/express/lib/router/index.js:346:12)
    at next (/app/node_modules/express/lib/router/index.js:280:10)
    at processTicksAndRejections (node:internal/process/task_queues:95:5)"""


class SlimTests(unittest.TestCase):
    def test_ansi_timestamps_uuids(self):
        text = ("\x1b[31m2026-11-14T10:00:00.123Z ERROR job 3f2b8c1e-1d2a-4b5c-9e8f-0a1b2c3d4e5f failed\x1b[0m\n"
                "[10:00:01] INFO retrying 3f2b8c1e-1d2a-4b5c-9e8f-0a1b2c3d4e5f")
        out = slim(text)
        self.assertEqual(out, "ERROR job <uuid> failed\nINFO retrying <uuid>")

    def test_duplicates_and_similar(self):
        lines = ["GET /health 200"] * 50 + [f"processed item {i} in {i * 3}ms" for i in range(30)] + ["done"]
        out = collapse_repeats(lines, True, 4)
        self.assertEqual(out[0], "GET /health 200   [×50]")
        self.assertEqual(out[1], "processed item 0 in 0ms")
        self.assertEqual(out[2], "    … 28 similar lines …")
        self.assertEqual(out[3], "processed item 29 in 87ms")
        self.assertEqual(out[-1], "done")

    def test_progress_bars(self):
        text = "\n".join(f"Downloading model {p}% |{'█' * (p // 10)}" for p in range(0, 101, 5)) + "\nready"
        out = slim(text).splitlines()
        self.assertEqual(len(out), 2)
        self.assertIn("100%", out[0])
        self.assertIn("earlier updates hidden", out[0])
        self.assertEqual(slim("a\rb\rfinal state"), "final state")

    def test_python_stack(self):
        out = slim(PY_TRACE)
        self.assertIn('File "/app/main.py", line 10', out)
        self.assertIn('File "/app/service.py", line 42', out)
        self.assertIn("library frames hidden", out)
        self.assertIn("psycopg.OperationalError: connection refused", out)
        self.assertLess(estimate(out), estimate(PY_TRACE))
        self.assertNotIn("core.py\", line 1078", out)

    def test_js_stack(self):
        out = collapse_stacks(JS_TRACE.splitlines(), keep=1)
        self.assertIn("    at getUser (/app/src/users.js:12:18)", out)
        self.assertTrue(any("library frames hidden" in l for l in out))
        self.assertEqual(out[-1], "    at processTicksAndRejections (node:internal/process/task_queues:95:5)")

    def test_budget_keeps_errors_and_tail(self):
        lines = [f"step {i}: ok {'x' * 40}" for i in range(2000)]
        lines[1200] = "FATAL: disk full on /var/lib/data"
        out = fit_budget(lines, 600, 2, estimate)
        joined = "\n".join(out)
        self.assertIn("FATAL: disk full", joined)
        self.assertIn("step 1999", joined)
        self.assertIn("lines omitted", joined)
        self.assertLessEqual(estimate(joined), 600)

    def test_options_off(self):
        text = "2026-11-14 10:00:00 hello\n2026-11-14 10:00:00 hello"
        out = slim(text, Options(strip_timestamps=False, normalize=False, dedupe=False))
        self.assertEqual(out, text)

    def test_cli(self):
        import io
        import sys
        from logslim import cli
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.TextIOWrapper(io.BytesIO(("line\n" * 20).encode()))
        sys.stdout = io.StringIO()
        try:
            self.assertEqual(cli.main(["-q", "-p"]), 0)
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        self.assertIn("line   [×20]", out)
        self.assertTrue(out.startswith("Here is the relevant log output"))


if __name__ == "__main__":
    unittest.main()
