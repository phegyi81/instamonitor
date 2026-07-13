#!/usr/bin/env python3
"""
InstaMonitor Model Runtime (pure standard library)
==================================================

Loads a Random Forest exported by train.py as JSON and evaluates it using
only the Python standard library. This is what runs on the OpenWrt router,
which cannot install scikit-learn -- the heavy training happens on the
laptop, and only this tiny dependency-free evaluator ships to the router.

Model JSON schema (produced by train.py):

    {
      "feature_names": [...],          # order features must be supplied in
      "classes": ["chat", ...],        # class labels
      "threshold": 0.6,                # min confidence, else -> "unknown"
      "trees": [                       # one entry per RF estimator
        {
          "children_left":  [int, ...],
          "children_right": [int, ...],
          "feature":        [int, ...],   # -2 at leaves
          "threshold":      [float, ...], # split value; x <= t -> left
          "value":          [[float, ...], ...]  # per-node class counts
        },
        ...
      ]
    }

A tree node is a leaf when children_left[node] == -1.
"""

import json
import os

TREE_LEAF = -1
UNKNOWN_LABEL = 'unknown'


class Model:
    """Dependency-free Random Forest evaluator."""

    def __init__(self, feature_names, classes, trees, threshold=0.6):
        self.feature_names = feature_names
        self.classes = classes
        self.trees = trees
        self.threshold = threshold

    @classmethod
    def load(cls, path):
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(
            feature_names=data['feature_names'],
            classes=data['classes'],
            trees=data['trees'],
            threshold=data.get('threshold', 0.6),
        )

    def _tree_proba(self, tree, x):
        """Walk one tree and return the leaf's normalized class distribution."""
        node = 0
        left = tree['children_left']
        right = tree['children_right']
        feat = tree['feature']
        thr = tree['threshold']
        while left[node] != TREE_LEAF:
            if x[feat[node]] <= thr[node]:
                node = left[node]
            else:
                node = right[node]
        counts = tree['value'][node]
        total = sum(counts)
        if total <= 0:
            return [0.0] * len(counts)
        return [c / total for c in counts]

    def predict_proba(self, feature_vector):
        """Average per-tree class probabilities (matches sklearn soft voting).

        feature_vector: list of values in self.feature_names order.
        Returns a dict class_label -> probability.
        """
        n_classes = len(self.classes)
        agg = [0.0] * n_classes
        for tree in self.trees:
            proba = self._tree_proba(tree, feature_vector)
            for i in range(n_classes):
                agg[i] += proba[i]
        n_trees = len(self.trees) or 1
        agg = [p / n_trees for p in agg]
        return dict(zip(self.classes, agg))

    def classify(self, feature_vector):
        """Return (label, confidence).

        If the top class probability is below the configured threshold the
        label is UNKNOWN_LABEL, so unfamiliar/background traffic is not forced
        into a known class.
        """
        proba = self.predict_proba(feature_vector)
        best_label = max(proba, key=proba.get)
        confidence = proba[best_label]
        if confidence < self.threshold:
            return UNKNOWN_LABEL, confidence
        return best_label, confidence


def load_if_present(path, threshold=None):
    """Load a model if the file exists, optionally overriding the threshold.

    Returns a Model or None.
    """
    if not path or not os.path.exists(path):
        return None
    model = Model.load(path)
    if threshold is not None:
        model.threshold = threshold
    return model
