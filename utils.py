import math 
import time

import numpy as np
import random 
import torch
import os
import gtimer as gt 
import datetime

from os.path import join
import os.path as osp
from collections import OrderedDict
from numbers import Number

from logger import logger
from global_const import *
from path_utils import project_path

_LOCAL_LOG_DIR = str(project_path('data'))

################
# Cut feature constructor utilities.  Structural features deliberately use
# SCIP variable metadata, not application-specific variable names, so the same
# extractor applies to Petri scheduling, MIPLIB, and arbitrary user MILPs.

def _get_integral_support(cut, model):
    nonz_coeff_cut = cut.getNNonz()
    # cols = cut.getCols()
    # cols_cur_lp = [col for col in cols if col.getLPPos() != -1]
    # nonz_coeff_integer = sum([1 for col in cols_cur_lp if col.isIntegral()])
    nonz_coeff_integer = model.getRowNumIntCols(cut)
    
    return float(nonz_coeff_integer / (nonz_coeff_cut + 1e-3))

def _get_cut_coeff_stats(cut):
    coeffs = cut.getVals()
    
    return np.mean(coeffs), np.max(coeffs), np.min(coeffs), np.std(coeffs)

def _get_obj_coeff_stats(scip_cutsel_env):
    vars = scip_cutsel_env.getVars()
    obj_coeffs = [var.getObj() for var in vars]
    
    return np.mean(obj_coeffs), np.max(obj_coeffs), np.min(obj_coeffs), np.std(obj_coeffs)

def compute_normalized_violation_scores(cut):
    lhs = cut.getLhs()
    rhs = cut.getRhs()
    cons = cut.getConstant()
    coeffs = cut.getVals()
    cols = cut.getCols()
    col_solution_value = [col.getPrimsol() for col in cols]
    lp_cut_value = np.dot(coeffs, col_solution_value) + cons
    if lp_cut_value < lhs:
        violation = (lhs - lp_cut_value) / abs(lhs+1e-1+1e-2)
        # violation = (lhs - lp_cut_value)
    elif lp_cut_value > rhs:
        violation = (lp_cut_value - rhs) / abs(rhs+1e-1+1e-2)
        # violation = (lp_cut_value - rhs)
    else:
        violation = 0.

    violation = max(0, violation)
    return violation

def _get_var_from_col(col):
    try:
        return col.getVar() if hasattr(col, "getVar") else None
    except Exception:
        return None


def _normalise_var_type(col, var):
    """Return a stable SCIP variable-type label across PySCIPOpt versions."""
    if var is not None:
        for attr_name in ("vtype", "getType"):
            attr = getattr(var, attr_name, None)
            if attr is None:
                continue
            try:
                value = attr() if callable(attr) else attr
                label = str(value).upper().replace("SCIP_VARTYPE.", "")
                if "BINARY" in label:
                    return "BINARY"
                if "IMPL" in label:
                    return "IMPLINT"
                if "INTEGER" in label:
                    return "INTEGER"
                if "CONTINUOUS" in label:
                    return "CONTINUOUS"
            except Exception:
                pass
    try:
        if hasattr(col, "isIntegral") and col.isIntegral():
            return "INTEGER"
    except Exception:
        pass
    return "UNKNOWN"


def _safe_var_obj(var):
    try:
        return float(var.getObj()) if var is not None else 0.0
    except Exception:
        return 0.0


def _safe_var_bounds(var):
    if var is None:
        return None, None
    try:
        return float(var.getLbGlobal()), float(var.getUbGlobal())
    except Exception:
        try:
            return float(var.getLbLocal()), float(var.getUbLocal())
        except Exception:
            return None, None


def _is_finite_scip_value(value):
    # SCIP commonly represents infinity by a finite sentinel near 1e20.
    return value is not None and np.isfinite(value) and abs(value) < 1e19


