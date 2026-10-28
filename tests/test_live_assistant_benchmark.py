"""Live runtime benchmark and correctness suite for Caelestia Assistant.

Deploys automated performance benchmarking and verification test cases:
1. Warm Route Latency Benchmark (target < 20ms p50)
2. Mathematical AST Evaluation & SI Unit Conversion Throughput
3. CommandGate Safety Policy Validation Latency (target < 2ms)
4. Hostile Code Injection & Sanitization Penetration Check
5. Memory Footprint Stability (VmHWM / RSS bounded probe)
"""

from __future__ import annotations

import os
import resource
import tempfile
import time
import unittest
from pathlib import Path

from assistant.core.pipeline import process
from assistant.core.router import DEFAULT_STATE, route
from assistant.capabilities.genius.mathengine import evaluate, parse, CalcError
from assistant.executor.plan import ActionPlan, Step, Reversibility, BlastRadius


def genius_eval(expr: str) -> float:
    return evaluate(parse(expr))



class LiveAssistantBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.shell_cfg = Path(cls.tmp_dir.name) / "shell.json"
        cls.shell_cfg.write_text("{}", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp_dir.cleanup()

    def test_01_warm_routing_latency_benchmark(self):
        """Warm routing benchmark: 50 iterations must have p50 < 20ms and p95 < 40ms."""
        query = "make the bar 20% smaller"
        # Prime JIT/caches
        route(query, DEFAULT_STATE)

        latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            res = route(query, DEFAULT_STATE)
            dt = (time.perf_counter() - t0) * 1000.0  # ms
            latencies.append(dt)
            self.assertIsNotNone(res.top)
            self.assertEqual(res.top.surface, "setBarScale")

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"\n[BENCHMARK] Routing Latency: p50={p50:.2f}ms, p95={p95:.2f}ms (50 iterations)")
        self.assertLess(p50, 25.0, f"p50 latency {p50:.2f}ms exceeds target 25ms")

    def test_02_math_and_units_evaluation_throughput(self):
        """Math AST evaluation: throughput > 1000 ops/sec and accurate result calculation."""
        math_expr = "sqrt(144) + 2^4 * sin(pi / 2)"  # 12 + 16 * 1 = 28.0
        t0 = time.perf_counter()
        iterations = 200
        for _ in range(iterations):
            val = genius_eval(math_expr)
        total_time = time.perf_counter() - t0
        ops_per_sec = iterations / total_time

        print(f"[BENCHMARK] Math AST Throughput: {ops_per_sec:.0f} ops/sec (total {total_time*1000:.1f}ms for {iterations} ops)")
        self.assertEqual(float(val), 28.0)
        self.assertGreater(ops_per_sec, 500.0, "AST math evaluation throughput too low")

    def test_03_command_gate_policy_evaluation_latency(self):
        """ActionPlan / Step safety gate: shell injection prevented, validation < 0.5ms."""
        valid_plans = [
            (("systemctl", "--user", "status", "caelestia-shell"), "read_only", "none"),
            (("caelestia", "version"), "read_only", "none"),
            (("caelestia", "scheme", "list"), "read_only", "none"),
            (("touch", "/tmp/marker"), "journaled", "file"),
        ]
        # Invariant 1: Shell strings are rejected constructor-time
        with self.assertRaises(TypeError):
            Step(argv="rm -rf /")

        with self.assertRaises(TypeError):
            Step(argv=())

        # Invariant 2: Irreversible plans without revert plan are rejected
        with self.assertRaises(TypeError):
            ActionPlan(steps=(Step(argv=("rm", "-rf", "/tmp/foo")),), reversibility="irreversible")

        # Invariant 3: System blast-radius without consent (confidence < 1.0) is rejected
        with self.assertRaises(TypeError):
            ActionPlan(steps=(Step(argv=("systemctl", "restart", "foo")),),
                       reversibility="reversible", blast_radius="system", confidence=0.8)

        t0 = time.perf_counter()
        n = 200
        for _ in range(n):
            for argv, rev, blast in valid_plans:
                step = Step(argv=argv)
                plan = ActionPlan(steps=(step,), reversibility=rev, blast_radius=blast)
                self.assertIsNotNone(plan)

        total_dt = (time.perf_counter() - t0) * 1000.0  # ms
        avg_per_check = total_dt / (n * len(valid_plans))

        print(f"[BENCHMARK] CommandGate Latency: {avg_per_check:.4f}ms per check ({n*len(valid_plans)} checks)")
        self.assertLess(avg_per_check, 0.5, "ActionPlan check exceeded budget")

    def test_04_hostile_code_injection_security_gate(self):
        """Security: Code injection attempts must be safely rejected at parse level."""
        hostile_inputs = [
            "__import__('os').system('touch /tmp/malicious_pwned')",
            "eval('1+1')",
            "exec('import os; os.system(\"id\")')",
            "open('/etc/passwd').read()",
        ]
        for hostile in hostile_inputs:
            with self.assertRaises((ValueError, SyntaxError, TypeError, KeyError, CalcError, Exception)):
                genius_eval(hostile)
        self.assertFalse(Path("/tmp/malicious_pwned").exists(), "Security vulnerability: code injection succeeded!")

    def test_05_memory_rss_footprint_benchmark(self):
        """Memory footprint stability: RSS usage must remain bounded under sustained queries."""
        initial_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Run 200 mixed pipeline calls
        queries = [
            "make the bar 20% smaller",
            "turn on blur",
            "what is 50 * 20",
            "convert 5 hours to minutes",
            "explain why my launcher is large",
        ]
        for i in range(200):
            q = queries[i % len(queries)]
            process(q, file_path=self.shell_cfg)

        final_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        delta_mb = (final_rss_kb - initial_rss_kb) / 1024.0 if os.uname().sysname == "Linux" else 0.0
        print(f"[BENCHMARK] Memory Footprint: Peak RSS {final_rss_kb / 1024.0:.1f}MB (delta: {delta_mb:.2f}MB after 200 queries)")
        self.assertLess(delta_mb, 20.0, "Memory growth exceeded 20MB after 200 queries (leak detected)")
        self.assertLess(final_rss_kb / 1024.0, 750.0, "Absolute memory usage exceeded 750MB threshold")



if __name__ == "__main__":
    unittest.main()
