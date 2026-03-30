\ SCIP STATISTICS
\   Problem name     : dual_source_rotary_cluster_shared_pm_pw_pairs
\   Variables        : 137 (93 binary, 0 integer, 0 implicit integer, 44 continuous)
\   Constraints      : 308
Minimize
 Obj: +1 c_max
Subject to
 full_wafer_assign_once_1: +1 wafer_to_full_pair_1_1 +1 wafer_to_full_pair_1_2 = +1
 full_wafer_assign_once_2: +1 wafer_to_full_pair_2_1 +1 wafer_to_full_pair_2_2 = +1
 full_wafer_assign_once_3: +1 wafer_to_full_pair_3_1 +1 wafer_to_full_pair_3_2 = +1
 full_pair_capacity_1: +1 wafer_to_full_pair_1_1 +1 wafer_to_full_pair_2_1 +1 wafer_to_full_pair_3_1 = +2
 full_pair_capacity_2: +1 wafer_to_full_pair_1_2 +1 wafer_to_full_pair_2_2 +1 wafer_to_full_pair_3_2 = +1
 full_pairing_order_1_2: +1 wafer_to_full_pair_1_1 +2 wafer_to_full_pair_1_2 -1 wafer_to_full_pair_2_1
  -2 wafer_to_full_pair_2_2 <= +0
 full_pairing_order_2_3: +1 wafer_to_full_pair_2_1 +2 wafer_to_full_pair_2_2 -1 wafer_to_full_pair_3_1
  -2 wafer_to_full_pair_3_2 <= +0
 mix_wafer_assign_once_4: +1 wafer_to_mix_pair_4_1 +1 wafer_to_mix_pair_4_2 +1 wafer_to_mix_pair_4_3 = +1
 mix_wafer_assign_once_5: +1 wafer_to_mix_pair_5_1 +1 wafer_to_mix_pair_5_2 +1 wafer_to_mix_pair_5_3 = +1
 mix_wafer_assign_once_6: +1 wafer_to_mix_pair_6_1 +1 wafer_to_mix_pair_6_2 +1 wafer_to_mix_pair_6_3 = +1
 mix_wafer_assign_once_7: +1 wafer_to_mix_pair_7_1 +1 wafer_to_mix_pair_7_2 +1 wafer_to_mix_pair_7_3 = +1
 mix_wafer_assign_once_8: +1 wafer_to_mix_pair_8_1 +1 wafer_to_mix_pair_8_2 +1 wafer_to_mix_pair_8_3 = +1
 mix_pair_capacity_1: +1 wafer_to_mix_pair_4_1 +1 wafer_to_mix_pair_5_1 +1 wafer_to_mix_pair_6_1 +1 wafer_to_mix_pair_7_1
  +1 wafer_to_mix_pair_8_1 = +2
 mix_pair_capacity_2: +1 wafer_to_mix_pair_4_2 +1 wafer_to_mix_pair_5_2 +1 wafer_to_mix_pair_6_2 +1 wafer_to_mix_pair_7_2
  +1 wafer_to_mix_pair_8_2 = +2
 mix_pair_capacity_3: +1 wafer_to_mix_pair_4_3 +1 wafer_to_mix_pair_5_3 +1 wafer_to_mix_pair_6_3 +1 wafer_to_mix_pair_7_3
  +1 wafer_to_mix_pair_8_3 = +1
 mix_pairing_order_4_5: +1 wafer_to_mix_pair_4_1 +2 wafer_to_mix_pair_4_2 +3 wafer_to_mix_pair_4_3 -1 wafer_to_mix_pair_5_1
  -2 wafer_to_mix_pair_5_2 -3 wafer_to_mix_pair_5_3 <= +0
 mix_pairing_order_5_6: +1 wafer_to_mix_pair_5_1 +2 wafer_to_mix_pair_5_2 +3 wafer_to_mix_pair_5_3 -1 wafer_to_mix_pair_6_1
  -2 wafer_to_mix_pair_6_2 -3 wafer_to_mix_pair_6_3 <= +0
 mix_pairing_order_6_7: +1 wafer_to_mix_pair_6_1 +2 wafer_to_mix_pair_6_2 +3 wafer_to_mix_pair_6_3 -1 wafer_to_mix_pair_7_1
  -2 wafer_to_mix_pair_7_2 -3 wafer_to_mix_pair_7_3 <= +0
 mix_pairing_order_7_8: +1 wafer_to_mix_pair_7_1 +2 wafer_to_mix_pair_7_2 +3 wafer_to_mix_pair_7_3 -1 wafer_to_mix_pair_8_1
  -2 wafer_to_mix_pair_8_2 -3 wafer_to_mix_pair_8_3 <= +0
 full_pair_schedule_once_1: +1 assign_full_1_1_1 +1 assign_full_1_1_2 +1 assign_full_1_1_3 +1 assign_full_1_2_1
  +1 assign_full_1_2_2 +1 assign_full_1_2_3 = +1
 full_pair_schedule_once_2: +1 assign_full_2_1_1 +1 assign_full_2_1_2 +1 assign_full_2_1_3 +1 assign_full_2_2_1
  +1 assign_full_2_2_2 +1 assign_full_2_2_3 = +1
 mix_pair_schedule_once_1: +1 assign_mix_1_1_1 +1 assign_mix_1_1_2 +1 assign_mix_1_1_3 +1 assign_mix_1_2_1
  +1 assign_mix_1_2_2 +1 assign_mix_1_2_3 = +1
 mix_pair_schedule_once_2: +1 assign_mix_2_1_1 +1 assign_mix_2_1_2 +1 assign_mix_2_1_3 +1 assign_mix_2_2_1
  +1 assign_mix_2_2_2 +1 assign_mix_2_2_3 = +1
 mix_pair_schedule_once_3: +1 assign_mix_3_1_1 +1 assign_mix_3_1_2 +1 assign_mix_3_1_3 +1 assign_mix_3_2_1
  +1 assign_mix_3_2_2 +1 assign_mix_3_2_3 = +1
 full_slot_capacity_1_1: +1 assign_full_1_1_1 +1 assign_full_2_1_1 +1 full_pec_pairs_1_1 -2 full_slot_used_1_1
  = +0
 full_slot_has_product_pair_1_1: +1 full_slot_used_1_1 -1 assign_full_1_1_1 -1 assign_full_2_1_1 <= +0
 full_slot_prefix_1_1: +1 full_slot_used_1_1 -1 full_slot_used_1_2 >= +0
 full_after_mix_monotone_1_1: +1 full_after_mix_1_1 -1 full_after_mix_1_2 <= +0
 full_slot_capacity_1_2: +1 assign_full_1_1_2 +1 assign_full_2_1_2 +1 full_pec_pairs_1_2 -2 full_slot_used_1_2
  = +0
 full_slot_has_product_pair_1_2: +1 full_slot_used_1_2 -1 assign_full_1_1_2 -1 assign_full_2_1_2 <= +0
 full_slot_prefix_1_2: +1 full_slot_used_1_2 -1 full_slot_used_1_3 >= +0
 full_after_mix_monotone_1_2: +1 full_after_mix_1_2 -1 full_after_mix_1_3 <= +0
 full_slot_capacity_1_3: +1 assign_full_1_1_3 +1 assign_full_2_1_3 +1 full_pec_pairs_1_3 -2 full_slot_used_1_3
  = +0
 full_slot_has_product_pair_1_3: +1 full_slot_used_1_3 -1 assign_full_1_1_3 -1 assign_full_2_1_3 <= +0
 mix_pos_capacity_1_1: +1 mix_pos_used_1_1 -1 assign_mix_1_1_1 -1 assign_mix_2_1_1 -1 assign_mix_3_1_1
  = +0
 mix_pos_prefix_1_1: +1 mix_pos_used_1_1 -1 mix_pos_used_1_2 >= +0
 mix_pos_capacity_1_2: +1 mix_pos_used_1_2 -1 assign_mix_1_1_2 -1 assign_mix_2_1_2 -1 assign_mix_3_1_2
  = +0
 mix_pos_prefix_1_2: +1 mix_pos_used_1_2 -1 mix_pos_used_1_3 >= +0
 mix_pos_capacity_1_3: +1 mix_pos_used_1_3 -1 assign_mix_1_1_3 -1 assign_mix_2_1_3 -1 assign_mix_3_1_3
  = +0
 mix_active_def_1: +1 mix_active_1 -1 mix_pos_used_1_1 = +0
 full_slot_capacity_2_1: +1 assign_full_1_2_1 +1 assign_full_2_2_1 +1 full_pec_pairs_2_1 -2 full_slot_used_2_1
  = +0
 full_slot_has_product_pair_2_1: +1 full_slot_used_2_1 -1 assign_full_1_2_1 -1 assign_full_2_2_1 <= +0
 full_slot_prefix_2_1: +1 full_slot_used_2_1 -1 full_slot_used_2_2 >= +0
 full_after_mix_monotone_2_1: +1 full_after_mix_2_1 -1 full_after_mix_2_2 <= +0
 full_slot_capacity_2_2: +1 assign_full_1_2_2 +1 assign_full_2_2_2 +1 full_pec_pairs_2_2 -2 full_slot_used_2_2
  = +0
 full_slot_has_product_pair_2_2: +1 full_slot_used_2_2 -1 assign_full_1_2_2 -1 assign_full_2_2_2 <= +0
 full_slot_prefix_2_2: +1 full_slot_used_2_2 -1 full_slot_used_2_3 >= +0
 full_after_mix_monotone_2_2: +1 full_after_mix_2_2 -1 full_after_mix_2_3 <= +0
 full_slot_capacity_2_3: +1 assign_full_1_2_3 +1 assign_full_2_2_3 +1 full_pec_pairs_2_3 -2 full_slot_used_2_3
  = +0
 full_slot_has_product_pair_2_3: +1 full_slot_used_2_3 -1 assign_full_1_2_3 -1 assign_full_2_2_3 <= +0
 mix_pos_capacity_2_1: +1 mix_pos_used_2_1 -1 assign_mix_1_2_1 -1 assign_mix_2_2_1 -1 assign_mix_3_2_1
  = +0
 mix_pos_prefix_2_1: +1 mix_pos_used_2_1 -1 mix_pos_used_2_2 >= +0
 mix_pos_capacity_2_2: +1 mix_pos_used_2_2 -1 assign_mix_1_2_2 -1 assign_mix_2_2_2 -1 assign_mix_3_2_2
  = +0
 mix_pos_prefix_2_2: +1 mix_pos_used_2_2 -1 mix_pos_used_2_3 >= +0
 mix_pos_capacity_2_3: +1 mix_pos_used_2_3 -1 assign_mix_1_2_3 -1 assign_mix_2_2_3 -1 assign_mix_3_2_3
  = +0
 mix_active_def_2: +1 mix_active_2 -1 mix_pos_used_2_1 = +0
 pec_wafer_budget: +2 full_pec_pairs_1_1 +2 full_pec_pairs_1_2 +2 full_pec_pairs_1_3 +2 full_pec_pairs_2_1
  +2 full_pec_pairs_2_2 +2 full_pec_pairs_2_3 +4 mix_active_1 +4 mix_active_2 <= +10
 mix_cycle_lead_exists_1: +1 mix_cycle_used_1_1 -1 mix_pos_used_1_1 = +0
 mix_cycle_prev_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_1 >= +0
 mix_cycle_next_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_2 >= +0
 mix_cycle_union_1_2: +1 mix_cycle_used_1_2 -1 mix_pos_used_1_1 -1 mix_pos_used_1_2 <= +0
 mix_cycle_prev_1_3: +1 mix_cycle_used_1_3 -1 mix_pos_used_1_2 >= +0
 mix_cycle_next_1_3: +1 mix_cycle_used_1_3 -1 mix_pos_used_1_3 >= +0
 mix_cycle_union_1_3: +1 mix_cycle_used_1_3 -1 mix_pos_used_1_2 -1 mix_pos_used_1_3 <= +0
 mix_cycle_tail_exists_1: +1 mix_cycle_used_1_4 -1 mix_pos_used_1_3 = +0
 mix_cycle_prefix_1_1: +1 mix_cycle_used_1_1 -1 mix_cycle_used_1_2 >= +0
 mix_cycle_prefix_1_2: +1 mix_cycle_used_1_2 -1 mix_cycle_used_1_3 >= +0
 mix_cycle_prefix_1_3: +1 mix_cycle_used_1_3 -1 mix_cycle_used_1_4 >= +0
 mix_last_cycle_unique_1: +1 mix_active_1 -1 mix_last_cycle_1_1 -1 mix_last_cycle_1_2 -1 mix_last_cycle_1_3
  -1 mix_last_cycle_1_4 = +0
 mix_last_cycle_active_1_1: +1 mix_last_cycle_1_1 -1 mix_cycle_used_1_1 <= +0
 mix_last_cycle_tail_only_1_1: +1 mix_last_cycle_1_1 +1 mix_cycle_used_1_2 <= +1
 mix_last_cycle_exact_1_1: +1 mix_last_cycle_1_1 -1 mix_cycle_used_1_1 +1 mix_cycle_used_1_2 >= +0
 mix_last_cycle_active_1_2: +1 mix_last_cycle_1_2 -1 mix_cycle_used_1_2 <= +0
 mix_last_cycle_tail_only_1_2: +1 mix_last_cycle_1_2 +1 mix_cycle_used_1_3 <= +1
 mix_last_cycle_exact_1_2: +1 mix_last_cycle_1_2 -1 mix_cycle_used_1_2 +1 mix_cycle_used_1_3 >= +0
 mix_last_cycle_active_1_3: +1 mix_last_cycle_1_3 -1 mix_cycle_used_1_3 <= +0
 mix_last_cycle_tail_only_1_3: +1 mix_last_cycle_1_3 +1 mix_cycle_used_1_4 <= +1
 mix_last_cycle_exact_1_3: +1 mix_last_cycle_1_3 -1 mix_cycle_used_1_3 +1 mix_cycle_used_1_4 >= +0
 mix_last_cycle_terminal_1: +1 mix_last_cycle_1_4 -1 mix_cycle_used_1_4 = +0
 mix_cycle_lead_exists_2: +1 mix_cycle_used_2_1 -1 mix_pos_used_2_1 = +0
 mix_cycle_prev_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_1 >= +0
 mix_cycle_next_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_2 >= +0
 mix_cycle_union_2_2: +1 mix_cycle_used_2_2 -1 mix_pos_used_2_1 -1 mix_pos_used_2_2 <= +0
 mix_cycle_prev_2_3: +1 mix_cycle_used_2_3 -1 mix_pos_used_2_2 >= +0
 mix_cycle_next_2_3: +1 mix_cycle_used_2_3 -1 mix_pos_used_2_3 >= +0
 mix_cycle_union_2_3: +1 mix_cycle_used_2_3 -1 mix_pos_used_2_2 -1 mix_pos_used_2_3 <= +0
 mix_cycle_tail_exists_2: +1 mix_cycle_used_2_4 -1 mix_pos_used_2_3 = +0
 mix_cycle_prefix_2_1: +1 mix_cycle_used_2_1 -1 mix_cycle_used_2_2 >= +0
 mix_cycle_prefix_2_2: +1 mix_cycle_used_2_2 -1 mix_cycle_used_2_3 >= +0
 mix_cycle_prefix_2_3: +1 mix_cycle_used_2_3 -1 mix_cycle_used_2_4 >= +0
 mix_last_cycle_unique_2: +1 mix_active_2 -1 mix_last_cycle_2_1 -1 mix_last_cycle_2_2 -1 mix_last_cycle_2_3
  -1 mix_last_cycle_2_4 = +0
 mix_last_cycle_active_2_1: +1 mix_last_cycle_2_1 -1 mix_cycle_used_2_1 <= +0
 mix_last_cycle_tail_only_2_1: +1 mix_last_cycle_2_1 +1 mix_cycle_used_2_2 <= +1
 mix_last_cycle_exact_2_1: +1 mix_last_cycle_2_1 -1 mix_cycle_used_2_1 +1 mix_cycle_used_2_2 >= +0
 mix_last_cycle_active_2_2: +1 mix_last_cycle_2_2 -1 mix_cycle_used_2_2 <= +0
 mix_last_cycle_tail_only_2_2: +1 mix_last_cycle_2_2 +1 mix_cycle_used_2_3 <= +1
 mix_last_cycle_exact_2_2: +1 mix_last_cycle_2_2 -1 mix_cycle_used_2_2 +1 mix_cycle_used_2_3 >= +0
 mix_last_cycle_active_2_3: +1 mix_last_cycle_2_3 -1 mix_cycle_used_2_3 <= +0
 mix_last_cycle_tail_only_2_3: +1 mix_last_cycle_2_3 +1 mix_cycle_used_2_4 <= +1
 mix_last_cycle_exact_2_3: +1 mix_last_cycle_2_3 -1 mix_cycle_used_2_3 +1 mix_cycle_used_2_4 >= +0
 mix_last_cycle_terminal_2: +1 mix_last_cycle_2_4 -1 mix_cycle_used_2_4 = +0
 full_start_cap_1_1: +1 full_start_1_1 -10000 full_slot_used_1_1 <= +0
 full_end_cap_1_1: +1 full_end_1_1 -10000 full_slot_used_1_1 <= +0
 full_duration_1_1: +1 full_end_1_1 -1 full_start_1_1 -120 full_slot_used_1_1 = +0
 full_sequence_lb_1_1: +1 full_start_1_2 -1 full_end_1_1 -10000 full_slot_used_1_1 -10000 full_slot_used_1_2
  >= -19994
 full_start_cap_1_2: +1 full_start_1_2 -10000 full_slot_used_1_2 <= +0
 full_end_cap_1_2: +1 full_end_1_2 -10000 full_slot_used_1_2 <= +0
 full_duration_1_2: +1 full_end_1_2 -1 full_start_1_2 -120 full_slot_used_1_2 = +0
 full_sequence_lb_1_2: +1 full_start_1_3 -1 full_end_1_2 -10000 full_slot_used_1_2 -10000 full_slot_used_1_3
  >= -19994
 full_start_cap_1_3: +1 full_start_1_3 -10000 full_slot_used_1_3 <= +0
 full_end_cap_1_3: +1 full_end_1_3 -10000 full_slot_used_1_3 <= +0
 full_duration_1_3: +1 full_end_1_3 -1 full_start_1_3 -120 full_slot_used_1_3 = +0
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
 mix_cycle_sequence_lb_1_3: +1 mix_cycle_start_1_4 -1 mix_cycle_end_1_3 -10000 mix_cycle_used_1_4 >= -9994
 mix_cycle_sequence_ub_1_3: +1 mix_cycle_start_1_4 -1 mix_cycle_end_1_3 +10000 mix_cycle_used_1_3 +10000 mix_cycle_used_1_4
  <= +20006
 mix_cycle_start_cap_1_4: +1 mix_cycle_start_1_4 -10000 mix_cycle_used_1_4 <= +0
 mix_cycle_end_cap_1_4: +1 mix_cycle_end_1_4 -10000 mix_cycle_used_1_4 <= +0
 mix_cycle_duration_1_4: +1 mix_cycle_end_1_4 -1 mix_cycle_start_1_4 -70 mix_cycle_used_1_4 = +0
 mix_block_end_cap_1: +1 mix_block_end_1 -10000 mix_active_1 <= +0
 mix_block_end_lb_1_1: +1 mix_block_end_1 -1 mix_cycle_end_1_1 -10000 mix_last_cycle_1_1 >= -10000
 mix_block_end_ub_1_1: +1 mix_block_end_1 -1 mix_cycle_end_1_1 +10000 mix_last_cycle_1_1 <= +10000
 mix_block_end_lb_1_2: +1 mix_block_end_1 -1 mix_cycle_end_1_2 -10000 mix_last_cycle_1_2 >= -10000
 mix_block_end_ub_1_2: +1 mix_block_end_1 -1 mix_cycle_end_1_2 +10000 mix_last_cycle_1_2 <= +10000
 mix_block_end_lb_1_3: +1 mix_block_end_1 -1 mix_cycle_end_1_3 -10000 mix_last_cycle_1_3 >= -10000
 mix_block_end_ub_1_3: +1 mix_block_end_1 -1 mix_cycle_end_1_3 +10000 mix_last_cycle_1_3 <= +10000
 mix_block_end_lb_1_4: +1 mix_block_end_1 -1 mix_cycle_end_1_4 -10000 mix_last_cycle_1_4 >= -10000
 mix_block_end_ub_1_4: +1 mix_block_end_1 -1 mix_cycle_end_1_4 +10000 mix_last_cycle_1_4 <= +10000
 full_before_mix_1_1: +1 full_end_1_1 -1 mix_cycle_start_1_1 -10000 full_after_mix_1_1 +10000 full_slot_used_1_1
  +10000 mix_active_1 <= +19994
 full_after_mix_1_1: +1 full_start_1_1 -1 mix_block_end_1 -10000 full_after_mix_1_1 -10000 full_slot_used_1_1
  -10000 mix_active_1 >= -29994
 full_before_mix_1_2: +1 full_end_1_2 -1 mix_cycle_start_1_1 -10000 full_after_mix_1_2 +10000 full_slot_used_1_2
  +10000 mix_active_1 <= +19994
 full_after_mix_1_2: +1 full_start_1_2 -1 mix_block_end_1 -10000 full_after_mix_1_2 -10000 full_slot_used_1_2
  -10000 mix_active_1 >= -29994
 full_before_mix_1_3: +1 full_end_1_3 -1 mix_cycle_start_1_1 -10000 full_after_mix_1_3 +10000 full_slot_used_1_3
  +10000 mix_active_1 <= +19994
 full_after_mix_1_3: +1 full_start_1_3 -1 mix_block_end_1 -10000 full_after_mix_1_3 -10000 full_slot_used_1_3
  -10000 mix_active_1 >= -29994
 full_start_cap_2_1: +1 full_start_2_1 -10000 full_slot_used_2_1 <= +0
 full_end_cap_2_1: +1 full_end_2_1 -10000 full_slot_used_2_1 <= +0
 full_duration_2_1: +1 full_end_2_1 -1 full_start_2_1 -120 full_slot_used_2_1 = +0
 full_sequence_lb_2_1: +1 full_start_2_2 -1 full_end_2_1 -10000 full_slot_used_2_1 -10000 full_slot_used_2_2
  >= -19994
 full_start_cap_2_2: +1 full_start_2_2 -10000 full_slot_used_2_2 <= +0
 full_end_cap_2_2: +1 full_end_2_2 -10000 full_slot_used_2_2 <= +0
 full_duration_2_2: +1 full_end_2_2 -1 full_start_2_2 -120 full_slot_used_2_2 = +0
 full_sequence_lb_2_2: +1 full_start_2_3 -1 full_end_2_2 -10000 full_slot_used_2_2 -10000 full_slot_used_2_3
  >= -19994
 full_start_cap_2_3: +1 full_start_2_3 -10000 full_slot_used_2_3 <= +0
 full_end_cap_2_3: +1 full_end_2_3 -10000 full_slot_used_2_3 <= +0
 full_duration_2_3: +1 full_end_2_3 -1 full_start_2_3 -120 full_slot_used_2_3 = +0
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
 mix_cycle_sequence_lb_2_3: +1 mix_cycle_start_2_4 -1 mix_cycle_end_2_3 -10000 mix_cycle_used_2_4 >= -9994
 mix_cycle_sequence_ub_2_3: +1 mix_cycle_start_2_4 -1 mix_cycle_end_2_3 +10000 mix_cycle_used_2_3 +10000 mix_cycle_used_2_4
  <= +20006
 mix_cycle_start_cap_2_4: +1 mix_cycle_start_2_4 -10000 mix_cycle_used_2_4 <= +0
 mix_cycle_end_cap_2_4: +1 mix_cycle_end_2_4 -10000 mix_cycle_used_2_4 <= +0
 mix_cycle_duration_2_4: +1 mix_cycle_end_2_4 -1 mix_cycle_start_2_4 -70 mix_cycle_used_2_4 = +0
 mix_block_end_cap_2: +1 mix_block_end_2 -10000 mix_active_2 <= +0
 mix_block_end_lb_2_1: +1 mix_block_end_2 -1 mix_cycle_end_2_1 -10000 mix_last_cycle_2_1 >= -10000
 mix_block_end_ub_2_1: +1 mix_block_end_2 -1 mix_cycle_end_2_1 +10000 mix_last_cycle_2_1 <= +10000
 mix_block_end_lb_2_2: +1 mix_block_end_2 -1 mix_cycle_end_2_2 -10000 mix_last_cycle_2_2 >= -10000
 mix_block_end_ub_2_2: +1 mix_block_end_2 -1 mix_cycle_end_2_2 +10000 mix_last_cycle_2_2 <= +10000
 mix_block_end_lb_2_3: +1 mix_block_end_2 -1 mix_cycle_end_2_3 -10000 mix_last_cycle_2_3 >= -10000
 mix_block_end_ub_2_3: +1 mix_block_end_2 -1 mix_cycle_end_2_3 +10000 mix_last_cycle_2_3 <= +10000
 mix_block_end_lb_2_4: +1 mix_block_end_2 -1 mix_cycle_end_2_4 -10000 mix_last_cycle_2_4 >= -10000
 mix_block_end_ub_2_4: +1 mix_block_end_2 -1 mix_cycle_end_2_4 +10000 mix_last_cycle_2_4 <= +10000
 full_before_mix_2_1: +1 full_end_2_1 -1 mix_cycle_start_2_1 -10000 full_after_mix_2_1 +10000 full_slot_used_2_1
  +10000 mix_active_2 <= +19994
 full_after_mix_2_1: +1 full_start_2_1 -1 mix_block_end_2 -10000 full_after_mix_2_1 -10000 full_slot_used_2_1
  -10000 mix_active_2 >= -29994
 full_before_mix_2_2: +1 full_end_2_2 -1 mix_cycle_start_2_1 -10000 full_after_mix_2_2 +10000 full_slot_used_2_2
  +10000 mix_active_2 <= +19994
 full_after_mix_2_2: +1 full_start_2_2 -1 mix_block_end_2 -10000 full_after_mix_2_2 -10000 full_slot_used_2_2
  -10000 mix_active_2 >= -29994
 full_before_mix_2_3: +1 full_end_2_3 -1 mix_cycle_start_2_1 -10000 full_after_mix_2_3 +10000 full_slot_used_2_3
  +10000 mix_active_2 <= +19994
 full_after_mix_2_3: +1 full_start_2_3 -1 mix_block_end_2 -10000 full_after_mix_2_3 -10000 full_slot_used_2_3
  -10000 mix_active_2 >= -29994
 full_pair_completion_lb_1_1_1: +1 full_pair_completion_1 -1 full_end_1_1 -10000 assign_full_1_1_1 >= -10000
 full_pair_completion_ub_1_1_1: +1 full_pair_completion_1 -1 full_end_1_1 +10000 assign_full_1_1_1 <= +10000
 full_pair_completion_lb_1_1_2: +1 full_pair_completion_1 -1 full_end_1_2 -10000 assign_full_1_1_2 >= -10000
 full_pair_completion_ub_1_1_2: +1 full_pair_completion_1 -1 full_end_1_2 +10000 assign_full_1_1_2 <= +10000
 full_pair_completion_lb_1_1_3: +1 full_pair_completion_1 -1 full_end_1_3 -10000 assign_full_1_1_3 >= -10000
 full_pair_completion_ub_1_1_3: +1 full_pair_completion_1 -1 full_end_1_3 +10000 assign_full_1_1_3 <= +10000
 full_pair_completion_lb_1_2_1: +1 full_pair_completion_1 -1 full_end_2_1 -10000 assign_full_1_2_1 >= -10000
 full_pair_completion_ub_1_2_1: +1 full_pair_completion_1 -1 full_end_2_1 +10000 assign_full_1_2_1 <= +10000
 full_pair_completion_lb_1_2_2: +1 full_pair_completion_1 -1 full_end_2_2 -10000 assign_full_1_2_2 >= -10000
 full_pair_completion_ub_1_2_2: +1 full_pair_completion_1 -1 full_end_2_2 +10000 assign_full_1_2_2 <= +10000
 full_pair_completion_lb_1_2_3: +1 full_pair_completion_1 -1 full_end_2_3 -10000 assign_full_1_2_3 >= -10000
 full_pair_completion_ub_1_2_3: +1 full_pair_completion_1 -1 full_end_2_3 +10000 assign_full_1_2_3 <= +10000
 full_pair_completion_lb_2_1_1: +1 full_pair_completion_2 -1 full_end_1_1 -10000 assign_full_2_1_1 >= -10000
 full_pair_completion_ub_2_1_1: +1 full_pair_completion_2 -1 full_end_1_1 +10000 assign_full_2_1_1 <= +10000
 full_pair_completion_lb_2_1_2: +1 full_pair_completion_2 -1 full_end_1_2 -10000 assign_full_2_1_2 >= -10000
 full_pair_completion_ub_2_1_2: +1 full_pair_completion_2 -1 full_end_1_2 +10000 assign_full_2_1_2 <= +10000
 full_pair_completion_lb_2_1_3: +1 full_pair_completion_2 -1 full_end_1_3 -10000 assign_full_2_1_3 >= -10000
 full_pair_completion_ub_2_1_3: +1 full_pair_completion_2 -1 full_end_1_3 +10000 assign_full_2_1_3 <= +10000
 full_pair_completion_lb_2_2_1: +1 full_pair_completion_2 -1 full_end_2_1 -10000 assign_full_2_2_1 >= -10000
 full_pair_completion_ub_2_2_1: +1 full_pair_completion_2 -1 full_end_2_1 +10000 assign_full_2_2_1 <= +10000
 full_pair_completion_lb_2_2_2: +1 full_pair_completion_2 -1 full_end_2_2 -10000 assign_full_2_2_2 >= -10000
 full_pair_completion_ub_2_2_2: +1 full_pair_completion_2 -1 full_end_2_2 +10000 assign_full_2_2_2 <= +10000
 full_pair_completion_lb_2_2_3: +1 full_pair_completion_2 -1 full_end_2_3 -10000 assign_full_2_2_3 >= -10000
 full_pair_completion_ub_2_2_3: +1 full_pair_completion_2 -1 full_end_2_3 +10000 assign_full_2_2_3 <= +10000
 mix_pair_completion_lb_1_1_1: +1 mix_pair_completion_1 -1 mix_cycle_end_1_2 -10000 assign_mix_1_1_1 >= -10000
 mix_pair_completion_ub_1_1_1: +1 mix_pair_completion_1 -1 mix_cycle_end_1_2 +10000 assign_mix_1_1_1 <= +10000
 mix_pair_completion_lb_1_1_2: +1 mix_pair_completion_1 -1 mix_cycle_end_1_3 -10000 assign_mix_1_1_2 >= -10000
 mix_pair_completion_ub_1_1_2: +1 mix_pair_completion_1 -1 mix_cycle_end_1_3 +10000 assign_mix_1_1_2 <= +10000
 mix_pair_completion_lb_1_1_3: +1 mix_pair_completion_1 -1 mix_cycle_end_1_4 -10000 assign_mix_1_1_3 >= -10000
 mix_pair_completion_ub_1_1_3: +1 mix_pair_completion_1 -1 mix_cycle_end_1_4 +10000 assign_mix_1_1_3 <= +10000
 mix_pair_completion_lb_1_2_1: +1 mix_pair_completion_1 -1 mix_cycle_end_2_2 -10000 assign_mix_1_2_1 >= -10000
 mix_pair_completion_ub_1_2_1: +1 mix_pair_completion_1 -1 mix_cycle_end_2_2 +10000 assign_mix_1_2_1 <= +10000
 mix_pair_completion_lb_1_2_2: +1 mix_pair_completion_1 -1 mix_cycle_end_2_3 -10000 assign_mix_1_2_2 >= -10000
 mix_pair_completion_ub_1_2_2: +1 mix_pair_completion_1 -1 mix_cycle_end_2_3 +10000 assign_mix_1_2_2 <= +10000
 mix_pair_completion_lb_1_2_3: +1 mix_pair_completion_1 -1 mix_cycle_end_2_4 -10000 assign_mix_1_2_3 >= -10000
 mix_pair_completion_ub_1_2_3: +1 mix_pair_completion_1 -1 mix_cycle_end_2_4 +10000 assign_mix_1_2_3 <= +10000
 mix_pair_completion_lb_2_1_1: +1 mix_pair_completion_2 -1 mix_cycle_end_1_2 -10000 assign_mix_2_1_1 >= -10000
 mix_pair_completion_ub_2_1_1: +1 mix_pair_completion_2 -1 mix_cycle_end_1_2 +10000 assign_mix_2_1_1 <= +10000
 mix_pair_completion_lb_2_1_2: +1 mix_pair_completion_2 -1 mix_cycle_end_1_3 -10000 assign_mix_2_1_2 >= -10000
 mix_pair_completion_ub_2_1_2: +1 mix_pair_completion_2 -1 mix_cycle_end_1_3 +10000 assign_mix_2_1_2 <= +10000
 mix_pair_completion_lb_2_1_3: +1 mix_pair_completion_2 -1 mix_cycle_end_1_4 -10000 assign_mix_2_1_3 >= -10000
 mix_pair_completion_ub_2_1_3: +1 mix_pair_completion_2 -1 mix_cycle_end_1_4 +10000 assign_mix_2_1_3 <= +10000
 mix_pair_completion_lb_2_2_1: +1 mix_pair_completion_2 -1 mix_cycle_end_2_2 -10000 assign_mix_2_2_1 >= -10000
 mix_pair_completion_ub_2_2_1: +1 mix_pair_completion_2 -1 mix_cycle_end_2_2 +10000 assign_mix_2_2_1 <= +10000
 mix_pair_completion_lb_2_2_2: +1 mix_pair_completion_2 -1 mix_cycle_end_2_3 -10000 assign_mix_2_2_2 >= -10000
 mix_pair_completion_ub_2_2_2: +1 mix_pair_completion_2 -1 mix_cycle_end_2_3 +10000 assign_mix_2_2_2 <= +10000
 mix_pair_completion_lb_2_2_3: +1 mix_pair_completion_2 -1 mix_cycle_end_2_4 -10000 assign_mix_2_2_3 >= -10000
 mix_pair_completion_ub_2_2_3: +1 mix_pair_completion_2 -1 mix_cycle_end_2_4 +10000 assign_mix_2_2_3 <= +10000
 mix_pair_completion_lb_3_1_1: +1 mix_pair_completion_3 -1 mix_cycle_end_1_2 -10000 assign_mix_3_1_1 >= -10000
 mix_pair_completion_ub_3_1_1: +1 mix_pair_completion_3 -1 mix_cycle_end_1_2 +10000 assign_mix_3_1_1 <= +10000
 mix_pair_completion_lb_3_1_2: +1 mix_pair_completion_3 -1 mix_cycle_end_1_3 -10000 assign_mix_3_1_2 >= -10000
 mix_pair_completion_ub_3_1_2: +1 mix_pair_completion_3 -1 mix_cycle_end_1_3 +10000 assign_mix_3_1_2 <= +10000
 mix_pair_completion_lb_3_1_3: +1 mix_pair_completion_3 -1 mix_cycle_end_1_4 -10000 assign_mix_3_1_3 >= -10000
 mix_pair_completion_ub_3_1_3: +1 mix_pair_completion_3 -1 mix_cycle_end_1_4 +10000 assign_mix_3_1_3 <= +10000
 mix_pair_completion_lb_3_2_1: +1 mix_pair_completion_3 -1 mix_cycle_end_2_2 -10000 assign_mix_3_2_1 >= -10000
 mix_pair_completion_ub_3_2_1: +1 mix_pair_completion_3 -1 mix_cycle_end_2_2 +10000 assign_mix_3_2_1 <= +10000
 mix_pair_completion_lb_3_2_2: +1 mix_pair_completion_3 -1 mix_cycle_end_2_3 -10000 assign_mix_3_2_2 >= -10000
 mix_pair_completion_ub_3_2_2: +1 mix_pair_completion_3 -1 mix_cycle_end_2_3 +10000 assign_mix_3_2_2 <= +10000
 mix_pair_completion_lb_3_2_3: +1 mix_pair_completion_3 -1 mix_cycle_end_2_4 -10000 assign_mix_3_2_3 >= -10000
 mix_pair_completion_ub_3_2_3: +1 mix_pair_completion_3 -1 mix_cycle_end_2_4 +10000 assign_mix_3_2_3 <= +10000
 wafer_full_completion_lb_1_1: +1 wafer_completion_1 -1 full_pair_completion_1 -10000 wafer_to_full_pair_1_1
  >= -10000
 wafer_full_completion_ub_1_1: +1 wafer_completion_1 -1 full_pair_completion_1 +10000 wafer_to_full_pair_1_1
  <= +10000
 wafer_full_completion_lb_1_2: +1 wafer_completion_1 -1 full_pair_completion_2 -10000 wafer_to_full_pair_1_2
  >= -10000
 wafer_full_completion_ub_1_2: +1 wafer_completion_1 -1 full_pair_completion_2 +10000 wafer_to_full_pair_1_2
  <= +10000
 wafer_full_completion_lb_2_1: +1 wafer_completion_2 -1 full_pair_completion_1 -10000 wafer_to_full_pair_2_1
  >= -10000
 wafer_full_completion_ub_2_1: +1 wafer_completion_2 -1 full_pair_completion_1 +10000 wafer_to_full_pair_2_1
  <= +10000
 wafer_full_completion_lb_2_2: +1 wafer_completion_2 -1 full_pair_completion_2 -10000 wafer_to_full_pair_2_2
  >= -10000
 wafer_full_completion_ub_2_2: +1 wafer_completion_2 -1 full_pair_completion_2 +10000 wafer_to_full_pair_2_2
  <= +10000
 wafer_full_completion_lb_3_1: +1 wafer_completion_3 -1 full_pair_completion_1 -10000 wafer_to_full_pair_3_1
  >= -10000
 wafer_full_completion_ub_3_1: +1 wafer_completion_3 -1 full_pair_completion_1 +10000 wafer_to_full_pair_3_1
  <= +10000
 wafer_full_completion_lb_3_2: +1 wafer_completion_3 -1 full_pair_completion_2 -10000 wafer_to_full_pair_3_2
  >= -10000
 wafer_full_completion_ub_3_2: +1 wafer_completion_3 -1 full_pair_completion_2 +10000 wafer_to_full_pair_3_2
  <= +10000
 wafer_mix_completion_lb_4_1: +1 wafer_completion_4 -1 mix_pair_completion_1 -10000 wafer_to_mix_pair_4_1
  >= -10000
 wafer_mix_completion_ub_4_1: +1 wafer_completion_4 -1 mix_pair_completion_1 +10000 wafer_to_mix_pair_4_1
  <= +10000
 wafer_mix_completion_lb_4_2: +1 wafer_completion_4 -1 mix_pair_completion_2 -10000 wafer_to_mix_pair_4_2
  >= -10000
 wafer_mix_completion_ub_4_2: +1 wafer_completion_4 -1 mix_pair_completion_2 +10000 wafer_to_mix_pair_4_2
  <= +10000
 wafer_mix_completion_lb_4_3: +1 wafer_completion_4 -1 mix_pair_completion_3 -10000 wafer_to_mix_pair_4_3
  >= -10000
 wafer_mix_completion_ub_4_3: +1 wafer_completion_4 -1 mix_pair_completion_3 +10000 wafer_to_mix_pair_4_3
  <= +10000
 wafer_mix_completion_lb_5_1: +1 wafer_completion_5 -1 mix_pair_completion_1 -10000 wafer_to_mix_pair_5_1
  >= -10000
 wafer_mix_completion_ub_5_1: +1 wafer_completion_5 -1 mix_pair_completion_1 +10000 wafer_to_mix_pair_5_1
  <= +10000
 wafer_mix_completion_lb_5_2: +1 wafer_completion_5 -1 mix_pair_completion_2 -10000 wafer_to_mix_pair_5_2
  >= -10000
 wafer_mix_completion_ub_5_2: +1 wafer_completion_5 -1 mix_pair_completion_2 +10000 wafer_to_mix_pair_5_2
  <= +10000
 wafer_mix_completion_lb_5_3: +1 wafer_completion_5 -1 mix_pair_completion_3 -10000 wafer_to_mix_pair_5_3
  >= -10000
 wafer_mix_completion_ub_5_3: +1 wafer_completion_5 -1 mix_pair_completion_3 +10000 wafer_to_mix_pair_5_3
  <= +10000
 wafer_mix_completion_lb_6_1: +1 wafer_completion_6 -1 mix_pair_completion_1 -10000 wafer_to_mix_pair_6_1
  >= -10000
 wafer_mix_completion_ub_6_1: +1 wafer_completion_6 -1 mix_pair_completion_1 +10000 wafer_to_mix_pair_6_1
  <= +10000
 wafer_mix_completion_lb_6_2: +1 wafer_completion_6 -1 mix_pair_completion_2 -10000 wafer_to_mix_pair_6_2
  >= -10000
 wafer_mix_completion_ub_6_2: +1 wafer_completion_6 -1 mix_pair_completion_2 +10000 wafer_to_mix_pair_6_2
  <= +10000
 wafer_mix_completion_lb_6_3: +1 wafer_completion_6 -1 mix_pair_completion_3 -10000 wafer_to_mix_pair_6_3
  >= -10000
 wafer_mix_completion_ub_6_3: +1 wafer_completion_6 -1 mix_pair_completion_3 +10000 wafer_to_mix_pair_6_3
  <= +10000
 wafer_mix_completion_lb_7_1: +1 wafer_completion_7 -1 mix_pair_completion_1 -10000 wafer_to_mix_pair_7_1
  >= -10000
 wafer_mix_completion_ub_7_1: +1 wafer_completion_7 -1 mix_pair_completion_1 +10000 wafer_to_mix_pair_7_1
  <= +10000
 wafer_mix_completion_lb_7_2: +1 wafer_completion_7 -1 mix_pair_completion_2 -10000 wafer_to_mix_pair_7_2
  >= -10000
 wafer_mix_completion_ub_7_2: +1 wafer_completion_7 -1 mix_pair_completion_2 +10000 wafer_to_mix_pair_7_2
  <= +10000
 wafer_mix_completion_lb_7_3: +1 wafer_completion_7 -1 mix_pair_completion_3 -10000 wafer_to_mix_pair_7_3
  >= -10000
 wafer_mix_completion_ub_7_3: +1 wafer_completion_7 -1 mix_pair_completion_3 +10000 wafer_to_mix_pair_7_3
  <= +10000
 wafer_mix_completion_lb_8_1: +1 wafer_completion_8 -1 mix_pair_completion_1 -10000 wafer_to_mix_pair_8_1
  >= -10000
 wafer_mix_completion_ub_8_1: +1 wafer_completion_8 -1 mix_pair_completion_1 +10000 wafer_to_mix_pair_8_1
  <= +10000
 wafer_mix_completion_lb_8_2: +1 wafer_completion_8 -1 mix_pair_completion_2 -10000 wafer_to_mix_pair_8_2
  >= -10000
 wafer_mix_completion_ub_8_2: +1 wafer_completion_8 -1 mix_pair_completion_2 +10000 wafer_to_mix_pair_8_2
  <= +10000
 wafer_mix_completion_lb_8_3: +1 wafer_completion_8 -1 mix_pair_completion_3 -10000 wafer_to_mix_pair_8_3
  >= -10000
 wafer_mix_completion_ub_8_3: +1 wafer_completion_8 -1 mix_pair_completion_3 +10000 wafer_to_mix_pair_8_3
  <= +10000
 cmax_ge_wafer_1: +1 c_max -1 wafer_completion_1 >= +0
 cmax_ge_wafer_2: +1 c_max -1 wafer_completion_2 >= +0
 cmax_ge_wafer_3: +1 c_max -1 wafer_completion_3 >= +0
 cmax_ge_wafer_4: +1 c_max -1 wafer_completion_4 >= +0
 cmax_ge_wafer_5: +1 c_max -1 wafer_completion_5 >= +0
 cmax_ge_wafer_6: +1 c_max -1 wafer_completion_6 >= +0
 cmax_ge_wafer_7: +1 c_max -1 wafer_completion_7 >= +0
 cmax_ge_wafer_8: +1 c_max -1 wafer_completion_8 >= +0
 full_order_symmetry_1_1: +1 assign_full_1_1_1 +2 assign_full_2_1_1 -1 assign_full_1_1_2 -2 assign_full_2_1_2
  +10000 full_slot_used_1_1 +10000 full_slot_used_1_2 <= +20000
 full_order_symmetry_1_2: +1 assign_full_1_1_2 +2 assign_full_2_1_2 -1 assign_full_1_1_3 -2 assign_full_2_1_3
  +10000 full_slot_used_1_2 +10000 full_slot_used_1_3 <= +20000
 mix_order_symmetry_1_1: +1 assign_mix_1_1_1 +2 assign_mix_2_1_1 +3 assign_mix_3_1_1 -1 assign_mix_1_1_2
  -2 assign_mix_2_1_2 -3 assign_mix_3_1_2 +10000 mix_pos_used_1_1 +10000 mix_pos_used_1_2 <= +20000
 mix_order_symmetry_1_2: +1 assign_mix_1_1_2 +2 assign_mix_2_1_2 +3 assign_mix_3_1_2 -1 assign_mix_1_1_3
  -2 assign_mix_2_1_3 -3 assign_mix_3_1_3 +10000 mix_pos_used_1_2 +10000 mix_pos_used_1_3 <= +20000
 full_order_symmetry_2_1: +1 assign_full_1_2_1 +2 assign_full_2_2_1 -1 assign_full_1_2_2 -2 assign_full_2_2_2
  +10000 full_slot_used_2_1 +10000 full_slot_used_2_2 <= +20000
 full_order_symmetry_2_2: +1 assign_full_1_2_2 +2 assign_full_2_2_2 -1 assign_full_1_2_3 -2 assign_full_2_2_3
  +10000 full_slot_used_2_2 +10000 full_slot_used_2_3 <= +20000
 mix_order_symmetry_2_1: +1 assign_mix_1_2_1 +2 assign_mix_2_2_1 +3 assign_mix_3_2_1 -1 assign_mix_1_2_2
  -2 assign_mix_2_2_2 -3 assign_mix_3_2_2 +10000 mix_pos_used_2_1 +10000 mix_pos_used_2_2 <= +20000
 mix_order_symmetry_2_2: +1 assign_mix_1_2_2 +2 assign_mix_2_2_2 +3 assign_mix_3_2_2 -1 assign_mix_1_2_3
  -2 assign_mix_2_2_3 -3 assign_mix_3_2_3 +10000 mix_pos_used_2_2 +10000 mix_pos_used_2_3 <= +20000
 pm_activity_symmetry: +1 full_slot_used_1_1 +1 full_slot_used_1_2 +1 full_slot_used_1_3 +1 mix_pos_used_1_1
  +1 mix_pos_used_1_2 +1 mix_pos_used_1_3 -1 full_slot_used_2_1 -1 full_slot_used_2_2 -1 full_slot_used_2_3
  -1 mix_pos_used_2_1 -1 mix_pos_used_2_2 -1 mix_pos_used_2_3 >= +0
