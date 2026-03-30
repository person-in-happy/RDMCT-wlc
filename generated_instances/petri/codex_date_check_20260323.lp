\ SCIP STATISTICS
\   Problem name     : dual_source_rotary_cluster_shared_pm
\   Variables        : 73 (46 binary, 0 integer, 0 implicit integer, 27 continuous)
\   Constraints      : 158
Minimize
 Obj: +1 c_max
Subject to
 full_pair_assign_once_2: +1 assign_full_2_1_1 +1 assign_full_2_1_2 +1 assign_full_2_2_1 +1 assign_full_2_2_2
  = +1
 full_pair_assign_once_4: +1 assign_full_4_1_1 +1 assign_full_4_1_2 +1 assign_full_4_2_1 +1 assign_full_4_2_2
  = +1
 mix_pair_assign_once_1: +1 assign_mix_1_1_1 +1 assign_mix_1_1_2 +1 assign_mix_1_2_1 +1 assign_mix_1_2_2
  = +1
 mix_pair_assign_once_3: +1 assign_mix_3_1_1 +1 assign_mix_3_1_2 +1 assign_mix_3_2_1 +1 assign_mix_3_2_2
  = +1
 full_slot_capacity_1_1: +1 assign_full_2_1_1 +1 assign_full_4_1_1 +1 full_pec_pairs_1_1 -2 full_slot_used_1_1
  = +0
 full_slot_has_product_1_1: +1 full_slot_used_1_1 -1 assign_full_2_1_1 -1 assign_full_4_1_1 <= +0
 full_slot_prefix_1_1: +1 full_slot_used_1_1 -1 full_slot_used_1_2 >= +0
 full_after_mix_monotone_1_1: +1 full_after_mix_1_1 -1 full_after_mix_1_2 <= +0
 full_slot_capacity_1_2: +1 assign_full_2_1_2 +1 assign_full_4_1_2 +1 full_pec_pairs_1_2 -2 full_slot_used_1_2
  = +0
 full_slot_has_product_1_2: +1 full_slot_used_1_2 -1 assign_full_2_1_2 -1 assign_full_4_1_2 <= +0
 mix_pos_capacity_1_1: +1 mix_pos_used_1_1 -1 assign_mix_1_1_1 -1 assign_mix_3_1_1 = +0
 mix_pos_prefix_1_1: +1 mix_pos_used_1_1 -1 mix_pos_used_1_2 >= +0
 mix_pos_capacity_1_2: +1 mix_pos_used_1_2 -1 assign_mix_1_1_2 -1 assign_mix_3_1_2 = +0
 mix_active_def_1: +1 mix_active_1 -1 mix_pos_used_1_1 = +0
 full_slot_capacity_2_1: +1 assign_full_2_2_1 +1 assign_full_4_2_1 +1 full_pec_pairs_2_1 -2 full_slot_used_2_1
  = +0
 full_slot_has_product_2_1: +1 full_slot_used_2_1 -1 assign_full_2_2_1 -1 assign_full_4_2_1 <= +0
 full_slot_prefix_2_1: +1 full_slot_used_2_1 -1 full_slot_used_2_2 >= +0
 full_after_mix_monotone_2_1: +1 full_after_mix_2_1 -1 full_after_mix_2_2 <= +0
 full_slot_capacity_2_2: +1 assign_full_2_2_2 +1 assign_full_4_2_2 +1 full_pec_pairs_2_2 -2 full_slot_used_2_2
  = +0
 full_slot_has_product_2_2: +1 full_slot_used_2_2 -1 assign_full_2_2_2 -1 assign_full_4_2_2 <= +0
 mix_pos_capacity_2_1: +1 mix_pos_used_2_1 -1 assign_mix_1_2_1 -1 assign_mix_3_2_1 = +0
 mix_pos_prefix_2_1: +1 mix_pos_used_2_1 -1 mix_pos_used_2_2 >= +0
 mix_pos_capacity_2_2: +1 mix_pos_used_2_2 -1 assign_mix_1_2_2 -1 assign_mix_3_2_2 = +0
 mix_active_def_2: +1 mix_active_2 -1 mix_pos_used_2_1 = +0
 pec_pair_budget: +1 full_pec_pairs_1_1 +1 full_pec_pairs_1_2 +1 full_pec_pairs_2_1 +1 full_pec_pairs_2_2
  +2 mix_active_1 +2 mix_active_2 <= +4
 mix_cycle_lead_exists_1: +1 mix_cycle_used_1_1 -1 mix_pos_used_1_1 = +0
 mix_cycle_prev_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_1 >= +0
 mix_cycle_next_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_2 >= +0
 mix_cycle_union_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_1 -1 mix_pos_used_1_2 <= +0
 mix_cycle_tail_exists_1: +1 mix_cycle_used_1_3 -1 mix_pos_used_1_2 = +0
 mix_cycle_prefix_1_1: +1 mix_cycle_used_1_1 -1 mix_cycle_used_1_2 >= +0
 mix_cycle_prefix_1_2: +1 mix_cycle_used_1_2 -1 mix_cycle_used_1_3 >= +0
 mix_last_cycle_unique_1: +1 mix_active_1 -1 mix_last_cycle_1_1 -1 mix_last_cycle_1_2 -1 mix_last_cycle_1_3
  = +0
 mix_last_cycle_active_1_1: +1 mix_last_cycle_1_1 -1 mix_cycle_used_1_1 <= +0
 mix_last_cycle_tail_only_1_1: +1 mix_last_cycle_1_1 +1 mix_cycle_used_1_2 <= +1
 mix_last_cycle_exact_1_1: +1 mix_last_cycle_1_1 -1 mix_cycle_used_1_1 +1 mix_cycle_used_1_2 >= +0
 mix_last_cycle_active_1_2: +1 mix_last_cycle_1_2 -1 mix_cycle_used_1_2 <= +0
 mix_last_cycle_tail_only_1_2: +1 mix_last_cycle_1_2 +1 mix_cycle_used_1_3 <= +1
 mix_last_cycle_exact_1_2: +1 mix_last_cycle_1_2 -1 mix_cycle_used_1_2 +1 mix_cycle_used_1_3 >= +0
 mix_last_cycle_terminal_1: +1 mix_last_cycle_1_3 -1 mix_cycle_used_1_3 = +0
 mix_cycle_lead_exists_2: +1 mix_cycle_used_2_1 -1 mix_pos_used_2_1 = +0
 mix_cycle_prev_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_1 >= +0
 mix_cycle_next_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_2 >= +0
 mix_cycle_union_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_1 -1 mix_pos_used_2_2 <= +0
 mix_cycle_tail_exists_2: +1 mix_cycle_used_2_3 -1 mix_pos_used_2_2 = +0
 mix_cycle_prefix_2_1: +1 mix_cycle_used_2_1 -1 mix_cycle_used_2_2 >= +0
 mix_cycle_prefix_2_2: +1 mix_cycle_used_2_2 -1 mix_cycle_used_2_3 >= +0
 mix_last_cycle_unique_2: +1 mix_active_2 -1 mix_last_cycle_2_1 -1 mix_last_cycle_2_2 -1 mix_last_cycle_2_3
  = +0
 mix_last_cycle_active_2_1: +1 mix_last_cycle_2_1 -1 mix_cycle_used_2_1 <= +0
 mix_last_cycle_tail_only_2_1: +1 mix_last_cycle_2_1 +1 mix_cycle_used_2_2 <= +1
 mix_last_cycle_exact_2_1: +1 mix_last_cycle_2_1 -1 mix_cycle_used_2_1 +1 mix_cycle_used_2_2 >= +0
 mix_last_cycle_active_2_2: +1 mix_last_cycle_2_2 -1 mix_cycle_used_2_2 <= +0
 mix_last_cycle_tail_only_2_2: +1 mix_last_cycle_2_2 +1 mix_cycle_used_2_3 <= +1
 mix_last_cycle_exact_2_2: +1 mix_last_cycle_2_2 -1 mix_cycle_used_2_2 +1 mix_cycle_used_2_3 >= +0
 mix_last_cycle_terminal_2: +1 mix_last_cycle_2_3 -1 mix_cycle_used_2_3 = +0
 full_start_cap_1_1: +1 full_start_1_1 -10000 full_slot_used_1_1 <= +0
 full_end_cap_1_1: +1 full_end_1_1 -10000 full_slot_used_1_1 <= +0
 full_duration_1_1: +1 full_end_1_1 -1 full_start_1_1 -120 full_slot_used_1_1 = +0
 full_sequence_lb_1_1: +1 full_start_1_2 -1 full_end_1_1 -10000 full_slot_used_1_1 -10000 full_slot_used_1_2
  >= -19994
 full_start_cap_1_2: +1 full_start_1_2 -10000 full_slot_used_1_2 <= +0
 full_end_cap_1_2: +1 full_end_1_2 -10000 full_slot_used_1_2 <= +0
 full_duration_1_2: +1 full_end_1_2 -1 full_start_1_2 -120 full_slot_used_1_2 = +0
 mix_cycle_start_cap_1_1: +1 mix_cycle_start_1_1 -10000 mix_cycle_used_1_1 <= +0
 mix_cycle_end_cap_1_1: +1 mix_cycle_end_1_1 -10000 mix_cycle_used_1_1 <= +0
 mix_cycle_duration_1_1: +1 mix_cycle_end_1_1 -1 mix_cycle_start_1_1 -70 mix_cycle_used_1_1 = +0
 mix_cycle_sequence_lb_1_1: +1 mix_cycle_start_1_2 -1 mix_cycle_end_1_1 -10000 mix_cycle_used_1_2 >= -9994
 mix_cycle_sequence_ub_1_1: +1 mix_cycle_start_1_2 -1 mix_cycle_end_1_1 +10000 mix_cycle_used_1_1 +10000 mix_cycle_used_1_2
  <= +20006
 mix_cycle_start_cap_1_2: +1 mix_cycle_start_1_2 -10000 mix_cycle_used_1_2 <= +0
 mix_cycle_end_cap_1_2: +1 mix_cycle_end_1_2 -10000 mix_cycle_used_1_2 <= +0
 mix_cycle_duration_1_2: +1 mix_cycle_end_1_2 -1 mix_cycle_start_1_2 -70 mix_cycle_used_1_2 = +0
 mix_cycle_sequence_lb_1_2: +1 mix_cycle_start_1_3 -1 mix_cycle_end_1_2 -10000 mix_cycle_used_1_3 >= -9994
 mix_cycle_sequence_ub_1_2: +1 mix_cycle_start_1_3 -1 mix_cycle_end_1_2 +10000 mix_cycle_used_1_2 +10000 mix_cycle_used_1_3
  <= +20006
 mix_cycle_start_cap_1_3: +1 mix_cycle_start_1_3 -10000 mix_cycle_used_1_3 <= +0
 mix_cycle_end_cap_1_3: +1 mix_cycle_end_1_3 -10000 mix_cycle_used_1_3 <= +0
 mix_cycle_duration_1_3: +1 mix_cycle_end_1_3 -1 mix_cycle_start_1_3 -70 mix_cycle_used_1_3 = +0
 mix_block_end_cap_1: +1 mix_block_end_1 -10000 mix_active_1 <= +0
 mix_block_end_lb_1_1: +1 mix_block_end_1 -1 mix_cycle_end_1_1 -10000 mix_last_cycle_1_1 >= -10000
 mix_block_end_ub_1_1: +1 mix_block_end_1 -1 mix_cycle_end_1_1 +10000 mix_last_cycle_1_1 <= +10000
 mix_block_end_lb_1_2: +1 mix_block_end_1 -1 mix_cycle_end_1_2 -10000 mix_last_cycle_1_2 >= -10000
 mix_block_end_ub_1_2: +1 mix_block_end_1 -1 mix_cycle_end_1_2 +10000 mix_last_cycle_1_2 <= +10000
 mix_block_end_lb_1_3: +1 mix_block_end_1 -1 mix_cycle_end_1_3 -10000 mix_last_cycle_1_3 >= -10000
 mix_block_end_ub_1_3: +1 mix_block_end_1 -1 mix_cycle_end_1_3 +10000 mix_last_cycle_1_3 <= +10000
 full_before_mix_1_1: +1 full_end_1_1 -1 mix_cycle_start_1_1 -10000 full_after_mix_1_1 +10000 full_slot_used_1_1
  +10000 mix_active_1 <= +19994
 full_after_mix_1_1: +1 full_start_1_1 -1 mix_block_end_1 -10000 full_after_mix_1_1 -10000 full_slot_used_1_1
  -10000 mix_active_1 >= -29994
 full_before_mix_1_2: +1 full_end_1_2 -1 mix_cycle_start_1_1 -10000 full_after_mix_1_2 +10000 full_slot_used_1_2
  +10000 mix_active_1 <= +19994
 full_after_mix_1_2: +1 full_start_1_2 -1 mix_block_end_1 -10000 full_after_mix_1_2 -10000 full_slot_used_1_2
  -10000 mix_active_1 >= -29994
 full_start_cap_2_1: +1 full_start_2_1 -10000 full_slot_used_2_1 <= +0
 full_end_cap_2_1: +1 full_end_2_1 -10000 full_slot_used_2_1 <= +0
 full_duration_2_1: +1 full_end_2_1 -1 full_start_2_1 -120 full_slot_used_2_1 = +0
 full_sequence_lb_2_1: +1 full_start_2_2 -1 full_end_2_1 -10000 full_slot_used_2_1 -10000 full_slot_used_2_2
  >= -19994
 full_start_cap_2_2: +1 full_start_2_2 -10000 full_slot_used_2_2 <= +0
 full_end_cap_2_2: +1 full_end_2_2 -10000 full_slot_used_2_2 <= +0
 full_duration_2_2: +1 full_end_2_2 -1 full_start_2_2 -120 full_slot_used_2_2 = +0
 mix_cycle_start_cap_2_1: +1 mix_cycle_start_2_1 -10000 mix_cycle_used_2_1 <= +0
 mix_cycle_end_cap_2_1: +1 mix_cycle_end_2_1 -10000 mix_cycle_used_2_1 <= +0
 mix_cycle_duration_2_1: +1 mix_cycle_end_2_1 -1 mix_cycle_start_2_1 -70 mix_cycle_used_2_1 = +0
 mix_cycle_sequence_lb_2_1: +1 mix_cycle_start_2_2 -1 mix_cycle_end_2_1 -10000 mix_cycle_used_2_2 >= -9994
 mix_cycle_sequence_ub_2_1: +1 mix_cycle_start_2_2 -1 mix_cycle_end_2_1 +10000 mix_cycle_used_2_1 +10000 mix_cycle_used_2_2
  <= +20006
 mix_cycle_start_cap_2_2: +1 mix_cycle_start_2_2 -10000 mix_cycle_used_2_2 <= +0
 mix_cycle_end_cap_2_2: +1 mix_cycle_end_2_2 -10000 mix_cycle_used_2_2 <= +0
 mix_cycle_duration_2_2: +1 mix_cycle_end_2_2 -1 mix_cycle_start_2_2 -70 mix_cycle_used_2_2 = +0
 mix_cycle_sequence_lb_2_2: +1 mix_cycle_start_2_3 -1 mix_cycle_end_2_2 -10000 mix_cycle_used_2_3 >= -9994
 mix_cycle_sequence_ub_2_2: +1 mix_cycle_start_2_3 -1 mix_cycle_end_2_2 +10000 mix_cycle_used_2_2 +10000 mix_cycle_used_2_3
  <= +20006
 mix_cycle_start_cap_2_3: +1 mix_cycle_start_2_3 -10000 mix_cycle_used_2_3 <= +0
 mix_cycle_end_cap_2_3: +1 mix_cycle_end_2_3 -10000 mix_cycle_used_2_3 <= +0
 mix_cycle_duration_2_3: +1 mix_cycle_end_2_3 -1 mix_cycle_start_2_3 -70 mix_cycle_used_2_3 = +0
 mix_block_end_cap_2: +1 mix_block_end_2 -10000 mix_active_2 <= +0
 mix_block_end_lb_2_1: +1 mix_block_end_2 -1 mix_cycle_end_2_1 -10000 mix_last_cycle_2_1 >= -10000
 mix_block_end_ub_2_1: +1 mix_block_end_2 -1 mix_cycle_end_2_1 +10000 mix_last_cycle_2_1 <= +10000
 mix_block_end_lb_2_2: +1 mix_block_end_2 -1 mix_cycle_end_2_2 -10000 mix_last_cycle_2_2 >= -10000
 mix_block_end_ub_2_2: +1 mix_block_end_2 -1 mix_cycle_end_2_2 +10000 mix_last_cycle_2_2 <= +10000
 mix_block_end_lb_2_3: +1 mix_block_end_2 -1 mix_cycle_end_2_3 -10000 mix_last_cycle_2_3 >= -10000
 mix_block_end_ub_2_3: +1 mix_block_end_2 -1 mix_cycle_end_2_3 +10000 mix_last_cycle_2_3 <= +10000
 full_before_mix_2_1: +1 full_end_2_1 -1 mix_cycle_start_2_1 -10000 full_after_mix_2_1 +10000 full_slot_used_2_1
  +10000 mix_active_2 <= +19994
 full_after_mix_2_1: +1 full_start_2_1 -1 mix_block_end_2 -10000 full_after_mix_2_1 -10000 full_slot_used_2_1
  -10000 mix_active_2 >= -29994
 full_before_mix_2_2: +1 full_end_2_2 -1 mix_cycle_start_2_1 -10000 full_after_mix_2_2 +10000 full_slot_used_2_2
  +10000 mix_active_2 <= +19994
 full_after_mix_2_2: +1 full_start_2_2 -1 mix_block_end_2 -10000 full_after_mix_2_2 -10000 full_slot_used_2_2
  -10000 mix_active_2 >= -29994
 pair_full_lb_2_1_1: +1 pair_completion_2 -1 full_end_1_1 -10000 assign_full_2_1_1 >= -10000
 pair_full_ub_2_1_1: +1 pair_completion_2 -1 full_end_1_1 +10000 assign_full_2_1_1 <= +10000
 pair_full_lb_2_1_2: +1 pair_completion_2 -1 full_end_1_2 -10000 assign_full_2_1_2 >= -10000
 pair_full_ub_2_1_2: +1 pair_completion_2 -1 full_end_1_2 +10000 assign_full_2_1_2 <= +10000
 pair_full_lb_2_2_1: +1 pair_completion_2 -1 full_end_2_1 -10000 assign_full_2_2_1 >= -10000
 pair_full_ub_2_2_1: +1 pair_completion_2 -1 full_end_2_1 +10000 assign_full_2_2_1 <= +10000
 pair_full_lb_2_2_2: +1 pair_completion_2 -1 full_end_2_2 -10000 assign_full_2_2_2 >= -10000
 pair_full_ub_2_2_2: +1 pair_completion_2 -1 full_end_2_2 +10000 assign_full_2_2_2 <= +10000
 pair_full_lb_4_1_1: +1 pair_completion_4 -1 full_end_1_1 -10000 assign_full_4_1_1 >= -10000
 pair_full_ub_4_1_1: +1 pair_completion_4 -1 full_end_1_1 +10000 assign_full_4_1_1 <= +10000
 pair_full_lb_4_1_2: +1 pair_completion_4 -1 full_end_1_2 -10000 assign_full_4_1_2 >= -10000
 pair_full_ub_4_1_2: +1 pair_completion_4 -1 full_end_1_2 +10000 assign_full_4_1_2 <= +10000
 pair_full_lb_4_2_1: +1 pair_completion_4 -1 full_end_2_1 -10000 assign_full_4_2_1 >= -10000
 pair_full_ub_4_2_1: +1 pair_completion_4 -1 full_end_2_1 +10000 assign_full_4_2_1 <= +10000
 pair_full_lb_4_2_2: +1 pair_completion_4 -1 full_end_2_2 -10000 assign_full_4_2_2 >= -10000
 pair_full_ub_4_2_2: +1 pair_completion_4 -1 full_end_2_2 +10000 assign_full_4_2_2 <= +10000
 pair_mix_lb_1_1_1: +1 pair_completion_1 -1 mix_cycle_end_1_2 -10000 assign_mix_1_1_1 >= -10000
 pair_mix_ub_1_1_1: +1 pair_completion_1 -1 mix_cycle_end_1_2 +10000 assign_mix_1_1_1 <= +10000
 pair_mix_lb_1_1_2: +1 pair_completion_1 -1 mix_cycle_end_1_3 -10000 assign_mix_1_1_2 >= -10000
 pair_mix_ub_1_1_2: +1 pair_completion_1 -1 mix_cycle_end_1_3 +10000 assign_mix_1_1_2 <= +10000
 pair_mix_lb_1_2_1: +1 pair_completion_1 -1 mix_cycle_end_2_2 -10000 assign_mix_1_2_1 >= -10000
 pair_mix_ub_1_2_1: +1 pair_completion_1 -1 mix_cycle_end_2_2 +10000 assign_mix_1_2_1 <= +10000
 pair_mix_lb_1_2_2: +1 pair_completion_1 -1 mix_cycle_end_2_3 -10000 assign_mix_1_2_2 >= -10000
 pair_mix_ub_1_2_2: +1 pair_completion_1 -1 mix_cycle_end_2_3 +10000 assign_mix_1_2_2 <= +10000
 pair_mix_lb_3_1_1: +1 pair_completion_3 -1 mix_cycle_end_1_2 -10000 assign_mix_3_1_1 >= -10000
 pair_mix_ub_3_1_1: +1 pair_completion_3 -1 mix_cycle_end_1_2 +10000 assign_mix_3_1_1 <= +10000
 pair_mix_lb_3_1_2: +1 pair_completion_3 -1 mix_cycle_end_1_3 -10000 assign_mix_3_1_2 >= -10000
 pair_mix_ub_3_1_2: +1 pair_completion_3 -1 mix_cycle_end_1_3 +10000 assign_mix_3_1_2 <= +10000
 pair_mix_lb_3_2_1: +1 pair_completion_3 -1 mix_cycle_end_2_2 -10000 assign_mix_3_2_1 >= -10000
 pair_mix_ub_3_2_1: +1 pair_completion_3 -1 mix_cycle_end_2_2 +10000 assign_mix_3_2_1 <= +10000
 pair_mix_lb_3_2_2: +1 pair_completion_3 -1 mix_cycle_end_2_3 -10000 assign_mix_3_2_2 >= -10000
 pair_mix_ub_3_2_2: +1 pair_completion_3 -1 mix_cycle_end_2_3 +10000 assign_mix_3_2_2 <= +10000
 cmax_ge_pair_1: +1 c_max -1 pair_completion_1 >= +0
 cmax_ge_pair_2: +1 c_max -1 pair_completion_2 >= +0
 cmax_ge_pair_3: +1 c_max -1 pair_completion_3 >= +0
 cmax_ge_pair_4: +1 c_max -1 pair_completion_4 >= +0
 full_order_symmetry_1_1: +2 assign_full_2_1_1 +4 assign_full_4_1_1 -2 assign_full_2_1_2 -4 assign_full_4_1_2
  +10000 full_slot_used_1_1 +10000 full_slot_used_1_2 <= +20000
 mix_order_symmetry_1_1: +1 assign_mix_1_1_1 +3 assign_mix_3_1_1 -1 assign_mix_1_1_2 -3 assign_mix_3_1_2
  +10000 mix_pos_used_1_1 +10000 mix_pos_used_1_2 <= +20000
 full_order_symmetry_2_1: +2 assign_full_2_2_1 +4 assign_full_4_2_1 -2 assign_full_2_2_2 -4 assign_full_4_2_2
  +10000 full_slot_used_2_1 +10000 full_slot_used_2_2 <= +20000
 mix_order_symmetry_2_1: +1 assign_mix_1_2_1 +3 assign_mix_3_2_1 -1 assign_mix_1_2_2 -3 assign_mix_3_2_2
  +10000 mix_pos_used_2_1 +10000 mix_pos_used_2_2 <= +20000
 pm_activity_symmetry: +1 full_slot_used_1_1 +1 full_slot_used_1_2 +1 mix_pos_used_1_1 +1 mix_pos_used_1_2
  -1 full_slot_used_2_1 -1 full_slot_used_2_2 -1 mix_pos_used_2_1 -1 mix_pos_used_2_2 >= +0
