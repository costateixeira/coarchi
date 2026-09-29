#!/usr/bin/env python3
"""Diff-friendly YAML views of an .archimate file.

  archimate_tool.py summary model.archimate            -> nested YAML summary
  archimate_tool.py diff old.archimate new.archimate   -> nested YAML change report

Layout/coordinates are ignored on purpose. Objects are matched by id, so
renames and moved folders are reported as changes, not remove+add.
"""
import re, sys
import xml.etree.ElementTree as ET
import yaml

XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
LAYERS = ["Strategy", "Business", "Application", "Technology", "Physical",
          "Motivation", "Implementation & Migration", "Other"]
EXPLICIT = {
    "Strategy": {"Resource", "Capability", "ValueStream", "CourseOfAction"},
    "Business": {"Contract", "Representation", "Product"},
    "Application": {"DataObject"},
    "Technology": {"Node", "Device", "SystemSoftware", "Path",
                   "CommunicationNetwork", "Artifact"},
    "Physical": {"Equipment", "Facility", "DistributionNetwork", "Material"},
    "Motivation": {"Stakeholder", "Driver", "Assessment", "Goal", "Outcome",
                   "Principle", "Requirement", "Constraint", "Meaning", "Value"},
    "Implementation & Migration": {"WorkPackage", "Deliverable",
                                   "ImplementationEvent", "Plateau", "Gap"},
}
ACCESS = {"0": "write", "1": "read", "2": "access", "3": "read/write"}


def words(t):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", t)

def layer_of(t):
    for p in ("Business", "Application", "Technology"):
        if t.startswith(p):
            return p
    for lay, types in EXPLICIT.items():
        if t in types:
            return lay
    return "Other"

def sid(i):
    return (i or "").replace("id-", "")[:8]

def walk(node, out):
    for ch in node:
        if ch.tag == "folder":
            walk(ch, out)
        elif ch.tag == "element":
            out.append(ch)

def details(e):
    d = {}
    doc = e.find("documentation")
    if doc is not None and doc.text and doc.text.strip():
        d["doc"] = " ".join(doc.text.split())
    props = {p.get("key"): p.get("value") for p in e.findall("property")}
    if props:
        d["props"] = dict(sorted(props.items()))
    return d


def parse(path):
    root = ET.parse(path).getroot()
    els = []
    walk(root, els)
    m = {"name": root.get("name", ""), "elements": {}, "relations": {}, "views": {}}
    for e in els:
        t = (e.get(XSI) or "").split(":")[-1]
        i = e.get("id")
        if t.endswith("Relationship"):
            rt = words(t[:-len("Relationship")])
            if t == "AccessRelationship":
                rt += f" ({ACCESS.get(e.get('accessType', '0'), '?')})"
            m["relations"][i] = {"type": rt, "src": e.get("source"), "tgt": e.get("target"),
                                 "name": e.get("name") or "", **details(e)}
        elif "DiagramModel" in t or t in ("SketchModel", "CanvasModel"):
            v = {"name": e.get("name") or "(unnamed)", "elements": set(), "relations": set(),
                 **details(e)}
            for n in e.iter():
                if n.get("archimateElement"):
                    v["elements"].add(n.get("archimateElement"))
                if n.get("archimateRelationship"):
                    v["relations"].add(n.get("archimateRelationship"))
            m["views"][i] = v
        else:
            m["elements"][i] = {"layer": layer_of(t), "type": words(t),
                                "name": e.get("name") or "(unnamed)", **details(e)}
    return m


def node_name(m, i):
    if i in m["elements"]:
        return m["elements"][i]["name"]
    if i in m["relations"]:
        return f"({m['relations'][i]['type']} relation)"
    return "?"

def elabel(m, i):
    return f"{m['elements'][i]['name']} [{sid(i)}]" if i in m["elements"] else f"? [{sid(i)}]"

def rlabel(m, i):
    r = m["relations"].get(i)
    if r is None:
        return f"? [{sid(i)}]"
    nm = f" '{r['name']}'" if r["name"] else ""
    return f"{node_name(m, r['src'])} --{r['type']}--> {node_name(m, r['tgt'])}{nm} [{sid(i)}]"

def vlabel(m, i):
    return f"{m['views'][i]['name']} [{sid(i)}]"

def extra(rec):
    return {k: rec[k] for k in ("doc", "props") if k in rec}


