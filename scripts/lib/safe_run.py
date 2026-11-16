import os
import signal
import subprocess
import sys
import time

LOCAL_TIMEOUT = 60
NETWORK_TIMEOUT = 120
PUSH_TIMEOUT = 600
RETRY_PAUSE = 2

LOW_SPEED_FLAGS = ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=30"]
GIT_NETWORK = ("fetch", "push", "clone", "ls-remote", "pull")
GIT_VALUE_OPTIONS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
GH_WRITES = (
    ("issue", "close"), ("issue", "comment"), ("issue", "create"), ("issue", "edit"),
    ("pr", "create"), ("pr", "comment"), ("pr", "edit"), ("pr", "merge"), ("pr", "close"),
)
GH_FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field")
GIT_TRANSIENT = (
    "could not resolve host", "connection timed out", "connection reset", "early eof",
    "rpc failed", "unable to access", "the remote end hung up",
)
GH_TRANSIENT = (
    "error connecting to", "dial tcp", "i/o timeout", "tls handshake timeout",
    "http 502", "http 503", "http 504",
)


def git_subcommand(args):
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GIT_VALUE_OPTIONS:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg
    return None


def tool(cmd):
    return os.path.basename(str(cmd[0])) if cmd else ""


def is_gh_write(args):
    positional = [a for a in args if not a.startswith("-")]
    if positional[:1] == ["api"]:
        for index, arg in enumerate(args):
            if arg in ("-X", "--method") and index + 1 < len(args):
                if args[index + 1].upper() in ("POST", "PATCH", "PUT", "DELETE"):
                    return True
            if arg.startswith("--method=") and arg.split("=", 1)[1].upper() in ("POST", "PATCH", "PUT", "DELETE"):
                return True
            if arg in GH_FIELD_FLAGS or arg.startswith(("--field=", "--raw-field=")):
                return True
        return False
    return tuple(positional[:2]) in GH_WRITES


def classify(cmd, network=False, write=False):
    name = tool(cmd)
    args = [str(a) for a in cmd[1:]]
    is_network = network
    is_write = write
    if name == "git":
        sub = git_subcommand(args)
        if sub in GIT_NETWORK:
            is_network = True
        if sub == "push":
            is_write = True
    elif name == "gh":
        is_network = True
        if is_gh_write(args):
            is_write = True
    if is_write:
        is_network = True
    return is_network, is_write


def default_timeout(cmd, network=False):
    name = tool(cmd)
    if name == "git" and git_subcommand([str(a) for a in cmd[1:]]) == "push":
        return PUSH_TIMEOUT
    if classify(cmd, network)[0]:
        return NETWORK_TIMEOUT
    return LOCAL_TIMEOUT


def build_command(cmd, network):
    cmd = list(cmd)
    if tool(cmd) == "git" and network and git_subcommand([str(a) for a in cmd[1:]]) is not None:
        return cmd[:1] + LOW_SPEED_FLAGS + cmd[1:]
    return cmd


def is_transient(cmd, stderr):
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    text = (stderr or "").lower()
    name = tool(cmd)
    markers = GIT_TRANSIENT if name == "git" else GH_TRANSIENT if name == "gh" else GIT_TRANSIENT + GH_TRANSIENT
    return any(marker in text for marker in markers)


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        pass


def attempt(cmd, timeout, cwd, env, input, text):
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, text=text, start_new_session=True,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        return None
    except BaseException:
        kill_group(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def describe(cmd):
    return " ".join(str(a) for a in cmd[:3])


def die(cmd, cause):
    sys.stderr.write("%s: %s\n" % (describe(cmd), cause))
    sys.exit(1)


def run(cmd, *, timeout=None, cwd=None, env=None, input=None, text=True, network=False, write=False):
    is_network, is_write = classify(cmd, network, write)
    limit = timeout if timeout is not None else default_timeout(cmd, is_network)
    full = build_command(cmd, is_network)
    retries = 1 if is_network and not is_write else 0
    for number in range(retries + 1):
        proc = attempt(full, limit, cwd, env, input, text)
        if proc is None:
            if number < retries:
                time.sleep(RETRY_PAUSE)
                continue
            cause = "timed out after %ds" % limit
            if retries:
                cause += " on both attempts"
            if is_write:
                cause += "; the write may have been applied"
            die(cmd, cause)
        if proc.returncode != 0 and number < retries and is_transient(cmd, proc.stderr):
            time.sleep(RETRY_PAUSE)
            continue
        if proc.returncode != 0 and retries and is_transient(cmd, proc.stderr):
            stderr = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
            die(cmd, "transient network failure on both attempts: %s" % stderr.strip()[-200:])
        return proc
