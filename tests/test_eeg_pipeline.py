"""Comprehensive automated test suite for EEG Brainwave Classification Pipeline.

Covers all 14 required validation, training, and inference scenarios:
1. Valid binary classification dataset.
2. Valid multiclass classification dataset.
3. Missing target column error.
4. Missing dataset file error.
5. Missing target labels removal.
6. Missing feature values handling via median imputer.
7. Infinite feature values handling.
8. Feature column containing only missing values dropped.
9. Dataset with only one class rejected.
10. Rare class with insufficient examples handled.
11. Group column with too few distinct groups rejected.
12. Missing or incompatible inference features rejected.
13. Successful model serialization and reloading.
14. Successful metrics and plot generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predict_eeg import load_inference_artifacts, predict, validate_inference_features
from train_eeg_xgboost import (
    EEGValidationError,
    load_dataset,
    prepare_features,
    run_pipeline,
    split_dataset,
    validate_dataset,
)


@pytest.fixture
def synthetic_multiclass_df() -> pd.DataFrame:
    """Generate a clean 3-class synthetic EEG DataFrame."""
    rng = np.random.RandomState(42)
    n_samples = 120
    data = {
        "subject_id": [f"sub-{i % 6:02d}" for i in range(n_samples)],
        "session_id": [f"ses-{i % 2:02d}" for i in range(n_samples)],
        "timestamp_ms": list(range(1000, 1000 + n_samples)),
        "brainwave_state": rng.choice(["Relaxed", "Neutral", "Concentrating"], size=n_samples),
        "F3_alpha_power": rng.normal(2.0, 0.5, size=n_samples),
        "F4_alpha_power": rng.normal(2.1, 0.5, size=n_samples),
        "C3_theta_power": rng.normal(1.5, 0.4, size=n_samples),
        "C4_beta_power": rng.normal(1.8, 0.4, size=n_samples),
        "O1_alpha_power": rng.normal(3.0, 0.6, size=n_samples),
        "O2_alpha_power": rng.normal(3.1, 0.6, size=n_samples),
    }
    return pd.DataFrame(data)


@pytest.fixture
def synthetic_binary_df() -> pd.DataFrame:
    """Generate a clean binary (2-class) synthetic EEG DataFrame."""
    rng = np.random.RandomState(101)
    n_samples = 100
    data = {
        "subject_id": [f"sub-{i % 5:02d}" for i in range(n_samples)],
        "session_id": ["ses-01"] * n_samples,
        "workload_state": rng.choice(["Low", "High"], size=n_samples),
        "F3_beta_power": rng.normal(2.0, 0.5, size=n_samples),
        "F4_beta_power": rng.normal(2.1, 0.5, size=n_samples),
        "P3_theta_power": rng.normal(1.7, 0.4, size=n_samples),
    }
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_1_valid_binary_classification(synthetic_binary_df, tmp_path):
    """1. Valid binary classification dataset trains and evaluates successfully."""
    csv_path = tmp_path / "binary_eeg.csv"
    synthetic_binary_df.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_binary"
    results = run_pipeline(
        dataset_path=str(csv_path),
        target_col="workload_state",
        group_col="subject_id",
        output_dir=str(out_dir),
    )

    assert results["pipeline"] is not None
    assert len(results["label_encoder"].classes_) == 2
    assert "accuracy" in results["metrics"]["test_metrics"]
    assert results["metrics"]["dataset_splits"]["n_classes"] == 2


def test_2_valid_multiclass_classification(synthetic_multiclass_df, tmp_path):
    """2. Valid multiclass classification dataset trains and evaluates successfully."""
    csv_path = tmp_path / "multiclass_eeg.csv"
    synthetic_multiclass_df.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_multi"
    results = run_pipeline(
        dataset_path=str(csv_path),
        target_col="brainwave_state",
        group_col="subject_id",
        output_dir=str(out_dir),
    )

    assert len(results["label_encoder"].classes_) == 3
    assert results["metrics"]["test_metrics"]["accuracy"] >= 0.0
    assert results["metrics"]["test_metrics"]["macro_f1"] >= 0.0


def test_3_missing_target_column(synthetic_multiclass_df):
    """3. Missing target column raises EEGValidationError with available column names."""
    with pytest.raises(EEGValidationError) as exc_info:
        validate_dataset(synthetic_multiclass_df, target_col="non_existent_target")
    assert "Target column 'non_existent_target' not found" in str(exc_info.value)


def test_4_missing_dataset_file(tmp_path):
    """4. Missing dataset file raises FileNotFoundError with actionable message."""
    missing_path = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_dataset(missing_path)
    assert "Dataset not found at" in str(exc_info.value)


def test_5_missing_target_labels(synthetic_multiclass_df):
    """5. Rows with missing target labels are removed and reported."""
    df_missing = synthetic_multiclass_df.copy()
    df_missing.loc[0:4, "brainwave_state"] = np.nan

    validated = validate_dataset(df_missing, target_col="brainwave_state")
    assert len(validated) == len(synthetic_multiclass_df) - 5
    assert validated["brainwave_state"].isna().sum() == 0


def test_6_missing_feature_values(synthetic_multiclass_df, tmp_path):
    """6. Missing feature values are safely handled by median imputation inside pipeline."""
    df_nan = synthetic_multiclass_df.copy()
    df_nan.loc[2:10, "F3_alpha_power"] = np.nan
    df_nan.loc[15:20, "C3_theta_power"] = np.nan

    csv_path = tmp_path / "nan_feats.csv"
    df_nan.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_nan"
    results = run_pipeline(
        dataset_path=str(csv_path),
        target_col="brainwave_state",
        group_col="subject_id",
        output_dir=str(out_dir),
    )
    assert results["pipeline"] is not None
    assert results["metrics"]["test_metrics"]["accuracy"] > 0.0


def test_7_infinite_feature_values(synthetic_multiclass_df):
    """7. Infinite feature values (+inf, -inf) are detected and replaced with NaN for imputation."""
    df_inf = synthetic_multiclass_df.copy()
    df_inf.loc[0, "F3_alpha_power"] = np.inf
    df_inf.loc[1, "C3_theta_power"] = -np.inf

    X, y, groups, feats = prepare_features(df_inf, target_col="brainwave_state")
    assert not np.isinf(X).any().any()
    assert np.isnan(X.loc[0, "F3_alpha_power"])
    assert np.isnan(X.loc[1, "C3_theta_power"])


def test_8_all_missing_column_detected(synthetic_multiclass_df):
    """8. Feature column containing only missing values is detected and dropped."""
    df_all_nan = synthetic_multiclass_df.copy()
    df_all_nan["dead_channel"] = np.nan

    X, y, groups, feats = prepare_features(df_all_nan, target_col="brainwave_state")
    assert "dead_channel" not in feats
    assert "dead_channel" not in X.columns


def test_9_single_class_rejected(synthetic_multiclass_df):
    """9. A dataset with only one target class is rejected."""
    df_single = synthetic_multiclass_df.copy()
    df_single["brainwave_state"] = "Relaxed"

    with pytest.raises(EEGValidationError) as exc_info:
        validate_dataset(df_single, target_col="brainwave_state")
    assert "contains only 1 unique class" in str(exc_info.value)


def test_10_rare_class_with_insufficient_samples(synthetic_multiclass_df):
    """10. Rare class with only 1 example raises descriptive error for stratification."""
    df_rare = synthetic_multiclass_df.copy()
    df_rare.loc[0, "brainwave_state"] = "ExtremelyRareState"

    X, y, groups, feats = prepare_features(df_rare, target_col="brainwave_state")
    with pytest.raises(EEGValidationError) as exc_info:
        split_dataset(X, y, groups=groups, use_group_split=False)
    assert "Stratified split requires at least 2 samples per class" in str(exc_info.value)


def test_11_group_column_with_too_few_groups(synthetic_multiclass_df):
    """11. Group-aware splitting with fewer than 2 distinct groups is rejected."""
    df_one_group = synthetic_multiclass_df.copy()
    df_one_group["subject_id"] = "sub-01"

    with pytest.raises(EEGValidationError) as exc_info:
        validate_dataset(df_one_group, target_col="brainwave_state", group_col="subject_id")
    assert "has only 1 unique group(s)" in str(exc_info.value)


def test_12_missing_or_incompatible_inference_features(synthetic_multiclass_df, tmp_path):
    """12. Inference rejects incompatible or missing feature columns."""
    csv_path = tmp_path / "eeg_sample.csv"
    synthetic_multiclass_df.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_inf"
    run_pipeline(
        dataset_path=str(csv_path),
        target_col="brainwave_state",
        output_dir=str(out_dir),
    )

    pipeline, le, expected_feats = load_inference_artifacts(out_dir)
    bad_df = pd.DataFrame({"random_col": [1.0, 2.0]})

    with pytest.raises(ValueError) as exc_info:
        validate_inference_features(bad_df, expected_feats)
    assert "Input data is missing" in str(exc_info.value)


def test_13_model_serialization_and_reload(synthetic_multiclass_df, tmp_path):
    """13. Pipeline and LabelEncoder are serialized atomically and reloaded identically."""
    csv_path = tmp_path / "eeg_sample.csv"
    synthetic_multiclass_df.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_reload"
    run_pipeline(
        dataset_path=str(csv_path),
        target_col="brainwave_state",
        output_dir=str(out_dir),
    )

    pipeline, le, feature_names = load_inference_artifacts(out_dir)
    assert pipeline is not None
    assert hasattr(pipeline, "predict")
    assert len(le.classes_) == 3

    # Run inference prediction using reloaded artifacts
    sample_df = synthetic_multiclass_df[feature_names].head(2)
    preds = predict(pipeline, le, feature_names, sample_df)
    assert len(preds) == 2
    assert preds[0]["predicted_brainwave_state"] in le.classes_


def test_14_metrics_and_plot_generation(synthetic_multiclass_df, tmp_path):
    """14. Metrics JSON is valid and all four visualization plots are generated."""
    csv_path = tmp_path / "eeg_sample.csv"
    synthetic_multiclass_df.to_csv(csv_path, index=False)

    out_dir = tmp_path / "artifacts_plots"
    run_pipeline(
        dataset_path=str(csv_path),
        target_col="brainwave_state",
        output_dir=str(out_dir),
    )

    metrics_file = out_dir / "eeg_metrics.json"
    assert metrics_file.is_file()
    with open(metrics_file, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)
    assert "test_metrics" in metrics_data
    assert "confusion_matrix_raw" in metrics_data

    # Check that all image plots exist and have non-zero size
    for plot_name in [
        "eeg_confusion_matrix.png",
        "eeg_confusion_matrix_normalized.png",
        "eeg_feature_importance.png",
        "eeg_permutation_importance.png",
    ]:
        plot_path = out_dir / plot_name
        assert plot_path.is_file(), f"Missing plot: {plot_name}"
        assert plot_path.stat().st_size > 0, f"Empty plot: {plot_name}"
