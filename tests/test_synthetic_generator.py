"""Tests for Session 2.5: Synthetic Telemetry Data Generator."""

import csv
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools"))

from tools.generate_synthetic_data import SyntheticDataGenerator


@pytest.fixture
def default_generator(tmp_path):
    """Generator with default settings."""
    return SyntheticDataGenerator(
        industry="hls", days=90, seed=42,
        include_edge_cases=True, output_dir=str(tmp_path)
    )


@pytest.fixture
def generated_output(tmp_path):
    """Run default generator and return (manifest, output_dir)."""
    gen = SyntheticDataGenerator(
        industry="hls", days=90, seed=42,
        include_edge_cases=True, output_dir=str(tmp_path)
    )
    manifest = gen.generate_all()
    return manifest, tmp_path


@pytest.fixture
def minimal_output(tmp_path):
    """Run minimal generator for quick tests."""
    gen = SyntheticDataGenerator(
        industry="hls", days=7, seed=42, entities=2,
        include_edge_cases=False, output_dir=str(tmp_path)
    )
    manifest = gen.generate_all()
    return manifest, tmp_path


class TestGeneratorProducesValidCSV:
    """All generated CSVs should parse without error."""

    def test_model_metrics_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "model_metrics.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert "source_entity_ref" in reader.fieldnames
        assert "metric_name" in reader.fieldnames
        assert "metric_value" in reader.fieldnames
        assert "timestamp" in reader.fieldnames

    def test_drift_events_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "drift_events.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_alerts_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "alerts.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_agent_traces_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "agent_traces.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0
        # Verify steps_json is valid JSON
        for row in rows[:10]:
            steps = json.loads(row["steps_json"])
            assert isinstance(steps, list)

    def test_lifecycle_events_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "lifecycle_events.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0
        # metadata_json should be valid
        for row in rows[:10]:
            meta = json.loads(row["metadata_json"])
            assert isinstance(meta, dict)

    def test_data_quality_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "data_quality.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_cohort_metrics_parses(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "cohort_metrics.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_manifest_exists(self, generated_output):
        manifest, output_dir = generated_output
        manifest_path = output_dir / "manifest.json"
        assert manifest_path.exists()
        with open(manifest_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["seed"] == 42
        assert loaded["industry"] == "hls"


class TestDeterministicOutput:
    """Same seed must produce identical output."""

    def test_same_seed_same_output(self, tmp_path):
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        gen1 = SyntheticDataGenerator(industry="hls", days=30, seed=42,
                                       include_edge_cases=False, output_dir=str(dir1))
        gen2 = SyntheticDataGenerator(industry="hls", days=30, seed=42,
                                       include_edge_cases=False, output_dir=str(dir2))
        gen1.generate_all()
        gen2.generate_all()

        # Compare all files
        for fname in ["model_metrics.csv", "drift_events.csv", "alerts.csv",
                      "agent_traces.csv", "lifecycle_events.csv",
                      "data_quality.csv", "cohort_metrics.csv", "manifest.json"]:
            content1 = (dir1 / fname).read_text(encoding="utf-8")
            content2 = (dir2 / fname).read_text(encoding="utf-8")
            assert content1 == content2, f"{fname} differs between runs"

    def test_different_seed_different_output(self, tmp_path):
        dir1 = tmp_path / "seed42"
        dir2 = tmp_path / "seed43"
        gen1 = SyntheticDataGenerator(industry="hls", days=30, seed=42,
                                       include_edge_cases=False, output_dir=str(dir1))
        gen2 = SyntheticDataGenerator(industry="hls", days=30, seed=43,
                                       include_edge_cases=False, output_dir=str(dir2))
        gen1.generate_all()
        gen2.generate_all()

        content1 = (dir1 / "model_metrics.csv").read_text(encoding="utf-8")
        content2 = (dir2 / "model_metrics.csv").read_text(encoding="utf-8")
        assert content1 != content2


class TestRowCountsMatchManifest:
    """Manifest row_count must match actual CSV row count."""

    def test_row_counts_accurate(self, generated_output):
        manifest, output_dir = generated_output
        for file_info in manifest["files"]:
            filepath = output_dir / file_info["path"]
            with open(filepath, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # skip header
                actual_count = sum(1 for _ in reader)
            assert actual_count == file_info["row_count"], \
                f"{file_info['path']}: manifest says {file_info['row_count']}, actual {actual_count}"


class TestEntityRefsInManifest:
    """Every source_entity_ref in CSVs should appear in the manifest."""

    def test_all_refs_in_manifest(self, generated_output):
        manifest, output_dir = generated_output
        manifest_refs = {e["source_entity_ref"] for e in manifest["entities"]}

        csv_files = ["model_metrics.csv", "drift_events.csv", "alerts.csv",
                     "agent_traces.csv", "lifecycle_events.csv",
                     "data_quality.csv", "cohort_metrics.csv"]
        for fname in csv_files:
            filepath = output_dir / fname
            with open(filepath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                file_refs = {row["source_entity_ref"] for row in reader}
            for ref in file_refs:
                assert ref in manifest_refs, \
                    f"{fname}: entity_ref '{ref}' not in manifest"


class TestEdgeCases:
    """Edge cases should be present when enabled."""

    def test_edge_cases_present(self, generated_output):
        manifest, output_dir = generated_output
        ec = manifest["edge_cases"]
        assert ec["duplicate_event_ids"] > 0
        assert ec["late_arrivals"] > 0
        assert ec["out_of_order"] > 0
        assert ec["missing_fields"] > 0
        assert ec["schema_violations"] > 0

    def test_missing_fields_in_csv(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "model_metrics.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            empty_values = [r for r in reader if r["metric_value"] == ""]
        assert len(empty_values) > 0

    def test_schema_violations_in_csv(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "model_metrics.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            violations = [r for r in reader if r["metric_value"] == "NOT_A_NUMBER"]
        assert len(violations) > 0

    def test_no_edge_cases_when_disabled(self, tmp_path):
        gen = SyntheticDataGenerator(industry="hls", days=30, seed=42,
                                      include_edge_cases=False, output_dir=str(tmp_path))
        manifest = gen.generate_all()
        ec = manifest["edge_cases"]
        assert ec["duplicate_event_ids"] == 0
        assert ec["missing_fields"] == 0


class TestTimestampRange:
    """Timestamps should span the configured day range."""

    def test_timestamps_span_days(self, generated_output):
        manifest, output_dir = generated_output
        with open(output_dir / "model_metrics.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            timestamps = []
            for row in reader:
                ts_str = row["timestamp"]
                if ts_str and "T" in ts_str:
                    try:
                        timestamps.append(ts_str)
                    except ValueError:
                        pass
        assert len(timestamps) > 0
        timestamps.sort()
        # Should span close to 90 days
        from datetime import datetime
        earliest = datetime.strptime(timestamps[0], "%Y-%m-%dT%H:%M:%SZ")
        latest = datetime.strptime(timestamps[-1], "%Y-%m-%dT%H:%M:%SZ")
        span_days = (latest - earliest).days
        assert span_days >= 80, f"Span is only {span_days} days, expected ~90"


class TestIndustrySupport:
    """Different industries produce different entity names."""

    def test_retail_industry(self, tmp_path):
        gen = SyntheticDataGenerator(industry="retail", days=30, seed=42,
                                      include_edge_cases=False, output_dir=str(tmp_path))
        manifest = gen.generate_all()
        names = [e["name"] for e in manifest["entities"]]
        assert any("Churn" in n or "Demand" in n or "Fraud" in n for n in names)

    def test_hls_industry(self, tmp_path):
        gen = SyntheticDataGenerator(industry="hls", days=30, seed=42,
                                      include_edge_cases=False, output_dir=str(tmp_path))
        manifest = gen.generate_all()
        names = [e["name"] for e in manifest["entities"]]
        assert any("Patient" in n or "Clinical" in n or "Drug" in n for n in names)


class TestMinimalGeneration:
    """Minimal settings should produce valid but small output."""

    def test_minimal_entities(self, minimal_output):
        manifest, output_dir = minimal_output
        assert len(manifest["entities"]) == 2

    def test_minimal_still_has_all_files(self, minimal_output):
        manifest, output_dir = minimal_output
        expected_files = ["model_metrics.csv", "drift_events.csv", "alerts.csv",
                          "agent_traces.csv", "lifecycle_events.csv",
                          "data_quality.csv", "cohort_metrics.csv", "manifest.json"]
        for fname in expected_files:
            assert (output_dir / fname).exists(), f"{fname} missing"

    def test_minimal_row_counts_positive(self, minimal_output):
        manifest, output_dir = minimal_output
        for file_info in manifest["files"]:
            assert file_info["row_count"] > 0, f"{file_info['path']} has 0 rows"


class TestCLI:
    """Test the CLI interface."""

    def test_help_flag(self):
        """--help should not error."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "tools/generate_synthetic_data.py", "--help"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        assert result.returncode == 0
        assert "Generate synthetic telemetry" in result.stdout

    def test_cli_generates_files(self, tmp_path):
        """CLI run produces files."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "tools/generate_synthetic_data.py",
             "--days", "7", "--entities", "2", "--no-edge-cases",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        assert result.returncode == 0
        assert (tmp_path / "manifest.json").exists()
        assert (tmp_path / "model_metrics.csv").exists()
