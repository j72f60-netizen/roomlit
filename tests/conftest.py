import os, sys, tempfile
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("APP_USERNAME", "admin")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="hpe-test-"))
os.environ.setdefault("TASK_TIMEOUT_S", "120")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
