import json,time,os
rows=[]
for _ in range(100):
    rows.append([time.monotonic_ns(),time.perf_counter_ns()])
    time.sleep(.001)
print(json.dumps({'pid':os.getpid(),'monotonic':vars(time.get_clock_info('monotonic')),'perf_counter':vars(time.get_clock_info('perf_counter')),'samples':rows}))
