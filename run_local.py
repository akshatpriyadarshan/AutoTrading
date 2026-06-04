"""
run_local.py — start AutoCrypto backend locally (no Docker).
Uses SQLite. Run with: python run_local.py
VSCode: press F5 with "Run Backend (local Python)" config.
"""
import os
import sys


# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT    = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
DATA    = os.path.join(ROOT, "data")

# ── PYTHONPATH must be set as env var BEFORE uvicorn spawns child processes ───
# sys.path only affects the current process; the reloader worker is a new
# subprocess that gets a fresh interpreter — it reads PYTHONPATH from env.
os.environ["PYTHONPATH"] = BACKEND

# ── Environment ───────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{DATA}/autocrypto.db")
os.environ.setdefault("APP_ENV",      "development")
os.environ.setdefault("DEBUG",        "true")

# Load .env if it exists (picks up saved CONFIG_ENCRYPTION_KEY)
env_file = os.path.join(ROOT, ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Auto-generate a valid Fernet key if still not set
if not os.environ.get("CONFIG_ENCRYPTION_KEY"):
    try:
        from importlib import import_module
        Fernet = import_module("cryptography.fernet").Fernet
    except ImportError:
        print("\n✗ Missing cryptography package. Install dependencies and rerun.")
        sys.exit(1)
    key = Fernet.generate_key().decode()
    os.environ["CONFIG_ENCRYPTION_KEY"] = key
    with open(env_file, "a") as f:
        f.write(f"\nCONFIG_ENCRYPTION_KEY={key}\n")
    print(f"✓ Generated Fernet key and saved to .env")

# ── Also add to sys.path for the main process ─────────────────────────────────
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ── Data dir & working dir ────────────────────────────────────────────────────
os.makedirs(DATA, exist_ok=True)
os.chdir(BACKEND)


# ── Dependency check ──────────────────────────────────────────────────────────
def check_deps():
    missing = []
    for pkg in ["fastapi", "uvicorn", "sqlalchemy", "loguru", "cryptography", "aiosqlite", "greenlet"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n✗ Missing: {', '.join(missing)}")
        print(f"  Fix: pip install -r {os.path.join(ROOT, 'backend', 'requirements-local.txt')}\n")
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    check_deps()

    print("\n" + "─" * 52)
    print("  AutoCrypto Trader — Local Mode (SQLite)")
    print("─" * 52)
    print(f"  API:       http://localhost:8000")
    print(f"  Docs:      http://localhost:8000/docs")
    print(f"  Setup:     open frontend/index.html")
    print(f"  Dashboard: open frontend/dashboard.html")
    print("─" * 52 + "\n")

    import uvicorn 
    
    uvicorn.run(
        "main:app",
        host        = "0.0.0.0",
        port        = 8000,
        reload      = True,
        reload_dirs = [BACKEND],
        log_level   = "info",
    )