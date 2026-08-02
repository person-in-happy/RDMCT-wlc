from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch
from torch import nn

from .environment import CHAMBER_FEATURE_DIM, GLOBAL_FEATURE_DIM, UNIT_FEATURE_DIM


class StructureAwareActorCritic(nn.Module):
    """Pointer-style actor with explicit unit/chamber structural embeddings."""

    def __init__(self, hidden_dim: int = 128):
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.unit_encoder = nn.Sequential(
            nn.Linear(UNIT_FEATURE_DIM, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.chamber_encoder = nn.Sequential(
            nn.Linear(CHAMBER_FEATURE_DIM, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.global_encoder = nn.Sequential(
            nn.Linear(GLOBAL_FEATURE_DIM, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.unit_message = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.chamber_message = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.global_message = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.pointer_vector = nn.Linear(hidden_dim, 1, bias=False)
        self.value_head = nn.Sequential(
            nn.Linear(3 * hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(
        self,
        unit_features: torch.Tensor,
        chamber_features: torch.Tensor,
        global_features: torch.Tensor,
        action_mask: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if unit_features.ndim != 2 or chamber_features.shape[0] != 2:
            raise ValueError("Expected [units, features] and [2, chamber_features].")
        units = self.unit_encoder(unit_features)
        chambers = self.chamber_encoder(chamber_features)
        global_state = self.global_encoder(global_features)
        joint = torch.tanh(
            self.unit_message(units)[:, None, :]
            + self.chamber_message(chambers)[None, :, :]
            + self.global_message(global_state)[None, None, :]
        )
        logits = self.pointer_vector(joint).squeeze(-1)
        logits = logits.masked_fill(~action_mask.bool(), torch.finfo(logits.dtype).min)
        pooled_units = units.mean(dim=0)
        pooled_chambers = chambers.mean(dim=0)
        value = self.value_head(
            torch.cat([pooled_units, pooled_chambers, global_state], dim=-1)
        ).squeeze(-1)
        return logits.reshape(-1), value

    @torch.no_grad()
    def action_log_probs(self, observation, device=None) -> torch.Tensor:
        tensors = observation.as_torch(device=device)
        logits, _ = self(**tensors)
        return torch.log_softmax(logits, dim=-1).cpu()

    @torch.no_grad()
    def choose_action(
        self, observation, greedy: bool = False, device=None
    ) -> Tuple[int, float, float]:
        tensors = observation.as_torch(device=device)
        logits, value = self(**tensors)
        distribution = torch.distributions.Categorical(logits=logits)
        action = torch.argmax(logits) if greedy else distribution.sample()
        return (
            int(action.item()),
            float(distribution.log_prob(action).item()),
            float(value.item()),
        )


def save_checkpoint(
    model: StructureAwareActorCritic,
    path: str | Path,
    *,
    optimizer: Optional[torch.optim.Optimizer] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "schema_version": "rl_sat_checkpoint_v1",
        "hidden_dim": model.hidden_dim,
        "model_state": model.state_dict(),
        "metadata": metadata or {},
    }
    if optimizer is not None:
        payload["optimizer_state"] = optimizer.state_dict()
    torch.save(payload, output)
    return output


def load_checkpoint(
    path: str | Path,
    *,
    device: str | torch.device = "cpu",
) -> Tuple[StructureAwareActorCritic, Dict[str, Any]]:
    payload = torch.load(Path(path), map_location=device, weights_only=False)
    if payload.get("schema_version") != "rl_sat_checkpoint_v1":
        raise ValueError("Unsupported or legacy RL-SAT checkpoint.")
    model = StructureAwareActorCritic(hidden_dim=int(payload["hidden_dim"]))
    model.load_state_dict(payload["model_state"])
    model.to(device)
    model.eval()
    return model, dict(payload.get("metadata", {}))
