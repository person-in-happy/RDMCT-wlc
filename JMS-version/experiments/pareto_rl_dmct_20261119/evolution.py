"""NSGA-II environmental selection and MOEA/D Tchebycheff replacement for integer schedules."""
import math


def ranks(population):
    from common import dominates
    size = len(population)
    dominates_ids = [[] for _ in population]
    counts = [0]*size
    for i,x in enumerate(population):
        for j in range(i):
            y = population[j]
            if dominates(x[1],y[1]):
                dominates_ids[i].append(j)
                counts[j] += 1
            elif dominates(y[1],x[1]):
                dominates_ids[j].append(i)
                counts[i] += 1
    front = [i for i,c in enumerate(counts) if c==0]
    rank, crowd = [0]*size,[0.]*size
    level = 0
    while front:
        nxt = []
        for i in front:
            rank[i] = level
            for j in dominates_ids[i]:
                counts[j] -= 1
                if counts[j]==0:
                    nxt.append(j)
        for k in range(2):
            ids = sorted(front,key=lambda i:population[i][1][k])
            span = population[ids[-1]][1][k]-population[ids[0]][1][k]
            if span>0:
                crowd[ids[0]] = crowd[ids[-1]] = math.inf
                for j in range(1,len(ids)-1):
                    crowd[ids[j]] += (population[ids[j+1]][1][k]-population[ids[j-1]][1][k])/span
        front,level = nxt,level+1
    return list(zip(rank,[-v for v in crowd]))


def run_evolution(search, method, end):
    rng = search.rng
    size = 16
    limits = search.limits+(18,)
    initial = search.initial
    def score(g):
        level = g[-1]
        goal = "B" if level==0 else "A"
        cap = None if level in (0,17) else search.floor+(search.initial_b-search.floor)*level/17
        pair = search.evaluate(g[:-1],goal,cap,False,end)
        return (g,pair) if pair is not None else None
    base = (initial+(17,),search.initial_ab)
    pop = [base]
    while len(pop)<size and search.remaining(end)>.04:
        g = tuple(rng.randrange(v) for v in limits)
        pop.append(score(g) or base)
    if len(pop)!=size:
        return
    weights = [(max(1e-5,i/(size-1)),max(1e-5,1-i/(size-1))) for i in range(size)]
    neighbors = [sorted(range(size),key=lambda i:abs(i-j))[:5] for j in range(size)]
    ideal = [min(v[1][k] for v in pop) for k in range(2)]
    def mate(a,b):
        return tuple(rng.randrange(lim) if rng.random()<1/len(limits) else
                     (x if rng.random()<.5 else y) for x,y,lim in zip(a,b,limits))
    while search.remaining(end)>.04:
        order = list(range(size))
        rng.shuffle(order)
        if method=="nsga2":
            keys = ranks(pop)
            def tournament():
                a,b = rng.sample(range(size),2)
                return pop[a if keys[a]<keys[b] or keys[a]==keys[b] and rng.random()<.5 else b][0]
            offspring = []
            for _ in order:
                if search.remaining(end)<.04:
                    break
                child = score(mate(tournament(),tournament()))
                if child:
                    offspring.append(child)
            combined = pop+offspring
            sort_keys = ranks(combined)
            pop = [combined[j] for j in sorted(range(len(combined)),key=sort_keys.__getitem__)[:size]]
        else:
            for j in order:
                if search.remaining(end)<.04:
                    break
                a,b = rng.sample(neighbors[j],2)
                child = score(mate(pop[a][0],pop[b][0]))
                if not child:
                    continue
                for k in range(2):
                    ideal[k] = min(ideal[k],child[1][k])
                for i in neighbors[j]:
                    def tcheby(obj):
                        return max(w*abs(o-z)/max(s,1) for o,w,z,s in zip(obj,weights[i],ideal,search.initial_ab))
                    if tcheby(child[1])<=tcheby(pop[i][1]):
                        pop[i] = child