Bounds
 0 <= assign_full_2_1_1 <= 1
 0 <= assign_full_2_1_2 <= 1
 0 <= assign_full_2_2_1 <= 1
 0 <= assign_full_2_2_2 <= 1
 0 <= assign_full_4_1_1 <= 1
 0 <= assign_full_4_1_2 <= 1
 0 <= assign_full_4_2_1 <= 1
 0 <= assign_full_4_2_2 <= 1
 0 <= full_slot_used_1_1 <= 1
 0 <= full_slot_used_1_2 <= 1
 0 <= full_slot_used_2_1 <= 1
 0 <= full_slot_used_2_2 <= 1
 0 <= full_pec_pairs_1_1 <= 1
 0 <= full_pec_pairs_1_2 <= 1
 0 <= full_pec_pairs_2_1 <= 1
 0 <= full_pec_pairs_2_2 <= 1
 0 <= full_after_mix_1_1 <= 1
 0 <= full_after_mix_1_2 <= 1
 0 <= full_after_mix_2_1 <= 1
 0 <= full_after_mix_2_2 <= 1
 0 <= assign_mix_1_1_1 <= 1
 0 <= assign_mix_1_1_2 <= 1
 0 <= assign_mix_1_2_1 <= 1
 0 <= assign_mix_1_2_2 <= 1
 0 <= assign_mix_3_1_1 <= 1
 0 <= assign_mix_3_1_2 <= 1
 0 <= assign_mix_3_2_1 <= 1
 0 <= assign_mix_3_2_2 <= 1
 0 <= mix_pos_used_1_1 <= 1
 0 <= mix_pos_used_1_2 <= 1
 0 <= mix_pos_used_2_1 <= 1
 0 <= mix_pos_used_2_2 <= 1
 0 <= mix_cycle_used_1_1 <= 1
 0 <= mix_cycle_used_1_2 <= 1
 0 <= mix_cycle_used_1_3 <= 1
 0 <= mix_cycle_used_2_1 <= 1
 0 <= mix_cycle_used_2_2 <= 1
 0 <= mix_cycle_used_2_3 <= 1
 0 <= mix_active_1 <= 1
 0 <= mix_active_2 <= 1
 0 <= mix_last_cycle_1_1 <= 1
 0 <= mix_last_cycle_1_2 <= 1
 0 <= mix_last_cycle_1_3 <= 1
 0 <= mix_last_cycle_2_1 <= 1
 0 <= mix_last_cycle_2_2 <= 1
 0 <= mix_last_cycle_2_3 <= 1
