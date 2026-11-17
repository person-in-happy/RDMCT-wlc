import json
import psutil

processes = list(psutil.process_iter())
for p in processes:
    try:
        p.cpu_percent(None)
    except psutil.Error:
        pass
total = psutil.cpu_percent(2)
rows = []
for p in processes:
    try:
        rows.append(dict(pid=p.pid, name=p.name(), cpu=p.cpu_percent(None),
                         rss_gib=round(p.memory_info().rss / 1024**3, 3)))
    except psutil.Error:
        pass
print(json.dumps(dict(cpu_percent=total, logical_cpus=psutil.cpu_count(),
                     available_gib=psutil.virtual_memory().available / 1024**3,
                     top=sorted(rows, key=lambda r: r['cpu'], reverse=True)[:10]), indent=2))
