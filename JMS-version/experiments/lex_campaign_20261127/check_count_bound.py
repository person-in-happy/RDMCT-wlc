"""独立复核 16 片等量混合实例在两种卸片顺序均允许时的工期下界。

任一腔室如分到 f 片 4×1 和 m 片 2×2，至少需 u=⌈f/4⌉ 个 4×1
周期和 v=⌈m/2⌉ 对含产品的 2×2 晶圆对。每个 2×2 对在同腔连续
加工两次，每周期最多一对产品开始第一次曝光。连续的 t 个混合周期
最多容纳 t−1 个开始曝光的产品对，因为末周期不能再开始。两次清洁之间
至多有 H 个生产周期，所以至少有 ⌈v/(H−1)⌉ 段混合周期，合计至少
w=v+⌈v/(H−1)⌉ 个混合周期。分段计数只给必要条件，未固定实际排程。

在首末生产周期之间至少有 k=max(0,⌊(u+w−1)/H⌋) 次清洁。故本腔
从首个生产开始到末个生产结束至少需 180u+90w+500k 秒。每个生产周期
都含产品。首个生产最早于第 76 秒开始，末个生产结束后其产品至少再用
40 秒回片。枚举两腔所有分配，取较慢腔耗时，再对分配取最小，是全域
物理下界。该计数允许理想配对，省略资源争用、非必需等待和末端清洁。
使计数最小的产品分配只属于这个放松问题，不证明设备排程可以达到该值。
"""
import hashlib
import json
from itertools import product
from pathlib import Path

JMS = Path(__file__).resolve().parents[2]
CAMPAIGN = "lex_campaign_20261127"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chamber(full, mixed, h, cfg):
    u = (full + 3) // 4
    pairs = (mixed + 1) // 2
    w = pairs + (pairs + h - 2) // (h - 1)
    k = max(0, (u + w - 1) // h)
    return u*cfg["full_time"] + w*cfg["mix_time"] + k*cfg["cleaning_time"]


def calculate(cfg, h):
    if (len(cfg["chambers"]) != 2 or h <= 1 or cfg["max_pairs"] or cfg["max_cycles"] or
            [sum(p[r] for p in cfg["load_ports"].values()) for r in ("4x1", "2x2")] != [8, 8]):
        raise ValueError("This audit requires two chambers and 8+8 products.")
    a, t = cfg["atr_handling"], cfg["atr_travel"]
    v, s = cfg["handling"], cfg["vtr_travel"]
    lead = 4*a + 2*t + cfg["alignment"] + cfg["pump"] + 2*v + s
    tail = 2*v + s + cfg["vent"] + 2*a + t
    exposure = min(cfg["full_time"], 2*cfg["mix_time"])
    after_aligner = t + a + cfg["pump"] + 2*v + s + exposure + tail
    aligner = a + t + 16*(2*a + cfg["alignment"]) + after_aligner
    splits = [(max(chamber(f, m, h, cfg), chamber(8-f, 8-m, h, cfg)), f, m)
              for f, m in product(range(9), repeat=2)]
    window = min(row[0] for row in splits)
    return dict(h=h, splits_enumerated=len(splits), min_max_chamber_seconds=window,
                minimizing_splits_4x1_2x2=[[[f,m],[8-f,8-m]] for val,f,m in splits if val == window],
                first_production_lead_s=lead, product_return_tail_s=tail,
                count_bound_s=lead+window+tail, aligner_bound_s=aligner,
                combined_external_bound_s=max(lead+window+tail, aligner))


if __name__ == "__main__":
    frozen = "results/table3_mixed16_20261125/input.json"
    cfg = json.loads((JMS / frozen).read_bytes())["config"]
    # The extended model inherits the cycle, label and physical-resource rules.
    evidence = [frozen, "model4_pjob_nonprocessing_20261103/joint_chamber_cycle_model.py",
                "model4_pjob_nonprocessing_20261103/joint_pairing_model.py",
                "experiments/terminal_unload_20261125/extended_model.py",
                "results/terminal_unload_20261125/product_bound/derivation.md"]
    result = dict(scope="external, independent chamber-count relaxation for extended unload",
                  initial_registered_A_bound_s=716, used_by_formal_solver=False,
                  sources={s: digest(JMS/s) for s in evidence}, script_sha256=digest(Path(__file__)),
                  cases=[calculate(cfg, h) for h in (3, 10)])
    target = JMS / "results" / CAMPAIGN / "external_count_bound.json"
    data = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if target.exists() and json.loads(target.read_bytes()) != result:
        raise ValueError("A different external audit exists at the target.")
    if not target.exists():
        target.parent.mkdir(exist_ok=True, parents=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf8")
        tmp.replace(target)
    for row in result["cases"]:
        print(f"H={row['h']} count={row['count_bound_s']} combined={row['combined_external_bound_s']} "
              f"splits={row['minimizing_splits_4x1_2x2']}")
