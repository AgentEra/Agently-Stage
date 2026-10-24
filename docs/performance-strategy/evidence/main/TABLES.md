# 全配置描述统计

自动复算；筛选决策由报告解释，不由脚本自动认定。区间为五轮极值，非置信区间。

| ID / 配置 | wall ms（中位/最小–最大） | CPU ms | 平均核数 | P99 ms |
|---|---:|---:|---:|---:|
| boundary-026da205c8bd `{"count": 50000, "group": "boundary", "iterations": 1, "language": "rust", "mode": "each"}` | 7.756 / 7.612–9.362 | 7.667 | 1.00 | — |
| boundary-62673c4db119 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "go", "mode": "batch"}` | 0.041 / 0.039–0.102 | 0.059 | 1.31 | — |
| boundary-6c5c2d2c1c52 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "go", "mode": "each"}` | 9.722 / 9.663–14.393 | 9.819 | 1.01 | — |
| boundary-cd381f1ba0e3 `{"count": 50000, "group": "boundary", "iterations": 1, "language": "rust", "mode": "batch"}` | 0.021 / 0.018–0.036 | 0.031 | 1.53 | — |
| broadcast-0a7fa7479f82 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 8, "wake": "local"}` | 309.527 / 309.470–309.900 | 24.582 | 0.08 | 0.553 |
| broadcast-0b5b5ef03f94 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 1, "wake": "baseline"}` | 2.099 / 1.867–2.341 | 2.066 | 0.98 | 1.281 |
| broadcast-18e400040fcb `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 8, "wake": "baseline"}` | 5.911 / 5.784–6.185 | 5.901 | 1.00 | 4.952 |
| broadcast-1a4abcbdfe29 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 32, "wake": "local"}` | 84.302 / 79.801–114.158 | 67.008 | 0.79 | 0.119 |
| broadcast-2ab8de08fceb `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 1, "wake": "local"}` | 2.045 / 1.822–2.293 | 1.979 | 0.98 | 1.063 |
| broadcast-2b501dbc1f72 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 8, "wake": "local"}` | 41.710 / 38.457–50.713 | 24.173 | 0.58 | 0.07 |
| broadcast-31d0d2912f21 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 8, "wake": "grouped"}` | 6.034 / 5.958–6.187 | 5.976 | 0.99 | 5.165 |
| broadcast-331d1ce5b7de `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 32, "wake": "baseline"}` | 20.085 / 19.815–26.632 | 19.916 | 0.99 | 18.679 |
| broadcast-3ac8e32899c1 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 8, "wake": "baseline"}` | 309.354 / 309.352–309.402 | 17.123 | 0.06 | 0.285 |
| broadcast-451c8b2c351e `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 32, "wake": "baseline"}` | 309.730 / 309.711–309.776 | 42.062 | 0.14 | 0.452 |
| broadcast-4cc28145437b `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 8, "wake": "local"}` | 309.366 / 309.358–309.485 | 16.633 | 0.05 | 0.316 |
| broadcast-56f22d2da485 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 1, "wake": "grouped"}` | 309.394 / 309.341–309.709 | 13.792 | 0.04 | 0.587 |
| broadcast-5b0177946260 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 32, "wake": "local"}` | 309.743 / 309.714–309.817 | 41.882 | 0.14 | 0.524 |
| broadcast-6151c9da3a02 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 8, "wake": "local"}` | 6.109 / 5.791–8.779 | 6.098 | 0.99 | 5.115 |
| broadcast-64fcfade53b7 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 1, "wake": "local"}` | 309.247 / 309.240–309.304 | 13.696 | 0.04 | 0.263 |
| broadcast-73221d082759 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 1, "wake": "grouped"}` | 23.712 / 19.188–29.755 | 13.265 | 0.56 | 0.104 |
| broadcast-75672444e470 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 1, "wake": "local"}` | 309.369 / 309.340–309.498 | 12.238 | 0.04 | 0.371 |
| broadcast-78472779021f `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 1, "wake": "grouped"}` | 2.097 / 2.007–3.233 | 2.052 | 0.97 | 1.227 |
| broadcast-7875d8307d0c `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 32, "wake": "local"}` | 309.924 / 309.730–310.826 | 38.527 | 0.12 | 0.609 |
| broadcast-7a7ed615e626 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 8, "wake": "baseline"}` | 309.462 / 309.454–309.582 | 27.851 | 0.09 | 0.41 |
| broadcast-7befbb2326b7 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 32, "wake": "grouped"}` | 309.783 / 309.717–310.070 | 36.432 | 0.12 | 0.418 |
| broadcast-84f388b0e775 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 32, "wake": "local"}` | 19.731 / 19.197–20.163 | 19.513 | 0.99 | 18.305 |
| broadcast-8b33dc6e32fc `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "thread", "readers": 32, "wake": "grouped"}` | 20.978 / 19.149–22.159 | 20.525 | 0.98 | 19.6 |
| broadcast-9a64cdf2a034 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 8, "wake": "grouped"}` | 309.451 / 309.333–309.473 | 16.510 | 0.05 | 0.389 |
| broadcast-a27d3e12e41d `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 32, "wake": "baseline"}` | 102.876 / 94.658–141.783 | 91.697 | 0.89 | 0.201 |
| broadcast-a5c3a49a0e0c `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 1, "wake": "baseline"}` | 23.342 / 19.166–45.384 | 13.766 | 0.58 | 0.049 |
| broadcast-b91aeacae042 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 8, "wake": "grouped"}` | 39.258 / 31.643–56.094 | 28.576 | 0.73 | 0.126 |
| broadcast-c5330cb6334b `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 8, "wake": "baseline"}` | 37.238 / 35.002–46.288 | 28.485 | 0.76 | 0.067 |
| broadcast-d8325e07e870 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 1, "wake": "grouped"}` | 309.260 / 309.233–309.433 | 15.803 | 0.05 | 0.346 |
| broadcast-db9b8c5e8140 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 32, "wake": "baseline"}` | 309.989 / 309.878–310.290 | 57.579 | 0.19 | 0.623 |
| broadcast-dd5cb62dd20d `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 1, "wake": "local"}` | 26.476 / 25.425–27.954 | 9.446 | 0.36 | 0.053 |
| broadcast-e4f9d388d00d `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 1, "wake": "baseline"}` | 309.342 / 309.320–309.638 | 16.366 | 0.05 | 0.462 |
| broadcast-ea688bbe5168 `{"count": 1500, "group": "broadcast", "interval": 0, "producer": "loop", "readers": 32, "wake": "grouped"}` | 84.755 / 75.185–128.437 | 74.173 | 0.88 | 0.176 |
| broadcast-ed7e1c814112 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 8, "wake": "grouped"}` | 309.364 / 309.343–309.468 | 21.845 | 0.07 | 0.365 |
| broadcast-f5dcd1f0907c `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "thread", "readers": 32, "wake": "grouped"}` | 309.849 / 309.635–311.166 | 32.971 | 0.11 | 0.54 |
| broadcast-fed6117bc6c6 `{"count": 300, "group": "broadcast", "interval": 0.001, "producer": "loop", "readers": 1, "wake": "baseline"}` | 309.300 / 309.217–309.581 | 15.276 | 0.05 | 0.28 |
| callbacks-a25d8246860e `{"count": 64, "group": "callbacks", "iterations": 20000, "workers": 4}` | 89.983 / 88.496–104.483 | 89.326 | 0.99 | — |
| callbacks-fc9bcfb73d14 `{"count": 64, "group": "callbacks", "iterations": 20000, "workers": 1}` | 90.642 / 84.959–115.783 | 90.458 | 0.99 | — |
| carrier-28dec13e576c `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 1, "scopes": 1}` | 46.433 / 35.415–51.737 | 48.389 | 1.02 | — |
| carrier-44e9bf8786ce `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 1, "scopes": 16}` | 39.469 / 36.384–40.700 | 39.929 | 1.02 | — |
| carrier-4a3cd8b23f13 `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 2, "scopes": 1}` | 110.101 / 103.407–166.977 | 112.435 | 1.02 | — |
| carrier-610563c7b0e3 `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 1, "scopes": 16}` | 111.634 / 109.537–152.409 | 112.821 | 1.01 | — |
| carrier-7ecd15957618 `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 4, "scopes": 1}` | 111.903 / 100.357–133.201 | 112.110 | 1.00 | — |
| carrier-7efcd4173606 `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 2, "scopes": 16}` | 115.790 / 107.064–157.576 | 117.294 | 1.01 | — |
| carrier-916280c89429 `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 4, "scopes": 1}` | 40.772 / 38.224–74.462 | 41.614 | 1.01 | — |
| carrier-9d4dbcd95f2d `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 4, "scopes": 16}` | 113.274 / 109.197–133.871 | 116.223 | 1.02 | — |
| carrier-b98deca5e393 `{"count": 1000, "group": "carrier", "kind": "cpu", "lanes": 1, "scopes": 1}` | 116.154 / 108.314–158.799 | 115.431 | 0.99 | — |
| carrier-b9e86057a211 `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 2, "scopes": 16}` | 43.429 / 40.961–49.891 | 45.671 | 1.05 | — |
| carrier-e372d58a847c `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 2, "scopes": 1}` | 37.817 / 36.920–40.591 | 39.189 | 1.05 | — |
| carrier-ea3b0cfb76ad `{"count": 1000, "group": "carrier", "kind": "io", "lanes": 4, "scopes": 16}` | 43.182 / 40.503–57.246 | 47.056 | 1.06 | — |
| compute-008345123c15 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "thread", "workers": 4}` | 227.144 / 226.113–259.357 | 226.815 | 1.00 | — |
| compute-0241f817ae98 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "process", "workers": 1}` | 220.341 / 211.498–312.896 | 223.508 | 1.01 | — |
| compute-06393ac26b94 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "thread", "workers": 4}` | 59.172 / 58.346–65.951 | 231.954 | 3.91 | — |
| compute-099faa7494bb `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "thread", "workers": 8}` | 232.612 / 215.173–255.903 | 232.881 | 0.98 | — |
| compute-0fef945c3656 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "thread", "workers": 1}` | 236.850 / 220.405–307.395 | 234.716 | 0.99 | — |
| compute-101ba4b66a6d `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "process", "workers": 2}` | 16.171 / 15.176–22.238 | 26.675 | 1.59 | — |
| compute-15f45c378a22 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "process", "workers": 4}` | 18.629 / 17.532–21.388 | 31.193 | 1.66 | — |
| compute-1d31599164bb `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "thread", "workers": 2}` | 51.926 / 51.214–61.090 | 102.637 | 1.98 | — |
| compute-31279681685f `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "process", "workers": 4}` | 65.812 / 64.325–79.152 | 256.892 | 3.85 | — |
| compute-334aac77879c `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "process", "workers": 4}` | 28.385 / 27.206–38.342 | 110.758 | 3.95 | — |
| compute-3a6d1bda0c4f `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "thread", "workers": 2}` | 2.749 / 2.603–4.886 | 2.732 | 0.99 | — |
| compute-4a1dec74846b `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "stage", "workers": 2}` | 54.450 / 52.135–66.011 | 109.869 | 2.00 | — |
| compute-553a8a9f497a `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "process", "workers": 1}` | 16.500 / 14.086–28.260 | 24.753 | 1.50 | — |
| compute-569211603e3b `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "thread", "workers": 1}` | 103.139 / 101.326–106.398 | 103.202 | 1.00 | — |
| compute-57a4bbdfae57 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "stage", "workers": 1}` | 109.863 / 102.186–133.383 | 112.602 | 1.02 | — |
| compute-5a7630c970b1 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "thread", "workers": 8}` | 18.824 / 16.759–19.360 | 127.303 | 6.83 | — |
| compute-5b1d23695ec1 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "thread", "workers": 1}` | 2.535 / 2.382–3.824 | 2.553 | 1.00 | — |
| compute-5bfb6df82a9d `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "stage", "workers": 1}` | 14.482 / 12.669–18.165 | 14.655 | 1.04 | — |
| compute-6fff268df87f `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "thread", "workers": 8}` | 2.887 / 2.495–3.640 | 2.871 | 0.99 | — |
| compute-86d1385ab735 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "stage", "workers": 8}` | 12.449 / 11.613–17.779 | 12.778 | 1.04 | — |
| compute-9b9a204eddd1 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "thread", "workers": 4}` | 28.773 / 26.272–31.854 | 109.362 | 3.85 | — |
| compute-9d64ae7e3c8c `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "thread", "workers": 1}` | 232.004 / 230.846–266.013 | 231.241 | 0.99 | — |
| compute-a28fd6b6d890 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "stage", "workers": 4}` | 236.079 / 223.951–271.816 | 235.024 | 1.00 | — |
| compute-a2f82aad3460 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "thread", "workers": 4}` | 2.713 / 2.528–3.981 | 2.704 | 1.00 | — |
| compute-a769b17c87a8 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "stage", "workers": 4}` | 30.664 / 29.805–37.192 | 116.868 | 3.76 | — |
| compute-a98f3960096f `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "process", "workers": 2}` | 121.333 / 115.619–157.652 | 242.711 | 1.99 | — |
| compute-b65ed99a1b2b `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "stage", "workers": 8}` | 233.565 / 227.176–290.978 | 232.731 | 1.00 | — |
| compute-c50a9d6d43a0 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "thread", "workers": 2}` | 227.567 / 219.458–231.619 | 226.944 | 1.00 | — |
| compute-ccc5e51f85d2 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "process", "workers": 2}` | 52.997 / 51.931–66.714 | 108.123 | 2.03 | — |
| compute-d14a43c73ae0 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "stage", "workers": 4}` | 13.476 / 11.845–15.603 | 14.303 | 1.04 | — |
| compute-d3dd20e9a486 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "stage", "workers": 1}` | 244.164 / 220.357–252.003 | 236.888 | 1.00 | — |
| compute-d9ab77842be7 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "go", "mode": "thread", "workers": 4}` | 60.006 / 59.117–60.767 | 234.780 | 3.93 | — |
| compute-dd253ce300e4 `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "process", "workers": 8}` | 36.238 / 35.395–45.373 | 267.027 | 7.37 | — |
| compute-de46958538ff `{"count": 32, "group": "compute", "iterations": 100000, "kind": "python", "mode": "stage", "workers": 2}` | 227.372 / 210.713–297.226 | 227.066 | 1.00 | — |
| compute-e27d233e5813 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "process", "workers": 1}` | 104.306 / 102.570–134.946 | 107.732 | 1.03 | — |
| compute-ee153474f972 `{"count": 32, "group": "compute", "iterations": 5000000, "kind": "rust", "mode": "thread", "workers": 1}` | 232.326 / 226.848–254.963 | 231.502 | 1.00 | — |
| compute-f1ab9f69d47d `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "process", "workers": 8}` | 15.872 / 15.685–16.744 | 118.274 | 7.47 | — |
| compute-f58c0b1eef2e `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "stage", "workers": 2}` | 12.653 / 11.620–17.439 | 13.206 | 1.03 | — |
| compute-f8680b74cc31 `{"count": 256, "group": "compute", "iterations": 64, "kind": "python", "mode": "process", "workers": 8}` | 16.561 / 16.084–21.421 | 30.442 | 1.81 | — |
| compute-fa3bdefdd683 `{"count": 32, "group": "compute", "iterations": 50000, "kind": "hash", "mode": "stage", "workers": 8}` | 18.674 / 16.872–19.330 | 124.475 | 6.67 | — |
| dispatch-1c3cb01603b4 `{"count": 2000, "delay": 0, "group": "dispatch", "mode": "asyncio"}` | 6.898 / 6.862–7.145 | 6.833 | 0.99 | — |
| dispatch-3dc342c54e97 `{"count": 2000, "delay": 0.001, "group": "dispatch", "mode": "carrier_batch"}` | 17.784 / 16.314–20.065 | 17.537 | 0.99 | — |
| dispatch-492c56b7e89f `{"count": 2000, "delay": 0, "group": "dispatch", "loop": "uvloop", "mode": "caller"}` | 58.039 / 53.764–71.636 | 57.398 | 0.99 | — |
| dispatch-57bbcbfd1151 `{"count": 2000, "delay": 0.001, "group": "dispatch", "mode": "carrier_each"}` | 116.591 / 84.167–125.534 | 115.460 | 1.02 | — |
| dispatch-76652aeaeada `{"count": 2000, "delay": 0, "group": "dispatch", "loop": "uvloop", "mode": "asyncio"}` | 4.394 / 4.002–7.908 | 4.350 | 0.99 | — |
| dispatch-7951b6c89e9c `{"count": 2000, "delay": 0, "group": "dispatch", "mode": "carrier_each"}` | 95.617 / 84.970–102.014 | 101.279 | 1.06 | — |
| dispatch-9c318a7c2d3f `{"count": 2000, "delay": 0, "group": "dispatch", "mode": "carrier_batch"}` | 12.920 / 12.073–13.904 | 12.783 | 0.99 | — |
| dispatch-def9050366d0 `{"count": 2000, "delay": 0.001, "group": "dispatch", "mode": "caller"}` | 86.195 / 74.818–102.517 | 85.094 | 0.99 | — |
| dispatch-e1f2838db853 `{"count": 2000, "delay": 0, "group": "dispatch", "mode": "caller"}` | 83.648 / 75.970–111.282 | 82.724 | 0.99 | — |
| dispatch-e8863c5e7f4a `{"count": 2000, "delay": 0.001, "group": "dispatch", "mode": "asyncio"}` | 11.402 / 11.024–16.113 | 11.314 | 0.99 | — |
| mixed-56ac7ec88b08 `{"group": "mixed", "mode": "split"}` | 357.720 / 351.302–364.028 | 22.028 | 0.06 | 1.278 |
| mixed-edd2e78daf55 `{"group": "mixed", "mode": "shared"}` | 280.523 / 275.667–288.574 | 23.915 | 0.09 | 259.639 |
| replay-04ab5e66b4f0 `{"count": 10000, "group": "replay", "mode": "sync", "storage": "chunk"}` | 4.631 / 4.497–5.476 | 4.607 | 1.00 | — |
| replay-04c6add65d3d `{"count": 10000, "group": "replay", "mode": "sync", "storage": "list"}` | 2.697 / 2.624–2.905 | 2.691 | 1.00 | — |
| replay-17d1e78e7384 `{"count": 100000, "group": "replay", "mode": "async", "storage": "deque"}` | 86.720 / 79.004–98.484 | 82.626 | 0.99 | — |
| replay-28401f5ba1e7 `{"count": 1000, "group": "replay", "mode": "async", "storage": "deque"}` | 0.706 / 0.592–0.986 | 0.635 | 0.90 | — |
| replay-3b660676a80a `{"count": 100000, "group": "replay", "mode": "sync", "storage": "chunk"}` | 46.725 / 45.279–63.572 | 46.472 | 0.99 | — |
| replay-4339c54d50a8 `{"count": 10000, "group": "replay", "mode": "async", "storage": "deque"}` | 3.773 / 3.596–4.149 | 3.709 | 0.98 | — |
| replay-514ab78b9945 `{"count": 10000, "group": "replay", "mode": "sync", "storage": "deque"}` | 2.970 / 2.942–4.041 | 2.971 | 1.00 | — |
| replay-62525dae9195 `{"count": 1000, "group": "replay", "mode": "sync", "storage": "list"}` | 0.331 / 0.314–0.347 | 0.335 | 1.01 | — |
| replay-64b783beadfc `{"count": 10000, "group": "replay", "mode": "async", "storage": "chunk"}` | 5.237 / 5.110–6.045 | 5.170 | 0.99 | — |
| replay-77098fe092a5 `{"count": 100000, "group": "replay", "mode": "sync", "storage": "deque"}` | 80.147 / 60.761–108.857 | 75.115 | 0.97 | — |
| replay-80fdce3f7efa `{"count": 1000, "group": "replay", "mode": "sync", "storage": "deque"}` | 0.328 / 0.318–0.534 | 0.335 | 1.02 | — |
| replay-909a12eeea86 `{"count": 100000, "group": "replay", "mode": "async", "storage": "chunk"}` | 51.360 / 48.588–52.700 | 50.566 | 0.99 | — |
| replay-929b36c6225f `{"count": 1000, "group": "replay", "mode": "async", "storage": "list"}` | 0.619 / 0.580–0.874 | 0.551 | 0.89 | — |
| replay-9ca877f98faf `{"count": 100000, "group": "replay", "mode": "sync", "storage": "list"}` | 26.669 / 25.916–29.449 | 26.348 | 0.99 | — |
| replay-a395be68a71c `{"count": 10000, "group": "replay", "mode": "async", "storage": "list"}` | 3.581 / 3.236–3.743 | 3.438 | 0.97 | — |
| replay-ad04aad6ca92 `{"count": 1000, "group": "replay", "mode": "sync", "storage": "chunk"}` | 0.546 / 0.530–0.568 | 0.545 | 1.01 | — |
| replay-b59d052b57d6 `{"count": 1000, "group": "replay", "mode": "async", "storage": "chunk"}` | 0.995 / 0.792–1.662 | 0.887 | 0.92 | — |
| replay-b5f4716cfd7e `{"count": 100000, "group": "replay", "mode": "async", "storage": "list"}` | 35.785 / 31.120–43.278 | 33.683 | 0.94 | — |
