import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

import registry_text

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
RESERVED = {"id", "type", "from", "to"}
TYPES = ("app", "plugin", "skill", "tool", "model", "task", "decision", "record", "commit", "asset", "source", "rule",
         "term", "checkout", "session", "machine", "license")
LINKS = ("USES", "DISABLES", "INSTALLED", "PROVIDES", "HAS", "REQUIRES", "SUPERSEDES", "PREFERS", "AFTER", "IN",
         "AFFECTS", "FOR", "USED", "RAN_ON", "PRODUCED", "CONCERNS", "REVIEWED_BY", "VERSION_OF", "FROM", "MADE_BY",
         "APPROVED", "APPLIES_TO", "ALIAS_OF", "HOLDS", "ON", "UNDER", "INVOKED")
REACH = "HAS|USES|INSTALLED|DISABLES"
REMOVAL_FLOOR = 10
REMOVAL_SHARE = 0.25
OPEN = ["todo", "doing", "blocked", "parked"]


class StoreError(RuntimeError):
    pass


class Store:
    def __init__(self, url, user, password, space="N"):
        if not NAME.fullmatch(space):
            raise ValueError(f"unsafe space name: {space!r}")
        self.url = url.rstrip("/") + "/db/neo4j/query/v2"
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self.headers = {"Content-Type": "application/json", "Accept": "application/json",
                        "Authorization": f"Basic {token}"}
        self.node, self.file, self.index = space, f"{space}File", f"{space.lower()}_search"
        self.timeout = 30
        self.deadline = None

    def run(self, statement, **parameters):
        body = json.dumps({"statement": statement, "parameters": parameters}).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, headers=self.headers, method="POST")
        wait = self.timeout
        if self.deadline is not None:
            wait = min(wait, self.deadline - time.monotonic())
            if wait <= 0.05:
                raise StoreError("out of time")
        try:
            with urllib.request.urlopen(request, timeout=wait) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise StoreError(f"query failed ({error.code}): {detail}") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise StoreError(f"graph server not reachable: {error}") from None
        return [dict(zip(data["data"]["fields"], row)) for row in data["data"]["values"]]


