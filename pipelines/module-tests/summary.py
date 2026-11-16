import glob
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

results_dir = sys.argv[1]
group = sys.argv[2] if len(sys.argv) > 2 else ""
modules = sorted((os.path.basename(p.rstrip("/")) for p in glob.glob("modules/*/")), key=len, reverse=True)


def module_of(classname):
    for m in modules:
        if classname == m or classname.startswith(m + "."):
            return m
    return "(otros)"


stats = defaultdict(lambda: {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0})
failed = []
for path in glob.glob(os.path.join(results_dir, "xml", "*.xml")):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        continue
    for case in root.iter("testcase"):
        s = stats[module_of(case.get("classname", ""))]
        s["tests"] += 1
        s["time"] += float(case.get("time") or 0)
        if case.find("failure") is not None:
            s["failures"] += 1
            failed.append(f"{case.get('classname')}.{case.get('name')}")
        elif case.find("error") is not None:
            s["errors"] += 1
            failed.append(f"{case.get('classname')}.{case.get('name')}")
        elif case.find("skipped") is not None:
            s["skipped"] += 1

print(f"## Module Tests {group}".rstrip())
print()
if not stats:
    print("No se encontraron resultados de tests.")
    sys.exit(0)

print("| Módulo | Tests | Fallos | Errores | Omitidos | Tiempo |")
print("|---|---:|---:|---:|---:|---:|")
total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
for m in sorted(stats):
    s = stats[m]
    mark = "❌" if s["failures"] or s["errors"] else "✅"
    print(f"| {mark} {m} | {s['tests']} | {s['failures']} | {s['errors']} | {s['skipped']} | {s['time']:.0f}s |")
    for k in total:
        total[k] += s[k]
print(f"| **Total** | **{total['tests']}** | **{total['failures']}** | **{total['errors']}** | **{total['skipped']}** | **{total['time']:.0f}s** |")

if os.path.exists("modules-cloned.tsv"):
    print()
    print("<details><summary>Módulos clonados</summary>")
    print()
    print("| Módulo | Rama | Commit |")
    print("|---|---|---|")
    with open("modules-cloned.tsv") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                print(f"| {parts[0]} | {parts[1]} | {parts[2]} |")
    print()
    print("</details>")

if failed:
    print()
    print("<details><summary>Tests fallidos</summary>")
    print()
    for t in failed[:200]:
        print(f"- `{t}`")
    print()
    print("</details>")
