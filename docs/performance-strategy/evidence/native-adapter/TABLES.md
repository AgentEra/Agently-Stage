# 全配置描述统计

自动复算；筛选决策由报告解释，不由脚本自动认定。区间为五轮极值，非置信区间。

| ID / 配置 | wall ms（中位/最小–最大） | CPU ms | 平均核数 | P99 ms |
|---|---:|---:|---:|---:|
| boundary-026da205c8bd `{"count": 50000, "group": "boundary", "iterations": 1, "language": "rust", "mode": "each"}` | 8.889 / 7.786–11.521 | 8.834 | 0.99 | — |
| boundary-62673c4db119 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "go", "mode": "batch"}` | 0.039 / 0.039–0.054 | 0.050 | 1.26 | — |
| boundary-6c5c2d2c1c52 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "go", "mode": "each"}` | 10.518 / 9.747–11.568 | 10.426 | 0.99 | — |
| boundary-cd381f1ba0e3 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "rust", "mode": "batch"}` | 0.018 / 0.018–0.019 | 0.027 | 1.42 | — |
| callbacks-a25d8246860e `{"count": 64, "group": "callbacks", "iterations": 20000, "workers": 4}` | 95.979 / 92.081–104.021 | 95.540 | 1.00 | — |
| callbacks-fc9bcfb73d14 `{"count": 64, "group": "callbacks", "iterations": 20000, "workers": 1}` | 97.640 / 93.624–100.322 | 95.943 | 0.98 | — |
| compute-06393ac26b94 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "thread", "workers": 4}` | 61.207 / 59.553–63.828 | 234.467 | 3.84 | — |
| compute-54b51caa5ee7 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "stage", "workers": 4}` | 63.402 / 61.169–65.449 | 239.237 | 3.81 | — |
| compute-59b55697a5ec `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "stage", "workers": 1}` | 241.251 / 237.502–247.431 | 240.946 | 1.00 | — |
| compute-69e7fdcf0782 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "stage", "workers": 4}` | 62.994 / 60.860–64.568 | 239.100 | 3.82 | — |
| compute-9d64ae7e3c8c `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "thread", "workers": 1}` | 240.521 / 230.195–244.053 | 237.111 | 0.99 | — |
| compute-d9ab77842be7 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "thread", "workers": 4}` | 61.189 / 60.861–63.659 | 236.672 | 3.88 | — |
| compute-ee153474f972 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "thread", "workers": 1}` | 238.650 / 232.763–253.091 | 233.419 | 0.98 | — |
| compute-ef6203ce452f `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "stage", "workers": 1}` | 242.096 / 230.920–249.587 | 238.406 | 0.99 | — |
