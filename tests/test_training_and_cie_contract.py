import inspect
import json
from pathlib import Path

import pytest

pytest.importorskip("torch")

from algorithms import ReinforceBaselineAlg
from parallel_reinforce_algorithm import _validate_checkpoint_reward_type
from utils import get_average_models


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIE_ROOT = PROJECT_ROOT / "cie"


def test_training_default_reward_is_primal_dual_integral():
    default = inspect.signature(ReinforceBaselineAlg.__init__).parameters[
        "reward_type"
    ].default
    assert default == "primaldualintegral"


def test_checkpoint_reward_contract():
    with pytest.warns(RuntimeWarning, match="legacy checkpoint"):
        _validate_checkpoint_reward_type(
            {},
            "primaldualintegral",
            "legacy.pkl",
        )
    with pytest.warns(RuntimeWarning, match="does not match"):
        _validate_checkpoint_reward_type(
            {"reward_type": "solving_time"},
            "primaldualintegral",
            "inference.pkl",
            strict=False,
        )
    with pytest.raises(ValueError, match="does not match"):
        _validate_checkpoint_reward_type(
            {"reward_type": "solving_time"},
            "primaldualintegral",
            "resume.pkl",
            strict=True,
        )


def test_checkpoint_ensembles_cannot_mix_reward_semantics():
    with pytest.raises(ValueError, match="different reward types"):
        get_average_models(
            [
                {"reward_type": "solving_time"},
                {"reward_type": "primaldualintegral"},
            ]
        )
    with pytest.raises(ValueError, match="legacy checkpoints"):
        get_average_models(
            [
                {"reward_type": "primaldualintegral"},
                {},
            ]
        )


def test_cie_active_paths_do_not_reference_legacy_submission_assets():
    active_files = []
    active_files.extend(CIE_ROOT.glob('run_cie*.ps1'))
    active_files.extend((CIE_ROOT / 'code').glob('*.py'))
    active_files.extend((CIE_ROOT / 'configs').glob('*.json'))
    active_files.extend((CIE_ROOT / 'docs').glob('*.md'))
    assert active_files
    for path in active_files:
        text = path.read_text(encoding='utf-8').lower()
        assert 'aaai/' not in text
        assert ('aaai' + chr(92)) not in text
        assert 'benchmark-transfer' not in text


def _legacy_test_only_cie_submission_tree_and_active_paths_remain():
    for removed_name in ("aaai", "incom2027", "cirp_cms2027"):
        assert not (PROJECT_ROOT / removed_name).exists()

    active_files = []
    active_files.extend(CIE_ROOT.glob("run_cie*.ps1"))
    active_files.extend((CIE_ROOT / "code").glob("*.py"))
    active_files.extend((CIE_ROOT / "configs").glob("*.json"))
    active_files.extend((CIE_ROOT / "docs").glob("*.md"))
    assert active_files
    for path in active_files:
        text = path.read_text(encoding="utf-8").lower()
        assert "aaai/" not in text
        assert ("aaai" + chr(92)) not in text
        assert "benchmark-transfer" not in text


def test_cie_manifest_configs_data_and_five_seed_checkpoints_exist():
    manifest_path = CIE_ROOT / "configs" / "cie_benchmark_suites.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["suites"]
    for suite in manifest["suites"]:
        suite_root = (manifest_path.parent / suite["root"]).resolve()
        assert suite_root.is_dir(), suite_root

    for name in (
        "cie_hem_train.json",
        "cie_feature_only_train.json",
        "cie_proposed_train.json",
    ):
        config = json.loads(
            (CIE_ROOT / "configs" / name).read_text(encoding="utf-8")
        )
        assert config["algorithm"]["reward_type"] == "primaldualintegral"
        assert (PROJECT_ROOT / config["env"]["instance_file_path"]).exists()
        assert (PROJECT_ROOT / config["test_kwargs"]["test_instance_path"]).exists()
        assert (PROJECT_ROOT / config["test_kwargs"]["test_model_path"]).is_file()

    for method in ("hem", "feature_only", "proposed"):
        for seed in range(1, 6):
            checkpoint_dir = CIE_ROOT / "models" / method / f"seed_{seed}"
            assert (checkpoint_dir / "variant.json").is_file()
            assert (checkpoint_dir / "itr_60.pkl").is_file()
            variant = json.loads(
                (checkpoint_dir / "variant.json").read_text(encoding="utf-8")
            )
            assert variant["algorithm"]["reward_type"] == "primaldualintegral"


def test_cie_training_seed_and_stage_contract_is_auditable():
    training_source = (
        PROJECT_ROOT / "parallel_reinforce_algorithm.py"
    ).read_text(encoding="utf-8")
    train_branch = training_source.index("elif args.train_type == 'train':")
    cli_seed_override = training_source.index(
        "all_kwargs['experiment']['seed'] = args.seed",
        train_branch,
    )
    rng_initialization = training_source.index(
        "seed = set_global_seed(experiment_kwargs['seed'])",
        train_branch,
    )
    assert cli_seed_override < rng_initialization

    runner = (CIE_ROOT / "run_cie.ps1").read_text(encoding="utf-8")
    for stage in (
        "train-hem",
        "train-feature-only",
        "train-proposed",
        "train-all",
        "benchmark-stability",
    ):
        assert stage in runner
    assert "'--scip_seed',$seed" in runner
    assert "'--use_cutsel_percent_policy','True'" in runner
    assert "Skipping legacy/non-auditable checkpoint metadata" in runner
    assert "AcsWeightsFile" in runner

    single_runner = (CIE_ROOT / "run_cie_single.ps1").read_text(encoding="utf-8")
    assert "a3cenv' in sys.executable" not in single_runner
    assert "AllowLegacyCheckpoints" in single_runner
    assert "AcsWeightsFile" in single_runner


def test_all_petri_configs_enable_linear_two_stage_stability():
    config_paths = sorted((PROJECT_ROOT / "configs").glob("petri*.json"))
    config_paths.extend(
        CIE_ROOT / "configs" / name
        for name in (
            "cie_hem_train.json",
            "cie_feature_only_train.json",
            "cie_proposed_train.json",
        )
    )
    assert config_paths

    for path in config_paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        env_sections = [config["env"]]
        for section_name in ("test_kwargs", "evaluate_kwargs", "online_test_kwargs"):
            section_env = config.get(section_name, {}).get("test_env_kwargs")
            if section_env is not None:
                env_sections.append(section_env)
        for env in env_sections:
            assert env["lexicographic_schedule_stability"] is True, path
            assert env["schedule_stability_mode"] == "linear", path
            assert float(env["lexicographic_stability_time_limit"]) > 0, path
            assert int(env["lexicographic_stability_node_limit"]) == 5000, path


def test_cie_stability_ablation_is_controlled_and_separate():
    runner = (CIE_ROOT / "run_cie.ps1").read_text(encoding="utf-8")
    benchmark = (CIE_ROOT / "code" / "run_cie_benchmarks.py").read_text(
        encoding="utf-8"
    )
    assert "foreach ($profile in @('full','stage2_off','linear_off'))" in runner
    assert "'--methods', 'proposed'" in runner
    assert "'--stability_profile', 'full'" in runner
    assert '"full": (True, "linear")' in benchmark
    assert '"stage2_off": (False, "linear")' in benchmark
    assert '"linear_off": (True, "quadratic")' in benchmark
    assert 'require --methods proposed' in benchmark
