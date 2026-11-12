"""Consolidate site.css: drop declarations a later rule with the same selector (in the
same @media) overrides, drop rules for classes nothing uses any more, merge rules that
are now adjacent and identical in selector, and print the result tidily.

    python3 scripts/tidy_css.py digest/static/site.css
"""
import re
import sys
from pathlib import Path

import tinycss2

ROOT = Path(__file__).resolve().parent.parent


def used_words() -> tuple[set[str], set[str]]:
    """Every word in the templates, scripts and Python, plus the prefixes of class names
    built from a value (e.g. `pf-{{ proven }}` or 'mk-st ' + ...)."""
    words, prefixes = set(), set()
    for p in list((ROOT / "digest/templates").rglob("*.j2")) + list((ROOT / "digest/static").glob("*.js")) + \
            list((ROOT / "digest").glob("*.py")):
        t = p.read_text()
        words |= set(re.findall(r"[A-Za-z][\w-]*", t))
        prefixes |= set(re.findall(r"([A-Za-z][\w-]*-)(?:\{\{|'\s*\+)", t))
    return words, prefixes


def ser(nodes) -> str:
    return tinycss2.serialize(nodes).strip()


def norm_sel(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def decls_of(rule):
    out = []
    for d in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
        if d.type == "declaration":
            out.append([d.lower_name if not d.name.startswith("--") else d.name, ser(d.value), d.important])
    return out


def main(path: str):
    src = Path(path).read_text()
    sheet = tinycss2.parse_stylesheet(src, skip_comments=False, skip_whitespace=True)
    used, prefixes = used_words()

    # flatten into items: ("comment", text) | ("rule", media, selector, decls) | ("raw", text)
    items = []
    for n in sheet:
        if n.type == "comment":
            items.append(["comment", n.value])
        elif n.type == "qualified-rule":
            items.append(["rule", "", norm_sel(ser(n.prelude)), decls_of(n)])
        elif n.type == "at-rule" and n.lower_at_keyword == "media":
            media = norm_sel(ser(n.prelude))
            for m in tinycss2.parse_rule_list(n.content, skip_comments=True, skip_whitespace=True):
                if m.type == "qualified-rule":
                    items.append(["rule", media, norm_sel(ser(m.prelude)), decls_of(m)])
        else:
            items.append(["raw", n.serialize()])

    # 1. dead selectors: a selector naming a class nothing uses can never match
    def alive(sel: str) -> bool:
        return all(c in used or any(c.startswith(p) for p in prefixes)
                   for c in re.findall(r"\.([A-Za-z][\w-]*)", sel))
    for it in items:
        if it[0] == "rule":
            parts = [p.strip() for p in it[2].split(",") if alive(p.strip())]
            it[2] = ", ".join(parts)
            if not parts:
                it[3] = []

    # 2. declarations a later rule with the same selector and media overrides
    last = {}
    for i in range(len(items) - 1, -1, -1):
        it = items[i]
        if it[0] != "rule" or not it[2]:
            continue
        key = (it[1], it[2])
        seen = last.setdefault(key, {})
        keep = []
        for name, value, imp in reversed(it[3]):
            later = seen.get(name)
            if later is not None and (later or not imp):
                continue  # overridden later (a later !important, or neither important)
            seen[name] = imp if later is None else (later or imp)
            keep.append([name, value, imp])
        it[3] = list(reversed(keep))
        # within one rule, keep only the last declaration of a property
        dedup, names = [], set()
        for d in reversed(it[3]):
            if d[0] not in names:
                names.add(d[0]); dedup.append(d)
        it[3] = list(reversed(dedup))

    # 2b. custom properties (--x) move up into the first rule with the same selector and
    # media, so each palette is defined in one place. Only custom properties move: they
    # don't compete with other selectors' declarations the way ordinary properties do.
    first = {}
    for it in items:
        if it[0] != "rule" or not it[2]:
            continue
        key = (it[1], it[2])
        if key not in first:
            first[key] = it
            continue
        custom = [d for d in it[3] if d[0].startswith("--")]
        if custom:
            target = first[key]
            target[3] = [d for d in target[3] if d[0] not in {c[0] for c in custom}] + custom
            it[3] = [d for d in it[3] if not d[0].startswith("--")]

    items = [it for it in items if it[0] != "rule" or (it[2] and it[3])]

    # 3. merge adjacent rules with the same selector and media
    merged = []
    for it in items:
        if it[0] == "rule" and merged and merged[-1][0] == "rule" and merged[-1][1:3] == it[1:3]:
            prev = {d[0]: d for d in merged[-1][3]}
            for d in it[3]:
                prev.pop(d[0], None)
            merged[-1][3] = list(prev.values()) + it[3]
            continue
        merged.append(it)

    # drop comments that no longer introduce anything (followed by another comment or the end)
    out_items = []
    for i, it in enumerate(merged):
        if it[0] == "comment":
            nxt = merged[i + 1] if i + 1 < len(merged) else None
            if nxt is None or nxt[0] == "comment":
                continue
        out_items.append(it)

    # print: consecutive rules in the same @media share one block
    lines, i = [], 0
    def decl_text(d):
        return f"{d[0]}: {d[1]}{' !important' if d[2] else ''};"
    def rule_text(sel, decls, indent=""):
        sel = sel.replace(", ", ",\n" + indent) if len(sel) > 90 else sel
        one = " ".join(decl_text(d) for d in decls)
        if len(decls) <= 4 and len(indent) + len(sel) + len(one) < 118 and "\n" not in sel:
            return f"{indent}{sel} {{ {one} }}"
        body = "\n".join(f"{indent}  {decl_text(d)}" for d in decls)
        return f"{indent}{sel} {{\n{body}\n{indent}}}"
    while i < len(out_items):
        it = out_items[i]
        if it[0] == "comment":
            lines.append(f"\n/*{it[1]}*/")
        elif it[0] == "raw":
            lines.append(it[1])
        elif it[1] == "":
            lines.append(rule_text(it[2], it[3]))
        else:
            media, block = it[1], []
            while i < len(out_items) and out_items[i][0] == "rule" and out_items[i][1] == media:
                block.append(rule_text(out_items[i][2], out_items[i][3], "  "))
                i += 1
            lines.append(f"@media {media} {{\n" + "\n".join(block) + "\n}")
            continue
        i += 1
    text = "\n".join(lines).strip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    Path(path).write_text(text)
    print(f"{len(src.splitlines())} -> {len(text.splitlines())} lines")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "digest/static/site.css"))