Bounds
 0 <= wafer_to_full_pair_1_1 <= 1
 0 <= wafer_to_full_pair_1_2 <= 1
 0 <= wafer_to_full_pair_2_1 <= 1
 0 <= wafer_to_full_pair_2_2 <= 1
 0 <= wafer_to_full_pair_3_1 <= 1
 0 <= wafer_to_full_pair_3_2 <= 1
 0 <= wafer_to_mix_pair_4_1 <= 1
 0 <= wafer_to_mix_pair_4_2 <= 1
 0 <= wafer_to_mix_pair_4_3 <= 1
 0 <= wafer_to_mix_pair_5_1 <= 1
 0 <= wafer_to_mix_pair_5_2 <= 1
 0 <= wafer_to_mix_pair_5_3 <= 1
 0 <= wafer_to_mix_pair_6_1 <= 1
 0 <= wafer_to_mix_pair_6_2 <= 1
 0 <= wafer_to_mix_pair_6_3 <= 1
 0 <= wafer_to_mix_pair_7_1 <= 1
 0 <= wafer_to_mix_pair_7_2 <= 1
 0 <= wafer_to_mix_pair_7_3 <= 1
 0 <= wafer_to_mix_pair_8_1 <= 1
 0 <= wafer_to_mix_pair_8_2 <= 1
 0 <= wafer_to_mix_pair_8_3 <= 1
 0 <= assign_full_1_1_1 <= 1
 0 <= assign_full_1_1_2 <= 1
 0 <= assign_full_1_1_3 <= 1
 0 <= assign_full_1_2_1 <= 1
 0 <= assign_full_1_2_2 <= 1
 0 <= assign_full_1_2_3 <= 1
 0 <= assign_full_2_1_1 <= 1
 0 <= assign_full_2_1_2 <= 1
 0 <= assign_full_2_1_3 <= 1
 0 <= assign_full_2_2_1 <= 1
 0 <= assign_full_2_2_2 <= 1
 0 <= assign_full_2_2_3 <= 1
 0 <= full_slot_used_1_1 <= 1
 0 <= full_slot_used_1_2 <= 1
 0 <= full_slot_used_1_3 <= 1
 0 <= full_slot_used_2_1 <= 1
 0 <= full_slot_used_2_2 <= 1
 0 <= full_slot_used_2_3 <= 1
 0 <= full_pec_pairs_1_1 <= 1
 0 <= full_pec_pairs_1_2 <= 1
 0 <= full_pec_pairs_1_3 <= 1
 0 <= full_pec_pairs_2_1 <= 1
 0 <= full_pec_pairs_2_2 <= 1
 0 <= full_pec_pairs_2_3 <= 1
 0 <= full_after_mix_1_1 <= 1
 0 <= full_after_mix_1_2 <= 1
 0 <= full_after_mix_1_3 <= 1
 0 <= full_after_mix_2_1 <= 1
 0 <= full_after_mix_2_2 <= 1
 0 <= full_after_mix_2_3 <= 1
 0 <= assign_mix_1_1_1 <= 1
 0 <= assign_mix_1_1_2 <= 1
 0 <= assign_mix_1_1_3 <= 1
 0 <= assign_mix_1_2_1 <= 1
 0 <= assign_mix_1_2_2 <= 1
 0 <= assign_mix_1_2_3 <= 1
 0 <= assign_mix_2_1_1 <= 1
 0 <= assign_mix_2_1_2 <= 1
 0 <= assign_mix_2_1_3 <= 1
 0 <= assign_mix_2_2_1 <= 1
 0 <= assign_mix_2_2_2 <= 1
 0 <= assign_mix_2_2_3 <= 1
 0 <= assign_mix_3_1_1 <= 1
 0 <= assign_mix_3_1_2 <= 1
 0 <= assign_mix_3_1_3 <= 1
 0 <= assign_mix_3_2_1 <= 1
 0 <= assign_mix_3_2_2 <= 1
 0 <= assign_mix_3_2_3 <= 1
 0 <= mix_pos_used_1_1 <= 1
 0 <= mix_pos_used_1_2 <= 1
 0 <= mix_pos_used_1_3 <= 1
 0 <= mix_pos_used_2_1 <= 1
 0 <= mix_pos_used_2_2 <= 1
 0 <= mix_pos_used_2_3 <= 1
 0 <= mix_cycle_used_1_1 <= 1
 0 <= mix_cycle_used_1_2 <= 1
 0 <= mix_cycle_used_1_3 <= 1
 0 <= mix_cycle_used_1_4 <= 1
 0 <= mix_cycle_used_2_1 <= 1
 0 <= mix_cycle_used_2_2 <= 1
 0 <= mix_cycle_used_2_3 <= 1
 0 <= mix_cycle_used_2_4 <= 1
 0 <= mix_active_1 <= 1
 0 <= mix_active_2 <= 1
 0 <= mix_last_cycle_1_1 <= 1
 0 <= mix_last_cycle_1_2 <= 1
 0 <= mix_last_cycle_1_3 <= 1
 0 <= mix_last_cycle_1_4 <= 1
 0 <= mix_last_cycle_2_1 <= 1
 0 <= mix_last_cycle_2_2 <= 1
 0 <= mix_last_cycle_2_3 <= 1
 0 <= mix_last_cycle_2_4 <= 1