def password():
    value = os.environ.get("HARNESS_NEO4J_PASSWORD")
    if value:
        return value
    try:
        return subprocess.run(["security", "find-generic-password", "-s", "harness-neo4j", "-a", "neo4j", "-w"],
                              check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise StoreError("no password: set HARNESS_NEO4J_PASSWORD or add the keychain item harness-neo4j") from None


def connect(space="N"):
    return Store(os.environ.get("HARNESS_NEO4J_URL", "http://127.0.0.1:7474"),
                 os.environ.get("HARNESS_NEO4J_USER", "neo4j"), password(), space)


def label(value):
    text = value.capitalize() if value.islower() else value
    if not NAME.fullmatch(text):
        raise ValueError(f"unsafe name: {value!r}")
    return text


def flat(item):
    result = {}
    for key, value in item.items():
        if key in RESERVED or not NAME.fullmatch(key):
            continue
        if isinstance(value, (str, int, float, bool)) or (
                isinstance(value, list) and all(isinstance(entry, str) for entry in value)):
            result[key] = value
        else:
            result[key] = json.dumps(value, ensure_ascii=False)
    return result


def problem(entry):
    for item in entry.get("nodes", []):
        key, kind = item.get("id"), item.get("type")
        if kind not in TYPES or not isinstance(key, str) or not key.startswith(f"{kind}:") or len(key) <= len(kind) + 1:
            return f"node {key!r} has no known type"
    for item in entry.get("links", []):
        if item.get("type") not in LINKS:
            return f"link type {item.get('type')!r} is not known"
        for end in (item.get("from"), item.get("to")):
            if not isinstance(end, str) or end.split(":", 1)[0] not in TYPES or ":" not in end:
                return f"link end {end!r} has no known type"
    return None


def checked(files):
    result = {}
    for path, entry in files.items():
        try:
            found = problem(entry)
        except (AttributeError, TypeError):
            found = "facts are not in the expected shape"
        if found:
            entry = {"kind": entry.get("kind"), "hash": entry.get("hash"), "nodes": [], "links": [],
                     "error": f"rejected: {found}"}
        result[path] = entry
    return result


def prepare(store):
    n, f = store.node, store.file
    store.run(f"CREATE CONSTRAINT {n.lower()}_id IF NOT EXISTS FOR (n:{n}) REQUIRE n.id IS UNIQUE")
    store.run(f"CREATE CONSTRAINT {f.lower()}_path IF NOT EXISTS FOR (f:{f}) REQUIRE f.path IS UNIQUE")
    store.run(f"DROP INDEX {n.lower()}_text IF EXISTS")
    store.run(f"CREATE FULLTEXT INDEX {store.index} IF NOT EXISTS FOR (n:{n}) "
              "ON EACH [n.name, n.text, n.means, n.keywords, n.terms] "
              "OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk'}}")
    store.run("CALL db.awaitIndexes(30)")


def stated(files):
    props, kinds, sources = {}, {}, {}
    for path in sorted(files, key=lambda path: (path.startswith("git:"), path)):
        for item in files[path]["nodes"]:
            props.setdefault(item["id"], {}).update(flat(item))
            kinds[item["id"]] = item["type"]
            sources.setdefault(item["id"], []).append(path)
    return props, kinds, sources


def add_terms(rows):
    texts = [" ".join(str(row["props"].get(key, "")) for key in ("name", "text", "keywords")) for row in rows]
    for row, terms in zip(rows, registry_text.index_terms_many(texts)):
        if terms:
            row["props"]["terms"] = terms


def rewrite_nodes(store, files, paths):
    n = store.node
    props, kinds, sources = stated(files)
    touched = {item["id"] for path in paths if path in files for item in files[path]["nodes"]}
    touched |= {row["id"] for row in store.run(
        f"MATCH (n:{n}) WHERE any(s IN coalesce(n.srcs, []) WHERE s IN $paths) RETURN n.id AS id", paths=paths)}
    by_type = {}
    for key in sorted(touched & set(props)):
        by_type.setdefault(kinds[key], []).append({"id": key, "props": props[key], "srcs": sources[key]})
    add_terms([row for rows in by_type.values() for row in rows])
    for kind, rows in by_type.items():
        store.run(f"UNWIND $rows AS row MERGE (n:{n} {{id: row.id}}) SET n = row.props, n:{label(kind)}, "
                  "n.id = row.id, n.type = $kind, n.srcs = row.srcs", rows=rows, kind=kind)
    gone = sorted(touched - set(props))
    if gone:
        store.run(f"UNWIND $ids AS id MATCH (n:{n} {{id: id}}) SET n = {{id: id, type: split(id, ':')[0], "
                  "name: substring(id, size(split(id, ':')[0]) + 1), srcs: []}", ids=gone)


def load_links(store, path, entry):
    n = store.node
    by_type = {}
    for item in entry["links"]:
        by_type.setdefault(item["type"], []).append({"from": item["from"], "to": item["to"], "props": flat(item)})
    for kind, rows in by_type.items():
        store.run(f"UNWIND $rows AS row MERGE (a:{n} {{id: row.from}}) ON CREATE SET a.type = split(row.from, ':')[0], "
                  "a.name = substring(row.from, size(split(row.from, ':')[0]) + 1), a.srcs = [] "
                  f"MERGE (b:{n} {{id: row.to}}) ON CREATE SET b.type = split(row.to, ':')[0], "
                  "b.name = substring(row.to, size(split(row.to, ':')[0]) + 1), b.srcs = [] "
                  f"CREATE (a)-[r:{label(kind)}]->(b) SET r = row.props, r.src = $path", rows=rows, path=path)
    store.run(f"MERGE (f:{store.file} {{path: $path}}) SET f.hash = $hash, f.kind = $kind, f.error = $error",
              path=path, hash=entry["hash"], kind=entry["kind"], error=entry.get("error"))


def sweep(store):
    n = store.node
    store.run(f"MATCH (n:{n}) WHERE size(coalesce(n.srcs, [])) = 0 AND NOT (n)--() DELETE n")
    kinds = store.run(f"MATCH (n:{n}) WHERE n.type IS NOT NULL RETURN DISTINCT n.type AS type")
    for kind in [row["type"] for row in kinds]:
        if NAME.fullmatch(kind):
            store.run(f"MATCH (n:{n} {{type: $kind}}) WHERE NOT n:{label(kind)} SET n:{label(kind)}", kind=kind)


def counts(store):
    n = store.node
    return {"nodes": store.run(f"MATCH (n:{n}) RETURN count(n) AS total")[0]["total"],
            "links": store.run(f"MATCH (:{n})-[r]->(:{n}) RETURN count(r) AS total")[0]["total"],
            "files": store.run(f"MATCH (f:{store.file}) RETURN count(f) AS total")[0]["total"]}


def drop(store):
    store.run(f"MATCH (n) WHERE n:{store.node} OR n:{store.file} DETACH DELETE n")


def sync(store, scanned, rebuild=False):
    prepare(store)
    if rebuild:
        drop(store)
    f = store.file
    known = {row["path"]: row["hash"] for row in store.run(f"MATCH (f:{f}) RETURN f.path AS path, f.hash AS hash")}
    files = checked(scanned["files"])
    changed = [path for path, entry in files.items() if known.get(path) != entry["hash"]]
    removed = [path for path in known if path not in files]
    if not rebuild and len(removed) > max(REMOVAL_FLOOR, len(known) * REMOVAL_SHARE):
        return {"changed": [], "removed": [], "held": removed,
                "skipped": [path for path, entry in files.items() if entry.get("error")], **counts(store)}
    held = []
    paths = changed + removed
    if paths:
        store.run(f"UNWIND $paths AS path MERGE (f:{f} {{path: path}}) SET f.hash = null", paths=paths)
        store.run(f"MATCH (:{store.node})-[r]->(:{store.node}) WHERE r.src IN $paths DELETE r", paths=paths)
        rewrite_nodes(store, files, paths)
    for path in changed:
        load_links(store, path, files[path])
    if removed:
        store.run(f"MATCH (f:{f}) WHERE f.path IN $paths DELETE f", paths=removed)
    if paths:
        sweep(store)
        store.run("CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh()")
    return {"changed": changed, "removed": removed, "held": held,
            "skipped": [path for path, entry in files.items() if entry.get("error")], **counts(store)}


def quoted(token):
    return '"' + token.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lucene(words, also=()):
    tokens = [token for word in words for token in word.split()]
    strong = [quoted(token) + ("^3" if also else "") for token in dict.fromkeys(tokens)]
    weak = [quoted(token) for token in dict.fromkeys(also) if token not in tokens]
    return " OR ".join(strong + weak)


def resolve(store, name):
    n = store.node
    rows = store.run(f"MATCH (n:{n}) WHERE n.id = $name RETURN n.id AS id", name=name)
    if not rows:
        rows = store.run(f"MATCH (t:{n}:Term {{name: $name}})-[:ALIAS_OF]->(n:{n}) RETURN DISTINCT n.id AS id", name=name)
    if not rows:
        rows = store.run(f"MATCH (n:{n}) WHERE n.name = $name OR n.id ENDS WITH (':' + $name) OR n.id ENDS WITH "
                         "('/' + $name) RETURN n.id AS id ORDER BY size(coalesce(n.srcs, [])) DESC, n.id LIMIT 6",
                         name=name)
    return [row["id"] for row in rows]


def find(store, words, kind=None, limit=5):
    n = store.node
    words = registry_text.query_words(words)
    phrase = " ".join(words)
    rows = store.run(f"MATCH (t:{n}:Term) WHERE $phrase CONTAINS t.name OPTIONAL MATCH (t)-[:ALIAS_OF]->(x:{n}) "
                     "RETURN DISTINCT t.name AS term, t.means AS means, x.id AS id, x.type AS type, x.name AS name, "
                     "x.path AS path, left(coalesce(x.text, ''), 160) AS text", phrase=phrase)
    terms = [row for row in rows if any(registry_text.names(word, row["term"]) for word in words)
             or (" " in row["term"] and row["term"] in phrase)]
    hits, seen = [], set()
    for row in terms:
        if row["id"] and row["id"] not in seen and (not kind or row["type"] == kind):
            hits.append({"id": row["id"], "type": row["type"], "name": row["name"], "path": row["path"],
                         "text": row["text"], "score": None})
            seen.add(row["id"])
    meanings = [word for row in terms if row["means"] and not row["id"] for word in row["means"].split()]
    query = lucene(words, [form for form in registry_text.expand(words) + meanings if form not in words])
    if query:
        rows = store.run(
            f"CALL db.index.fulltext.queryNodes('{store.index}', $q) YIELD node, score "
            "WHERE ($kind IS NULL OR node.type = $kind) AND node.type <> 'term' "
            "RETURN node.id AS id, node.type AS type, node.name AS name, node.path AS path, "
            "left(coalesce(node.text, ''), 160) AS text, round(score, 2) AS score LIMIT $limit",
            q=query, kind=kind, limit=limit + len(seen))
        for row in rows:
            if row["id"] not in seen:
                hits.append(row)
                seen.add(row["id"])
    return hits[:limit]


def app_at(store, folder):
    paths = []
    current = os.path.abspath(folder)
    while current not in paths:
        paths.append(current)
        current = os.path.dirname(current)
    rows = store.run(f"MATCH (a:{store.node}:App) WHERE a.path IN $paths RETURN a.id AS id, a.path AS path", paths=paths)
    return max(rows, key=lambda row: len(row["path"]))["id"] if rows else None


def within(store, app_id, ids):
    n = store.node
    rows = store.run(
        f"MATCH (a:{n} {{id: $app}}) UNWIND $ids AS id MATCH (s:{n} {{id: id}}) "
        f"WHERE (a)-[:HAS|USES|INSTALLED]->(s) OR (a)-[:USES|INSTALLED]->(:{n}:Plugin)-[:PROVIDES]->(s) "
        "OR (s)-[:APPLIES_TO]->(a) RETURN DISTINCT s.id AS id", app=app_id, ids=ids)
    return {row["id"] for row in rows}


def shared(store, ids):
    n = store.node
    rows = store.run(
        f"UNWIND $ids AS id MATCH (s:{n} {{id: id}}) "
        f"WHERE (:{n})-[:HAS {{scope: 'user'}}]->(s) "
        f"OR (:{n})-[:USES {{scope: 'user'}}]->(:{n}:Plugin)-[:PROVIDES]->(s) "
        f"OR (s)-[:APPLIES_TO {{scope: 'user'}}]->(:{n}) RETURN DISTINCT s.id AS id", ids=ids)
    return {row["id"] for row in rows}


def neighbors(store, node_id, kind=None, limit=60):
    n = store.node
    return store.run(
        f"MATCH (x:{n} {{id: $id}})-[r]-(m:{n}) WHERE $kind IS NULL OR m.type = $kind "
        "WITH r, m, startNode(r).id = $id AS outgoing "
        "RETURN type(r) AS link, outgoing, m.id AS id, m.name AS name, m.status AS status, m.state AS state, "
        "r.version AS version, r.scope AS scope, r.result AS result, r.license AS license "
        "ORDER BY link, outgoing DESC, id LIMIT $limit", id=node_id, kind=kind, limit=limit)


def reach(store, ids):
    n = store.node
    return store.run(
        f"UNWIND $ids AS id MATCH (s:{n} {{id: id}}) "
        f"CALL {{ WITH s MATCH (a:{n})-[r:{REACH}]->(s) RETURN a, type(r) AS how, r.scope AS scope, r.version AS version "
        f"UNION WITH s MATCH (a:{n})-[r:{REACH}]->(:{n}:Plugin)-[:PROVIDES]->(s) "
        "RETURN a, type(r) AS how, r.scope AS scope, r.version AS version "
        f"UNION WITH s MATCH (s)-[r:APPLIES_TO]->(a:{n}) RETURN a, 'APPLIES_TO' AS how, r.scope AS scope, null AS version }} "
        f"WITH a, collect(DISTINCT how + CASE WHEN version IS NULL THEN '' ELSE ' ' + version END + "
        "CASE WHEN scope IS NULL THEN '' ELSE ' (' + scope + ')' END) AS how "
        f"OPTIONAL MATCH (t:{n}:Task)-[:IN]->(a) WHERE t.status IN $open "
        "RETURN a.id AS id, how, count(t) AS open_tasks ORDER BY id", ids=ids, open=OPEN)


def dependents(store, ids):
    return [row["id"] for row in store.run(
        f"MATCH (d:{store.node})-[:REQUIRES*1..8]->(x:{store.node}) WHERE x.id IN $ids AND NOT d.id IN $ids "
        "RETURN DISTINCT d.id AS id ORDER BY id", ids=ids)]


def impact(store, node_id):
    n = store.node
    needing = dependents(store, [node_id])
    ids = [node_id] + needing
    records = store.run(f"MATCH (r:{n}:Record)-[l:USED|CONCERNS]->(s:{n}) WHERE s.id IN $ids "
                        "RETURN r.id AS id, r.name AS name, collect(DISTINCT type(l)) AS links ORDER BY id DESC LIMIT 20", ids=ids)
    used = store.run(f"MATCH (a:{n})-[u:INVOKED]->(s:{n}) WHERE s.id IN $ids RETURN a.id AS id, u.agent AS agent, "
                     "u.sessions AS sessions, u.first AS first, u.last AS last ORDER BY id, agent", ids=ids)
    return {"dependents": needing, "apps": reach(store, ids), "records": records, "used": used}


def spread(store, record_id):
    n = store.node
    concerns = [row["id"] for row in store.run(
        f"MATCH (:{n} {{id: $id}})-[:CONCERNS]->(c:{n}) RETURN c.id AS id ORDER BY id", id=record_id)]
    covered = {row["app"]: row["records"] for row in store.run(
        f"MATCH (r:{n}:Record)-[:CONCERNS]->(c:{n}) WHERE c.id IN $ids MATCH (r)-[:IN]->(a:{n}) "
        "RETURN a.id AS app, collect(DISTINCT r.id) AS records", ids=concerns)}
    apps = [row for row in reach(store, concerns + dependents(store, concerns))
            if not all(how.startswith("DISABLES") for how in row["how"])]
    return {"concerns": concerns,
            "needs": [row for row in apps if row["id"] not in covered],
            "done": [{"id": app, "records": records} for app, records in sorted(covered.items())]}


def lineage(store, asset_id):
    n = store.node
    return store.run(
        f"MATCH p = (a:{n} {{id: $id}})-[:VERSION_OF*0..20]->(v:{n}) WITH v, length(p) AS step "
        f"OPTIONAL MATCH (v)-[f:FROM]->(s:{n}) OPTIONAL MATCH (v)-[:MADE_BY]->(m:{n}) "
        f"OPTIONAL MATCH (d:{n})-[:APPROVED]->(v) OPTIONAL MATCH (c:{n}:Commit)-[:PRODUCED]->(v) "
        "RETURN step, v.id AS id, v.file AS file, s.name AS source, f.license AS license, "
        "collect(DISTINCT m.name) AS made_by, collect(DISTINCT d.name) AS approved_by, "
        "collect(DISTINCT c.id + '  ' + coalesce(c.name, '')) AS commits ORDER BY step", id=asset_id)


def needs(store, node_id):
    n = store.node
    return store.run(f"MATCH p = (:{n} {{id: $id}})-[:REQUIRES*1..10]->(d:{n}) "
                     "RETURN d.id AS id, d.type AS type, min(length(p)) AS step, "
                     "size(coalesce(d.srcs, [])) > 0 AS known ORDER BY step, id", id=node_id)


def latest(store, node_id):
    n = store.node
    rows = store.run(f"MATCH p = (x:{n})-[:SUPERSEDES*1..50]->(:{n} {{id: $id}}) WHERE NOT (:{n})-[:SUPERSEDES]->(x) "
                     "RETURN x.id AS id, length(p) AS step ORDER BY step DESC, id", id=node_id)
    return rows or [{"id": node_id, "step": 0}]


def unused(store, usage=False):
    n = store.node
    logged = store.run(f"MATCH (r:{n}:Record)-[:USED]->() RETURN count(r) AS total")[0]["total"]
    rows = store.run(
        f"MATCH (s:{n}:Skill) WHERE size(coalesce(s.srcs, [])) > 0 "
        f"AND NOT (:{n}:App)-[:HAS|USES]->(s) AND NOT (:{n}:App)-[:USES]->(:{n}:Plugin)-[:PROVIDES]->(s) "
        f"AND NOT (:{n}:Record)-[:USED]->(s) RETURN s.id AS id, s.path AS path ORDER BY id")
    never = store.run(
        f"MATCH (s:{n}:Skill) WHERE size(coalesce(s.srcs, [])) > 0 AND NOT (:{n}:Record)-[:USED]->(s) "
        "RETURN s.id AS id ORDER BY id") if logged else []
    counted = store.run(f"MATCH (:{n})-[u:INVOKED]->(:{n}) RETURN count(u) AS total")[0]["total"]
    idle = store.run(
        f"MATCH (s:{n}:Skill) WHERE size(coalesce(s.srcs, [])) > 0 AND NOT (:{n})-[:INVOKED]->(s) "
        "RETURN s.id AS id ORDER BY id") if usage else []
    return {"unreachable": rows, "never_recorded": never, "records_with_skills": logged, "never_used": idle,
            "usage_counted": counted, "usage_configured": bool(usage)}


def sessions(store, app_id):
    n = store.node
    return store.run(
        f"MATCH (s:{n}:Session)-[:IN]->(:{n} {{id: $id}}) OPTIONAL MATCH (s)-[:ON]->(m:{n}) "
        f"OPTIONAL MATCH (s)-[h:HOLDS]->(t:{n}) "
        "WITH s, m, h, t ORDER BY h.lane, t.name "
        "RETURN s.id AS id, s.name AS name, s.session_id AS session_id, s.text AS text, "
        "collect(DISTINCT m.name) AS machines, "
        "[x IN collect({lane: h.lane, work: t.name}) WHERE x.work IS NOT NULL] AS holds ORDER BY name", id=app_id)


def licenses(store, app_id, group=None, attribution=False):
    n = store.node
    return store.run(
        f"MATCH (a:{n}:Asset)-[:IN]->(:{n} {{id: $id}}) WHERE a.group IS NOT NULL AND ($group IS NULL OR a.group = $group) "
        f"OPTIONAL MATCH (a)-[:UNDER]->(l:{n}) OPTIONAL MATCH (a)-[:FROM]->(s:{n}) "
        "WITH a.group AS group, l, a, s "
        "WITH group, coalesce(l.name, 'unknown') AS license, coalesce(l.attribution, 'check') AS attribution, "
        "count(DISTINCT a) AS assets, collect(DISTINCT s.id) AS sources, collect(DISTINCT a.srcs[0]) AS files "
        "WHERE NOT $attribution OR attribution <> 'no' "
        "RETURN group, license, attribution, assets, sources, files ORDER BY group, license",
        id=app_id, group=group, attribution=attribution)


def status(store):
    f = store.file
    skipped = store.run(f"MATCH (f:{f}) WHERE f.error IS NOT NULL RETURN f.path AS path, f.error AS error ORDER BY path")
    kinds = store.run(f"MATCH (n:{store.node}) RETURN n.type AS type, count(*) AS total ORDER BY type")
    return {**counts(store), "types": {row["type"]: row["total"] for row in kinds}, "skipped": skipped}