def summary(m):
    out = {"model": m["name"], "elements": {}, "relations": {}, "views": {}}
    for i, e in sorted(m["elements"].items(),
                       key=lambda kv: (LAYERS.index(kv[1]["layer"]), kv[1]["type"], kv[1]["name"], kv[0])):
        out["elements"].setdefault(e["layer"], {}).setdefault(e["type"], {})[elabel(m, i)] = extra(e)
    for i in sorted(m["relations"], key=lambda i: rlabel(m, i)):
        out["relations"][rlabel(m, i)] = extra(m["relations"][i])
    for i in sorted(m["views"], key=lambda i: vlabel(m, i)):
        v = m["views"][i]
        out["views"][vlabel(m, i)] = {
            **extra(v),
            "elements": sorted(elabel(m, x) for x in v["elements"]),
            "relations": sorted(rlabel(m, x) for x in v["relations"]),
        }
    return out


def arrow(a, b):
    return f"{a if a not in (None, '') else '(none)'} -> {b if b not in (None, '') else '(none)'}"

def field_changes(o, n, fields):
    ch = {}
    for f in fields:
        if o.get(f) != n.get(f):
            ch[f] = arrow(o.get(f), n.get(f))
    op, np_ = o.get("props", {}), n.get("props", {})
    pc = {k: arrow(op.get(k), np_.get(k)) for k in sorted(set(op) | set(np_)) if op.get(k) != np_.get(k)}
    if pc:
        ch["props"] = pc
    return ch


def diff(old, new):
    rep = {}

    # elements
    added, removed, changed = {}, {}, {}
    for i in sorted(set(new["elements"]) - set(old["elements"])):
        e = new["elements"][i]
        added.setdefault(e["layer"], {}).setdefault(e["type"], []).append(elabel(new, i))
    for i in sorted(set(old["elements"]) - set(new["elements"])):
        e = old["elements"][i]
        removed.setdefault(e["layer"], {}).setdefault(e["type"], []).append(elabel(old, i))
    for i in sorted(set(old["elements"]) & set(new["elements"])):
        ch = field_changes(old["elements"][i], new["elements"][i], ["name", "layer", "type", "doc"])
        if ch:
            changed[elabel(new, i)] = ch
    sec = {k: v for k, v in (("added", added), ("removed", removed), ("changed", changed)) if v}
    for d in (added, removed):
        for lay in d:
            for t in d[lay]:
                d[lay][t].sort()
    if sec:
        rep["elements"] = sec

    # relations
    sec = {}
    a = sorted(rlabel(new, i) for i in set(new["relations"]) - set(old["relations"]))
    r = sorted(rlabel(old, i) for i in set(old["relations"]) - set(new["relations"]))
    c = {}
    for i in set(old["relations"]) & set(new["relations"]):
        o, n = old["relations"][i], new["relations"][i]
        ch = field_changes(o, n, ["type", "src", "tgt", "name", "doc"])
        for k in ("src", "tgt"):
            if k in ch:
                ch[{"src": "source", "tgt": "target"}[k]] = arrow(node_name(old, o[k]), node_name(new, n[k]))
                del ch[k]
        if ch:
            c[rlabel(new, i)] = ch
    if a: sec["added"] = a
    if r: sec["removed"] = r
    if c: sec["changed"] = dict(sorted(c.items()))
    if sec:
        rep["relations"] = sec

    # views
    sec = {}
    va = {}
    for i in sorted(set(new["views"]) - set(old["views"])):
        v = new["views"][i]
        va[vlabel(new, i)] = {"elements": sorted(elabel(new, x) for x in v["elements"]),
                              "relations": sorted(rlabel(new, x) for x in v["relations"])}
    vr = sorted(vlabel(old, i) for i in set(old["views"]) - set(new["views"]))
    vc = {}
    for i in set(old["views"]) & set(new["views"]):
        o, n = old["views"][i], new["views"][i]
        ch = field_changes(o, n, ["name", "doc"])
        for kind, lab in (("elements", elabel), ("relations", rlabel)):
            ad = sorted(lab(new, x) for x in n[kind] - o[kind])
            rm = sorted(lab(old, x) for x in o[kind] - n[kind])
            if ad or rm:
                ch[kind] = {**({"added": ad} if ad else {}), **({"removed": rm} if rm else {})}
        if ch:
            vc[vlabel(new, i)] = ch
    if va: sec["added"] = va
    if vr: sec["removed"] = vr
    if vc: sec["changed"] = dict(sorted(vc.items()))
    if sec:
        rep["views"] = sec
    return rep


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def dump(obj):
    return yaml.dump(obj, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                     default_flow_style=False, width=10000)


def main(argv):
    if len(argv) == 3 and argv[1] == "summary":
        print(dump(summary(parse(argv[2]))), end="")
    elif len(argv) == 4 and argv[1] == "diff":
        rep = diff(parse(argv[2]), parse(argv[3]))
        print(dump(rep) if rep else "# no model changes (layout-only changes are ignored)", end="")
    else:
        sys.exit(__doc__)

main(sys.argv)
