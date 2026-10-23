"""Conservative Russian statement parser for the coordinate contract.

Only complete clauses from the supported grammar are accepted. Unparsed
clauses block verification; this is not a general natural-language parser.
No production hooks, model calls or coordinate changes.
"""
import re
from dataclasses import dataclass, field

from .statement_contract import Requirement, audit

PAIR = r"[A-Z]{2}"
NUM = r"\d+(?:[.,]\d+)?"
ROLE = rf"(медиана|биссектриса)\s+({PAIR})"
TRI = r"(?:В\s+треугольнике|Дан\s+треугольник|Треугольник)\s+([A-Z]{3})\b"


@dataclass
class Extraction:
    requirements: list = field(default_factory=list)
    unparsed: list = field(default_factory=list)
    goals: list = field(default_factory=list)

    @property
    def complete(self):
        return bool(self.requirements) and not self.unparsed


def extract(text):
    out = Extraction()
    clauses = [s.strip() for s in re.split(r"[!?;]|\.(?!\d)|\n+", text) if s.strip()]
    triangles = []
    for source in clauses:
        m = re.match(TRI, source)
        if m and len(set(m[1])) == 3:
            triangles.append(tuple(m[1]))
    triangles = list(dict.fromkeys(triangles))

    def add(kind, points, source, value=None):
        out.requirements.append(Requirement(f"r{len(out.requirements)+1}", kind,
                                            tuple(points), source, value))

    def role(kind, segment, source):
        vertex, foot = segment
        matches = [t for t in triangles if vertex in t and foot not in t]
        if len(matches) != 1:
            return False
        sides = [n for n in matches[0] if n != vertex]
        if kind == "медиана":
            add("midpoint", (foot, *sides), source)
        else:
            add("bisector", (vertex, foot, *sides), source)
            add("on_segment", (foot, *sides), source)
        return True

    for source in clauses:
        body = re.sub(r"\s+", " ", source).strip()
        goal = re.fullmatch(rf"Найдите (?:стороны треугольника [A-Z]{{3}}|"
                            rf"(?:длину (?:отрезка )?)?{PAIR})", body)
        if goal:
            out.goals.append(source)
            continue
        tri = re.match(TRI, body)
        if tri:
            if len(set(tri[1])) != 3:
                out.unparsed.append(source)
                continue
            add("triangle", tri[1], source)
            body = body[tri.end():].strip(" ,:")
            if not body:
                continue
        body = re.sub(r"^(?:проведены|проведена)\s+", "", body)
        pair_roles = re.fullmatch(rf"{ROLE}\s+и\s+{ROLE}(.*)", body)
        if pair_roles:
            k1,p1,k2,p2,tail = pair_roles.groups()
            accepted = role(k1,p1,source) & role(k2,p2,source)
            tail = tail.strip()
            rel = re.fullmatch(rf"(перпендикулярны|параллельны)(?: и имеют "
                               rf"одинаковую длину,? равную ({NUM}))?", tail)
            if rel:
                add("perpendicular" if rel[1] == "перпендикулярны" else "parallel", p1+p2, source)
                if rel[2]:
                    value = float(rel[2].replace(",", "."))
                    add("length",p1,source,value)
                    add("length",p2,source,value)
            if not accepted or (tail and not rel):
                out.unparsed.append(source)
            continue
        single = re.fullmatch(ROLE,body)
        reverse = re.fullmatch(rf"({PAIR})\s*[—–-]\s*(медиана|биссектриса)",body)
        if single or reverse:
            kind, seg = (single[1],single[2]) if single else (reverse[2],reverse[1])
            if not role(kind,seg,source):
                out.unparsed.append(source)
            continue
        mid = re.fullmatch(r"(?:точка )?([A-Z])\s*[—–-]\s*середина (?:стороны |отрезка )?([A-Z]{2})",body)
        if mid and len(set(mid[1]+mid[2])) == 3:
            add("midpoint",mid[1]+mid[2],source)
            continue
        rel = re.fullmatch(rf"({PAIR})\s*(⊥|∥|перпендикулярна|параллельна)\s*({PAIR})",body)
        if rel:
            add("perpendicular" if rel[2] in ("⊥","перпендикулярна") else "parallel",rel[1]+rel[3],source)
            continue
        lengths = re.fullmatch(rf"({PAIR}(?:\s*=\s*{PAIR})*)\s*=\s*({NUM})",body)
        if lengths:
            for seg in re.findall(PAIR,lengths[1]):
                add("length",seg,source,float(lengths[2].replace(",",".")))
            continue
        equal = re.fullmatch(rf"({PAIR})\s*=\s*({PAIR})",body)
        if equal:
            add("equal_length",equal[1]+equal[2],source)
            continue
        out.unparsed.append(source)
    return out


def audit_statement(text, coords):
    extraction = extract(text)
    report = audit(extraction.requirements,coords)
    verified = extraction.complete and report["ok"]
    return {"ok":verified,
            "status":"verified" if verified else "incomplete" if not extraction.complete else "violated",
            "unparsed":extraction.unparsed, "goals":extraction.goals,
            "requirements":report["requirements"]}
