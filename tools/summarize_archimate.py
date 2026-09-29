#!/usr/bin/env python3
"""Deterministic one-line-per-object summary of an .archimate file, for diffing."""
import sys, json
import xml.etree.ElementTree as ET

XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"

def short(t):
    return (t or "").split(":")[-1]

def props(e):
    return ";".join(sorted(f"{p.get('key')}={p.get('value')}" for p in e.findall("property")))

def doc(e):
    d = e.find("documentation")
    return json.dumps(d.text.strip(), ensure_ascii=False) if d is not None and d.text else ""

def collect(node, path, out):
    for ch in node:
        if ch.tag == "folder":
            collect(ch, path + [ch.get("name", "")], out)
        elif ch.tag == "element":
            out.append((path, ch))

def refs(view):
    ids = set()
    for n in view.iter():
        for a in ("archimateElement", "archimateRelationship"):
            if n.get(a):
                ids.add(n.get(a))
    return ids

def main(p):
    root = ET.parse(p).getroot()
    items = []
    collect(root, [], items)
    names = {e.get("id"): e.get("name", "") for _, e in items}
    lines = []
    for path, e in items:
        t, i, folder = short(e.get(XSI)), e.get("id"), "/".join(path)
        if t.endswith("Relationship"):
            s, d = e.get("source"), e.get("target")
            core = f"{names.get(s, s)} -> {names.get(d, d)}"
            lines.append((i, f"REL  | {t} | {folder} | {core} | {e.get('name','')} | {i} | {doc(e)} | {props(e)}"))
        elif "DiagramModel" in t or t in ("SketchModel", "CanvasModel"):
            members = ", ".join(sorted(names.get(r, r) for r in refs(e)))
            lines.append((i, f"VIEW | {t} | {folder} | {e.get('name','')} | {i} | {doc(e)} | {props(e)} | contains: {members}"))
        else:
            lines.append((i, f"ELEM | {t} | {folder} | {e.get('name','')} | {i} | {doc(e)} | {props(e)}"))
    print(f"MODEL | {root.get('name','')}")
    for _, l in sorted(lines, key=lambda x: (x[1].split(' | ')[0], x[0])):
        print(l)

main(sys.argv[1])
