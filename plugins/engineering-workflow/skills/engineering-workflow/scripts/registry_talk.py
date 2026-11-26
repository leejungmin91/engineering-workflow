import hashlib
import re
from pathlib import Path

import registry_scan

READER = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")


def talk_facts(content, app):
    fields, body = registry_scan.frontmatter(content)
    key = f"{app}/{fields['id']}"
    date = str(fields.get("date") or fields["id"])[:10]
    return ([registry_scan.node("talk", key, name=fields.get("title") or fields["id"],
                                text=body[:registry_scan.BODY_LIMIT], date=date if DATE.match(date) else None)],
            [registry_scan.link(f"talk:{key}", "IN", f"app:{app}")])


def files(config):
    folder = config.get("talk")
    if not folder:
        return {}
    found = {}
    for item in config.get("apps", []):
        name = item.get("name")
        place = Path(folder).expanduser() / name if isinstance(name, str) else None
        for path in sorted(place.glob("*.md")) if place and place.is_dir() else []:
            entry = {"kind": "talk"}
            try:
                raw = path.read_bytes()
                entry["hash"] = hashlib.sha256(raw + f"\n{name}\n{READER}".encode("utf-8")).hexdigest()
                entry["nodes"], entry["links"] = talk_facts(raw.decode("utf-8"), name)
                for node in entry["nodes"]:
                    node["path"] = str(path)
            except Exception as error:
                entry.update({"nodes": [], "links": [], "error": f"{type(error).__name__}: {error}"})
                entry.setdefault("hash", "unreadable")
            found[str(path)] = entry
    return found
