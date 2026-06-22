"""
第二章配套 demo：用 CHI 协议跑单核 SE 程序 (hello)，配合
--debug-flags=ProtocolTrace 抓取一次 load miss 的
L1 -> L2 -> HNF(directory) -> SNF(memory) -> DRAM -> 返回 全过程。

层级用 gem5 v25.1 stdlib 自带的 CHI
``PrivateL1PrivateL2CacheHierarchy``（每核私有 split L1 + 私有 L2，
单一集中式 HNF 目录，内存通道对应 SNF）。

运行（工作目录必须是 CHI 版 gem5 源码根）：
  cd /home/rivers/projects/micro-architecture-study/gem5
  ./build/ARM/gem5.opt \
      --outdir=/home/rivers/projects/gem5-tutorials/ch2/m5out_trace \
      --debug-flags=ProtocolTrace \
      --debug-file=protocol_trace.txt \
      /home/rivers/projects/gem5-tutorials/gem5-study/jl-tutorials/ch2/chi_trace_demo.py
"""

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.chi.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.memory.single_channel import SingleChannelDDR4_2400
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator

# --- CHI 缓存层级：所有构造参数全部必填 ---
cache_hierarchy = PrivateL1PrivateL2CacheHierarchy(
    l1i_size="32KiB",
    l1i_assoc=8,
    l1d_size="32KiB",
    l1d_assoc=8,
    l2_size="256KiB",
    l2_assoc=8,
)

# --- 内存（SNF 背后的 DRAM）---
memory = SingleChannelDDR4_2400(size="512MiB")

# --- 单核 Timing CPU，ARM ISA ---
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    num_cores=1,
    isa=ISA.ARM,
)

# --- 主板 ---
board = SimpleBoard(
    clk_freq="1GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# --- SE 工作负载：预编译 ARM 静态 hello ---
board.set_se_binary_workload(
    BinaryResource(
        "/home/rivers/projects/micro-architecture-study/gem5/tests/test-progs/hello/bin/arm/linux/hello"
    )
)

# --- 仿真 ---
simulator = Simulator(board=board)
# hello 很短，会自然 exit；max_ticks 仅作为 trace 大小上限的保险。
simulator.run(max_ticks=20_000_000)

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(),
        simulator.get_last_exit_event_cause(),
    )
)
