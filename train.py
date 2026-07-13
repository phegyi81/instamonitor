#!/usr/bin/env python3
"""
InstaMonitor Model Trainer (runs on your laptop, NOT the router)
================================================================

Trains a Random Forest on the labeled flow features collected by label.sh
and exports a dependency-free model.json that the router evaluates via
model.py.

Requirements (laptop only):

    pip install scikit-learn

Typical usage:

    ./train.py --input data/training_data.csv --output model.json

Then copy model.json into the project directory on the router. The live
analyzer picks it up automatically on its next start.
"""

import argparse
import csv
import json
import sys

# Import the canonical feature order so training and the router agree.
try:
    from features import FEATURE_NAMES
except ImportError:
    print("ERROR: features.py must be in the same directory as train.py.",
          file=sys.stderr)
    sys.exit(1)


def load_dataset(path):
    """Load the labeled training CSV. Returns (X, y, feature_names)."""
    rows = []
    labels = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        if 'label' not in reader.fieldnames:
            print("ERROR: training CSV has no 'label' column. Record labeled "
                  "sessions with label.sh first.", file=sys.stderr)
            sys.exit(1)
        missing = [c for c in FEATURE_NAMES if c not in reader.fieldnames]
        if missing:
            print(f"ERROR: training CSV missing feature columns: {missing}",
                  file=sys.stderr)
            sys.exit(1)
        for row in reader:
            rows.append([float(row[name]) for name in FEATURE_NAMES])
            labels.append(row['label'])
    return rows, labels


def export_model(clf, threshold, path):
    """Serialize a fitted RandomForest to dependency-free JSON."""
    trees = []
    for est in clf.estimators_:
        t = est.tree_
        trees.append({
            'children_left': t.children_left.tolist(),
            'children_right': t.children_right.tolist(),
            'feature': t.feature.tolist(),
            'threshold': t.threshold.tolist(),
            # value shape is (n_nodes, 1, n_classes) -> flatten middle dim.
            'value': [node[0].tolist() for node in t.value],
        })
    model = {
        'feature_names': list(FEATURE_NAMES),
        'classes': [str(c) for c in clf.classes_],
        'threshold': threshold,
        'trees': trees,
    }
    with open(path, 'w') as f:
        json.dump(model, f)
    return len(trees)


def main():
    parser = argparse.ArgumentParser(
        description='Train a Random Forest on labeled flow features.')
    parser.add_argument('--input', default='data/training_data.csv',
                        help='Labeled training CSV (default data/training_data.csv).')
    parser.add_argument('--output', default='model.json',
                        help='Output model path (default model.json).')
    parser.add_argument('--trees', type=int, default=200,
                        help='Number of trees in the forest (default 200).')
    parser.add_argument('--max-depth', type=int, default=None,
                        help='Max tree depth (default: unlimited).')
    parser.add_argument('--threshold', type=float, default=0.6,
                        help='Min confidence for a prediction, else "unknown" '
                             '(default 0.6).')
    parser.add_argument('--test-size', type=float, default=0.25,
                        help='Fraction held out for the test report (default 0.25).')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for reproducibility (default 42).')
    args = parser.parse_args()

    # scikit-learn is only required to actually train (laptop side).
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split, cross_val_score
        from sklearn.metrics import classification_report, confusion_matrix
    except ImportError:
        print("ERROR: scikit-learn is not installed.\n"
              "Install it on your laptop with:  pip install scikit-learn",
              file=sys.stderr)
        sys.exit(1)

    X, y = load_dataset(args.input)
    n = len(y)
    if n == 0:
        print("ERROR: no rows in training data.", file=sys.stderr)
        sys.exit(1)

    classes = sorted(set(y))
    print(f"Loaded {n} labeled flows across {len(classes)} classes: {classes}")
    for c in classes:
        print(f"  {c}: {y.count(c)}")
    if len(classes) < 2:
        print("ERROR: need at least 2 classes to train. Record more labeled "
              "sessions (e.g. chat, video_call, reels, other).", file=sys.stderr)
        sys.exit(1)

    clf = RandomForestClassifier(
        n_estimators=args.trees,
        max_depth=args.max_depth,
        random_state=args.seed,
        class_weight='balanced',
        n_jobs=-1,
    )

    # Hold-out evaluation (only if every class has enough samples to stratify).
    min_class = min(y.count(c) for c in classes)
    if min_class >= 2 and n >= 8:
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=args.test_size, random_state=args.seed, stratify=y)
        clf.fit(X_tr, y_tr)
        y_pred = clf.predict(X_te)
        print("\n=== Hold-out test report ===")
        print(classification_report(y_te, y_pred, zero_division=0))
        print("Confusion matrix (rows=true, cols=pred), label order:",
              list(clf.classes_))
        print(confusion_matrix(y_te, y_pred))

        # Cross-validation gives a more stable accuracy estimate.
        folds = min(5, min_class)
        if folds >= 2:
            scores = cross_val_score(clf, X, y, cv=folds)
            print(f"\n{folds}-fold CV accuracy: "
                  f"{scores.mean():.3f} +/- {scores.std():.3f}")
    else:
        print("\nWARNING: too few samples per class for a reliable test split; "
              "training on all data and skipping the hold-out report. "
              "Collect more labeled sessions for a trustworthy accuracy estimate.")

    # Final fit on all data for the exported model.
    clf.fit(X, y)

    # Feature importances help you understand what drives the classifier.
    importances = sorted(zip(FEATURE_NAMES, clf.feature_importances_),
                         key=lambda kv: kv[1], reverse=True)
    print("\n=== Top feature importances ===")
    for name, imp in importances[:12]:
        print(f"  {name:22s} {imp:.4f}")

    n_trees = export_model(clf, args.threshold, args.output)
    print(f"\nExported model to {args.output} "
          f"({n_trees} trees, threshold {args.threshold}).")
    print("Copy this file into the project directory on the router; the "
          "analyzer loads it automatically on next start.")


if __name__ == '__main__':
    main()
