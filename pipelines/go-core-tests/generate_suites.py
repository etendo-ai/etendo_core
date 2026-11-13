import csv
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
DECISIONS = ROOT / "pipelines/go-core-tests/decisions.csv"
OUT_PKG = "org.openbravo.test.go"
OUT_DIR = ROOT / "src-test/src" / OUT_PKG.replace(".", "/")
TEST_ROOTS = [ROOT / "src-test/src"] + sorted(p for p in (ROOT / "modules_core").glob("*/src-test") if (p / "org").is_dir()) + sorted((ROOT / "modules_core").glob("*/src-test/test/groovy"))
NAME_RE = re.compile(r"^(Test.*|.+[.$]Test.*|.*Tests?)$")


def load_decisions():
    with DECISIONS.open() as f:
        return {r["test_class"]: r["decision"] for r in csv.DictReader(f, delimiter=";")}


def index_sources():
    idx = {}
    for root in TEST_ROOTS:
        for p in list(root.rglob("*.java")) + list(root.rglob("*.groovy")):
            fqn = ".".join(p.relative_to(root).with_suffix("").parts)
            idx.setdefault(fqn, p)
    return idx


def resolve(simple, src_text, own_pkg, idx):
    m = re.search(r"^import\s+([\w.]+\." + re.escape(simple) + r")\s*;", src_text, re.M)
    if m:
        return m.group(1)
    cand = f"{own_pkg}.{simple}"
    if cand in idx:
        return cand
    hits = [k for k in idx if k.endswith("." + simple)]
    return hits[0] if len(hits) == 1 else None


def strip_comments(text):
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)


def class_list(text, annotation):
    text = strip_comments(text)
    m = re.search(annotation + r"\s*\(\s*\{(.*?)\}\s*\)", text, re.S)
    if not m:
        return []
    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", m.group(1), flags=re.S)
    return re.findall(r"([A-Za-z_][\w.]*)\.class", body)


def string_list(text, annotation):
    text = strip_comments(text)
    m = re.search(annotation + r"\s*\(\s*\{?(.*?)\}?\s*\)", text, re.S)
    if not m:
        return []
    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", m.group(1), flags=re.S)
    return re.findall(r'"([^"]+)"', body)


def expand(fqn, idx, seen):
    if fqn in seen or fqn not in idx:
        return [fqn] if fqn not in seen else []
    seen.add(fqn)
    text = idx[fqn].read_text(encoding="utf-8", errors="ignore")
    pkg = fqn.rsplit(".", 1)[0]
    members = class_list(text, r"@Suite\.SuiteClasses") or class_list(text, r"@SuiteClasses") or class_list(text, r"@SelectClasses")
    if not members:
        return [fqn]
    out = []
    for s in members:
        r = s if "." in s and s in idx else resolve(s.split(".")[-1], text, pkg, idx)
        if r:
            out.extend(expand(r, idx, seen))
    return out


def package_scan(packages, excludes, idx):
    found = []
    for fqn in sorted(idx):
        simple_ok = NAME_RE.match(fqn)
        if not simple_ok or not any(fqn.startswith(p + ".") for p in packages):
            continue
        if any(re.fullmatch(e, fqn) for e in excludes):
            continue
        if idx[fqn].suffix != ".java":
            continue
        txt = idx[fqn].read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\babstract\s+class\s+" + re.escape(fqn.rsplit(".", 1)[1]) + r"\b", txt) or not re.search(r"@(Test|ParameterizedTest|RepeatedTest|TestFactory)\b|@RunWith|extends\s+\w+Test\b", txt):
            continue
        found.append(fqn)
    return found


def effective(suite_fqn, idx):
    text = idx[suite_fqn].read_text(encoding="utf-8", errors="ignore")
    pkg = suite_fqn.rsplit(".", 1)[0]
    seen = {suite_fqn}
    out = []
    for s in class_list(text, r"@SelectClasses"):
        r = resolve(s.split(".")[-1], text, pkg, idx)
        if r:
            out.extend(expand(r, idx, seen))
    pkgs = string_list(text, r"@SelectPackages")
    if pkgs:
        out.extend(package_scan(pkgs, string_list(text, r"@ExcludeClassNamePatterns"), idx))
    return list(dict.fromkeys(out))


def pattern_classes(prefix, idx, dec):
    return [k for k in sorted(idx) if k.startswith(prefix) and (k in dec or idx[k].suffix == ".groovy" and NAME_RE.match(k))]


def keep(classes, dec):
    return [c for c in classes if dec.get(c, "MANTENER") != "QUITAR"]


def split_groovy(classes, idx):
    java = [c for c in classes if c not in idx or idx[c].suffix == ".java"]
    return java, [c for c in classes if c not in java]


def write_suite(name, classes):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"package {OUT_PKG};", "", "import org.junit.platform.suite.api.SelectClasses;",
             "import org.junit.platform.suite.api.Suite;", "", "@Suite", "@SelectClasses({"]
    lines += [f"    {c.replace('$', '.')}.class," for c in classes]
    lines += ["})", f"public class {name} {{", "}", ""]
    (OUT_DIR / f"{name}.java").write_text("\n".join(lines), encoding="utf-8")
    return len(classes)


def main():
    dec = load_decisions()
    idx = index_sources()
    plan = {
        "GoStandaloneTestSuite": effective("org.openbravo.test.StandaloneTestSuite", idx),
        "GoCoverageTestSuite": effective("org.openbravo.test.CoverageTestSuite", idx),
        "GoComSmfTestSuite": effective("com.smf.test.CoreTestSuite", idx),
        "GoEtendoerpTestSuite": pattern_classes("com.etendoerp.", idx, dec),
    }
    unknown = sorted({c for v in plan.values() for c in v if c not in dec and not c.endswith("PaymentExecutionActionHandlerTest")})
    extra = []
    for name, classes in plan.items():
        java, groovy = split_groovy(keep(classes, dec), idx)
        extra += groovy
        print(f"{name}: {write_suite(name, java)} de {len(classes)}")
    (ROOT / "pipelines/go-core-tests/extra-tests.txt").write_text("".join(c + "\n" for c in extra), encoding="utf-8")
    print("Extra (groovy):", *extra)
    if unknown:
        print("Sin decision (se mantienen):", *unknown, sep="\n  ")


if __name__ == "__main__":
    main()
