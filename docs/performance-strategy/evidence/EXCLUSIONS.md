# 预检与排除记录

- `preflight/` 是每类一个配置的一轮连通性预检，不参与五轮性能汇总。不是完整候选正确性验收。
- `candidate-tests.txt` 首次候选测试：10通过、2失败。失败来自测试把 `retained_range` 属性写为方法；deque基线与chunk候选均同样失败。修正测试调用，不改候选或生产实现；复验另存 `candidate-tests-final.txt`。
- 未删除慢性能样本；正式样本的失败/超时由runner明确记录，不以成功样本覆盖。
- 首轮 `main/` 640次中620有效、20失败。4个Stage+原生函数配置各5次均出现 `_classify_task` 对ctypes函数递归的 `RecursionError`。它们是兼容性缺口证据，不纳入性能汇总。`main/source/`保留原脚本；不修改Stage，改用普通Python函数包装native调用，在Stage和直接thread两臂都使用相同包装；`native-adapter/`重新运行完整14配置×5轮原生组。所有H8性能比较使用新组，不能将旧direct结果与新Stage结果混比。
