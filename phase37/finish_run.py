"""Complete Phase 37 deliverables from existing replay outputs."""

from phase37.run import run_phase37

if __name__ == "__main__":
    import os
    os.environ["PHASE37_SKIP_REPLAY"] = "1"
    run_phase37()
