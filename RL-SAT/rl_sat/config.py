from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List


FULL_MODE = "4x1"
MIX_MODE = "2x2"
VALID_MODES = {FULL_MODE, MIX_MODE}


def _normalise_mode(value: str) -> str:
    token = str(value).strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "4": FULL_MODE,
        "4x1": FULL_MODE,
        "full": FULL_MODE,
        "2": MIX_MODE,
        "2x2": MIX_MODE,
        "mix": MIX_MODE,
    }
    if token not in aliases:
        raise ValueError(f"Unsupported wafer mode: {value!r}. Expected 4x1 or 2x2.")
    return aliases[token]


@dataclass
class ToolConfig:
    """Device and recipe parameters aligned with ``PetriMIPConfig`` defaults."""

    num_pm: int = 2
    num_steps: int = 13
    process_mode: str = "mixed"
    mode_4x1_wafers: int = 10
    mode_2x2_wafers: int = 10
    mode_sequence: List[str] = field(default_factory=list)
    pec_pool_size: int = 8
    pec_storage_slots: int = 10
    batch_size: int = 4
    pm_rotation_time_180: float = 2.0
    pair_transfer_time: float = 4.0
    atr_transfer_time: float = 3.0
    atr_return_time: float = 3.0
    aligner_time: float = 20.0
    llupper_time: float = 30.0
    lllower_time: float = 25.0
    full_process_time: float = 180.0
    mix_boundary_process_time: float = 180.0
    mix_internal_process_time: float = 180.0
    cleaning_interval: int = 5
    cleaning_process_time: float = 500.0
    max_module_residency_time: float = 10000.0
    max_robot_residency_time: float = 10000.0
    max_schedule_wait_time: float = 0.0
    chamber_idle_penalty: float = 0.0001
    post_process_wait_penalty: float = 0.05
    ll_wait_penalty: float = 0.0001
    load_ports: int = 4
    load_port_slots: int = 25
    allow_dynamic_chamber_assignment: bool = False

    @property
    def pm_ids(self) -> List[int]:
        return [2, 3]

    @property
    def atr_load_unload_time(self) -> float:
        return self.pair_transfer_time

    @property
    def atr_lp_al_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_transfer_time

    @property
    def atr_al_llupper_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_transfer_time

    @property
    def atr_lllower_lp_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_return_time

    @property
    def atr_empty_ll_to_lp_time(self) -> float:
        return 2.0 * self.atr_transfer_time

    @property
    def al_exchange_time(self) -> float:
        return 2.0 * self.atr_load_unload_time

    @property
    def mix_process_time(self) -> float:
        return self.mix_boundary_process_time

    @property
    def effective_cleaning_process_time(self) -> float:
        return self.cleaning_process_time or 2.0 * self.full_process_time

    def resolved_modes(self) -> List[str]:
        if self.mode_sequence:
            return [_normalise_mode(mode) for mode in self.mode_sequence]
        process_mode = str(self.process_mode).strip().lower()
        if process_mode in {"4x1", "4", "full"}:
            count = self.mode_4x1_wafers
            return [FULL_MODE] * count
        if process_mode in {"2x2", "2", "mix"}:
            count = self.mode_2x2_wafers
            return [MIX_MODE] * count
        if process_mode not in {"auto", "mixed", "both"}:
            raise ValueError(
                "process_mode must be auto, mixed, both, 4x1, or 2x2 "
                f"(got {self.process_mode!r})."
            )
        return [FULL_MODE] * self.mode_4x1_wafers + [MIX_MODE] * self.mode_2x2_wafers

    def validate(self) -> None:
        if self.num_pm != 2:
            raise ValueError("The project device contains CH2 and CH3; num_pm must be 2.")
        if self.batch_size != 4:
            raise ValueError("The rotary chamber batch size is fixed to four wafers.")
        modes = self.resolved_modes()
        if not modes:
            raise ValueError("At least one product wafer is required.")
        if len(modes) > self.load_ports * self.load_port_slots:
            raise ValueError("Product wafer count exceeds configured load-port capacity.")
        if not 0 <= self.pec_pool_size <= self.pec_storage_slots:
            raise ValueError("pec_pool_size must stay within PEC storage capacity.")
        if self.pec_pool_size < 4 * self.num_pm or self.pec_pool_size % self.num_pm:
            raise ValueError(
                "Four chamber-bound PEC wafers are required per chamber; "
                "pec_pool_size must be at least 8 and divisible by two."
            )
        if self.cleaning_interval < 0:
            raise ValueError("cleaning_interval must be non-negative; zero disables cleaning.")
        if MIX_MODE in modes and self.cleaning_interval == 1:
            raise ValueError("2x2 needs two adjacent exposures; cleaning_interval cannot be 1.")
        if abs(self.mix_boundary_process_time - self.mix_internal_process_time) > 1e-9:
            raise ValueError("Both 2x2 exposures must have identical durations.")
        numeric = [
            self.pm_rotation_time_180,
            self.pair_transfer_time,
            self.atr_transfer_time,
            self.atr_return_time,
            self.aligner_time,
            self.llupper_time,
            self.lllower_time,
            self.full_process_time,
            self.mix_boundary_process_time,
            self.mix_internal_process_time,
            self.cleaning_process_time,
            self.max_module_residency_time,
            self.max_robot_residency_time,
            self.max_schedule_wait_time,
        ]
        if min(numeric) < 0:
            raise ValueError("Durations and residency limits must be non-negative.")


