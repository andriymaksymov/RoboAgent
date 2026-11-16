"""Child-process entry point for ``execute_python``; not a tool and never imported.

Run as ``python _sandbox.py`` with the snippet on stdin. Installs an audit hook that
blocks process creation (it cannot be removed from Python code), then executes the
snippet as ``__main__``. A guard rail, not a sandbox: native code can still bypass it.
"""

import sys

BLOCKED_AUDIT_EVENTS = frozenset({
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.startfile",
    "os.fork",
    "os.forkpty",
    "_winapi.CreateProcess",
})


def _guard(event: str, args: tuple) -> None:
    if event in BLOCKED_AUDIT_EVENTS:
        raise PermissionError(
            f"execute_python is for pure computation; '{event}' (starting a process) is blocked."
        )


def main() -> None:
    # Running a script puts its own directory first on sys.path; use the working directory
    # instead (as ``python -c`` would), so snippets can import the project's modules.
    sys.path[0] = ""
    code = sys.stdin.buffer.read().decode("utf-8")
    sys.addaudithook(_guard)
    namespace = {"__name__": "__main__", "__builtins__": __builtins__}
    exec(compile(code, "<execute_python>", "exec"), namespace)  # noqa: S102 - running the snippet is the point


if __name__ == "__main__":
    main()
