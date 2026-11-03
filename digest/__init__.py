"""Weekly cholesterol-drug pipeline digest."""

STAGES = [
    ("phase1", "Phase 1"),
    ("phase2", "Phase 2"),
    ("phase3", "Phase 3"),
    ("filed", "Filed"),
    ("approved", "Approved"),
]
STAGE_RANK = {key: i + 1 for i, (key, _) in enumerate(STAGES)}
STAGE_LABEL = dict(STAGES)
RANK_STAGE = {v: k for k, v in STAGE_RANK.items()}
