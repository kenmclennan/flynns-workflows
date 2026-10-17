import json
import os


def data_dir():
    return os.environ.get("LC_WORKFLOW_DATA_DIR") or os.getcwd()


def state_path():
    return os.path.join(data_dir(), "kb-audit-state.json")


def read_sha():
    try:
        with open(state_path(), encoding="utf-8") as handle:
            return json.load(handle)["audited_sha"] or None
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("%s is not a valid audit state file: %r" % (state_path(), exc)) from None


def write_sha(sha):
    path = state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"audited_sha": sha}, handle)
    os.replace(tmp, path)
