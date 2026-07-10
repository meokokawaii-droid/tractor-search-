import traceback, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Starting pipeline test...", flush=True)
try:
    from demo import run_b2b_pipeline
    print("Import OK", flush=True)

    def cb(step, total, msg):
        print(f"  [{step}/{total}] {msg}", flush=True)

    result = run_b2b_pipeline(progress_callback=cb)
    print(f"\nDone! companies={result.get('total_companies')}, error={result.get('error')}", flush=True)
except Exception as e:
    print(f"\nEXCEPTION: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
