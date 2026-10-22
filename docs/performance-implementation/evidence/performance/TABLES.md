# 本轮性能对照全表

五次独立进程配对，变体次序交替；耗时均为 ms。改善为逐轮百分比的中位数，非中位耗时之比。

|case|指标|基线/默认中位数|候选中位数|配对改善|改善轮数|
|---|---|---|---|---|---|
|0: default / {'kind': 'replay', 'count': 1000, 'mode': 'sync'}|wall_s|0.313|0.317|-0.4%|2/5|
|0: default / {'kind': 'replay', 'count': 1000, 'mode': 'sync'}|fill_s|0.431|0.382|13.1%|5/5|
|0: default / {'kind': 'replay', 'count': 1000, 'mode': 'sync'}|cpu_s|0.766|0.703|7.8%|5/5|
|1: default / {'kind': 'replay', 'count': 1000, 'mode': 'async'}|wall_s|0.606|0.619|3.8%|3/5|
|1: default / {'kind': 'replay', 'count': 1000, 'mode': 'async'}|fill_s|0.427|0.375|11.5%|5/5|
|1: default / {'kind': 'replay', 'count': 1000, 'mode': 'async'}|cpu_s|0.976|0.931|8.1%|4/5|
|2: default / {'kind': 'replay', 'count': 10000, 'mode': 'sync'}|wall_s|2.917|2.642|8.7%|5/5|
|2: default / {'kind': 'replay', 'count': 10000, 'mode': 'sync'}|fill_s|3.904|3.459|13.3%|5/5|
|2: default / {'kind': 'replay', 'count': 10000, 'mode': 'sync'}|cpu_s|6.962|6.159|11.2%|5/5|
|3: default / {'kind': 'replay', 'count': 10000, 'mode': 'async'}|wall_s|3.558|3.279|7.3%|5/5|
|3: default / {'kind': 'replay', 'count': 10000, 'mode': 'async'}|fill_s|3.930|3.433|12.4%|5/5|
|3: default / {'kind': 'replay', 'count': 10000, 'mode': 'async'}|cpu_s|7.514|6.753|9.9%|5/5|
|4: default / {'kind': 'replay', 'count': 100000, 'mode': 'sync'}|wall_s|64.781|25.500|60.1%|5/5|
|4: default / {'kind': 'replay', 'count': 100000, 'mode': 'sync'}|fill_s|37.552|34.277|9.4%|5/5|
|4: default / {'kind': 'replay', 'count': 100000, 'mode': 'sync'}|cpu_s|103.104|60.695|42.0%|5/5|
|5: default / {'kind': 'replay', 'count': 100000, 'mode': 'async'}|wall_s|69.110|31.822|51.8%|5/5|
|5: default / {'kind': 'replay', 'count': 100000, 'mode': 'async'}|fill_s|38.745|34.417|10.6%|4/5|
|5: default / {'kind': 'replay', 'count': 100000, 'mode': 'async'}|cpu_s|108.813|66.841|36.5%|5/5|
|6: default / {'kind': 'replay', 'count': 100000, 'limit': 128, 'mode': 'sync'}|wall_s|0.072|0.072|10.6%|3/5|
|6: default / {'kind': 'replay', 'count': 100000, 'limit': 128, 'mode': 'sync'}|fill_s|44.510|41.921|5.3%|5/5|
|6: default / {'kind': 'replay', 'count': 100000, 'limit': 128, 'mode': 'sync'}|cpu_s|44.529|41.931|5.3%|5/5|
|7: default / {'kind': 'replay', 'count': 100000, 'limit': 10000, 'mode': 'sync'}|wall_s|2.973|2.907|2.1%|4/5|
|7: default / {'kind': 'replay', 'count': 100000, 'limit': 10000, 'mode': 'sync'}|fill_s|46.438|42.123|9.3%|5/5|
|7: default / {'kind': 'replay', 'count': 100000, 'limit': 10000, 'mode': 'sync'}|cpu_s|49.081|44.997|8.3%|5/5|
|8: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|wall_s|5.122|5.005|3.1%|4/5|
|8: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|wall_s|5.005|4.956|1.7%|3/5|
|8: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|cpu_s|3.050|2.893|4.9%|4/5|
|8: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|cpu_s|2.893|2.893|3.1%|3/5|
|8: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|p99_s|0.036|0.037|19.5%|3/5|
|8: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0}|p99_s|0.037|0.038|-1.2%|2/5|
|9: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|wall_s|409.290|409.311|-0.0%|2/5|
|9: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|wall_s|409.311|409.437|-0.0%|2/5|
|9: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|cpu_s|18.221|18.800|-0.0%|2/5|
|9: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|cpu_s|18.800|25.285|-20.8%|2/5|
|9: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|p99_s|0.231|0.249|-1.5%|2/5|
|9: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'loop', 'interval': 0.001}|p99_s|0.249|0.381|-60.1%|1/5|
|10: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|wall_s|409.499|409.540|-0.0%|2/5|
|10: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|wall_s|409.540|409.463|0.0%|3/5|
|10: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|cpu_s|24.137|26.663|9.7%|3/5|
|10: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|cpu_s|26.663|23.886|0.5%|3/5|
|10: default / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|p99_s|0.491|0.437|-4.7%|2/5|
|10: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 1, 'producer': 'thread', 'interval': 0.001}|p99_s|0.437|0.517|-0.7%|2/5|
|11: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|wall_s|11.743|10.751|8.4%|4/5|
|11: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|wall_s|10.751|9.227|13.4%|5/5|
|11: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|cpu_s|9.715|8.806|9.9%|4/5|
|11: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|cpu_s|8.806|7.340|15.6%|5/5|
|11: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|p99_s|0.131|0.086|24.1%|4/5|
|11: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0}|p99_s|0.086|0.078|10.7%|4/5|
|12: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|wall_s|409.396|409.523|-0.0%|1/5|
|12: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|wall_s|409.523|409.441|0.0%|4/5|
|12: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|cpu_s|34.846|40.067|-16.7%|1/5|
|12: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|cpu_s|40.067|32.076|15.1%|4/5|
|12: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|p99_s|0.553|0.496|13.9%|3/5|
|12: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'loop', 'interval': 0.001}|p99_s|0.496|0.561|-13.1%|2/5|
|13: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|wall_s|409.668|409.689|-0.0%|1/5|
|13: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|wall_s|409.689|409.682|0.0%|3/5|
|13: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|cpu_s|49.918|63.569|-7.6%|1/5|
|13: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|cpu_s|63.569|40.316|29.8%|4/5|
|13: default / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|p99_s|0.693|0.633|3.1%|4/5|
|13: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 8, 'producer': 'thread', 'interval': 0.001}|p99_s|0.633|0.596|-1.2%|2/5|
|14: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|wall_s|24.680|24.925|-0.0%|2/5|
|14: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|wall_s|24.925|19.797|20.4%|5/5|
|14: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|cpu_s|23.323|23.542|0.3%|3/5|
|14: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|cpu_s|23.542|18.520|21.4%|5/5|
|14: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|p99_s|0.129|0.138|-7.2%|1/5|
|14: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0}|p99_s|0.138|0.104|21.1%|5/5|
|15: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|wall_s|409.813|409.738|0.0%|4/5|
|15: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|wall_s|409.738|409.774|-0.0%|2/5|
|15: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|cpu_s|85.509|82.674|-0.2%|2/5|
|15: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|cpu_s|82.674|65.985|23.9%|5/5|
|15: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|p99_s|0.645|0.614|4.7%|4/5|
|15: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'loop', 'interval': 0.001}|p99_s|0.614|0.511|14.2%|4/5|
|16: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|wall_s|410.141|410.168|0.0%|3/5|
|16: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|wall_s|410.168|410.027|0.1%|3/5|
|16: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|cpu_s|114.986|108.564|2.4%|3/5|
|16: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|cpu_s|108.564|78.527|28.4%|5/5|
|16: default / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|p99_s|0.792|0.709|5.6%|4/5|
|16: grouped / {'kind': 'broadcast', 'count': 400, 'readers': 32, 'producer': 'thread', 'interval': 0.001}|p99_s|0.709|0.644|36.5%|4/5|
