# Workspace Query Adapter 与 Unified Command Boundary 实施计划

1. 先以契约测试固定 ProjectionEnvelope、OperationsSnapshot、查询 DTO、刷新状态与命令状态。

最终状态：已完成。workspace、integration、projection 测试及静态校验通过。
2. 实现只读查询协议与 Adapter，确保仅依赖 ProjectionReader。
3. 实现 Event → section 映射和可诊断、可 retry 的刷新协调器。
4. 实现通用 CommandRequest/Result、幂等缓存、版本冲突和测试 handler。
5. 添加跨层契约测试并运行定向测试、全量 pytest、compileall、git diff --check。

每一步遵循 TDD：先写测试并确认预期失败，再写最小实现，保持依赖方向为 query/refresh/command → projection/runtime/domain ports。
