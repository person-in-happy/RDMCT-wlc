"""Pjob event model with an optional product-first unload at an emptying boundary.

Run this module with an instance JSON to export a makespan MILP or a process
MIQCP. The archived Pjob backend supplies routes, identity and robot capacity.
"""
import argparse
import json
from pathlib import Path
import sys

JMS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JMS / "model4_pjob_nonprocessing_20261103"))
from model import Config, Integrated as PjobModel
from scip_imports import scip


class Integrated(PjobModel):
    def chambers(self):
        cy, cfg, model = self.cy, self.cfg, self.model
        self.product_first = {}
        for c in cfg.chambers:
            for q in range(self.Q):
                used = cy.used[c, q]
                keep = self.bit(f"carry_{c}_{q}")
                tail = self.bit(f"tail_{c}_{q}")
                model.addCons(keep == sum(cy.occupancy[p,c,q] - cy.first[p,c,q] for p in range(self.P)))
                model.addCons(tail == used - sum(cy.occupancy[p,c,q] - cy.last[p,c,q] for p in range(self.P)))
                self.keep[c,q], self.tail[c,q] = keep, tail
                flip = self.bit(f"product_first_{c}_{q}")
                self.product_first[c,q] = flip
                model.addCons(flip <= tail)
                self.rot_before[c,q] = before = self.rotation_event("before", c, q, used)
                self.rot_after[c,q] = between = self.rotation_event("after", c, q, tail)
                first_turn = self.rotation_event("priority", c, q, flip)
                self.ge(first_turn["s"], cy.end[c,q], flip)
                self.ge(between["s"], cy.end[c,q], tail)
                if q:
                    self.ge(before["s"], cy.end[c,q-1], keep)
                fronts = []
                for p in range(self.P):
                    occ, first, last = cy.occupancy[p,c,q], cy.first[p,c,q], cy.last[p,c,q]
                    front = self.bit(f"front_{p}_{c}_{q}")
                    self.front[p,c,q] = front
                    fronts.append(front)
                    model.addCons(front <= first)
                    model.addCons(front <= occ)
                    if q:
                        model.addCons(self.front[p,c,q-1] >= occ-first)
                    model.addCons(front >= cy.product_pair[p] + cy.kind[c,q,"2x2"] + occ - 2 - keep)
                    load, unload = self.load[p], self.unload[p]
                    self.ge(cy.start[c,q], load["e"], occ)
                    self.ge(unload["s"], cy.end[c,q], occ)
                    self.ge(before["s"], load["e"], first-front)
                    self.ge(load["s"], before["e"], front)
                    self.eq(cy.start[c,q], load["e"], front)
                    back = occ-front
                    back_tail = self.and_(back, tail, f"bt_{p}_{c}_{q}")
                    front_exit = front-(occ-last)
                    # At a chain end the back pair carries product. Only a
                    # pure auxiliary front may be deferred behind that pair.
                    model.addCons(flip <= 2-front-cy.product_pair[p])
                    model.addCons(flip <= 1-back+cy.product_pair[p])
                    self.ge(between["s"], unload["e"], front_exit-flip)
                    self.ge(unload["s"], between["e"], back_tail-flip)
                    self.ge(unload["s"], first_turn["e"], back_tail+flip-1)
                    self.ge(between["s"], unload["e"], back_tail+flip-1)
                    self.ge(unload["s"], between["e"], front_exit+flip-1)
                    if q+1 < self.Q:
                        self.vars["out",p,c,q] = back-back_tail
                model.addCons(sum(fronts) == used)
        for c in cfg.chambers:
            for q in range(1,self.Q):
                empty = self.cont(f"empty_boundary_{c}_{q}")
                exchanged = self.cont(f"exchange_boundary_{c}_{q}")
                for p in range(self.P):
                    out = self.vars["out",p,c,q-1]
                    self.ge(self.unload[p]["s"], self.rot_before[c,q]["e"], out)
                    self.ge(exchanged, self.unload[p]["e"], out)
                    self.ge(empty, self.unload[p]["e"], cy.last[p,c,q-1])
                for p in range(self.P):
                    incoming = cy.first[p,c,q]
                    self.ge(self.load[p]["s"], exchanged, incoming)
                    self.ge(self.load[p]["s"], empty, incoming-self.keep[c,q])
        for p in range(self.P):
            self.ge(self.unload[p]["s"], self.load[p]["e"], self.pair.active[p])
            processing = (cfg.full_time*self.pair.mode[p,"4x1"]
                          + cfg.mix_time*(2 if p < self.N else 1)*self.pair.mode[p,"2x2"]
                          + cfg.cleaning_time*self.pair.mode[p,"clean"])
            model.addCons(self.unload[p]["s"]-self.load[p]["e"]-processing
                          <= cfg.module_residency+self.M*(1-self.pair.active[p]))

    def rotation_event(self, phase, c, q, active):
        return self.event(f"rot_{phase}_{c}_{q}", "rotate", None, active,
                          {f"CH{c}": 1}, self.cfg.rotation, chamber=c, cycle=q)

    def minimize_process_score(self, delta=1.0, gamma=1.0):
        if delta <= 0 or gamma < 0:
            raise ValueError("Expected delta > 0 and gamma >= 0")
        m, cfg = self.model, self.cfg
        spread = self.cont("residence_spread")
        modes = sorted({group.mode for group in self.groups})
        limits = {mode: (self.cont(f"res_low_{mode}"), self.cont(f"res_high_{mode}")) for mode in modes}
        for low, high in limits.values():
            m.addCons(spread >= high-low)
        residence = []
        duration = {"2x2": 2*cfg.mix_time, "4x1": cfg.full_time}
        for job in self.jobs.values():
            if job["product"] is None:
                continue
            p, r = job["product"]
            flags = {mode: scip.quicksum(self.pair.member[g.identifier,p,r] for g in self.groups if g.mode == mode)
                     for mode in modes}
            dwell = job["unload_s"] - job["load_e"] - scip.quicksum(duration[k]*v for k,v in flags.items())
            residence.append(dwell)
            for mode, active in flags.items():
                low, high = limits[mode]
                self.ge(dwell, low, active)
                self.ge(high, dwell, active)
        deficits = []
        for c in cfg.chambers:
            for q in range(1,self.Q):
                clean = self.cy.kind[c,q,"clean"]
                prior = self.cy.counter[c,q-1]
                h = cfg.cleaning_interval
                deficit = m.addVar(lb=0, ub=h, name=f"unused_{c}_{q}")
                m.addCons(deficit <= h*clean)
                m.addCons(deficit >= h*clean-prior)
                m.addCons(deficit <= h-prior+h*(1-clean))
                deficits.append(deficit)
        penalty = m.addVar(lb=0, name="spread_penalty")
        m.addCons(spread*spread <= 2*delta*penalty)
        score = scip.quicksum(residence)/self.N + penalty + gamma*scip.quicksum(deficits)
        m.setObjective(score, "minimize")
        return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path, help="SCIP model file, for example instance.cip")
    parser.add_argument("--objective", choices=["makespan","process"], default="makespan")
    parser.add_argument("--cap", type=float)
    parser.add_argument("--gamma", type=float, default=1.)
    args = parser.parse_args()
    settings = json.loads(args.config.read_text(encoding="utf-8-sig"))
    instance = Integrated(Config(**settings.get("config", settings)))
    if args.cap is not None:
        instance.model.addCons(instance.cmax <= args.cap)
    if args.objective == "process":
        instance.minimize_process_score(gamma=args.gamma)
    instance.model.writeProblem(str(args.output))