def _classify_mip_var_family(col):
    var = _get_var_from_col(col)
    var_type = _normalise_var_type(col, var)
    if var_type == "BINARY":
        return "binary_decision", var
    if var_type in {"INTEGER", "IMPLINT"}:
        return "general_integer", var
    if var_type == "CONTINUOUS":
        if abs(_safe_var_obj(var)) > 1e-12:
            return "continuous_objective", var
        return "continuous_auxiliary", var
    return "other", var

def _compute_family_entropy(probabilities):
    probs = np.asarray(probabilities, dtype=np.float64)
    probs = probs[probs > 1e-12]
    if probs.size <= 1:
        return 0.0
    entropy = -(probs * np.log(probs)).sum()
    return float(entropy / np.log(len(MIP_VAR_FAMILY_NAMES)))

def _extract_structure_profile(cut):
    cols = cut.getCols()
    coeffs = np.asarray(cut.getVals(), dtype=np.float64)
    abs_coeffs = np.abs(coeffs)
    total_abs_coeff = float(abs_coeffs.sum()) + 1e-12

    family_mass = OrderedDict((name, 0.0) for name in MIP_VAR_FAMILY_NAMES)
    bounded_mass = 0.0
    positive_mass = 0.0

    for col, raw_coeff, abs_coeff in zip(cols, coeffs, abs_coeffs):
        family_name, var = _classify_mip_var_family(col)
        mass = float(abs_coeff)
        family_mass[family_name] += mass
        lb, ub = _safe_var_bounds(var)
        if _is_finite_scip_value(lb) and _is_finite_scip_value(ub):
            bounded_mass += mass
        if raw_coeff > 0:
            positive_mass += mass

    family_fractions = np.array(
        [family_mass[name] / total_abs_coeff for name in MIP_VAR_FAMILY_NAMES],
        dtype=np.float64,
    )
    structural_fractions = family_fractions[:-1]
    if structural_fractions.sum() > 1e-12:
        dominant_family_index = int(np.argmax(structural_fractions))
        dominant_family_ratio = float(structural_fractions[dominant_family_index])
    else:
        dominant_family_index = len(MIP_VAR_FAMILY_NAMES) - 1
        dominant_family_ratio = float(family_fractions[-1])
    discrete_mass = float(family_fractions[0] + family_fractions[1])
    continuous_mass = float(family_fractions[2] + family_fractions[3])
    # Four times the product maps a balanced 50/50 discrete--continuous cut
    # to one and a single-role cut to zero.  Unlike two complementary sign
    # fractions, this adds non-redundant interaction information.
    discrete_continuous_coupling = float(4.0 * discrete_mass * continuous_mass)

    return {
        "family_fractions": family_fractions,
        "dominant_family": MIP_VAR_FAMILY_NAMES[dominant_family_index],
        "dominant_family_index": dominant_family_index,
        "bounded_ratio": float(bounded_mass / total_abs_coeff),
        "positive_ratio": float(positive_mass / total_abs_coeff),
        "discrete_continuous_coupling": discrete_continuous_coupling,
        "dominant_family_ratio": dominant_family_ratio,
        "family_entropy": _compute_family_entropy(family_fractions),
        "structured_ratio": float(1.0 - family_fractions[-1]),
    }

def _build_structure_feature_tail(profile):
    family_fractions = profile["family_fractions"]
    return [
        float(family_fractions[0]),
        float(family_fractions[1]),
        float(family_fractions[2]),
        float(family_fractions[3]),
        float(family_fractions[4]),
        float(profile["bounded_ratio"]),
        float(profile["positive_ratio"]),
        float(profile["discrete_continuous_coupling"]),
        float(profile["dominant_family_ratio"]),
        float(profile["family_entropy"]),
    ]

def get_structure_family_names():
    return list(MIP_VAR_FAMILY_NAMES)

