GENERIC_CUT_FEATURE_DIM = 12
GENERIC_ADVANCED_CUT_FEATURE_DIM = 13
STRUCTURE_AWARE_EXTRA_DIM = 10
GENERIC_CUT_FEATURE_SCHEMA = "generic_cut13_v1"
STRUCTURE_AWARE_CUT_FEATURE_SCHEMA = "universal_mip_role23_v2"
STRUCTURE_AWARE_POSTPROCESSOR_SCHEMA = "role_submodular_v1"

CutFeatureNum = GENERIC_CUT_FEATURE_DIM + STRUCTURE_AWARE_EXTRA_DIM
AdvancedCutFeatureNum = GENERIC_ADVANCED_CUT_FEATURE_DIM + STRUCTURE_AWARE_EXTRA_DIM

MIP_VAR_FAMILY_NAMES = [
    "binary_decision",
    "general_integer",
    "continuous_objective",
    "continuous_auxiliary",
    "other",
]

# Backward import compatibility only.  The feature extractor no longer uses
# Petri variable names or formulation-specific prefixes.
PETRI_VAR_FAMILY_NAMES = MIP_VAR_FAMILY_NAMES


def cut_feature_schema_for_dim(feature_dim):
    if int(feature_dim) == GENERIC_ADVANCED_CUT_FEATURE_DIM:
        return GENERIC_CUT_FEATURE_SCHEMA
    if int(feature_dim) == AdvancedCutFeatureNum:
        return STRUCTURE_AWARE_CUT_FEATURE_SCHEMA
    return "unknown_{}d".format(int(feature_dim))


def validate_checkpoint_feature_schema(checkpoint, feature_dim, checkpoint_path="checkpoint"):
    """Prevent old name-based 23D weights from silently using the new schema."""
    expected = cut_feature_schema_for_dim(feature_dim)
    actual = checkpoint.get("cut_feature_schema")
    if int(feature_dim) == AdvancedCutFeatureNum and actual != expected:
        raise ValueError(
            "{} uses cut_feature_schema={!r}, expected {!r}. The universal "
            "23D feature semantics changed; retrain the proposed model instead "
            "of reusing a legacy 23D checkpoint.".format(
                checkpoint_path, actual, expected
            )
        )
    if actual is not None and actual != expected:
        raise ValueError(
            "{} uses cut_feature_schema={!r}, expected {!r}.".format(
                checkpoint_path, actual, expected
            )
        )


def cut_postprocessor_schema_for_dim(feature_dim, use_structure_rerank=None):
    if int(feature_dim) == AdvancedCutFeatureNum and use_structure_rerank is not False:
        return STRUCTURE_AWARE_POSTPROCESSOR_SCHEMA
    return "none"


def validate_checkpoint_postprocessor_schema(
    checkpoint,
    feature_dim,
    checkpoint_path="checkpoint",
    expected_postprocessor=None,
):
    expected = (
        cut_postprocessor_schema_for_dim(feature_dim)
        if expected_postprocessor is None
        else str(expected_postprocessor)
    )
    actual = checkpoint.get("cut_postprocessor_schema")
    if expected == "none" and actual in {None, "none"}:
        return
    if actual != expected:
        raise ValueError(
            "{} uses cut_postprocessor_schema={!r}, expected {!r}. "
            "Retrain the checkpoint with the current selector; postprocessor "
            "semantics are part of the learned environment transition.".format(
                checkpoint_path, actual, expected
            )
        )