Binaries
 assign_full_2_1_1 assign_full_2_1_2 assign_full_2_2_1 assign_full_2_2_2 assign_full_4_1_1 assign_full_4_1_2
 assign_full_4_2_1 assign_full_4_2_2 full_slot_used_1_1 full_slot_used_1_2 full_slot_used_2_1 full_slot_used_2_2
 full_pec_pairs_1_1 full_pec_pairs_1_2 full_pec_pairs_2_1 full_pec_pairs_2_2 full_after_mix_1_1 full_after_mix_1_2
 full_after_mix_2_1 full_after_mix_2_2 assign_mix_1_1_1 assign_mix_1_1_2 assign_mix_1_2_1 assign_mix_1_2_2
 assign_mix_3_1_1 assign_mix_3_1_2 assign_mix_3_2_1 assign_mix_3_2_2 mix_pos_used_1_1 mix_pos_used_1_2
 mix_pos_used_2_1 mix_pos_used_2_2 mix_cycle_used_1_1 mix_cycle_used_1_2 mix_cycle_used_1_3 mix_cycle_used_2_1
 mix_cycle_used_2_2 mix_cycle_used_2_3 mix_active_1 mix_active_2 mix_last_cycle_1_1 mix_last_cycle_1_2
 mix_last_cycle_1_3 mix_last_cycle_2_1 mix_last_cycle_2_2 mix_last_cycle_2_3
End
