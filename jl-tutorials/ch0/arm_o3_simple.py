"""
第零章配套用例：ARM O3CPU + 私有 L1 缓存系统

搭建一个最小化的 ARM 乱序处理器系统，运行简单测试程序，
理解 stats.txt 中关键统计量的含义。

用法：
    # 编译 gem5（仅需一次）
    scons build/ARM/gem5.opt -j$(nproc)

    # 运行仿真
    ./build/ARM/gem5.opt jl-tutorials/ch0/arm_o3_simple.py
"""

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

requires(isa_required=ISA.ARM)

# ── 缓存层级 ──────────────────────────────────────────────
# 私有 L1：32 KiB I-Cache + 32 KiB D-Cache
cache_hierarchy = PrivateL1CacheHierarchy(
    l1d_size="32KiB",
    l1i_size="32KiB",
    l1d_assoc=8,
    l1i_assoc=8,
)

# ── 内存 ──────────────────────────────────────────────────
memory = SingleChannelDDR3_1600(size="256MiB")

# ── 处理器 ────────────────────────────────────────────────
# 使用 O3CPU（乱序核心），单核
processor = SimpleProcessor(
    cpu_type=CPUTypes.O3,
    isa=ISA.ARM,
    num_cores=1,
)

# ── 板级 ──────────────────────────────────────────────────
board = SimpleBoard(
    clk_freq="2GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# ── 工作负载 ──────────────────────────────────────────────
# 使用 gem5-resources 提供的 ARM hello world 静态链接程序
board.set_se_binary_workload(
    obtain_resource("arm-hello64-static", resource_version="1.0.0")
)

# ── 运行 ──────────────────────────────────────────────────
simulator = Simulator(board=board)
simulator.run()

print("=" * 60)
print("仿真完成！")
print(f"仿真 Tick 数: {simulator.get_current_tick()}")
print(f"统计文件位于: m5out/stats.txt")
print("=" * 60)
