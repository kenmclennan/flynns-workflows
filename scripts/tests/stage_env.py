import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def front_matter(path):
    with open(path) as handle:
        text = handle.read()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else ""


def block(front, name):
    values = {}
    lines = front.split("\n")
    for i, line in enumerate(lines):
        if line == name + ":":
            for entry in lines[i + 1:]:
                if not entry.startswith("  "):
                    break
                key, _, value = entry.strip().partition(":")
                values[key.strip()] = value.strip()
            break
    return values


def step_keys(step_name):
    front = front_matter(os.path.join(ROOT, "steps", step_name + ".md"))
    match = re.search(r"^config:\s*\[(.*)\]\s*$", front, re.M)
    if not match:
        return []
    return [key.strip() for key in match.group(1).split(",") if key.strip()]


def workflow_front(workflow_name):
    return front_matter(os.path.join(ROOT, "workflows", workflow_name + ".md"))


def variable(key):
    return "LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_")


def stage_env(step_name, workflow_name, **overrides):
    examples = block(workflow_front(workflow_name), "config-example")
    replaced = {key.replace("_", "-"): value for key, value in overrides.items()}
    env = {}
    for key in step_keys(step_name):
        if key in replaced:
            env[variable(key)] = str(replaced[key])
        elif key in examples:
            env[variable(key)] = examples[key]
    return env


def declared(workflow_name):
    return block(workflow_front(workflow_name), "config")


def examples(workflow_name):
    return block(workflow_front(workflow_name), "config-example")


def with_environment(base, config):
    env = {k: v for k, v in base.items() if not k.startswith("LC_WORKFLOW_CONFIG_")}
    env.update(config)
    return env


def workflow_env(workflow_name, **overrides):
    env = {variable(key): value for key, value in examples(workflow_name).items()}
    for key, value in overrides.items():
        env[variable(key.replace("_", "-"))] = str(value)
    return env
