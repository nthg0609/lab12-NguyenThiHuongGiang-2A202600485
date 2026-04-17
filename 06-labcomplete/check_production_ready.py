"""Production readiness checker for the final Day 12 project."""
import os
import sys


def check(name: str, passed: bool, detail: str = "") -> dict:
    icon = "[OK]" if passed else "[X]"
    print(f"  {icon} {name}" + (f" - {detail}" if detail else ""))
    return {"name": name, "passed": passed}


def run_checks():
    results = []
    base = os.path.dirname(__file__)

    print("\n" + "=" * 55)
    print("  Production Readiness Check - Day 12 Lab")
    print("=" * 55)

    print("\nRequired Files")
    results.append(check("Dockerfile exists", os.path.exists(os.path.join(base, "Dockerfile"))))
    results.append(
        check("docker-compose.yml exists", os.path.exists(os.path.join(base, "docker-compose.yml")))
    )
    results.append(check(".dockerignore exists", os.path.exists(os.path.join(base, ".dockerignore"))))
    results.append(check(".env.example exists", os.path.exists(os.path.join(base, ".env.example"))))
    results.append(check("requirements.txt exists", os.path.exists(os.path.join(base, "requirements.txt"))))
    results.append(
        check(
            "railway.toml or render.yaml exists",
            os.path.exists(os.path.join(base, "railway.toml"))
            or os.path.exists(os.path.join(base, "render.yaml")),
        )
    )
    results.append(check("utils/mock_llm.py exists", os.path.exists(os.path.join(base, "utils", "mock_llm.py"))))

    print("\nSecurity")
    env_ignored = False
    for gitignore_path in [os.path.join(base, ".gitignore"), os.path.join(base, "..", ".gitignore")]:
        if os.path.exists(gitignore_path) and ".env" in open(gitignore_path, encoding="utf-8").read():
            env_ignored = True
            break
    results.append(check(".env ignored by git", env_ignored))

    secrets_found = []
    for rel_path in ["app/main.py", "app/config.py", "app/auth.py"]:
        full_path = os.path.join(base, rel_path)
        if not os.path.exists(full_path):
            continue
        content = open(full_path, encoding="utf-8").read()
        for bad in ["sk-", "password123", "hardcoded"]:
            if bad in content:
                secrets_found.append(f"{rel_path}:{bad}")
    results.append(check("No obvious hardcoded secrets", len(secrets_found) == 0, ", ".join(secrets_found)))

    print("\nAPI Endpoints (code check)")
    main_py = os.path.join(base, "app", "main.py")
    if os.path.exists(main_py):
        content = open(main_py, encoding="utf-8").read()
        results.append(check("/health endpoint defined", '"/health"' in content or "'/health'" in content))
        results.append(check("/ready endpoint defined", '"/ready"' in content or "'/ready'" in content))
        results.append(check("/ask endpoint defined", '"/ask"' in content or "'/ask'" in content))
        results.append(check("History endpoint defined", '"/history/' in content or "'/history/" in content))
        results.append(check("Authentication imported", "verify_api_key" in content))
        results.append(check("Rate limiting imported", "rate_limiter" in content))
        results.append(check("Cost guard imported", "cost_guard" in content))
        results.append(check("Graceful shutdown (SIGTERM)", "SIGTERM" in content))
        results.append(check("Structured logging (JSON)", "json.dumps" in content or '"event"' in content))
        results.append(check("Redis-backed storage referenced", "storage_name" in content or "session_store" in content))
    else:
        results.append(check("app/main.py exists", False))

    print("\nDocker")
    dockerfile = os.path.join(base, "Dockerfile")
    if os.path.exists(dockerfile):
        content = open(dockerfile, encoding="utf-8").read()
        results.append(check("Multi-stage build", "AS builder" in content and "AS runtime" in content))
        results.append(check("Non-root user", "USER " in content))
        results.append(check("HEALTHCHECK instruction", "HEALTHCHECK" in content))
        results.append(check("Slim base image", "slim" in content or "alpine" in content))

    dockerignore = os.path.join(base, ".dockerignore")
    if os.path.exists(dockerignore):
        content = open(dockerignore, encoding="utf-8").read()
        results.append(check(".dockerignore covers .env", ".env" in content))
        results.append(check(".dockerignore covers __pycache__", "__pycache__" in content))

    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    pct = round(passed / total * 100)

    print("\n" + "=" * 55)
    print(f"  Result: {passed}/{total} checks passed ({pct}%)")
    if pct == 100:
        print("  PRODUCTION READY! Deploy now!")
    elif pct >= 80:
        print("  Almost there! Fix the failed items above.")
    elif pct >= 60:
        print("  Good progress. Several items need attention.")
    else:
        print("  Not ready. Review the checklist carefully.")
    print("=" * 55 + "\n")
    return pct == 100


if __name__ == "__main__":
    ready = run_checks()
    sys.exit(0 if ready else 1)