"""Equivalent deterministic plans for side points fixed by an angle.

An LLM often leaves D and E as free points with angle + on_segment
constraints. That creates a poorly conditioned, scale-invariant nonlinear
system with many spurious local minima. Intersecting the angle ray with the
specified side eliminates those degrees of freedom without changing the
constraints. Both signed ray orientations are tried; the unchanged
constraints and correctness gate reject wrong branches.
"""
from __future__ import annotations

from itertools import product

from .schema import FigurePlan, PlanError, validate_plan


def angle_side_variants(plan: FigurePlan) -> list[FigurePlan]:
    """Return up to four equivalent plans, or [] if the pattern is absent."""
    eligible = []
    built: set[str] = set()
    for construction in plan.constructions:
        if construction.op == "free_point" and construction.out:
            name = construction.out
            sides = [
                c for c in plan.constraints
                if c.type == "on_segment" and c.args[0] == name
            ]
            angles = [
                c for c in plan.constraints
                if c.type == "angle" and name in (c.args[0], c.args[2])
                and c.value is not None and 0 < c.value < 180
            ]
            if len(sides) == len(angles) == 1:
                side, angle = sides[0], angles[0]
                origin = angle.args[1]
                base = angle.args[2] if angle.args[0] == name else angle.args[0]
                if all(ref in built for ref in (side.args[1], side.args[2], origin, base)):
                    eligible.append((name, side.args[1:], origin, base, angle.value))
        built.add(construction.out)
    # Cap combinatorial exploration and leave mixed/ambiguous plans to the
    # existing solver instead of guessing which constraints define a point.
    if not 1 <= len(eligible) <= 2:
        return []

    variants = []
    for signs in product((1, -1), repeat=len(eligible)):
        replacements = {}
        declared = set(plan.points)
        for (name, side, origin, base, theta), sign in zip(eligible, signs):
            witness = f"_ray_{name}"
            while witness in declared:
                witness += "_"
            declared.add(witness)
            replacements[name] = (
                witness,
                {"op": "angle_ray", "out": witness,
                 "args": [origin, base], "value": sign * theta},
                {"op": "line_intersect", "out": name,
                 "args": [side[0], side[1], origin, witness]},
            )
        data = plan.to_dict()
        data["points"].extend(item[0] for item in replacements.values())
        data["draw"]["hide_labels"].extend(item[0] for item in replacements.values())
        converted = []
        for construction in data["constructions"]:
            replace = replacements.get(construction["out"])
            if replace:
                converted.extend(replace[1:])
            else:
                converted.append(construction)
        data["constructions"] = converted
        candidate = FigurePlan.from_dict(data)
        try:
            validate_plan(candidate)
        except PlanError:
            continue
        variants.append(candidate)
    return variants
