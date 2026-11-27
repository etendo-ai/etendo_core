import csv
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
HERE = ROOT / "pipelines/core-tests"
OUT = HERE / "coverage-exclusions-unused.txt"
PROD_ROOTS = [ROOT / "src", ROOT / "src-core/src"] + sorted((ROOT / "modules_core").glob("*/src"))
TEST_ROOTS = [ROOT / "src-test/src"] + sorted(p for p in (ROOT / "modules_core").glob("*/src-test") if p.is_dir())
CONSUMER_ROOTS = sorted((ROOT / "modules").glob("*/src"))
PACKAGES = [
    "org.openbravo.service.rest",
    "org.openbravo.service.web",
    "org.openbravo.service.centralrepository",
    "org.openbravo.materialmgmt.refinventory",
    "org.openbravo.erpCommon.info",
    "org.openbravo.client.kernel.freemarker",
    "com.smf.mobile.utils",
    "org.openbravo.service.datasource",
    "org.openbravo.userinterface.selector",
]
SUFFIXES = ("IntegrationTest", "JupiterTest", "Tests", "Test")


def load_decisions():
    with (HERE / "decisions.csv").open() as f:
        return {r["test_class"]: r["decision"] for r in csv.DictReader(f, delimiter=";")}


def index(roots, exts=(".java",)):
    idx = {}
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.suffix in exts:
                idx.setdefault(".".join(p.relative_to(root).with_suffix("").parts), p)
    return idx


def target_of(test_fqn, prod):
    pkg, name = test_fqn.rsplit(".", 1)
    for suf in SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            base = name[: -len(suf)]
            if f"{pkg}.{base}" in prod:
                return f"{pkg}.{base}"
            hits = [k for k in prod if k.endswith("." + base)]
            if len(hits) == 1:
                return hits[0]
    return None


TOKEN = re.compile(r"\b(?:org|com)\.[\w.]+")
WILDCARD = re.compile(r"\bimport\s+([\w.]+)\.\*;")


def refs(texts):
    names, wild = set(), set()
    for t in texts:
        names.update(TOKEN.findall(t))
        wild.update(WILDCARD.findall(t))
    return names, wild


def referenced(fqn, ref):
    names, wild = ref
    return fqn in names or fqn.rsplit(".", 1)[0] in wild


def main():
    dec = load_decisions()
    prod = index(PROD_ROOTS)
    tests = index(TEST_ROOTS, (".java", ".groovy"))
    kept_texts = [tests[c].read_text(errors="ignore") for c, d in dec.items() if d != "QUITAR" and c in tests]
    consumer_texts = [p.read_text(errors="ignore") for r in CONSUMER_ROOTS for p in r.rglob("*.java")]
    kept_ref, consumer_ref = refs(kept_texts), refs(consumer_texts)
    if not consumer_texts:
        sys.exit("No hay modulos en modules/: este script necesita el workspace con los modulos instalados")
    candidates = {}
    for c, d in dec.items():
        if d == "QUITAR":
            t = target_of(c, prod)
            if t:
                candidates[t] = f"solo lo prueba {c}"
    for fqn in prod:
        if any(fqn.startswith(p + ".") for p in PACKAGES):
            candidates.setdefault(fqn, "paquete sin uso en los modulos instalados")
    excluded = {}
    for fqn, why in sorted(candidates.items()):
        if referenced(fqn, consumer_ref) or referenced(fqn, kept_ref):
            continue
        excluded[fqn] = why
    lines = []
    for fqn in sorted(excluded):
        rel = prod[fqn].relative_to(ROOT).as_posix()
        lines.append(rel)
    OUT.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    print(f"{len(lines)} clases excluidas de cobertura -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
