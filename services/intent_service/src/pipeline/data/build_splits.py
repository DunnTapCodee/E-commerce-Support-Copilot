"""Stratified group-safe 80/10/10 split before translation augmentation."""
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold


def build_splits(frame):
    base = frame.drop_duplicates('src_id').sort_values('src_id').reset_index(drop=True)
    assignment = np.full(len(base), 'train', dtype=object)
    folds = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=42)
    for fold, (_, indices) in enumerate(folds.split(base, base.intent, base.group_id)):
        if fold == 0:
            assignment[indices] = 'test'
        elif fold == 1:
            assignment[indices] = 'val'
    base['split'] = assignment
    assert base.groupby('group_id').split.nunique().max() == 1, 'group leakage'
    assert base.groupby('src_id').split.nunique().max() == 1, 'source leakage'
    return base[['src_id','group_id','split']]