def generic_advanced_cut_feature_generator(scip_cutsel_env, cuts):
    """Return the 13 generic cut features used by the HEM baseline.

    This intentionally excludes all variable-role structure features.
    Keeping this extractor separate from ``advanced_cut_feature_generator``
    makes the HEM comparison auditable: a 13-dimensional checkpoint cannot
    silently consume the proposed 10-dimensional structural feature tail.
    """
    cut_features = np.zeros((len(cuts), GENERIC_ADVANCED_CUT_FEATURE_DIM))
    mean_coeff_obj, max_coeff_obj, min_coeff_obj, std_coeff_obj = _get_obj_coeff_stats(
        scip_cutsel_env
    )
    for i, cut in enumerate(cuts):
        nonz_coeff_cut = cut.getNNonz()
        num_vars = scip_cutsel_env.getNVars()
        cut_features[i, :] = np.asarray(
            [
                scip_cutsel_env.getRowObjParallelism(cut),
                scip_cutsel_env.getCutEfficacy(cut),
                float(nonz_coeff_cut / (num_vars + 1e-3)),
                _get_integral_support(cut, scip_cutsel_env),
                compute_normalized_violation_scores(cut),
                *_get_cut_coeff_stats(cut),
                mean_coeff_obj,
                max_coeff_obj,
                min_coeff_obj,
                std_coeff_obj,
            ],
            dtype=np.float64,
        )
    return cut_features

def advanced_cut_feature_generator(scip_cutsel_env, cuts, return_metadata=False):
    # add normalized violation feature and structure-aware features
    cut_features = np.zeros((len(cuts), AdvancedCutFeatureNum))
    mean_coeff_obj, max_coeff_obj, min_coeff_obj, std_coeff_obj = _get_obj_coeff_stats(scip_cutsel_env)
    structure_metadata = []
    for i, cut in enumerate(cuts):
        obj_parall = scip_cutsel_env.getRowObjParallelism(cut)
        eff = scip_cutsel_env.getCutEfficacy(cut)
        nonz_coeff_cut = cut.getNNonz()
        num_vars = scip_cutsel_env.getNVars()
        support = float(nonz_coeff_cut / (num_vars + 1e-3))
        integral_support = _get_integral_support(cut, scip_cutsel_env)
        normalized_violation = compute_normalized_violation_scores(cut)

        mean_coeff_cut, max_coeff_cut, min_coeff_cut, std_coeff_cut = _get_cut_coeff_stats(cut)
        structure_profile = _extract_structure_profile(cut)
        structure_tail = _build_structure_feature_tail(structure_profile)

        cut_feature = [
            obj_parall,
            eff,
            support,
            integral_support,
            normalized_violation,
            mean_coeff_cut,
            max_coeff_cut,
            min_coeff_cut,
            std_coeff_cut,
            mean_coeff_obj,
            max_coeff_obj,
            min_coeff_obj,
            std_coeff_obj,
            *structure_tail,
        ]
        cut_features[i, :] = np.array(cut_feature)
        structure_metadata.append(structure_profile)
    if return_metadata:
        return cut_features, structure_metadata
    return cut_features

def cut_feature_generator(scip_cutsel_env, cuts, return_metadata=False):
    """
    Input: scip_model static information + cuts dynamic information
    Output: the sequence of cut features
    """
    cut_features = np.zeros((len(cuts), CutFeatureNum))
    # scip_cutsel_env.getLPSol()
    # best_primal_sol = scip_cutsel_env.getBestSol()
    mean_coeff_obj, max_coeff_obj, min_coeff_obj, std_coeff_obj = _get_obj_coeff_stats(scip_cutsel_env)
    structure_metadata = []
    for i, cut in enumerate(cuts):
        obj_parall = scip_cutsel_env.getRowObjParallelism(cut)
        eff = scip_cutsel_env.getCutEfficacy(cut)
        # directed_cut_off_distance = scip_cutsel_env.getCutLPSolCutoffDistance(cut, best_primal_sol)
        # nonz_coeff_cut = cut.getNLPNonz()
        nonz_coeff_cut = cut.getNNonz()
        num_vars = scip_cutsel_env.getNVars()
        support = float(nonz_coeff_cut / (num_vars + 1e-3))
        integral_support = _get_integral_support(cut, scip_cutsel_env)
        mean_coeff_cut, max_coeff_cut, min_coeff_cut, std_coeff_cut = _get_cut_coeff_stats(cut)
        structure_profile = _extract_structure_profile(cut)
        structure_tail = _build_structure_feature_tail(structure_profile)
        
        cut_feature = [
            obj_parall,
            eff,
            support,
            integral_support,
            mean_coeff_cut,
            max_coeff_cut,
            min_coeff_cut,
            std_coeff_cut,
            mean_coeff_obj,
            max_coeff_obj,
            min_coeff_obj,
            std_coeff_obj,
            *structure_tail,
        ]
        cut_features[i, :] = np.array(cut_feature)
        structure_metadata.append(structure_profile)
    if return_metadata:
        return cut_features, structure_metadata
    return cut_features
