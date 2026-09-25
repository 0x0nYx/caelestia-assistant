"""genius.cli — the command surface of the universal intelligence layer.

    python3 -m assistant.genius "what is 15% of 80"
    caelestia-assist do "solve x^2 - 2 = 0"          # via the hub
    caelestia-assist genius stats "1,2,3,4,5"       # direct domain access

Every command prints a human-readable result by default and machine JSON
with --json. Nothing writes except `learn`, which updates the learned
routing weights inside the brain's own state file (same atomic path the
other learners use).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import (baysnet, creative, data, decision, language, linalg, logic,
               markov, mathengine, metacog, probability, stats, sysintel,
               tasks)
from . import meta as genius_meta


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True, default=str))
        return
    _pretty(obj)


def _pretty(obj: Any, indent: int = 0) -> None:
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = k.replace("_", " ")
            if isinstance(v, (dict, list)):
                print(f"{pad}{key}:")
                _pretty(v, indent + 1)
            else:
                print(f"{pad}{key}: {v}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _pretty(item, indent)
            else:
                print(f"{pad}- {item}")
    else:
        print(f"{pad}{obj}")


# ---------------------------------------------------------------------------
# command implementations
# ---------------------------------------------------------------------------

def cmd_do(args, out) -> int:
    text = args.text if args.text else (Path(args.stdin_file).read_text() if
                                        args.stdin_file else "")
    if not text.strip():
        print("genius: give me something to do — a calculation, text, a goal",
              file=sys.stderr)
        return 2
    from ..brain import state as st
    state = st.load() if Path(st.DEFAULT_STATE).exists() else {}
    result = genius_meta.route_and_do(text, state.get("genius_learn"))
    if args.json:
        _print(result, True)
        return 0 if result.get("ok", result.get("verdict") == "ROUTE") else 1
    _print(result, False)
    return 0 if result.get("ok", result.get("verdict") == "ROUTE") else 1


def cmd_math(args, out) -> int:
    try:
        _print(mathengine.expression_info(args.expr), args.json)
        return 0
    except mathengine.CalcError as exc:
        print(f"genius math: {exc}", file=sys.stderr)
        return 1


def cmd_solve(args, out) -> int:
    try:
        res = mathengine.solve_root(args.expr, method=args.method,
                                    lo=args.lo, hi=args.hi, x0=args.x0)
        _print(res, args.json)
        return 0
    except mathengine.CalcError as exc:
        print(f"genius solve: {exc}", file=sys.stderr)
        return 1


def cmd_calc(args, out) -> int:
    try:
        if args.derivative:
            node = mathengine.parse(args.derivative)
            d = mathengine.simplify(mathengine.differentiate(node))
            _print({"expr": mathengine.to_str(node),
                    "derivative": mathengine.to_str(d),
                    "simplified": mathengine.to_str(mathengine.simplify(node))},
                   args.json)
        elif args.integral:
            _print(mathengine.integrate(args.integral, args.a, args.b,
                                        method=args.quad), args.json)
        elif args.taylor:
            _print(mathengine.taylor(args.taylor, around=args.at,
                                     order=args.order), args.json)
        elif args.ode:
            _print(mathengine.ode_solve(args.ode, args.x0, args.y0,
                                        args.end, args.h, method=args.ode_method), args.json)
        else:
            print("genius calculus: pick --derivative/--integral/--taylor/--ode",
                  file=sys.stderr)
            return 2
        return 0
    except mathengine.CalcError as exc:
        print(f"genius calculus: {exc}", file=sys.stderr)
        return 1


def _numlist(s: str) -> List[float]:
    return [float(x) for x in s.replace(",", " ").split()]


def cmd_stats(args, out) -> int:
    try:
        nums = _numlist(args.nums)
        d = stats.describe(nums)
        result: Dict[str, Any] = {"describe": d}
        if args.test:
            if args.test == "outliers":
                result["outliers"] = stats.detect_outliers(nums, method=args.om or "iqr")
            elif args.test == "normality":
                result["jarque_bera"] = stats.jarque_bera(nums)
        if len(nums) >= 8:
            result["acf"] = data.autocorrelation(nums)
        _print(result, args.json)
        return 0
    except ValueError as exc:
        print(f"genius stats: {exc}", file=sys.stderr)
        return 1


def cmd_solve_matrix(args, out) -> int:
    try:
        rows = json.loads(args.matrix)
        a = [[float(v) for v in r] for r in rows]
        result = {"determinant": linalg.determinant(a), "rank": linalg.rank(a)}
        try:
            lam, vec = linalg.power_iteration(a)
            result["dominant_eigenvalue"] = lam
            result["dominant_eigenvector"] = [round(v, 6) for v in vec]
        except linalg.LinAlgError:
            pass
        if args.b:
            b = _numlist(args.b)
            result["solution"] = linalg.solve(a, b)
        _print(result, args.json)
        return 0
    except (ValueError, linalg.LinAlgError) as exc:
        print(f"genius matrix: {exc}", file=sys.stderr)
        return 1


def cmd_probability(args, out) -> int:
    try:
        if args.bayes:
            p, lh, lf = (float(x) for x in args.bayes.split(","))
            _print(probability.bayes(p, lh, lf), args.json)
        elif args.ncr:
            n, r = (int(x) for x in args.ncr.split(","))
            _print({"nCr": probability.nCr(n, r), "nPr": probability.nPr(n, r)}, args.json)
        elif args.mc:
            expr, n = args.mc, args.n
            _print(probability.simulate_expression(expr, n=n), args.json)
        elif args.markov:
            m = json.loads(args.markov)
            _print(probability.markov_stationary(m), args.json)
        else:
            print("genius prob: pick --bayes p,pe|pe / --ncr n,r / --mc 'expr' / --markov T",
                  file=sys.stderr)
            return 2
        return 0
    except (ValueError, KeyError) as exc:
        print(f"genius prob: {exc}", file=sys.stderr)
        return 1


def cmd_logic(args, out) -> int:
    try:
        if args.equivalent:
            parts = args.equivalent.split("|")
            _print(logic.equivalent(parts[0].strip(), parts[1].strip()), args.json)
        elif args.entails:
            parts = args.entails.split("|")
            _print(logic.entails(parts[0].strip(), parts[1].strip()), args.json)
        elif args.sat:
            _print(logic.sat_solve(args.sat), args.json)
        elif args.rules:
            spec = json.loads(Path(args.rules).read_text())
            _print(logic.rule_infer(spec["rules"], spec.get("facts", [])), args.json)
        else:
            _print(logic.classify_formula(args.formula), args.json)
        return 0
    except logic.LogicError as exc:
        print(f"genius logic: {exc}", file=sys.stderr)
        return 1


def cmd_decide(args, out) -> int:
    try:
        matrix = json.loads(args.matrix)
        labels = args.labels.split(",")
        criteria = args.criteria.split(",")
        weights = [float(x) for x in args.weights.split(",")]
        benefits = ([x == "1" for x in args.benefits.split(",")]
                    if args.benefits else None)
        method = args.method
        if method == "ahp":
            _print(decision.ahp(matrix, labels), args.json)
        elif method == "pareto":
            _print(decision.pareto_frontier(matrix, labels, benefits), args.json)
        elif method == "regret":
            _print(decision.minimax_regret(matrix, labels, criteria), args.json)
        elif method == "topsis":
            _print(decision.topsis(matrix, labels, weights, criteria, benefits), args.json)
        else:
            _print(decision.weighted_sum(matrix, labels, weights, criteria, benefits), args.json)
            if args.sensitivity:
                _print(decision.sensitivity(matrix, labels, weights, criteria, benefits), args.json)
        return 0
    except ValueError as exc:
        print(f"genius decide: {exc}", file=sys.stderr)
        return 1


def cmd_tree(args, out) -> int:
    try:
        raw = args.tree
        if raw.endswith(".json") and Path(raw).exists():
            raw = Path(raw).read_text()
        tree = json.loads(raw)
        _print(decision.decision_tree(tree), args.json)
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f"genius tree: {exc}", file=sys.stderr)
        return 1


def cmd_data(args, out) -> int:
    try:
        if args.csv:
            text = Path(args.csv).read_text(encoding="utf-8", errors="replace")
            table = data.parse_table(text, delimiter=args.delimiter)
            if args.profile:
                _print(data.profile_table(table), args.json)
            elif args.groupby:
                key, value, agg = (args.groupby.split(":") + ["mean"])[:3]
                _print(data.groupby(table, key, value, agg), args.json)
            elif args.corr:
                _print(data.correlation_matrix(table, method=args.corr), args.json)
            else:
                _print(data.profile_table(table), args.json)
        elif args.series:
            nums = _numlist(args.series)
            if len(nums) < 3:
                raise ValueError("series needs >= 3 numbers")
            if args.cluster:
                pts = [[nums[i], nums[i + 1]] for i in range(len(nums) - 1)]
                km = data.kmeans(pts, k=args.cluster)
                _print(km, args.json)
            elif args.changepoints:
                _print(data.changepoints(nums), args.json)
            elif args.forecast:
                _print(data.forecast_ar(nums, horizon=args.forecast), args.json)
            else:
                out_d: Dict[str, Any] = {"describe": stats.describe(nums)}
                out_d["autocorrelation"] = data.autocorrelation(nums)
                if len(nums) >= 8:
                    out_d["changepoints"] = data.changepoints(nums)
                    out_d["forecast_ar"] = data.forecast_ar(nums, horizon=5)
                _print(out_d, args.json)
        else:
            print("genius data: pick --csv FILE or --series NUMS", file=sys.stderr)
            return 2
        return 0
    except (ValueError, KeyError) as exc:
        print(f"genius data: {exc}", file=sys.stderr)
        return 1


def cmd_text(args, out) -> int:
    text = args.text or (Path(args.file).read_text(encoding="utf-8", errors="replace")
                         if args.file else "")
    if not text.strip():
        print("genius text: give me text (positional or --file)", file=sys.stderr)
        return 2
    result: Dict[str, Any] = {}
    if args.all or (not any([args.sentiment, args.readability, args.keywords,
                             args.entities, args.language, args.stats])):
        result["sentiment"] = language.sentiment(text)
        result["keywords"] = language.rake_keywords(text, top=8)["keywords"]
        result["stats"] = language.text_stats(text)
    if args.sentiment:
        result["sentiment"] = language.sentiment(text)
    if args.readability:
        result["readability"] = language.readability(text)
    if args.keywords:
        result["keywords_rake"] = language.rake_keywords(text, top=10)["keywords"]
        result["keywords_yake"] = language.yake_keywords(text, top=10)["keywords"]
    if args.entities:
        result["entities"] = language.extract_entities(text)["entities"]
    if args.language:
        result["language"] = language.detect_language(text)
    if args.stats:
        result["stats"] = language.text_stats(text)
    _print(result, args.json)
    return 0


def cmd_qa(args, out) -> int:
    try:
        source = (Path(args.from_file).read_text(encoding="utf-8", errors="replace")
                  if args.from_file else args.source)
        _print(language.answer_question(args.question, source), args.json)
        return 0
    except (ValueError, OSError) as exc:
        print(f"genius qa: {exc}", file=sys.stderr)
        return 1


def cmd_summarize(args, out) -> int:
    try:
        source = (Path(args.file).read_text(encoding="utf-8", errors="replace")
                  if args.file else args.text)
        _print(language.summarize_focused(source, args.query or "main topics",
                                          n_sentences=args.sentences), args.json)
        return 0
    except ValueError as exc:
        print(f"genius summarize: {exc}", file=sys.stderr)
        return 1


def cmd_palette(args, out) -> int:
    try:
        if args.contrast:
            _print(creative.contrast_ratio(args.hex, args.contrast), args.json)
        elif args.accent:
            _print(creative.auto_accent(args.hex, mode=args.accent), args.json)
        else:
            _print(creative.palette(args.hex, harmony=args.harmony,
                                    n=args.count, seed=args.seed), args.json)
        return 0
    except ValueError as exc:
        print(f"genius palette: {exc}", file=sys.stderr)
        return 1


def cmd_generate(args, out) -> int:
    try:
        if args.name:
            _print(markov.generate_name(args.name, pattern=args.pattern), args.json)
        elif args.tagline:
            _print(creative.tagline(args.tagline, tone=args.tone), args.json)
        elif args.corpus:
            corpus = Path(args.corpus).read_text(encoding="utf-8", errors="replace")
            _print(markov.generate_text(corpus, n_words=args.words, order=args.order,
                                        seed=args.seed), args.json)
        elif args.ideas:
            _print(creative.idea_sprint(args.ideas, seed=args.seed), args.json)
        else:
            print("genius gen: pick --name N / --tagline X / --corpus F / --ideas T",
                  file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError) as exc:
        print(f"genius gen: {exc}", file=sys.stderr)
        return 1


def cmd_sys(args, out) -> int:
    try:
        if args.duplicates:
            _print(sysintel.find_duplicates(args.duplicates), args.json)
        elif args.disk:
            _print(sysintel.disk_hotspots(args.disk, depth=args.depth), args.json)
        elif args.logs:
            lines = Path(args.logs).read_text(
                encoding="utf-8", errors="replace").splitlines()
            _print(sysintel.mine_log_templates(lines), args.json)
        elif args.lint:
            _print(sysintel.lint_json_config(args.lint), args.json)
        else:
            print("genius sys: pick --duplicates DIR / --disk DIR / --logs FILE / --lint FILE",
                  file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError) as exc:
        print(f"genius sys: {exc}", file=sys.stderr)
        return 1


def cmd_history(args, out) -> int:
    try:
        parsed = sysintel.parse_shell_history(args.file)
        if not parsed["commands"]:
            print(f"genius history: {parsed['note']}", file=sys.stderr)
            return 1
        _print(sysintel.analyze_history(parsed["commands"],
                                         parsed["timestamps"]), args.json)
        return 0
    except (ValueError, OSError) as exc:
        print(f"genius history: {exc}", file=sys.stderr)
        return 1


def cmd_plan(args, out) -> int:
    result = tasks.decompose(args.goal)
    if result["verdict"] == "DECOMPOSED" and args.fit:
        result["today_fit"] = tasks.fit_today(result["steps"], args.fit)
    _print(result, args.json)
    return 0 if result["verdict"] == "DECOMPOSED" else 2



def cmd_graphs(args, out) -> int:
    """graphs: dijkstra / topsort / mst / assign — classical graph algorithms."""
    import json as _json
    from . import graphs as g
    try:
        if args.action == "dijkstra":
            graph = _json.loads(args.data)
            res = g.dijkstra(graph, args.source, target=args.target)
            res["algorithm"] = "dijkstra O((V+E) log V)"
        elif args.action == "topsort":
            edges = [tuple(e) for e in _json.loads(args.data)]
            res = g.toposort(edges)
            res["algorithm"] = "kahn toposort O(V+E)"
        elif args.action == "mst":
            payload = _json.loads(args.data)
            res = g.min_spanning_tree(payload["nodes"],
                                      [tuple(e) for e in payload["edges"]])
            res["algorithm"] = "kruskal O(E log E)"
        elif args.action == "assign":
            rows = [float(x) for x in args.rows.split(",")]
            cost = [[float(x) for x in row.split(",")]
                    for row in args.costs.split(";")]
            res = g.hungarian(cost)
            res["rows"] = rows
            res["algorithm"] = "hungarian/jonker-volgenant O(n^2 m)"
        else:
            raise ValueError(f"unknown graphs action {args.action!r}")
    except (ValueError, KeyError, TypeError, _json.JSONDecodeError) as exc:
        print(f"genius graphs: {exc}", file=sys.stderr)
        return 1
    _print(res, args.json)
    return 0


def cmd_optimize(args, out) -> int:
    """optimize: anneal / hillclimb / genetic / pareto / ternary."""
    import json as _json
    from . import mathengine as me
    from . import optimize as op
    try:
        if args.action == "pareto":
            points = _json.loads(args.target or "[]")
            axes = args.axes or (list(points[0].keys()) if points else [])
            dirs = (args.directions.split(",") if args.directions
                    else ["min"] * len(axes))
            res = op.pareto_frontier(points, list(axes), dirs)
            res["algorithm"] = "non-dominated frontier"
        elif args.action == "ternary":
            expr = args.expr or args.target or "x^2"
            res = op.ternary_min(lambda x: me.expression_info(expr, {"x": x})["value"],
                                 args.lo, args.hi)
            res["algorithm"] = "ternary search on unimodal f"
        elif args.action in ("anneal", "hillclimb", "genetic"):
            node = me.parse(args.expr or args.target or "x^2")
            bounds = ([tuple(b) for b in
                       _json.loads(args.bounds)] if args.bounds else [])
            lo_x = bounds[0][0] if bounds else -10.0
            # variable names from the AST (parse-level, no evaluation):
            var_names = sorted({n.name for n in me._walk(node)
                                if n.kind == "var"}) or ["x"]

            def energy(vec):
                env = dict(zip(var_names, vec))
                return me.evaluate(node, env)
            x0 = ([float(v) for v in args.x0.split(",")] if args.x0
                  else [lo_x])
            if args.action == "anneal":
                res = op.anneal(energy, x0, bounds=bounds)
                res["algorithm"] = "simulated annealing"
            elif args.action == "hillclimb":
                res = op.hill_climb(energy, x0, bounds=bounds)
                res["algorithm"] = "hill climbing + restarts"
            else:
                if not bounds:
                    raise ValueError("genetic needs --bounds [[lo,hi], ...]")
                res = op.genetic(energy, bounds)
                res["algorithm"] = "steady-state genetic algorithm"
        else:
            raise ValueError(f"unknown optimize action {args.action!r}")
    except (ValueError, KeyError, TypeError, _json.JSONDecodeError,
            me.CalcError) as exc:
        print(f"genius optimize: {exc}", file=sys.stderr)
        return 1
    _print(res, args.json)
    return 0


def cmd_report(args, out) -> int:
    from ..brain import state as st
    state = st.load() if Path(st.DEFAULT_STATE).exists() else {}
    ledger_path = Path(args.ledger)
    if ledger_path.exists():
        proposals = json.loads(ledger_path.read_text()).get("proposals", [])
    else:
        proposals = []
    usage = [{"domain": p.get("kind", "unknown"),
              "accepted": p.get("status") == "approved",
              "day": 1}
             for p in proposals if p.get("status") in ("approved", "rejected")]
    history = [{"features": {"kind": p.get("kind", "?"),
                             "confidence": ("high" if p.get("confidence", 0) >= 0.7
                                            else "low"),
                             "target_word": str(p.get("target", "")).split()[0]
                             if str(p.get("target", "")).split() else "-"},
                "outcome": "approve" if p.get("status") == "approved" else "reject"}
               for p in proposals if p.get("status") in ("approved", "rejected")]
    requests = [str(p.get("reason", ""))[:120] for p in proposals if p.get("reason")]
    report: Dict[str, Any] = {
        "n_proposals": len(proposals),
        "n_decided": len(usage),
        "coverage": metacog.coverage_map(usage),
        "learned_rules": metacog.induce_rules(history),
        "request_clusters": metacog.cluster_requests(requests) if requests else None,
        "learned_routing": state.get("genius_learn"),
        "self": {"modules": 15, "domains": len(genius_meta._DOMAIN_CUES),
                 "llm": "none — classical algorithms only"},
    }
    _print(report, args.json)
    return 0


def cmd_learn(args, out) -> int:
    from ..brain import state as st
    state = st.load() if Path(st.DEFAULT_STATE).exists() else {}
    table = genius_meta.learn_feedback(args.text, args.domain,
                                        args.decision == "approve",
                                        state.get("genius_learn"))
    state["genius_learn"] = table
    st.save(state)
    _print({"updated": True, "domain": args.domain,
            "decision": args.decision,
            "n_tokens": sum(len(w) for w in table.values())}, args.json)
    return 0


def cmd_classify(args, out) -> int:
    try:
        if args.train:
            clf = language.TextClassifier()
            texts, labels = [], []
            for line in Path(args.train).read_text().splitlines():
                if "|" in line:
                    t, l = line.rsplit("|", 1)
                    texts.append(t.strip())
                    labels.append(l.strip())
            clf.fit(texts, labels)
            _print(clf.predict(args.text), args.json)
            return 0
        print("genius classify: --train examples.txt (lines of 'text|label')",
              file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"genius classify: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genius",
                                 description="universal local intelligence layer (no LLM)")
    sub = p.add_subparsers(dest="cmd")

    def sp(name: str, fn, **kw):
        q = sub.add_parser(name, **kw)
        q.add_argument("--json", action="store_true", help="machine-readable output")
        q.set_defaults(fn=fn)
        return q

    q = sp("do", cmd_do, help="any request: classify then dispatch")
    q.add_argument("text", nargs="?", default="")
    q.add_argument("--stdin-file", default=None)

    q = sp("math", cmd_math, help="evaluate an arithmetic expression")
    q.add_argument("expr")

    q = sp("solve", cmd_solve, help="find a root of f(x)=0")
    q.add_argument("expr")
    q.add_argument("--method", default="bisection", choices=["bisection", "newton", "secant"])
    q.add_argument("--lo", type=float, default=-100.0)
    q.add_argument("--hi", type=float, default=100.0)
    q.add_argument("--x0", type=float, default=None)

    q = sp("calc", cmd_calc, help="derivative / integral / taylor / ode")
    q.add_argument("--derivative")
    q.add_argument("--integral")
    q.add_argument("--a", type=float, default=0.0)
    q.add_argument("--b", type=float, default=1.0)
    q.add_argument("--quad", default="simpson", choices=["trapezoid", "simpson", "adaptive"])
    q.add_argument("--taylor")
    q.add_argument("--at", type=float, default=0.0)
    q.add_argument("--order", type=int, default=5)
    q.add_argument("--ode")
    q.add_argument("--x0", type=float, default=0.0)
    q.add_argument("--y0", type=float, default=1.0)
    q.add_argument("--end", type=float, default=1.0)
    q.add_argument("--h", type=float, default=0.01)
    q.add_argument("--ode-method", default="rk4", choices=["euler", "rk4"],
                   dest="ode_method")

    q = sp("stats", cmd_stats, help="descriptive statistics on numbers")
    q.add_argument("nums")
    q.add_argument("--test", choices=["outliers", "normality"])
    q.add_argument("--om", choices=["iqr", "zscore", "mad"])

    q = sp("matrix", cmd_solve_matrix, help="matrix ops (det/rank/eigen/solve)")
    q.add_argument("matrix", help="JSON rows, e.g. '[[2,1],[1,3]]'")
    q.add_argument("--b", help="JSON/vector to solve Ax=b, e.g. 4,5")

    q = sp("prob", cmd_probability, help="probability: bayes/ncr/mc/markov")
    q.add_argument("--bayes", help="prior,likelihood,false-positive")
    q.add_argument("--ncr", help="n,r")
    q.add_argument("--mc", help="expression over u1..u9")
    q.add_argument("--n", type=int, default=100000)
    q.add_argument("--markov", help="JSON transition matrix")

    q = sp("logic", cmd_logic, help="propositional logic: classify/sat/...")
    q.add_argument("formula", nargs="?", default="")
    q.add_argument("--equivalent", help="A | B")
    q.add_argument("--entails", help="A | B")
    q.add_argument("--sat")
    q.add_argument("--rules", help="JSON file {rules: [...], facts: [...]}")

    q = sp("decide", cmd_decide, help="multi-criteria decision analysis")
    q.add_argument("--matrix", required=True, help="JSON rows alternatives x criteria")
    q.add_argument("--labels", required=True)
    q.add_argument("--criteria", required=True)
    q.add_argument("--weights", default="1,1")
    q.add_argument("--benefits", help="1,0,1 (1=benefit, 0=cost)")
    q.add_argument("--method", default="wsm",
                   choices=["wsm", "wpm", "topsis", "ahp", "pareto", "regret"])
    q.add_argument("--sensitivity", action="store_true")

    q = sp("tree", cmd_tree, help="expected-value decision tree (JSON)")
    q.add_argument("tree", help="JSON tree inline, or a .json file path")

    q = sp("data", cmd_data, help="tabular + time-series analysis")
    q.add_argument("--csv")
    q.add_argument("--delimiter", default=",")
    q.add_argument("--series")
    q.add_argument("--profile", action="store_true")
    q.add_argument("--groupby", help="key:value:agg")
    q.add_argument("--corr", choices=["pearson", "spearman"])
    q.add_argument("--cluster", type=int)
    q.add_argument("--changepoints", action="store_true")
    q.add_argument("--forecast", type=int)

    q = sp("text", cmd_text, help="text intelligence")
    q.add_argument("text", nargs="?", default="")
    q.add_argument("--file")
    q.add_argument("--sentiment", action="store_true")
    q.add_argument("--readability", action="store_true")
    q.add_argument("--keywords", action="store_true")
    q.add_argument("--entities", action="store_true")
    q.add_argument("--language", action="store_true")
    q.add_argument("--stats", action="store_true")
    q.add_argument("--all", action="store_true")

    q = sp("qa", cmd_qa, help="question answering over text")
    q.add_argument("question")
    q.add_argument("--source", default="")
    q.add_argument("--from-file", dest="from_file")

    q = sp("summarize", cmd_summarize, help="query-focused extractive summary")
    q.add_argument("--text", default="")
    q.add_argument("--file")
    q.add_argument("--query", default="")
    q.add_argument("--sentences", type=int, default=3)

    q = sp("classify", cmd_classify, help="self-learning text classifier")
    q.add_argument("text")
    q.add_argument("--train")

    q = sp("palette", cmd_palette, help="OKLch palette + contrast")
    q.add_argument("hex")
    q.add_argument("--harmony", default="analogous",
                   choices=["complementary", "analogous", "triadic", "tetradic",
                            "split_complementary"])
    q.add_argument("--count", type=int, default=5)
    q.add_argument("--seed", type=int, default=7)
    q.add_argument("--contrast", help="second hex for contrast ratio")
    q.add_argument("--accent", choices=["auto", "boost", "brighten", "hue_shift"])

    q = sp("gen", cmd_generate, help="generation: names/taglines/markov/ideas")
    q.add_argument("--name", type=int)
    q.add_argument("--pattern")
    q.add_argument("--tagline")
    q.add_argument("--tone", default="confident",
                   choices=["confident", "playful", "minimal"])
    q.add_argument("--corpus")
    q.add_argument("--words", type=int, default=40)
    q.add_argument("--order", type=int, default=2)
    q.add_argument("--ideas")
    q.add_argument("--seed", type=int, default=7)

    q = sp("sys", cmd_sys, help="system scans (read-only)")
    q.add_argument("--duplicates")
    q.add_argument("--disk")
    q.add_argument("--depth", type=int, default=3)
    q.add_argument("--logs")
    q.add_argument("--lint")

    q = sp("history", cmd_history, help="shell history mining")
    q.add_argument("file")

    q = sp("plan", cmd_plan, help="decompose a goal into steps")
    q.add_argument("goal")
    q.add_argument("--fit", type=int)

    gr = sp("graphs", cmd_graphs, help="graph algorithms: dijkstra/topsort/mst/assign")
    gr.add_argument("action", choices=["dijkstra", "topsort", "mst", "assign"])
    gr.add_argument("data", nargs="?", default="{}", help="JSON payload")
    gr.add_argument("--source", default="a")
    gr.add_argument("--target", default=None)
    gr.add_argument("--rows", default="", help="comma numbers for assign")
    gr.add_argument("--costs", default="", help="';'-separated rows for assign")

    op_ = sp("optimize", cmd_optimize, help="anneal/hillclimb/genetic/pareto/ternary")
    op_.add_argument("action",
                     choices=["anneal", "hillclimb", "genetic", "pareto", "ternary"])
    op_.add_argument("target", nargs="?", default=None,
                     help="energy expression in x (optimizers) or JSON points (pareto)")
    op_.add_argument("--expr", default=None,
                     help="override the energy expression")
    op_.add_argument("--x0", default=None)
    op_.add_argument("--bounds", default=None, help="JSON [[lo,hi], ...]")
    op_.add_argument("--lo", type=float, default=-10.0)
    op_.add_argument("--hi", type=float, default=10.0)
    op_.add_argument("--axes", nargs="*", default=None)
    op_.add_argument("--directions", default=None)

    q = sp("report", cmd_report, help="self-reflection over your ledger")
    q.add_argument("--ledger", default=str(Path.home() /
                                            ".local/state/caelestia-brain/ledger.json"))

    q = sp("learn", cmd_learn, help="teach the router (approve/reject feedback)")
    q.add_argument("--text", required=True)
    q.add_argument("--domain", required=True)
    q.add_argument("--decision", required=True, choices=["approve", "reject"])

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    # universal form: `genius "some request"` == `genius do "some request"`
    subcommands = {"do", "math", "solve", "calc", "stats", "matrix", "prob",
                   "logic", "decide", "tree", "data", "text", "qa", "summarize",
                   "classify", "palette", "gen", "sys", "history", "plan",
                   "graphs", "optimize", "report", "learn"}
    if argv and not argv[0].startswith("-") and argv[0] not in subcommands:
        argv = ["do"] + argv
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.fn(args, None)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