Binaries
 wafer_to_full_pair_1_1 wafer_to_full_pair_1_2 wafer_to_full_pair_2_1 wafer_to_full_pair_2_2 wafer_to_full_pair_3_1
 wafer_to_full_pair_3_2 wafer_to_mix_pair_4_1 wafer_to_mix_pair_4_2 wafer_to_mix_pair_4_3 wafer_to_mix_pair_5_1
 wafer_to_mix_pair_5_2 wafer_to_mix_pair_5_3 wafer_to_mix_pair_6_1 wafer_to_mix_pair_6_2 wafer_to_mix_pair_6_3
 wafer_to_mix_pair_7_1 wafer_to_mix_pair_7_2 wafer_to_mix_pair_7_3 wafer_to_mix_pair_8_1 wafer_to_mix_pair_8_2
 wafer_to_mix_pair_8_3 assign_full_1_1_1 assign_full_1_1_2 assign_full_1_1_3 assign_full_1_2_1 assign_full_1_2_2
 assign_full_1_2_3 assign_full_2_1_1 assign_full_2_1_2 assign_full_2_1_3 assign_full_2_2_1 assign_full_2_2_2
 assign_full_2_2_3 full_slot_used_1_1 full_slot_used_1_2 full_slot_used_1_3 full_slot_used_2_1 full_slot_used_2_2
 full_slot_used_2_3 full_pec_pairs_1_1 full_pec_pairs_1_2 full_pec_pairs_1_3 full_pec_pairs_2_1 full_pec_pairs_2_2
 full_pec_pairs_2_3 full_after_mix_1_1 full_after_mix_1_2 full_after_mix_1_3 full_after_mix_2_1 full_after_mix_2_2
 full_after_mix_2_3 assign_mix_1_1_1 assign_mix_1_1_2 assign_mix_1_1_3 assign_mix_1_2_1 assign_mix_1_2_2
 assign_mix_1_2_3 assign_mix_2_1_1 assign_mix_2_1_2 assign_mix_2_1_3 assign_mix_2_2_1 assign_mix_2_2_2
 assign_mix_2_2_3 assign_mix_3_1_1 assign_mix_3_1_2 assign_mix_3_1_3 assign_mix_3_2_1 assign_mix_3_2_2
 assign_mix_3_2_3 mix_pos_used_1_1 mix_pos_used_1_2 mix_pos_used_1_3 mix_pos_used_2_1 mix_pos_used_2_2
 mix_pos_used_2_3 mix_cycle_used_1_1 mix_cycle_used_1_2 mix_cycle_used_1_3 mix_cycle_used_1_4 mix_cycle_used_2_1
 mix_cycle_used_2_2 mix_cycle_used_2_3 mix_cycle_used_2_4 mix_active_1 mix_active_2 mix_last_cycle_1_1
 mix_last_cycle_1_2 mix_last_cycle_1_3 mix_last_cycle_1_4 mix_last_cycle_2_1 mix_last_cycle_2_2 mix_last_cycle_2_3
 mix_last_cycle_2_4
End
