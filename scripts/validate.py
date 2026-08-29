#!/usr/bin/env python3
"""Cooking 볼트 포맷 검증. 규약은 CLAUDE.md 참조."""
import os
import re
import sys
import collections

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Cooking")

COMMON = ["type", "title", "tags", "updated"]
EXTRA = {
    "recipe": ["cuisine", "category", "servings", "time_total", "time_active",
               "difficulty", "key_ingredients"],
    "ingredient": ["group", "storage", "storage_short", "storage_long", "tastes"],
    "technique": ["group", "heat"],
    "taste": ["group"],
    "tool": ["group"],
    "index": ["scope"],
}
SECTIONS = {
    "recipe": ["재료", "만드는 법", "핵심 포인트", "관련 문서"],
    "ingredient": ["고르기", "손질과 형태", "보관", "맛과 성분", "조리 활용", "관련 문서"],
    # ingredient 는 ### 하위 섹션도 검사 (SUBSECTIONS 참조)
    "technique": ["원리", "기본 방법", "변수", "흔한 실수", "적용 요리", "관련 문서"],
    "taste": ["원리", "주요 급원", "조리 활용", "다른 맛과의 관계", "관련 문서"],
    "tool": ["종류와 선택", "사용법", "관리와 보관", "관련 문서"],
    "index": ["시작하기", "전체 목록"],
}


def walk():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d != ".obsidian"]
        for f in sorted(fn):
            if f.endswith(".md"):
                yield os.path.join(dp, f)


def parse_fm(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    raw = text[4:end]
    body = text[end + 5:]
    fm = {}
    key = None
    for line in raw.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            fm[key] = m.group(2).strip()
        elif line.startswith("  - ") and key:
            fm[key] = (fm.get(key) or "") + line.strip()[2:] + ","
    return fm, body


def check_common(r, body, names, errs):
    """frontmatter 유무와 무관하게 모든 문서에 적용되는 검사."""
    if "Tags" in [h.strip() for h in re.findall(r"^## (.+)$", body, re.M)]:
        errs["금지: ## Tags 섹션"].append(r)
    for line in body.split("\n"):
        if re.match(r"^#[^\s#]", line.strip()):
            errs["금지: 본문 해시태그 줄"].append(f"{r}: {line.strip()[:40]}")
            break
    for m in re.findall(r"\[\[([^\]]+)\]\]", body):
        tgt = m.split("|")[0].split("#")[0].strip()
        if "/" in tgt:
            errs["경로형 링크"].append(f"{r}: [[{tgt}]]")
            tgt = tgt.split("/")[-1]
        if tgt not in names:
            errs["깨진 링크"].append(f"{r}: [[{tgt}]]")
        elif tgt == r[:-3].split("/")[-1]:
            errs["자기 자신 링크"].append(f"{r}: [[{tgt}]]")


def main():
    paths = list(walk())
    names = {}
    dupes = collections.defaultdict(list)
    for p in paths:
        b = os.path.basename(p)[:-3]
        dupes[b].append(p)
        names[b] = p

    errs = collections.defaultdict(list)

    for name, ps in dupes.items():
        if len(ps) > 1:
            errs["중복 파일명"].append(f"{name}: " + ", ".join(rel(x) for x in ps))

    for p in paths:
        r = rel(p)
        text = open(p, encoding="utf-8").read()
        fm, body = parse_fm(text)

        # frontmatter 유무와 무관하게 링크·금지항목은 항상 검사한다.
        # (예전에는 여기서 continue 해서 볼트의 2/3가 검사되지 않았다)
        t = fm.get("type", "") if fm else ""

        if fm is None:
            errs["frontmatter 없음"].append(r)
        elif t not in EXTRA:
            errs["type 잘못됨"].append(f"{r}: {t or '(없음)'}")
        else:
            missing = [k for k in COMMON + EXTRA[t] if not fm.get(k)]
            if missing:
                errs["필수 필드 누락"].append(f"{r}: {', '.join(missing)}")

        if t not in EXTRA:
            check_common(r, body, names, errs)
            continue

        title = fm.get("title", "").strip().strip("\"'")
        if title and title != os.path.basename(p)[:-3]:
            errs["title≠파일명"].append(f"{r}: title={title}")

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", fm.get("updated", "")):
            errs["updated 형식"].append(r)

        tags = [x for x in re.split(r"[,\[\]]", fm.get("tags", "")) if x.strip()]
        if len(tags) < 2:
            errs["tags 2개 미만"].append(r)

        heads = [h.strip() for h in re.findall(r"^## (.+)$", body, re.M)]
        subs = [h.strip() for h in re.findall(r"^### (.+)$", body, re.M)]
        for s in SECTIONS[t]:
            if s not in heads:
                errs["필수 섹션 누락"].append(f"{r}: ## {s}")
        if t == "ingredient":
            tables = len(re.findall(r"^\|[-: |]+\|$", body, re.M))
            if tables < 3:
                errs["표 3개 미만"].append(f"{r}: {tables}개")
            for s in ("단기 보관", "장기 보관"):
                if s not in subs:
                    errs["보관 하위 섹션 누락"].append(f"{r}: ### {s}")
            stor = body.split("## 보관", 1)[-1].split("## 맛과 성분")[0]
            if not re.search(r"\d\s*°C", stor):
                errs["보관: 온도 숫자 없음"].append(r)
            if not re.search(r"\d+\s*(일|주|개월|년)", stor):
                errs["보관: 기간 숫자 없음"].append(r)

        if not re.search(r"^# .+\n+> ", body, re.M):
            errs["제목 뒤 요약(>) 없음"].append(r)

        check_common(r, body, names, errs)

    total = sum(len(v) for v in errs.values())
    print(f"검사 파일: {len(paths)}개")
    if not total:
        print("✅ 통과 — 위반 없음")
        return 0
    for k in sorted(errs, key=lambda x: -len(errs[x])):
        v = errs[k]
        print(f"\n[{k}] {len(v)}건")
        for line in v[:15]:
            print(f"  - {line}")
        if len(v) > 15:
            print(f"  … 외 {len(v) - 15}건")
    print(f"\n❌ 총 {total}건")
    return 1


def rel(p):
    return os.path.relpath(p, ROOT)


if __name__ == "__main__":
    sys.exit(main())