@dataclass
class RLConfig:
    seed: int = 1
    hidden_dim: int = 128
    learning_rate: float = 0.0003
    gamma: float = 0.99
    value_loss_weight: float = 0.5
    entropy_weight: float = 0.01
    gradient_clip: float = 1.0
    train_episodes: int = 300
    workers: int = 2
    checkpoint_every: int = 50
    structural_cost_weight: float = 0.02

    def validate(self) -> None:
        if self.hidden_dim <= 0 or self.train_episodes < 0 or self.workers <= 0:
            raise ValueError("RL dimensions, episodes, and workers must be positive.")
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1].")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive.")


@dataclass
class BeamConfig:
    width: int = 8
    expand_per_node: int = 4
    candidates_for_cpsat: int = 4
    policy_weight: float = 1.0
    lower_bound_weight: float = 0.04
    imbalance_weight: float = 0.02
    diversity_weight: float = 0.05

    def validate(self) -> None:
        if min(self.width, self.expand_per_node, self.candidates_for_cpsat) <= 0:
            raise ValueError("Beam widths and candidate counts must be positive.")


@dataclass
class CPSATConfig:
    time_scale: int = 10
    time_limit_seconds: float = 120.0
    candidate_time_limit_seconds: float = 15.0
    final_polish_seconds: float = 60.0
    num_workers: int = 8
    random_seed: int = 1
    lexicographic_stability: bool = True
    log_search_progress: bool = False
    require_exact_scaling: bool = True

    def validate(self, tool: ToolConfig) -> None:
        if self.time_scale <= 0:
            raise ValueError("time_scale must be positive.")
        if self.time_limit_seconds <= 0 or self.candidate_time_limit_seconds <= 0:
            raise ValueError("CP-SAT time limits must be positive.")
        if self.num_workers <= 0:
            raise ValueError("num_workers must be positive.")
        if self.require_exact_scaling:
            for value in duration_values(tool):
                to_ticks(value, self.time_scale, exact=True)


@dataclass
class OutputConfig:
    run_name: str = "rl_sat_run"
    output_dir: str = "RL-SAT/results"
    write_legacy_solution_json: bool = True
    render_gantt: bool = True


@dataclass
class ExperimentConfig:
    schema_version: str = "rl_sat_config_v1"
    tool: ToolConfig = field(default_factory=ToolConfig)
    rl: RLConfig = field(default_factory=RLConfig)
    beam: BeamConfig = field(default_factory=BeamConfig)
    cpsat: CPSATConfig = field(default_factory=CPSATConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def validate(self) -> None:
        if self.schema_version != "rl_sat_config_v1":
            raise ValueError(f"Unsupported config schema: {self.schema_version}")
        self.tool.validate()
        self.rl.validate()
        self.beam.validate()
        self.cpsat.validate(self.tool)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def duration_values(tool: ToolConfig) -> List[float]:
    return [
        tool.pm_rotation_time_180,
        tool.pair_transfer_time,
        tool.atr_transfer_time,
        tool.atr_return_time,
        tool.aligner_time,
        tool.llupper_time,
        tool.lllower_time,
        tool.full_process_time,
        tool.mix_boundary_process_time,
        tool.mix_internal_process_time,
        tool.effective_cleaning_process_time,
        tool.max_module_residency_time,
        tool.max_robot_residency_time,
        tool.max_schedule_wait_time,
    ]


def to_ticks(value: float, scale: int, exact: bool = True) -> int:
    try:
        scaled = Decimal(str(value)) * Decimal(scale)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid time value: {value!r}") from exc
    nearest = scaled.to_integral_value()
    if exact and scaled != nearest:
        raise ValueError(
            f"Time value {value!r} is not exactly representable at scale {scale}. "
            "Increase cpsat.time_scale or disable require_exact_scaling explicitly."
        )
    result = int(nearest if exact else round(float(scaled)))
    if abs(result) >= 2**62:
        raise ValueError("Scaled time exceeds the safe CP-SAT integer range.")
    return result


def estimate_horizon(tool: ToolConfig, scale: int) -> int:
    wafers = len(tool.resolved_modes())
    pairs = math.ceil(wafers / 2)
    per_pair = (
        tool.atr_lp_al_total_time
        + 2 * tool.aligner_time
        + tool.al_exchange_time
        + tool.atr_al_llupper_total_time
        + tool.llupper_time
        + 4 * tool.pair_transfer_time
        + 2 * max(tool.full_process_time, tool.mix_process_time)
        + tool.lllower_time
        + tool.atr_lllower_lp_total_time
    )
    clean_count = max(1, pairs // max(tool.cleaning_interval, 1))
    seconds = max(100.0, pairs * per_pair + clean_count * tool.effective_cleaning_process_time)
    return max(1, to_ticks(seconds * 2.0, scale, exact=False))


def _construct(dataclass_type, raw: Dict[str, Any]):
    valid = dataclass_type.__dataclass_fields__
    unknown = sorted(set(raw) - set(valid))
    if unknown:
        raise ValueError(f"Unknown {dataclass_type.__name__} fields: {', '.join(unknown)}")
    return dataclass_type(**raw)


def load_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    allowed = {"schema_version", "tool", "rl", "beam", "cpsat", "output"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"Unknown top-level config fields: {', '.join(unknown)}")
    cfg = ExperimentConfig(
        schema_version=raw.get("schema_version", "rl_sat_config_v1"),
        tool=_construct(ToolConfig, raw.get("tool", {})),
        rl=_construct(RLConfig, raw.get("rl", {})),
        beam=_construct(BeamConfig, raw.get("beam", {})),
        cpsat=_construct(CPSATConfig, raw.get("cpsat", {})),
        output=_construct(OutputConfig, raw.get("output", {})),
    )
    cfg.validate()
    return cfg


def save_config(config: ExperimentConfig, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, ensure_ascii=False, indent=2)
