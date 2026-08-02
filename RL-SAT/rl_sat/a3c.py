from __future__ import annotations

import json
import queue
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn.functional as F

from .config import ExperimentConfig
from .domain import Problem
from .environment import StructureAwareSchedulingEnv
from .model import StructureAwareActorCritic, save_checkpoint


@dataclass
class EpisodeMetrics:
    episode: int
    worker: int
    reward: float
    loss: float
    policy_loss: float
    value_loss: float
    entropy: float
    estimate: float
    elapsed: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "episode": self.episode,
            "worker": self.worker,
            "reward": self.reward,
            "loss": self.loss,
            "policy_loss": self.policy_loss,
            "value_loss": self.value_loss,
            "entropy": self.entropy,
            "estimate": self.estimate,
            "elapsed": self.elapsed,
        }


class A3CTrainer:
    """Threaded advantage actor-critic with shared parameters.

    Workers keep local models, generate independent episodes, and apply
    gradients to one shared model under a short optimizer lock.  A one-worker
    setting is available for deterministic smoke tests.
    """

    def __init__(
        self,
        problem: Problem,
        config: ExperimentConfig,
        *,
        device: str | torch.device = "cpu",
    ):
        self.problem = problem
        self.config = config
        self.device = torch.device(device)
        self.shared_model = StructureAwareActorCritic(config.rl.hidden_dim).to(self.device)
        self.optimizer = torch.optim.Adam(
            self.shared_model.parameters(), lr=config.rl.learning_rate
        )
        self.optimizer_lock = threading.Lock()
        self.counter_lock = threading.Lock()
        self.next_episode = 0
        self.metrics_queue: "queue.Queue[EpisodeMetrics]" = queue.Queue()
        self.stop_event = threading.Event()

    def _claim_episode(self) -> Optional[int]:
        with self.counter_lock:
            if self.next_episode >= self.config.rl.train_episodes:
                return None
            episode = self.next_episode
            self.next_episode += 1
            return episode

    def _worker(self, worker_id: int, started: float) -> None:
        seed = self.config.rl.seed + 1009 * worker_id
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        env = StructureAwareSchedulingEnv(self.problem, seed=seed)
        local_model = StructureAwareActorCritic(self.config.rl.hidden_dim).to(self.device)
        while not self.stop_event.is_set():
            episode = self._claim_episode()
            if episode is None:
                return
            local_model.load_state_dict(self.shared_model.state_dict())
            local_model.train()
            observation = env.reset()
            log_probs: List[torch.Tensor] = []
            values: List[torch.Tensor] = []
            rewards: List[float] = []
            entropies: List[torch.Tensor] = []
            done = False
            while not done:
                tensors = observation.as_torch(device=self.device)
                logits, value = local_model(**tensors)
                distribution = torch.distributions.Categorical(logits=logits)
                action = distribution.sample()
                next_observation, reward, done, _ = env.step(int(action.item()))
                log_probs.append(distribution.log_prob(action))
                values.append(value)
                rewards.append(float(reward))
                entropies.append(distribution.entropy())
                observation = next_observation

            returns: List[torch.Tensor] = []
            running = torch.zeros((), dtype=torch.float32, device=self.device)
            for reward in reversed(rewards):
                running = torch.as_tensor(
                    reward, dtype=torch.float32, device=self.device
                ) + self.config.rl.gamma * running
                returns.append(running)
            returns.reverse()
            returns_tensor = torch.stack(returns)
            values_tensor = torch.stack(values)
            log_probs_tensor = torch.stack(log_probs)
            entropy_tensor = torch.stack(entropies)
            advantages = returns_tensor - values_tensor
            policy_loss = -(log_probs_tensor * advantages.detach()).mean()
            value_loss = F.mse_loss(values_tensor, returns_tensor)
            entropy = entropy_tensor.mean()
            loss = (
                policy_loss
                + self.config.rl.value_loss_weight * value_loss
                - self.config.rl.entropy_weight * entropy
            )
            local_model.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                local_model.parameters(), self.config.rl.gradient_clip
            )
            with self.optimizer_lock:
                self.optimizer.zero_grad(set_to_none=True)
                for shared_parameter, local_parameter in zip(
                    self.shared_model.parameters(), local_model.parameters()
                ):
                    if local_parameter.grad is not None:
                        shared_parameter.grad = local_parameter.grad.detach().clone()
                self.optimizer.step()
            estimate = float(env.plan.score or 0.0)
            self.metrics_queue.put(
                EpisodeMetrics(
                    episode=episode + 1,
                    worker=worker_id,
                    reward=float(sum(rewards)),
                    loss=float(loss.detach().cpu().item()),
                    policy_loss=float(policy_loss.detach().cpu().item()),
                    value_loss=float(value_loss.detach().cpu().item()),
                    entropy=float(entropy.detach().cpu().item()),
                    estimate=estimate,
                    elapsed=time.perf_counter() - started,
                )
            )

    def train(
        self,
        *,
        checkpoint_path: str | Path,
        metrics_path: str | Path,
    ) -> List[EpisodeMetrics]:
        started = time.perf_counter()
        checkpoint = Path(checkpoint_path)
        metrics_output = Path(metrics_path)
        metrics_output.parent.mkdir(parents=True, exist_ok=True)
        workers = [
            threading.Thread(
                target=self._worker,
                args=(worker_id, started),
                name=f"rl-sat-a3c-{worker_id}",
                daemon=True,
            )
            for worker_id in range(self.config.rl.workers)
        ]
        for worker in workers:
            worker.start()
        metrics: List[EpisodeMetrics] = []
        try:
            while any(worker.is_alive() for worker in workers) or not self.metrics_queue.empty():
                try:
                    metric = self.metrics_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                metrics.append(metric)
                if (
                    self.config.rl.checkpoint_every > 0
                    and metric.episode % self.config.rl.checkpoint_every == 0
                ):
                    save_checkpoint(
                        self.shared_model,
                        checkpoint,
                        optimizer=self.optimizer,
                        metadata={
                            "episodes": metric.episode,
                            "config": self.config.to_dict(),
                        },
                    )
        finally:
            self.stop_event.set()
            for worker in workers:
                worker.join(timeout=5.0)
        metrics.sort(key=lambda item: item.episode)
        with metrics_output.open("w", encoding="utf-8") as handle:
            for metric in metrics:
                handle.write(json.dumps(metric.to_dict(), ensure_ascii=False) + "\n")
        save_checkpoint(
            self.shared_model,
            checkpoint,
            optimizer=self.optimizer,
            metadata={
                "episodes": len(metrics),
                "config": self.config.to_dict(),
                "elapsed": time.perf_counter() - started,
            },
        )
        return metrics
