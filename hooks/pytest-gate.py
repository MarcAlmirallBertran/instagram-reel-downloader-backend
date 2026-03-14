#!/usr/bin/env python3
import json
import subprocess
import sys


def main():
    input_data = json.load(sys.stdin)

    # CRITICAL: Prevent infinite loops.
    # When stop_hook_active is True, Claude was already blocked once
    # and is retrying — let it stop to avoid an endless cycle.
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    # Run pytest with short traceback and no header noise
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "--tb=short",       # traceback corto pero útil
                "--no-header",      # sin cabecera innecesaria
                "-q",               # salida compacta
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        # pytest no instalado — no bloquear
        sys.exit(0)
    except subprocess.TimeoutExpired:
        output = json.dumps({
            "decision": "block",
            "reason": (
                "pytest timed out after 120 seconds. "
                "Check for hanging tests or infinite loops, then retry."
            ),
        })
        print(output)
        sys.exit(0)

    if result.returncode != 0:
        # Combinar stdout + stderr y truncar para no saturar el contexto
        test_output = (result.stdout + "\n" + result.stderr).strip()
        max_chars = 3000
        if len(test_output) > max_chars:
            test_output = test_output[:max_chars] + "\n... (output truncated)"

        output = json.dumps({
            "decision": "block",
            "reason": (
                "Tests are failing. Fix ALL failing tests before completing.\n\n"
                f"pytest output:\n```\n{test_output}\n```"
            ),
        })
        print(output)
        sys.exit(0)

    # All tests passed — allow Claude to stop
    sys.exit(0)


if __name__ == "__main__":
    main()