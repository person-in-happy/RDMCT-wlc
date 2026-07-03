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
        # self.cuts_info ={}
        self.lp_info = {
            "lp_solution_value": [],
            "lp_solution_integer_var_value": []
        }
        self.mean_std = mean_std

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
        family_names = get_structure_family_names()
        proposed_idxes = self._dedupe_preserve_order(proposed_idxes, num_cuts)
        if len(proposed_idxes) == 0:
            proposed_idxes = [0]

        base_scores = self._compute_structure_scores(cut_features, structure_metadata)
        heuristic_tail = list(np.argsort(-base_scores))
        candidate_rank = self._dedupe_preserve_order(proposed_idxes + heuristic_tail, num_cuts)
        quota, active_families = self._compute_family_quota(candidate_rank, structure_metadata, target_count)

        if not quota:
            selected = candidate_rank[:target_count]
            if len(selected) == 0:
                selected = [0]
            return selected, {
                "family_quota": {},
                "family_counts": {},
                "base_scores": base_scores.tolist(),
            }

        selected = []
        selected_set = set()
        family_counts = {family_name: 0 for family_name in active_families}

        for family_name in sorted(active_families, key=lambda name: quota.get(name, 0), reverse=True):
            need = quota.get(family_name, 0)
            if need <= 0:
                continue
            family_candidates = [
                idx for idx in candidate_rank
                if idx not in selected_set and structure_metadata[idx]["dominant_family"] == family_name
            ]
            if len(family_candidates) < need:
                family_index = family_names.index(family_name)
                family_candidates.extend(
                    idx for idx in candidate_rank
                    if idx not in selected_set
                    and idx not in family_candidates
                    and structure_metadata[idx]["family_fractions"][family_index] >= 0.25
                )
            for idx in family_candidates[:need]:
                selected.append(idx)
                selected_set.add(idx)
                family_counts[family_name] += 1
                if len(selected) >= target_count:
                    break
            if len(selected) >= target_count:
                break

        while len(selected) < target_count:
            best_idx = None
            best_score = -1e18
            for idx in candidate_rank:
                if idx in selected_set:
                    continue
                family_name = structure_metadata[idx]["dominant_family"]
                diversity_penalty = 0.0
                if selected:
                    diversity_penalty = max(
                        self._structure_similarity(idx, prev_idx, cut_features, structure_metadata)
                        for prev_idx in selected
                    )
                quota_penalty = 0.0
                if family_name in family_counts and family_counts[family_name] >= quota.get(family_name, 0):
                    quota_penalty = 0.08 * (family_counts[family_name] - quota.get(family_name, 0) + 1)
                score = float(base_scores[idx]) - 0.12 * diversity_penalty - quota_penalty
                if score > best_score:
                    best_score = score
                    best_idx = idx
            if best_idx is None:
                break
            selected.append(best_idx)
            selected_set.add(best_idx)
            dominant_family = structure_metadata[best_idx]["dominant_family"]
            if dominant_family in family_counts:
                family_counts[dominant_family] += 1

        if len(selected) == 0:
            selected = [0]
        return selected[:target_count], {
            "family_quota": quota,
            "family_counts": family_counts,
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
        cuts_features, structure_metadata = advanced_cut_feature_generator(
            self.scip_model,
            candidate_cuts,
            return_metadata=True,
        )
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
        print(f"process input time: {st_end_input-st_before_input} s")
        print(f"input feature extractor time: {et_feature_extractor-st_before_input} s")
        print(f"input cpu data to gpu time: {st_end_input-et_feature_extractor} s")
        print(f"pointer net inference time: {st_end_inference - st_end_input} s")
        idxes = [input.cpu().detach().item() for input in input_idxs]
        true_idxes, structure_info = self._apply_structure_aware_selection(
            idxes,
            cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
        )
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
        st_before_input = time.time()
        cuts_features, structure_metadata = advanced_cut_feature_generator(
            self.scip_model,
            candidate_cuts,
            return_metadata=True,
        )
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
        selected_local_idxes, structure_info = self._apply_structure_aware_selection(
            [idx for idx in idxes if idx != len(candidate_cuts)],
            candidate_cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
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
        policy_type
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
            policy_type
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
        cuts_features, structure_metadata = advanced_cut_feature_generator(
            self.scip_model,
            candidate_cuts,
            return_metadata=True,
        )
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

        print(f"process input time: {st_end_input-st_before_input} s")
        print(f"input feature extractor time: {et_feature_extractor-st_before_input} s")
        print(f"input cpu data to gpu time: {st_end_input-et_feature_extractor} s")
        print(f"high level policy time: {st_end_highlevel_policy_inference-st_end_input} s")
        print(f"pointer net inference time: {st_end_pointer_net_inference - st_end_highlevel_policy_inference} s")

        idxes = [input.cpu().detach().item() for input in input_idxs]
        selected_local_idxes, structure_info = self._apply_structure_aware_selection(
            idxes,
            candidate_cuts,
            cuts_features,
            structure_metadata,
            sel_cuts_num,
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

        cut_features = advanced_cut_feature_generator(self.scip_model, cuts)
        base_scores = self._compute_base_scores(cut_features)
        candidate_pool = self._candidate_pool_indices(base_scores, sel_cuts_num)
        candidate_features = cut_features[candidate_pool]
        candidate_scores = base_scores[candidate_pool]
        similarity = self._compute_similarity(candidate_features)
        selected_local_idxes = self._beam_select(candidate_scores, similarity, min(sel_cuts_num, len(candidate_pool)))
        true_idxes = [int(candidate_pool[idx]) for idx in selected_local_idxes]

        all_idxes = list(range(num_cuts))
        not_sel_idxes = [idx for idx in all_idxes if idx not in set(true_idxes)]
        sorted_cuts = [cuts[idx] for idx in true_idxes]
        sorted_cuts.extend([cuts[idx] for idx in not_sel_idxes])

        if not self.data:
            self.data = {
                "state": cut_features,
                "action": true_idxes,
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
