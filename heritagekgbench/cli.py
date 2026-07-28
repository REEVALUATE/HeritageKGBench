"""Command-line interface for the HeritageKGBench evaluation harness.

Subcommands:
  evaluate      Score a directory of prediction JSONs against the gold standard.
  run           Run a baseline pipeline variant (single_prompt/baseline/shacl)
                over the benchmark texts (needs [pipeline] extras + API key).
  fm-metrics    Compute failure-mode metrics FM1/FM2/FM5/FM6/FM7 over the
                shipped V1/V2/V4 predictions.
  significance  Bootstrap 95% CIs on per-text F1 from the shipped score files.
  el-sensitivity  F1 with vs without owl:sameAs links (entity-linking floor).
  paper-tables  Rebuild paper Tables 4/5 as CSVs, checked against the PDF.
"""

import argparse
import json
import logging
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="heritagekgbench",
        description="HeritageKGBench evaluation harness",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate a prediction directory")
    p_eval.add_argument("--pred-dir", required=True,
                        help="Directory with per-text prediction JSONs ({'id', 'output'})")
    p_eval.add_argument("--domain", default=None,
                        choices=["architecture", "fashion", "olympic", "sound"],
                        help="Optional domain filter")
    p_eval.add_argument("--output", default=None,
                        help="Write the score dict to this JSON file")
    p_eval.add_argument("--debug", action="store_true", help="Per-item debug logging")

    p_run = sub.add_parser("run", help="Run a baseline pipeline variant over the benchmark")
    p_run.add_argument("--variant", required=True,
                       choices=["single_prompt", "baseline", "shacl"],
                       help="Pipeline variant (paper labels: V1, V2, V4)")
    p_run.add_argument("--output-dir", required=True,
                       help="Directory for per-text prediction JSONs")
    p_run.add_argument("--domain", default=None,
                       choices=["architecture", "fashion", "olympic", "sound"],
                       help="Optional domain filter")
    p_run.add_argument("--model-id", default=None,
                       help="LiteLLM model id (default: the paper's gemini-2.5-flash via OpenRouter)")

    sub.add_parser("fm-metrics", add_help=False,
                   help="Failure-mode metrics (delegates to heritagekgbench.fm_metrics)")
    sub.add_parser("significance", add_help=False,
                   help="Bootstrap CIs (delegates to heritagekgbench.significance_tests)")
    sub.add_parser("el-sensitivity", add_help=False,
                   help="sameAs sensitivity (delegates to heritagekgbench.el_sensitivity)")
    sub.add_parser("paper-tables", add_help=False,
                   help="Reproduce paper Tables 4 & 5 as CSVs (delegates to "
                        "heritagekgbench.paper_tables)")

    # Split known args so delegated subcommands keep their own flags.
    args, rest = parser.parse_known_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "evaluate":
        from heritagekgbench.evaluate import evaluate_ch_benchmark

        result = evaluate_ch_benchmark(args.pred_dir, domain=args.domain, debug=args.debug)
        if result is None:
            print("No valid predictions found.", file=sys.stderr)
            return 1
        summary = {k: v for k, v in result.items() if k != "details"}
        print(json.dumps(summary, indent=2))
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"Wrote full scores (incl. per-item details) to {out}", file=sys.stderr)
        return 0

    if args.command == "run":
        import asyncio

        try:
            from heritagekgbench.pipeline.config import MODEL_ID
            from heritagekgbench.pipeline.runner import process_single_text
        except ImportError as e:
            print(
                f"Pipeline dependencies missing ({e}). "
                "Install with: pip install heritagekgbench[pipeline]",
                file=sys.stderr,
            )
            return 1

        from heritagekgbench.config import CH_BENCHMARK_CONFIG
        from heritagekgbench.evaluate import load_benchmark_items, save_prediction

        model_id = args.model_id or MODEL_ID
        ontology_path = CH_BENCHMARK_CONFIG["ontology"]
        items = load_benchmark_items(args.domain)
        if not items:
            print("No benchmark items found.", file=sys.stderr)
            return 1

        print(f"Running {args.variant} on {len(items)} texts with {model_id}")
        print(f"Output: {args.output_dir}\n")

        async def _run():
            for i, item in enumerate(items, 1):
                text_id = item["id"]
                print(f"[{i}/{len(items)}] {text_id} ({item['domain']})...", flush=True)
                try:
                    result = await process_single_text(
                        text=item["text"],
                        ontology_path=ontology_path,
                        model_id=model_id,
                        variant=args.variant,
                    )
                    if result.get("status") == "failed":
                        print(f"  FAILED: {result.get('error', 'unknown error')}")
                        continue
                    turtle_output = result.get("raw_response", "")
                    save_prediction(turtle_output, text_id, args.output_dir)
                    print(f"  OK ({len(turtle_output)} chars)")
                except Exception as e:
                    print(f"  ERROR: {e}")

        asyncio.run(_run())
        print(f"\nDone. Score with: heritagekgbench evaluate --pred-dir {args.output_dir}")
        return 0

    if args.command == "fm-metrics":
        from heritagekgbench.fm_metrics import main as fm_main
        sys.argv = ["fm-metrics"] + rest
        fm_main()
        return 0

    if args.command == "significance":
        from heritagekgbench.significance_tests import main as sig_main
        sys.argv = ["significance"] + rest
        sig_main()
        return 0

    if args.command == "el-sensitivity":
        from heritagekgbench.el_sensitivity import main as el_main
        sys.argv = ["el-sensitivity"] + rest
        el_main()
        return 0

    if args.command == "paper-tables":
        from heritagekgbench.paper_tables import main as pt_main
        sys.argv = ["paper-tables"] + rest
        pt_main()
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
