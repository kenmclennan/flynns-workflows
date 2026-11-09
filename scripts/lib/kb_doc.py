import posixpath
import re

LINK = re.compile(r"(?<!!)\[(?:[^\[\]]|\[[^\]]*\])*\]\((?:<([^>\n]+)>|([^)\s<]+))(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```+|~~~+)")


def split_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    return text[4:end], text[end + 4:].lstrip("\n")


def top_level_keys(front, unquote=False):
    return {m.group(1): (m.group(2).strip().strip("\"'") if unquote else m.group(2).strip()) for m in re.finditer(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", front, re.M)}


def source_resources(front):
    block = re.search(r"^sources:[ \t]*\n((?:[ \t]+.*\n?|\n)*)", front + "\n", re.M)
    if not block:
        return []
    return [m.group(1).strip().strip("\"'") for m in re.finditer(r"^\s*-?\s*resource:\s*(.+)$", block.group(1), re.M)]


def body_links(body):
    links, fenced = [], False
    for line in body.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            links.extend(m.group(1) or m.group(2) for m in LINK.finditer(re.sub(r"`[^`]*`", "", line)))
    return links


def resolve(path, target):
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or target.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(path), target))


def address_paths(front):
    match = re.search(r"^addresses:[ \t]*(.*)$", front, re.M)
    if not match:
        return []
    rest = match.group(1).strip()
    if not rest and front[match.end():].lstrip().startswith("["):
        rest = "["
    if rest.startswith("["):
        start = front.index("[", match.start(1))
        end = front.find("]", start)
        raw = front[start + 1:end if end != -1 else len(front)].split(",")
    elif rest:
        raw = [rest]
    else:
        raw = []
        for line in front[match.end():].split("\n"):
            item = re.match(r"^[ \t]*-[ \t]*(.+)$", line)
            if item:
                raw.append(item.group(1))
            elif line.strip():
                break
    return [r.strip().strip("\"'").strip() for r in raw if r.strip().strip("\"'").strip()]


def resolve_address(path, target, exists):
    for candidate in (resolve(path, target), posixpath.normpath(target)):
        if candidate and exists(candidate):
            return candidate
    return None
