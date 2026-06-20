"""
第二章 2.1 / 2.3 配套用例：ARM + Ruby(MESI_Two_Level) 两级缓存系统

用 stdlib 的 MESITwoLevelCacheHierarchy 搭建私有 L1 + 共享 L2 的
Ruby 系统，用于观察 Sequencer 路径（2.1）与 L1/L2 缓存统计（2.3）。

注意：本例使用 MESI_Two_Level 一致性协议，需要专门构建该协议的
二进制（ARM 默认构建的是 CHI 协议）：

    scons build/ARM_MESI_Two_Level/gem5.opt PROTOCOL=MESI_Two_Level -j$(nproc)

运行：
    ./build/ARM_MESI_Two_Level/gem5.opt \
        jl-tutorials/ch2/ruby_mesi_two_level.py

观察 Sequencer / Ruby 行为（2.1）：
    ./build/ARM_MESI_Two_Level/gem5.opt \
        --debug-flags=RubySequencer,ProtocolTrace \
        jl-tutorials/ch2/ruby_mesi_two_level.py 2>&1 | head -200
"""

from gem5.coherence_protocol import CoherenceProtocol
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import (
    MESITwoLevelCacheHierarchy,
)
from gem5.components.memory import SingleChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

requires(
    isa_required=ISA.ARM,
    coherence_protocol_required=CoherenceProtocol.MESI_TWO_LEVEL,
)

# ── 缓存层级：私有 L1（32KiB I + 32KiB D）+ 共享 L2（256KiB）──
cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1i_size="32KiB",
    l1i_assoc=8,
    l1d_size="32KiB",
    l1d_assoc=8,
    l2_size="256KiB",
    l2_assoc=16,
    num_l2_banks=1,
)

memory = SingleChannelDDR4_2400(size="512MiB")

processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    isa=ISA.ARM,
    num_cores=1,
)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

board.set_se_binary_workload(
    obtain_resource("arm-hello64-static", resource_version="1.0.0")
)

simulator = Simulator(board=board)
simulator.run()

print("=" * 60)
print("Ruby MESI_Two_Level 仿真完成")
print(f"仿真 Tick 数: {simulator.get_current_tick()}")
print("L1/L2 统计见 m5out/stats.txt 中 board.cache_hierarchy.ruby_system.*")
print("=" * 60)
