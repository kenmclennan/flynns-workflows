import os
import sys


def config(key):
    value = os.environ.get("LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_"))
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _split(value):
    return [part.strip() for part in value.split(",") if part.strip()]


def config_list(key):
    value = config(key)
    if value is None:
        return []
    return _split(value)


def require_config(key, cast=str):
    raw = config(key)
    if raw is None:
        sys.stderr.write("config key %s is required and is not set\n" % key)
        sys.exit(1)
    try:
        return cast(raw)
    except ValueError:
        sys.stderr.write("config key %s is %s, which is not a valid %s\n" % (key, raw, cast.__name__))
        sys.exit(1)


def require_config_list(key):
    return _split(require_config(key))
