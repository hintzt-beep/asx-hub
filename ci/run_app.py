import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fake_store
sys.modules["store"] = fake_store
REPO = os.environ["REPO_DIR"]
sys.path.insert(0, REPO)
exec(compile(open(os.path.join(REPO, "dashboard.py")).read(), "dashboard.py", "exec"), {"__name__": "__main__"})