################

################
# set seed utils
def set_global_seed(seed=None):
    if seed is None:
        seed = int(time.time())%4096
    np.random.seed(seed)    
    random.seed(seed)    
    torch.manual_seed(seed) #cpu    
    torch.cuda.manual_seed_all(seed)  #并行gpu    
    # torch.backends.cudnn.deterministic = True  #cpu/gpu结果一致    
    # torch.backends.cudnn.benchmark = True 
    return seed
################

################
# logger utils
def create_exp_name(exp_prefix, exp_id=0, seed=0):
    """
    Create a semi-unique experiment name that has a timestamp
    :param exp_prefix:
    :param exp_id:
    :return:
    """
    now = datetime.datetime.now().astimezone()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return "%s_%s_%04d--s-%d" % (exp_prefix, timestamp, exp_id, seed)

def create_log_dir(
        exp_prefix,
        exp_id=0,
        seed=0,
        base_log_dir=None,
):
    """
    Creates and returns a unique log directory.
    :param exp_prefix: All experiments with this prefix will have log directories be under this directory.
    :param exp_id: The number of the specific experiment run within this experiment.
    :param base_log_dir: The directory where all log should be saved.
    :return:
    """
    exp_name = create_exp_name(exp_prefix, exp_id, seed)

    if base_log_dir is None:
        base_log_dir = _LOCAL_LOG_DIR

    log_dir = join(base_log_dir, exp_prefix, exp_name)

    if osp.exists(log_dir):
        logger.log("WARNING: Log directory already exists {}".format(log_dir))
    os.makedirs(log_dir, exist_ok=True)

    return log_dir

def setup_logger(
        exp_prefix="default",
        variant=None,
        text_log_file="debug.log",
        variant_log_file="variant.json",
        tabular_log_file="progress.csv",
        snapshot_mode="last",
        snapshot_gap=1,
        log_tabular_only=False,
        compact_text_log=False,
        text_log_max_mb=0,
        text_log_backup_count=2,
        compact_log_patterns=None,
        log_dir=None,
        script_name=None,
        **create_log_dir_kwargs
):
    """
    Set up logger to have some reasonable default settings.
    Will save log output to

        base_log_dir/exp_prefix/exp_name.

    exp_name will be auto-generated to be unique.
    If log_dir is specified, then that directory is used as the output dir.

    :param exp_prefix: The sub-directory for this specific experiment.
    :param variant: 实验参数字典
    :param text_log_file:
    :param variant_log_file:
    :param tabular_log_file:
    :param snapshot_mode:
    :param log_tabular_only:
    :param snapshot_gap:
    :param log_dir:
    :param script_name: If set, save the script name to this.
    :return:
    """

    first_time = log_dir is None
    if first_time:
        log_dir = create_log_dir(exp_prefix, **create_log_dir_kwargs)

    logger.configure_text_logging(
        compact=compact_text_log,
        max_mb=text_log_max_mb,
        backup_count=text_log_backup_count,
        keep_patterns=compact_log_patterns,
    )

    if variant is not None:
        logger.log("Variant:")
        # logger.log(json.dumps(dict_to_safe_json(variant), indent=2))
        variant_log_path = join(log_dir, variant_log_file)
        logger.log_variant(variant_log_path, variant)

    tabular_log_path = join(log_dir, tabular_log_file)
    text_log_path = join(log_dir, text_log_file)
    logger.add_text_output(text_log_path)

    if first_time:
        logger.add_tabular_output(tabular_log_path)

    else:
        logger._add_output(tabular_log_path, logger._tabular_outputs, logger._tabular_fds, mode='a')
        for tabular_fd in logger._tabular_fds:
            logger._tabular_header_written.add(tabular_fd)

    logger.set_snapshot_dir(log_dir)
    logger.set_snapshot_mode(snapshot_mode)
    logger.set_snapshot_gap(snapshot_gap)
    logger.set_log_tabular_only(log_tabular_only)
    exp_name = log_dir.split("/")[-1]
    logger.push_prefix("[%s] " % exp_name)

    if script_name is not None:
        with open(join(log_dir, "script_name.txt"), "w") as f:
            f.write(script_name)
    return log_dir

