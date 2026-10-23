# -*- coding: utf-8 -*-
"""T7: test curator plan items save via direct service call."""
from models import db, User, CuratorPlanItem
from services.curator_plan_service import set_plan


def test_t7_curator_route(app):
    """set_plan saves 21 items, verified by direct DB count."""
    with app.app_context():
        items = [
            ("t1p1", 1, 1), ("t1p2", 1, 2), ("t1p3", 1, 3),
            ("t1p4", 1, 4), ("t1p5", 1, 5), ("t1p6", 1, 6), ("t1p7", 1, 7),
            ("t2p1", 2, 1), ("t2p2", 2, 2), ("t2p3", 2, 3),
            ("t2p4", 2, 4), ("t2p5", 2, 5), ("t2p6", 2, 6), ("t2p7", 2, 7),
            ("t3p1", 3, 1), ("t3p2", 3, 2), ("t3p3", 3, 3),
            ("t3p4", 3, 4), ("t3p5", 3, 5), ("t3p6", 3, 6), ("t3p7", 3, 7),
        ]
        set_plan(items)
        count = CuratorPlanItem.query.count()
        assert count == 21
