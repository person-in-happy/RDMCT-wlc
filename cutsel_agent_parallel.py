import torch
import torch.nn as nn
import torch.autograd as autograd
from torch.autograd import Variable
import torch.nn.functional as F
import math
import numpy as np
import time
from collections import namedtuple
from scip_imports import SCIP_RESULT, scip, scip_core

# from beam_search import Beam
from utils import (
    cut_feature_generator,
    advanced_cut_feature_generator,
    generic_advanced_cut_feature_generator,
    get_structure_family_names,
)
# from utils_fix_isp_bug import cut_feature_generator
from logger import logger

CutselBase = getattr(scip, "Cutsel", getattr(scip_core, "Cutsel", object))
_BeamState = namedtuple("_BeamState", ["selected", "score"])
_GENERIC_FEATURE_DIM = 13


class CutSelectAgent(CutselBase):
    def __init__(
        self,
        scip_model,
        pointer_net,
        value_net,
        sel_cuts_percent,
        device,
        decode_type,
        mean_std,
        policy_type,
        max_candidates=512,
        max_selected_cuts=64,
        use_structure_rerank=None,
        structure_pool_factor=2.0,
        structure_anchor_ratio=0.25,
        structure_quality_weight=0.35,
        structure_policy_weight=0.20,
        structure_coverage_weight=0.25,
        structure_representation_weight=0.20,
    ):
        super().__init__()
        self.scip_model = scip_model
        self.policy = pointer_net
        self.value = value_net
        self.sel_cuts_percent = sel_cuts_percent
        self.device = device
        self.decode_type = decode_type
        self.policy_type = policy_type
        # Pointer decoding is sequential.  Letting it decode thousands of
        # root-node cuts makes the callback dominate SCIP's solve time
        # (especially for the dense 2x2 Petri model).  These caps only limit
        # the learned-policy candidate pool; omitted cuts are still returned
        # to SCIP after the selected prefix.
        self.max_candidates = max_candidates
        self.max_selected_cuts = max_selected_cuts

        self.data = {}
        self._callback_calls = 0
        self._callback_time_seconds = 0.0
        self._callback_input_cuts = 0
        self._callback_max_input_cuts = 0
        self._callback_forced_cuts = 0
        self._callback_root_calls = 0
        self._callback_nonroot_calls = 0
        self._phase_time_seconds = {
            "feature_extraction": 0.0,
            "device_transfer": 0.0,
            "policy_inference": 0.0,
            "structure_rerank": 0.0,
        }
        # self.cuts_info ={}
        self.lp_info = {
            "lp_solution_value": [],
            "lp_solution_integer_var_value": []
        }
        self.mean_std = mean_std
        self.feature_dim = int(getattr(pointer_net, "embedding_dim", 0) or 0)
        if self.feature_dim not in {_GENERIC_FEATURE_DIM, 23}:
            raise ValueError(
                "Unsupported cut-policy input dimension "
                f"{self.feature_dim}; expected 13 (HEM) or 23 (structure-aware)."
            )
        self.use_structure_features = self.feature_dim > _GENERIC_FEATURE_DIM
        self.use_structure_rerank = (
            self.use_structure_features
            if use_structure_rerank is None
            else bool(use_structure_rerank)
        )
        self.structure_pool_factor = max(1.0, float(structure_pool_factor))
        self.structure_anchor_ratio = min(
            1.0, max(0.0, float(structure_anchor_ratio))
        )
        structure_weights = np.asarray(
            [
                structure_quality_weight,
                structure_policy_weight,
                structure_coverage_weight,
                structure_representation_weight,
            ],
            dtype=np.float64,
        )
        if np.any(structure_weights < 0) or structure_weights.sum() <= 0:
            raise ValueError("structure submodular weights must be nonnegative with positive sum")
        structure_weights /= structure_weights.sum()
        (
            self.structure_quality_weight,
            self.structure_policy_weight,
            self.structure_coverage_weight,
            self.structure_representation_weight,
        ) = structure_weights.tolist()

    @staticmethod
    def _fallback_cutsel_result(cuts, maxnselectedcuts):
        """Return a Cython-safe result when learned cut selection fails.

        PySCIPOpt invokes ``cutselselect`` directly from a C callback.  An
        exception escaping this method is converted to SCIP_ERROR at the C
        boundary (and can terminate the Windows process without the original
        Python traceback).  Preserve SCIP's supplied order and select its
        allowed prefix instead of letting an optional learned policy turn one
        bad callback into a solver crash.
        """
        try:
            selection_limit = max(0, int(maxnselectedcuts))
        except (TypeError, ValueError, OverflowError):
            selection_limit = 0
        return {
            "cuts": list(cuts),
            "nselectedcuts": min(len(cuts), selection_limit),
            "result": SCIP_RESULT.SUCCESS,
        }

    @classmethod
    def _validate_cutsel_result(cls, result, cuts, maxnselectedcuts):
        """Normalize a learned response before PySCIPOpt hands it to SCIP."""
        if not isinstance(result, dict):
            raise TypeError(f"cut selector returned {type(result).__name__}, expected dict")

        ordered_cuts = result.get("cuts", cuts)
        if not isinstance(ordered_cuts, (list, tuple)):
            raise TypeError("cut selector returned a non-sequence `cuts` value")
        if len(ordered_cuts) != len(cuts):
            raise ValueError(
                "cut selector must return every candidate exactly once: "
                f"got {len(ordered_cuts)} of {len(cuts)} cuts"
            )
        # The returned items must be the very Row wrappers supplied by SCIP,
        # with no duplicated or foreign rows.  Cython casts them to SCIP_ROW*
        # without further validation, so check identity before crossing back
        # into native code.
        if sorted(map(id, ordered_cuts)) != sorted(map(id, cuts)):
            raise ValueError("cut selector returned duplicated or foreign cut rows")

        try:
            selection_limit = max(0, int(maxnselectedcuts))
            selected_count = int(result.get("nselectedcuts", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("cut selector returned an invalid selected-cut count") from exc
        selected_count = min(max(0, selected_count), len(cuts), selection_limit)

        return {
            "cuts": list(ordered_cuts),
            "nselectedcuts": selected_count,
            "result": result.get("result", SCIP_RESULT.SUCCESS),
        }

    def _safe_learned_cutsel_call(self, selector, cuts, forcedcuts, root, maxnselectedcuts):
        """Run a Python policy without allowing exceptions through SCIP's C API."""
        callback_start = time.perf_counter()
        try:
            result = selector(cuts, forcedcuts, root, maxnselectedcuts)
            return self._validate_cutsel_result(result, cuts, maxnselectedcuts)
        except Exception as exc:
            try:
                logger.log(
                    "warning: learned cut selector failed; falling back to SCIP candidate order: "
                    f"{type(exc).__name__}: {exc}"
                )
            except Exception:
                # Logging must not be allowed to reintroduce a C-callback
                # failure while recovering from the original exception.
                pass
            return self._fallback_cutsel_result(cuts, maxnselectedcuts)
        finally:
            self._callback_calls += 1
            self._callback_time_seconds += time.perf_counter() - callback_start
            self._callback_input_cuts += len(cuts)
            self._callback_max_input_cuts = max(
                self._callback_max_input_cuts, len(cuts)
            )
            self._callback_forced_cuts += len(forcedcuts)
            if bool(root):
                self._callback_root_calls += 1
            else:
                self._callback_nonroot_calls += 1

    def _record_phase_times(
        self,
        feature_extraction=0.0,
        device_transfer=0.0,
        policy_inference=0.0,
        structure_rerank=0.0,
    ):
        self._phase_time_seconds["feature_extraction"] += float(feature_extraction)
        self._phase_time_seconds["device_transfer"] += float(device_transfer)
        self._phase_time_seconds["policy_inference"] += float(policy_inference)
        self._phase_time_seconds["structure_rerank"] += float(structure_rerank)

    def get_telemetry(self):
        calls = int(self._callback_calls)
        total_time = float(self._callback_time_seconds)
        feature_summary = {}
        state = self.data.get("state") if isinstance(self.data, dict) else None
        if isinstance(state, np.ndarray) and state.ndim == 2 and len(state):
            candidate_indices = self.data.get("candidate_indices", list(range(len(state))))
            candidate_position = {
                int(global_idx): local_idx
                for local_idx, global_idx in enumerate(candidate_indices)
            }
            selected_positions = [
                candidate_position[int(global_idx)]
                for global_idx in self.data.get("selected_action", [])
                if int(global_idx) in candidate_position
            ]
            if selected_positions:
                selected_features = state[selected_positions]
                feature_summary = {
                    "selected_count": len(selected_positions),
                    "mean_obj_parallelism": float(np.mean(selected_features[:, 0])),
                    "mean_efficacy": float(np.mean(selected_features[:, 1])),
                    "mean_support": float(np.mean(selected_features[:, 2])),
                    "max_support": float(np.max(selected_features[:, 2])),
                    "mean_integral_support": float(np.mean(selected_features[:, 3])),
                    "mean_violation": float(np.mean(selected_features[:, 4])),
                }
        return {
            "callback_calls": calls,
            "callback_time_seconds": total_time,
            "mean_callback_time_seconds": total_time / calls if calls else 0.0,
            "mean_input_cuts": self._callback_input_cuts / calls if calls else 0.0,
            "max_input_cuts": int(self._callback_max_input_cuts),
            "total_forced_cuts": int(self._callback_forced_cuts),
            "root_calls": int(self._callback_root_calls),
            "nonroot_calls": int(self._callback_nonroot_calls),
            "phase_time_seconds": dict(self._phase_time_seconds),
            "effective_max_candidates": self.max_candidates,
            "effective_max_selected_cuts": self.max_selected_cuts,
            "decode_type": self.decode_type,
            "use_structure_rerank": bool(self.use_structure_rerank),
            "selected_feature_summary": feature_summary,
        }

    def _policy_candidate_indices(self, cuts):
        """Keep a deterministic, inexpensive high-efficacy policy pool."""
        num_cuts = len(cuts)
        if self.max_candidates is None or int(self.max_candidates) <= 0:
            return np.arange(num_cuts, dtype=np.int64)
        limit = min(num_cuts, int(self.max_candidates))
        if limit >= num_cuts:
            return np.arange(num_cuts, dtype=np.int64)

        # This SCIP accessor is substantially cheaper than calculating all
        # 23 structural features (which traverses every row-column support).
        # Tie-breaking by original index makes the candidate pool repeatable.
        efficacy = np.fromiter(
            (float(self.scip_model.getCutEfficacy(cut)) for cut in cuts),
            dtype=np.float64,
            count=num_cuts,
        )
        candidate = np.argpartition(-efficacy, limit - 1)[:limit]
        return candidate[np.lexsort((candidate, -efficacy[candidate]))]

    def _cap_selected_count(self, target_count, candidate_count):
        target_count = min(int(target_count), int(candidate_count))
        if self.max_selected_cuts is not None and int(self.max_selected_cuts) > 0:
            target_count = min(target_count, int(self.max_selected_cuts))
        return max(0, target_count)

    @staticmethod
    def _sort_all_cuts(cuts, selected_indices):
        selected_set = set(selected_indices)
        return [cuts[idx] for idx in selected_indices] + [
            cut for idx, cut in enumerate(cuts) if idx not in selected_set
        ]

    def _target_cut_count(self, num_cuts, maxnselectedcuts, desired_count, min_when_possible=2):
        limit = min(int(num_cuts), int(maxnselectedcuts))
        if limit <= 0:
            return 0
        desired_count = int(desired_count)
        if limit >= min_when_possible:
            desired_count = max(desired_count, min_when_possible)
        else:
            desired_count = max(desired_count, 1)
        return max(0, min(desired_count, limit))

    def _capped_target_cut_count(self, num_cuts, maxnselectedcuts, desired_count, min_when_possible=2):
        cap_count = int(num_cuts * self.sel_cuts_percent)
        if self.sel_cuts_percent > 0 and cap_count <= 0:
            cap_count = 1
        desired_count = min(int(desired_count), cap_count)
        min_when_possible = min(min_when_possible, cap_count)
        return self._target_cut_count(
            num_cuts,
            maxnselectedcuts,
            desired_count,
            min_when_possible=min_when_possible,
        )

    def _normalize(self, cuts_features):
        # print(f"debug log mean: {self.mean_std.mean}, std: {self.mean_std.std}")
        return (cuts_features-self.mean_std.mean) / (self.mean_std.std + self.mean_std.epsilon)

    def _extract_policy_features(self, candidate_cuts):
        if self.use_structure_features:
            return advanced_cut_feature_generator(
                self.scip_model,
                candidate_cuts,
                return_metadata=True,
            )
        if self.use_structure_rerank:
            # A generic 13D A3C checkpoint can still be combined with the
            # proposed structure-aware post-processor.  The neural policy
            # sees exactly its original 13 features; only the deterministic
            # reranker consumes the structural metadata.
            features, metadata = advanced_cut_feature_generator(
                self.scip_model,
                candidate_cuts,
                return_metadata=True,
            )
            return features[:, :_GENERIC_FEATURE_DIM], metadata
        features = generic_advanced_cut_feature_generator(
            self.scip_model,
            candidate_cuts,
        )
        return features, None

    def _select_policy_indices(
        self,
        policy_indices,
        candidate_cuts,
        cut_features,
        structure_metadata,
        target_count,
    ):
        if self.use_structure_rerank:
            if structure_metadata is None:
                raise ValueError("structure-aware reranking requires structure metadata")
            return self._apply_structure_aware_selection(
                policy_indices,
                candidate_cuts,
                cut_features,
                structure_metadata,
                target_count,
            )
        selected = self._dedupe_preserve_order(policy_indices, len(candidate_cuts))
        if len(selected) < target_count:
            selected_set = set(selected)
            selected.extend(
                idx
                for idx in range(len(candidate_cuts))
                if idx not in selected_set
            )
        selected = selected[:target_count]
        return selected, {
            "enabled": False,
            "feature_mode": "structure23_no_rerank" if self.use_structure_features else "hem_generic13",
            "selected_count": len(selected),
        }

    def _dedupe_preserve_order(self, idxes, num_cuts):
        seen = set()
        ordered = []
        for idx in idxes:
            if 0 <= idx < num_cuts and idx not in seen:
                ordered.append(idx)
                seen.add(idx)
        return ordered

    def _compute_structure_scores(self, cut_features, structure_metadata):
        if len(cut_features) == 0:
            return np.array([], dtype=np.float64)

        def _minmax(values):
            values = np.asarray(values, dtype=np.float64)
            if values.size == 0:
                return values
            vmin = values.min()
            vmax = values.max()
            if abs(vmax - vmin) <= 1e-12:
                return np.zeros_like(values)
            return (values - vmin) / (vmax - vmin)

        efficacy = _minmax(cut_features[:, 1])
        integral_support = _minmax(cut_features[:, 3])
        violation = _minmax(cut_features[:, 4])
        structured_ratio = np.asarray([meta["structured_ratio"] for meta in structure_metadata], dtype=np.float64)
        dominant_ratio = np.asarray([meta["dominant_family_ratio"] for meta in structure_metadata], dtype=np.float64)
        entropy = np.asarray([meta["family_entropy"] for meta in structure_metadata], dtype=np.float64)

        return (
            0.36 * efficacy
            + 0.24 * violation
            + 0.15 * integral_support
            + 0.15 * structured_ratio
            + 0.10 * dominant_ratio
            - 0.05 * entropy
        )

    def _compute_family_quota(self, candidate_rank, structure_metadata, target_count):
        family_names = get_structure_family_names()[:-1]
        if target_count <= 0 or not candidate_rank:
            return {}, family_names

        weighted_mass = np.zeros(len(family_names), dtype=np.float64)
        top_window = candidate_rank[:max(target_count * 3, target_count)]
        for idx in top_window:
            weighted_mass += structure_metadata[idx]["family_fractions"][:-1]

        if weighted_mass.sum() <= 1e-12:
            return {}, family_names

        shares = weighted_mass / weighted_mass.sum()
        quota = {family_name: 0 for family_name in family_names}
        active_indices = [i for i, share in enumerate(shares) if share >= 0.12]
        if active_indices:
            for i in active_indices:
                quota[family_names[i]] = 1

        remaining = max(0, target_count - sum(quota.values()))
        if remaining > 0:
            fractional = shares * remaining
            floors = np.floor(fractional).astype(int)
            for i, add_count in enumerate(floors):
                quota[family_names[i]] += int(add_count)
            assigned = int(floors.sum())
            if assigned < remaining:
                residual_order = np.argsort(-(fractional - floors))
                for i in residual_order[: remaining - assigned]:
                    quota[family_names[int(i)]] += 1

        total_quota = sum(quota.values())
        if total_quota > target_count:
            family_order = sorted(family_names, key=lambda name: quota[name], reverse=True)
            extra = total_quota - target_count
            for family_name in family_order:
                if extra <= 0:
                    break
                reducible = min(extra, max(0, quota[family_name] - 1))
                quota[family_name] -= reducible
                extra -= reducible
        return quota, family_names

    def _structure_similarity(self, idx_a, idx_b, cut_features, structure_metadata):
        feature_vec_a = np.concatenate(
            [
                cut_features[idx_a, :5].astype(np.float64),
                structure_metadata[idx_a]["family_fractions"][:-1].astype(np.float64),
            ]
        )
        feature_vec_b = np.concatenate(
            [
                cut_features[idx_b, :5].astype(np.float64),
                structure_metadata[idx_b]["family_fractions"][:-1].astype(np.float64),
            ]
        )
        denom = (np.linalg.norm(feature_vec_a) * np.linalg.norm(feature_vec_b)) + 1e-12
        return float(np.dot(feature_vec_a, feature_vec_b) / denom)

    def _apply_structure_aware_selection(
        self,
        proposed_idxes,
        cuts,
        cut_features,
        structure_metadata,
        target_count,
    ):
        num_cuts = len(cuts)
        proposed_idxes = self._dedupe_preserve_order(proposed_idxes, num_cuts)
        if len(proposed_idxes) == 0:
            proposed_idxes = [0]

        base_scores = self._compute_structure_scores(cut_features, structure_metadata)
        if len(base_scores):
            score_min = float(np.min(base_scores))
            score_max = float(np.max(base_scores))
            if score_max - score_min > 1e-12:
                quality = (base_scores - score_min) / (score_max - score_min)
            else:
                quality = np.zeros_like(base_scores)
        else:
            quality = base_scores
        heuristic_tail = list(np.argsort(-base_scores))
        candidate_rank = self._dedupe_preserve_order(proposed_idxes + heuristic_tail, num_cuts)
        pool_size = min(
            len(candidate_rank),
            max(target_count, int(math.ceil(target_count * self.structure_pool_factor))),
        )
        expansion_pool = candidate_rank[:pool_size]
        policy_set = candidate_rank[:target_count]

        # F(S) is a nonnegative modular quality/prior term plus two monotone
        # submodular terms: concave-over-modular role coverage and facility
        # location over the expansion pool.  Greedy completion after fixed
        # policy anchors therefore retains the standard (1-1/e) guarantee for
        # the residual cardinality-constrained problem.
        family_matrix = np.asarray(
            [structure_metadata[idx]["family_fractions"] for idx in expansion_pool],
            dtype=np.float64,
        )
        demand = family_matrix.sum(axis=0)
        if demand.sum() > 1e-12:
            demand = demand / demand.sum()
        else:
            demand = np.full(family_matrix.shape[1], 1.0 / family_matrix.shape[1])

        # Compute all cosine similarities in one matrix multiplication.  The
        # old nested loop rebuilt two descriptors per pair and needlessly
        # extended every SCIP cut-selection callback.
        expansion_index = np.asarray(expansion_pool, dtype=np.int64)
        similarity_features = np.concatenate(
            [
                cut_features[expansion_index, :5].astype(np.float64),
                family_matrix[:, :-1],
            ],
            axis=1,
        )
        similarity_norms = np.linalg.norm(similarity_features, axis=1)
        similarity = (similarity_features @ similarity_features.T) / (
            np.outer(similarity_norms, similarity_norms) + 1e-12
        )
        similarity = np.clip(similarity, 0.0, 1.0)
        np.fill_diagonal(similarity, 1.0)

        pool_position = {idx: pos for pos, idx in enumerate(expansion_pool)}
        policy_rank = {idx: rank for rank, idx in enumerate(candidate_rank)}
        anchor_count = min(
            len(proposed_idxes),
            len(policy_set),
            max(1, int(math.ceil(target_count * self.structure_anchor_ratio))),
        )
        selected = list(policy_set[:anchor_count])
        selected_set = set(selected)
        coverage = np.zeros(family_matrix.shape[1], dtype=np.float64)
        represented = np.zeros(pool_size, dtype=np.float64)
        for idx in selected:
            pos = pool_position[idx]
            coverage += family_matrix[pos]
            represented = np.maximum(represented, similarity[:, pos])

        marginal_trace = []
        while len(selected) < target_count:
            best_idx = None
            best_score = -1e18
            best_components = None
            for idx in expansion_pool:
                if idx in selected_set:
                    continue
                pos = pool_position[idx]
                policy_prior = 1.0 - policy_rank[idx] / max(1, len(candidate_rank) - 1)
                modular_gain = (
                    self.structure_quality_weight * float(quality[idx])
                    + self.structure_policy_weight * policy_prior
                )
                coverage_gain = self.structure_coverage_weight * float(
                    np.dot(
                        demand,
                        np.sqrt(coverage + family_matrix[pos]) - np.sqrt(coverage),
                    )
                )
                representation_gain = self.structure_representation_weight * float(
                    np.mean(np.maximum(represented, similarity[:, pos]) - represented)
                )
                total_gain = modular_gain + coverage_gain + representation_gain
                if total_gain > best_score:
                    best_score = total_gain
                    best_idx = idx
                    best_components = {
                        "modular": modular_gain,
                        "role_coverage": coverage_gain,
                        "representativeness": representation_gain,
                    }
            if best_idx is None:
                break
            selected.append(best_idx)
            selected_set.add(best_idx)
            best_pos = pool_position[best_idx]
            coverage += family_matrix[best_pos]
            represented = np.maximum(represented, similarity[:, best_pos])
            marginal_trace.append(
                {
                    "candidate": int(best_idx),
                    "gain": float(best_score),
                    **best_components,
                }
            )

        if len(selected) == 0:
            selected = [0]
        selected = [int(idx) for idx in selected]
        return selected, {
            "enabled": True,
            "feature_mode": "role_submodular_rerank_v1",
            "policy_anchor_count": anchor_count,
            "candidate_pool_size": pool_size,
            "objective_weights": {
                "quality": self.structure_quality_weight,
                "policy": self.structure_policy_weight,
                "role_coverage": self.structure_coverage_weight,
                "representativeness": self.structure_representation_weight,
            },
            "policy_set_retained": len(set(selected).intersection(policy_set)),
            "role_coverage": coverage.tolist(),
            "marginal_trace": marginal_trace,
            "base_scores": base_scores.tolist(),
        }
    
    def cutselselect(self, cuts, forcedcuts, root, maxnselectedcuts):
        selector = (
            self._cutselselect_with_token
            if self.policy_type == 'with_token'
            else self._cutselselect
        )
        return self._safe_learned_cutsel_call(
            selector, cuts, forcedcuts, root, maxnselectedcuts
        )
    
    def _cutselselect(self, cuts, forcedcuts, root, maxnselectedcuts):
        '''first method called in each iteration in the main solving loop. '''
        # this method needs to be implemented by the user
        logger.log("cut selection policy without token!!!")
        logger.log(f"forcedcuts length: {len(forcedcuts)}")
        logger.log(f"len cuts: {len(cuts)}")
        num_cuts = len(cuts)
        # cur_lp_info = self._get_lp_info()
        # for k in cur_lp_info.keys():
        #     self.lp_info[k].append(cur_lp_info[k])
        if num_cuts <= 1:
            return {
                'cuts': cuts, # selected sorted cuts
                'nselectedcuts': max(0, min(num_cuts, int(maxnselectedcuts))), # num of selected cuts
                'result': SCIP_RESULT.SUCCESS
            }            
        candidate_indices = self._policy_candidate_indices(cuts)
        candidate_cuts = [cuts[int(idx)] for idx in candidate_indices]
        sel_cuts_num = self._target_cut_count(
            num_cuts,
            maxnselectedcuts,
            int(num_cuts * self.sel_cuts_percent),
        )
        sel_cuts_num = self._cap_selected_count(sel_cuts_num, len(candidate_cuts))
        if sel_cuts_num <= 0:
            return {
                'cuts': cuts,
                'nselectedcuts': 0,
                'result': SCIP_RESULT.SUCCESS
            }
        st_before_input = time.time()
        cuts_features, structure_metadata = self._extract_policy_features(candidate_cuts)
        et_feature_extractor = time.time()
        if self.mean_std is not None:
            # normalize cut features
            normalize_cut_features = self._normalize(cuts_features)
            input_cuts = torch.from_numpy(normalize_cut_features).to(self.device)
        else:
            input_cuts = torch.from_numpy(cuts_features).to(self.device)
        
        input_cuts = input_cuts.reshape(input_cuts.shape[0], 1, input_cuts.shape[1])
        st_end_input = time.time()
        # 只做选择动作的功能，不做计算梯度的功能
        with torch.no_grad():
            decode_len = sel_cuts_num if self.policy_type != 'with_token' else (len(candidate_cuts) + 1)
            _, input_idxs = self.policy(input_cuts.float(), decode_len, self.decode_type)
        st_end_inference = time.time()
        if not logger.is_compact_text_log():
            print(f"process input time: {st_end_input-st_before_input} s")
            print(f"input feature extractor time: {et_feature_extractor-st_before_input} s")
            print(f"input cpu data to gpu time: {st_end_input-et_feature_extractor} s")
            print(f"pointer net inference time: {st_end_inference - st_end_input} s")
        idxes = [input.cpu().detach().item() for input in input_idxs]
        rerank_start = time.time()
        true_idxes, structure_info = self._select_policy_indices(
            idxes,
            candidate_cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
        )
        rerank_end = time.time()
        self._record_phase_times(
            feature_extraction=et_feature_extractor - st_before_input,
            device_transfer=st_end_input - et_feature_extractor,
            policy_inference=st_end_inference - st_end_input,
            structure_rerank=rerank_end - rerank_start,
        )
        true_idxes = [int(candidate_indices[idx]) for idx in true_idxes]
        all_idxes = list(range(num_cuts))
        selected_set = set(true_idxes)
        not_sel_idxes = [idx for idx in all_idxes if idx not in selected_set]
        sorted_cuts = [cuts[idx] for idx in true_idxes]
        not_sel_cuts = [cuts[n_idx] for n_idx in not_sel_idxes]
        sorted_cuts.extend(not_sel_cuts)
        # debug
        # sorted_cuts = cuts
        # 只log 第一次cut 处的state 和 action
        if not self.data:
            self.data = {
                "state": cuts_features,
                # Train on the stochastic trajectory produced by the policy.
                # Structure-aware reranking is part of the environment transition.
                "action": idxes,
                "sel_cuts_num": len(idxes),
                "selected_action": true_idxes,
                "selected_cuts_num": len(true_idxes),
                "candidate_indices": candidate_indices.tolist(),
                "structure_info": structure_info,
            }
            # self.cuts_info = {
            #     "length_cuts": num_cuts,
            #     "length_forced_cuts": len(forcedcuts),
            #     "cut_features": cuts_features
            # }

        return {
            'cuts': sorted_cuts, # selected sorted cuts
            'nselectedcuts': len(true_idxes), # num of selected cuts
            'result': SCIP_RESULT.SUCCESS
        }

    def _cutselselect_with_token(self, cuts, forcedcuts, root, maxnselectedcuts):
        '''first method called in each iteration in the main solving loop. '''
        # this method needs to be implemented by the user
        logger.log("cut selection policy with token!!!")
        logger.log(f"forcedcuts length: {len(forcedcuts)}")
        logger.log(f"len cuts: {len(cuts)}")
        num_cuts = len(cuts)
        # cur_lp_info = self._get_lp_info()
        # for k in cur_lp_info.keys():
        #     self.lp_info[k].append(cur_lp_info[k])
        if num_cuts <= 1:
            return {
                'cuts': cuts, # selected sorted cuts
                'nselectedcuts': max(0, min(num_cuts, int(maxnselectedcuts))), # num of selected cuts
                'result': SCIP_RESULT.SUCCESS
            }            
        candidate_indices = self._policy_candidate_indices(cuts)
        candidate_cuts = [cuts[int(idx)] for idx in candidate_indices]
        max_sel_cuts_num = len(candidate_cuts) + 1
        if self.max_selected_cuts is not None and int(self.max_selected_cuts) > 0:
            # Only the capped prefix can be returned to SCIP.  Preserve one
            # additional step for the learned end token and skip the rest.
            max_sel_cuts_num = min(
                max_sel_cuts_num,
                int(self.max_selected_cuts) + 1,
            )
        st_before_input = time.time()
        cuts_features, structure_metadata = self._extract_policy_features(candidate_cuts)
        et_feature_extractor = time.time()
        if self.mean_std is not None:
            # normalize cut features
            normalize_cut_features = self._normalize(cuts_features)
            input_cuts = torch.from_numpy(normalize_cut_features).to(self.device)
        else:
            input_cuts = torch.from_numpy(cuts_features).to(self.device)
        
        input_cuts = input_cuts.reshape(input_cuts.shape[0], 1, input_cuts.shape[1])
        st_end_input = time.time()
        # 只做选择动作的功能，不做计算梯度的功能
        with torch.no_grad():
            _, input_idxs =  self.policy(input_cuts.float(), max_sel_cuts_num, self.decode_type) # (list of tensor, list of tensor)
        st_end_inference = time.time()
        if not logger.is_compact_text_log():
            print(f"process input time: {st_end_input-st_before_input} s")
            print(f"input feature extractor time: {et_feature_extractor-st_before_input} s")
            print(f"input cpu data to gpu time: {st_end_input-et_feature_extractor} s")
            print(f"pointer net inference time: {st_end_inference - st_end_input} s")

        idxes = [input.cpu().detach().item() for input in input_idxs]
        raw_sel_cuts_num = len(idxes)
        sel_cuts_num = self._capped_target_cut_count(
            num_cuts,
            maxnselectedcuts,
            raw_sel_cuts_num - 1,
        )
        sel_cuts_num = self._cap_selected_count(sel_cuts_num, len(candidate_cuts))
        if sel_cuts_num <= 0:
            return {
                'cuts': cuts,
                'nselectedcuts': 0,
                'result': SCIP_RESULT.SUCCESS
            }
        # select cuts 
        rerank_start = time.time()
        selected_local_idxes, structure_info = self._select_policy_indices(
            [idx for idx in idxes if idx != len(candidate_cuts)],
            candidate_cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
        )
        rerank_end = time.time()
        self._record_phase_times(
            feature_extraction=et_feature_extractor - st_before_input,
            device_transfer=st_end_input - et_feature_extractor,
            policy_inference=st_end_inference - st_end_input,
            structure_rerank=rerank_end - rerank_start,
        )
        true_idxes = [int(candidate_indices[idx]) for idx in selected_local_idxes]
        sorted_cuts = self._sort_all_cuts(cuts, true_idxes)

        if self.data and "structure_info" not in self.data:
            self.data["structure_info"] = structure_info
        if not self.data:
            self.data = {
                "state": cuts_features,
                # Keep the raw sampled trajectory, including the end token.
                "action": idxes,
                "sel_cuts_num": raw_sel_cuts_num,
                "selected_action": true_idxes,
                "selected_cuts_num": len(true_idxes),
                "target_sel_cuts_num": sel_cuts_num,
                "candidate_indices": candidate_indices.tolist(),
                "structure_info": structure_info,
            }

        return {
            'cuts': sorted_cuts, # selected sorted cuts
            'nselectedcuts': len(true_idxes), # num of selected cuts
            'result': SCIP_RESULT.SUCCESS
        }

    def _get_lp_info(self):
        lp_info = {}
        lp_info['lp_solution_value'] = self.scip_model.getLPObjVal()
        cols = self.scip_model.getLPColsData()
        col_solution_value = [col.getPrimsol() for col in cols if col.isIntegral()]
        lp_info['lp_solution_integer_var_value'] = [val for val in col_solution_value if val != 0.]

        return lp_info

    def get_data(self):
        return self.data

    def get_lp_info(self):
        return self.lp_info

    # def get_cuts_info(self):
    #     return self.cuts_info
        
    def free_problem(self):
        # The SCIP model is owned and freed by SCIPCutSelEnv.step().
        self.scip_model = None

class HierarchyCutSelectAgent(CutSelectAgent):
    def __init__(
        self,
        scip_model,
        pointer_net,
        cutsel_percent_policy,
        value_net,
        sel_cuts_percent,
        device,
        decode_type,
        mean_std,
        policy_type,
        max_candidates=512,
        max_selected_cuts=64,
        use_structure_rerank=None,
        structure_pool_factor=2.0,
        structure_anchor_ratio=0.25,
        structure_quality_weight=0.35,
        structure_policy_weight=0.20,
        structure_coverage_weight=0.25,
        structure_representation_weight=0.20,
    ):
        CutSelectAgent.__init__(
            self,
            scip_model,
            pointer_net,
            value_net,
            sel_cuts_percent,
            device,
            decode_type,
            mean_std,
            policy_type,
            max_candidates=max_candidates,
            max_selected_cuts=max_selected_cuts,
            use_structure_rerank=use_structure_rerank,
            structure_pool_factor=structure_pool_factor,
            structure_anchor_ratio=structure_anchor_ratio,
            structure_quality_weight=structure_quality_weight,
            structure_policy_weight=structure_policy_weight,
            structure_coverage_weight=structure_coverage_weight,
            structure_representation_weight=structure_representation_weight,
        )
        self.cutsel_percent_policy = cutsel_percent_policy
        self.high_level_data = {}

    def cutselselect(self, cuts, forcedcuts, root, maxnselectedcuts):
        return self._safe_learned_cutsel_call(
            self._cutselselect_hierarchy,
            cuts,
            forcedcuts,
            root,
            maxnselectedcuts,
        )

    def _cutselselect_hierarchy(self, cuts, forcedcuts, root, maxnselectedcuts):
        '''first method called in each iteration in the main solving loop. '''
        # this method needs to be implemented by the user
        logger.log(f"forcedcuts length: {len(forcedcuts)}")
        logger.log(f"len cuts: {len(cuts)}")
        num_cuts = len(cuts)
        # cur_lp_info = self._get_lp_info()
        # for k in cur_lp_info.keys():
        #     self.lp_info[k].append(cur_lp_info[k])
        if num_cuts <= 1:
            return {
                'cuts': cuts, # selected sorted cuts
                'nselectedcuts': max(0, min(num_cuts, int(maxnselectedcuts))), # num of selected cuts
                'result': SCIP_RESULT.SUCCESS
            }
        candidate_indices = self._policy_candidate_indices(cuts)
        candidate_cuts = [cuts[int(idx)] for idx in candidate_indices]

        st_before_input = time.time()

        # compute states
        cuts_features, structure_metadata = self._extract_policy_features(candidate_cuts)
        et_feature_extractor = time.time()
        # normalize states
        if self.mean_std is not None:
            # normalize cut features
            normalize_cut_features = self._normalize(cuts_features)
            input_cuts = torch.from_numpy(normalize_cut_features).to(self.device)
        else:
            input_cuts = torch.from_numpy(cuts_features).to(self.device)
        input_cuts = input_cuts.reshape(input_cuts.shape[0], 1, input_cuts.shape[1])

        st_end_input = time.time()

        # compute sel cuts percent
        with torch.no_grad():
            if self.decode_type in ['greedy', 'beam_search']:
                deterministic = True
            else:
                deterministic = False
            raw_sel_cuts_percent = self.cutsel_percent_policy.action(input_cuts.float(), deterministic=deterministic)
        st_end_highlevel_policy_inference = time.time()

        sel_cuts_percent = min(raw_sel_cuts_percent.item() * 0.5 + 0.5, self.sel_cuts_percent)
        sel_cuts_num = self._target_cut_count(
            num_cuts,
            maxnselectedcuts,
            int(num_cuts * sel_cuts_percent),
        )
        sel_cuts_num = self._cap_selected_count(sel_cuts_num, len(candidate_cuts))
        if sel_cuts_num <= 0:
            return {
                'cuts': cuts,
                'nselectedcuts': 0,
                'result': SCIP_RESULT.SUCCESS
            }
        # 只做选择动作的功能，不做计算梯度的功能
        with torch.no_grad():
            decode_len = sel_cuts_num
            _, input_idxs = self.policy(input_cuts.float(), decode_len, self.decode_type)
        st_end_pointer_net_inference = time.time()

        if not logger.is_compact_text_log():
            print(f"process input time: {st_end_input-st_before_input} s")
            print(f"input feature extractor time: {et_feature_extractor-st_before_input} s")
            print(f"input cpu data to gpu time: {st_end_input-et_feature_extractor} s")
            print(f"high level policy time: {st_end_highlevel_policy_inference-st_end_input} s")
            print(f"pointer net inference time: {st_end_pointer_net_inference - st_end_highlevel_policy_inference} s")

        idxes = [input.cpu().detach().item() for input in input_idxs]
        rerank_start = time.time()
        selected_local_idxes, structure_info = self._select_policy_indices(
            idxes,
            candidate_cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
        )
        rerank_end = time.time()
        self._record_phase_times(
            feature_extraction=et_feature_extractor - st_before_input,
            device_transfer=st_end_input - et_feature_extractor,
            policy_inference=st_end_pointer_net_inference - st_end_input,
            structure_rerank=rerank_end - rerank_start,
        )
        true_idxes = [int(candidate_indices[idx]) for idx in selected_local_idxes]
        sorted_cuts = self._sort_all_cuts(cuts, true_idxes)
        # debug
        # sorted_cuts = cuts
        # 只log 第一次cut 处的state 和 action
        if not self.data:
            self.data = {
                "state": cuts_features,
                # Keep the sampled low-level trajectory for policy-gradient replay.
                "action": idxes,
                "sel_cuts_num": len(idxes),
                "selected_action": true_idxes,
                "selected_cuts_num": len(true_idxes),
                "target_sel_cuts_num": sel_cuts_num,
                "candidate_indices": candidate_indices.tolist(),
                "structure_info": structure_info,
            }
        if not self.high_level_data:
            self.high_level_data = {
                "state": cuts_features,
                "action": raw_sel_cuts_percent.item(),
                "capped_action": sel_cuts_percent,
                "target_sel_cuts_num": sel_cuts_num,
            }

        return {
            'cuts': sorted_cuts, # selected sorted cuts
            'nselectedcuts': len(true_idxes), # num of selected cuts
            'result': SCIP_RESULT.SUCCESS
        }

    def get_high_level_data(self):
        return self.high_level_data


class HeuristicBeamCutSelectAgent(CutselBase):
    def __init__(
        self,
        scip_model,
        sel_cuts_percent,
        beam_size=3,
        redundancy_weight=0.15,
        max_candidates=256,
        max_selected_cuts=256,
        score_weights=None,
    ):
        super().__init__()
        self.scip_model = scip_model
        self.sel_cuts_percent = sel_cuts_percent
        self.beam_size = beam_size
        self.redundancy_weight = redundancy_weight
        self.max_candidates = max_candidates
        self.max_selected_cuts = max_selected_cuts
        self.score_weights = score_weights or {
            "obj_parallelism": 0.15,
            "efficacy": 0.35,
            "support_penalty": 0.10,
            "integral_support": 0.15,
            "violation": 0.25,
        }
        self.data = {}
        self._callback_calls = 0
        self._callback_time_seconds = 0.0
        self._callback_input_cuts = 0
        self._callback_max_input_cuts = 0
        self._callback_root_calls = 0
        self._callback_nonroot_calls = 0

    def _minmax(self, values):
        values = np.asarray(values, dtype=np.float64)
        if values.size == 0:
            return values
        vmin = values.min()
        vmax = values.max()
        if abs(vmax - vmin) <= 1e-12:
            return np.zeros_like(values)
        return (values - vmin) / (vmax - vmin)

    def _compute_base_scores(self, cut_features):
        obj_parallelism = self._minmax(cut_features[:, 0])
        efficacy = self._minmax(cut_features[:, 1])
        support = self._minmax(cut_features[:, 2])
        integral_support = self._minmax(cut_features[:, 3])
        violation = self._minmax(cut_features[:, 4])
        structured_ratio = self._minmax(1.0 - cut_features[:, 18])
        dominant_ratio = self._minmax(cut_features[:, 21])

        return (
            self.score_weights["obj_parallelism"] * obj_parallelism
            + self.score_weights["efficacy"] * efficacy
            - self.score_weights["support_penalty"] * support
            + self.score_weights["integral_support"] * integral_support
            + self.score_weights["violation"] * violation
            + 0.08 * structured_ratio
            + 0.05 * dominant_ratio
        )

    def _candidate_pool_indices(self, base_scores, target_count):
        raw_pool_size = max(self.beam_size * target_count * 2, target_count)
        if self.max_candidates is not None and self.max_candidates > 0:
            raw_pool_size = min(raw_pool_size, int(self.max_candidates))
        candidate_pool_size = min(len(base_scores), max(target_count, raw_pool_size))
        return np.argsort(-base_scores)[:candidate_pool_size]

    def _cheap_candidate_indices(self, cuts):
        """Apply the same efficacy-first budget used by learned selectors."""
        num_cuts = len(cuts)
        if self.max_candidates is None or int(self.max_candidates) <= 0:
            return np.arange(num_cuts, dtype=np.int64)
        limit = min(num_cuts, int(self.max_candidates))
        if limit >= num_cuts:
            return np.arange(num_cuts, dtype=np.int64)
        efficacy = np.fromiter(
            (float(self.scip_model.getCutEfficacy(cut)) for cut in cuts),
            dtype=np.float64,
            count=num_cuts,
        )
        candidate = np.argpartition(-efficacy, limit - 1)[:limit]
        return candidate[np.lexsort((candidate, -efficacy[candidate]))]

    def _compute_similarity(self, cut_features):
        core_features = np.concatenate(
            [cut_features[:, :5], cut_features[:, 13:18]],
            axis=1
        ).astype(np.float64)
        norms = np.linalg.norm(core_features, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        normalized = core_features / norms
        similarity = normalized @ normalized.T
        np.fill_diagonal(similarity, 0.0)
        return similarity

    def _beam_select(self, base_scores, similarity, target_count):
        candidate_pool = list(range(len(base_scores)))
        beam = [_BeamState(selected=tuple(), score=0.0)]

        for _ in range(target_count):
            next_beam = {}
            for state in beam:
                used = set(state.selected)
                for idx in candidate_pool:
                    if idx in used:
                        continue
                    if state.selected:
                        redundancy = max(similarity[idx, prev] for prev in state.selected)
                    else:
                        redundancy = 0.0
                    candidate = tuple(list(state.selected) + [int(idx)])
                    candidate_score = state.score + float(base_scores[idx]) - self.redundancy_weight * float(redundancy)
                    if candidate not in next_beam or candidate_score > next_beam[candidate]:
                        next_beam[candidate] = candidate_score
            if not next_beam:
                break
            ranked = sorted(
                (_BeamState(selected=key, score=val) for key, val in next_beam.items()),
                key=lambda item: item.score,
                reverse=True,
            )
            beam = ranked[:self.beam_size]

        if not beam:
            return [0]
        return list(beam[0].selected) if beam[0].selected else [0]

    def cutselselect(self, cuts, forcedcuts, root, maxnselectedcuts):
        callback_start = time.perf_counter()
        try:
            return self._cutselselect_impl(
                cuts, forcedcuts, root, maxnselectedcuts
            )
        finally:
            self._callback_calls += 1
            self._callback_time_seconds += time.perf_counter() - callback_start
            self._callback_input_cuts += len(cuts)
            self._callback_max_input_cuts = max(
                self._callback_max_input_cuts, len(cuts)
            )
            if bool(root):
                self._callback_root_calls += 1
            else:
                self._callback_nonroot_calls += 1

    def _cutselselect_impl(self, cuts, forcedcuts, root, maxnselectedcuts):
        logger.log("heuristic beam cut selection policy")
        logger.log(f"forcedcuts length: {len(forcedcuts)}")
        logger.log(f"len cuts: {len(cuts)}")
        num_cuts = len(cuts)
        if num_cuts <= 1:
            return {
                'cuts': cuts,
                'nselectedcuts': max(0, min(num_cuts, int(maxnselectedcuts))),
                'result': SCIP_RESULT.SUCCESS
            }

        limit = min(int(num_cuts), int(maxnselectedcuts))
        if limit <= 0:
            return {
                'cuts': cuts,
                'nselectedcuts': 0,
                'result': SCIP_RESULT.SUCCESS
            }
        sel_cuts_num = int(num_cuts * self.sel_cuts_percent)
        sel_cuts_num = max(sel_cuts_num, 2 if limit >= 2 else 1)
        sel_cuts_num = min(sel_cuts_num, limit)
        if self.max_selected_cuts is not None and self.max_selected_cuts > 0:
            sel_cuts_num = min(sel_cuts_num, int(self.max_selected_cuts))
        if self.max_candidates is not None and self.max_candidates > 0:
            sel_cuts_num = min(sel_cuts_num, int(self.max_candidates))

        candidate_indices = self._cheap_candidate_indices(cuts)
        candidate_cuts = [cuts[int(idx)] for idx in candidate_indices]
        cut_features = advanced_cut_feature_generator(
            self.scip_model,
            candidate_cuts,
        )
        base_scores = self._compute_base_scores(cut_features)
        candidate_pool = self._candidate_pool_indices(base_scores, sel_cuts_num)
        candidate_features = cut_features[candidate_pool]
        candidate_scores = base_scores[candidate_pool]
        similarity = self._compute_similarity(candidate_features)
        selected_local_idxes = self._beam_select(candidate_scores, similarity, min(sel_cuts_num, len(candidate_pool)))
        selected_candidate_idxes = [
            int(candidate_pool[idx])
            for idx in selected_local_idxes
        ]
        true_idxes = [
            int(candidate_indices[idx])
            for idx in selected_candidate_idxes
        ]

        all_idxes = list(range(num_cuts))
        not_sel_idxes = [idx for idx in all_idxes if idx not in set(true_idxes)]
        sorted_cuts = [cuts[idx] for idx in true_idxes]
        sorted_cuts.extend([cuts[idx] for idx in not_sel_idxes])

        if not self.data:
            self.data = {
                "state": cut_features,
                "action": selected_candidate_idxes,
                "selected_action": true_idxes,
                "candidate_indices": candidate_indices.tolist(),
                "sel_cuts_num": len(true_idxes),
                "candidate_pool_size": int(len(candidate_pool)),
                "base_scores": base_scores.tolist(),
            }

        return {
            'cuts': sorted_cuts,
            'nselectedcuts': len(true_idxes),
            'result': SCIP_RESULT.SUCCESS
        }

    def get_data(self):
        return self.data

    def get_telemetry(self):
        calls = int(self._callback_calls)
        total_time = float(self._callback_time_seconds)
        feature_summary = {}
        state = self.data.get("state") if isinstance(self.data, dict) else None
        selected_indices = self.data.get("action", []) if isinstance(self.data, dict) else []
        if (
            isinstance(state, np.ndarray)
            and state.ndim == 2
            and len(state)
            and selected_indices
        ):
            selected_features = state[np.asarray(selected_indices, dtype=np.int64)]
            feature_summary = {
                "selected_count": len(selected_indices),
                "mean_obj_parallelism": float(np.mean(selected_features[:, 0])),
                "mean_efficacy": float(np.mean(selected_features[:, 1])),
                "mean_support": float(np.mean(selected_features[:, 2])),
                "max_support": float(np.max(selected_features[:, 2])),
                "mean_integral_support": float(np.mean(selected_features[:, 3])),
                "mean_violation": float(np.mean(selected_features[:, 4])),
            }
        return {
            "callback_calls": calls,
            "callback_time_seconds": total_time,
            "mean_callback_time_seconds": total_time / calls if calls else 0.0,
            "mean_input_cuts": self._callback_input_cuts / calls if calls else 0.0,
            "max_input_cuts": int(self._callback_max_input_cuts),
            "root_calls": int(self._callback_root_calls),
            "nonroot_calls": int(self._callback_nonroot_calls),
            "effective_max_candidates": self.max_candidates,
            "effective_max_selected_cuts": self.max_selected_cuts,
            "decode_type": "heuristic_beam",
            "use_structure_rerank": True,
            "selected_feature_summary": feature_summary,
        }

    def get_lp_info(self):
        return {}

    def free_problem(self):
        # The SCIP model is owned and freed by SCIPCutSelEnv.step().
        self.scip_model = None

## testing code
# if __name__ == '__main__':
#     from environments import SCIPCutSelEnv
#     from pointer_net import PointerNetwork
#     instance_file_path = "/datasets/learning_to_cut/dataset/data_nips_competition/instances/2_load_balancing/train/train_mps"
#     seed = 1
#     env_kwargs = {
#         "scip_time_limit": 30,
#         "single_instance_file": "all",
#         "presolving": True,
#         "separating": True,
#         "conflict": True, 
#         "heuristics": True,
#         "max_rounds_root": 1
#     }
#     env = SCIPCutSelEnv(
#         instance_file_path,
#         seed,
#         **env_kwargs
#     )  

#     device = torch.device('cuda:1')
#     pointer_net = PointerNetwork(
#         embedding_dim=13,
#         hidden_dim=128,
#         n_glimpses=1,
#         tanh_exploration=5,
#         use_tanh=True,
#         beam_size=1,
#         use_cuda=torch.cuda.is_available()
#     ).to(device)

#     for _ in range(10):
#         env.reset()
#         cutsel_agent = CutSelectAgent(
#             env.m,
#             pointer_net,
#             None,
#             0.5,
#             device,
#             'stochastic',
#             None,
#             'no_token'
#         )
#         _ = env.step(cutsel_agent)