def create_stats_ordered_dict(
        name,
        data,
        stat_prefix=None,
        always_show_all_stats=True,
        exclude_max_min=False,
):
    if stat_prefix is not None:
        name = "{}{}".format(stat_prefix, name)
    if isinstance(data, Number):
        return OrderedDict({name: data})

    if len(data) == 0:
        return OrderedDict()

    if isinstance(data, tuple):
        ordered_dict = OrderedDict()
        for number, d in enumerate(data):
            sub_dict = create_stats_ordered_dict(
                "{0}_{1}".format(name, number),
                d,
            )
            ordered_dict.update(sub_dict)
        return ordered_dict

    if isinstance(data, list):
        try:
            iter(data[0])
        except TypeError:
            pass
        else:
            data = np.concatenate(data)

    if (isinstance(data, np.ndarray) and data.size == 1
            and not always_show_all_stats):
        return OrderedDict({name: float(data)})

    stats = OrderedDict([
        (name + ' Mean', np.mean(data)),
        (name + ' Std', np.std(data)),
    ])
    if not exclude_max_min:
        stats[name + ' Max'] = np.max(data)
        stats[name + ' Min'] = np.min(data)
    return stats
################

# get average weight of multiple models
def get_average_models(models_state_dict):
    recorded_reward_types = {
        state_dict.get('reward_type')
        for state_dict in models_state_dict
        if state_dict.get('reward_type') is not None
    }
    missing_reward_metadata = sum(
        state_dict.get('reward_type') is None
        for state_dict in models_state_dict
    )
    if len(recorded_reward_types) > 1:
        raise ValueError(
            "Cannot average checkpoints trained with different reward types: "
            f"{sorted(recorded_reward_types)}"
        )
    if recorded_reward_types and missing_reward_metadata:
        raise ValueError(
            "Cannot average reward-tagged checkpoints with legacy checkpoints "
            "whose reward_type is unknown."
        )
    average_model_state_dict = OrderedDict()
    for key in models_state_dict[0].keys():
        if 'net' in key:
            # pointer_net and cut_percent_policy
            average_model_state_dict[key] = OrderedDict()
            for model_key in models_state_dict[0][key].keys():
                weight_sum = 0
                for i in range(len(models_state_dict)):
                    weight_sum += models_state_dict[i][key][model_key]
                average_model_state_dict[key][model_key] = weight_sum / len(models_state_dict)
        else:
            # w_sum = 0
            # for i in range(len(models_state_dict)):
            #     w_sum += models_state_dict[i][key] 
            # average_model_state_dict[key] = w_sum / len(models_state_dict)
            average_model_state_dict[key] = models_state_dict[-1][key]
    return average_model_state_dict

# if __name__ == '__main__':
#     from ipdb import set_trace
#     data_base_path = "/datasets/code_run_experiments/code_220422_norstate_rewardscale_valid/data/parallel_reinforce_with_baseline_fix_logprobs_clamp_logp_all_anonymous/parallel_reinforce_with_baseline_fix_logprobs_clamp_logp_all_anonymous_2022_04_22_19_44_44_0000--s-1324"
#     test_model =  ["itr_70.pkl", "itr_112.pkl", "itr_140.pkl"]
#     models_state_dict = [torch.load(os.path.join(data_base_path, model_file)) for model_file in test_model]

#     state_dict = get_average_models(models_state_dict)
#     set_trace()
