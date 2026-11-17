import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
print("## Core Tests\n")
print("| Suite | Tests | Fallos | Errores | Omitidos | Tiempo (min) |")
print("|---|---|---|---|---|---|")
failures = []
for suite_dir in sorted(p for p in root.glob("*") if p.is_dir()):
    t = f = e = s = 0
    secs = 0.0
    for x in (suite_dir / "xml").glob("TEST-*.xml"):
        try:
            ts = ET.parse(x).getroot()
        except ET.ParseError:
            continue
        t += int(ts.get("tests", 0))
        f += int(ts.get("failures", 0))
        e += int(ts.get("errors", 0))
        s += int(ts.get("skipped", 0))
        secs += float(ts.get("time", 0) or 0)
        for tc in ts.iter("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                failures.append(f"{tc.get('classname')}.{tc.get('name')}")
    print(f"| {suite_dir.name} | {t} | {f} | {e} | {s} | {secs / 60:.1f} |")
if failures:
    print("\n### Tests fallidos\n")
    for name in failures[:200]:
        print(f"- `{name}`")
    if len(failures) > 200:
        print(f"- ... y {len(failures) - 200} más")
