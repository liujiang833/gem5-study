"""
第二章 2.4 配套用例：CHI 协议下"共享 L2 vs 私有 L2"对 DDR 带宽的影响

对比两种缓存层级（在相同的 L2 总容量预算下）：
  * private : stdlib 自带的 PrivateL1PrivateL2CacheHierarchy
              —— 每核一个私有 L2，每个大小 = --l2-size-per-core
  * shared  : 本章自定义的 PrivateL1SharedL2CacheHierarchy
              —— 全体核心共享一个 L2，大小 = (核数 x --l2-size-per-core)

这样两种配置的 L2 硅面积预算相同，差异仅在"私有还是共享"，
从而干净地隔离出"共享"本身带来的收益。

工作负载：多线程整数矩阵乘法 igemm（C = A x B，512x512x512）。
4 个线程读同一个 B —— B 是跨核复用的共享数据。

用法（需先构建 CHI 版 gem5，ARM 默认即 CHI）：
    scons build/ARM/gem5.opt -j$(nproc)

    # 交叉编译工作负载
    aarch64-linux-gnu-gcc -O2 -static -pthread \
        -DN=512 -DNTHREADS=4 jl-tutorials/ch2/igemm.c -o jl-tutorials/ch2/igemm

    # 共享 L2（4 x 512KiB = 2MiB 共享）
    ./build/ARM/gem5.opt --outdir=m5out/shared \
        jl-tutorials/ch2/chi_l2_experiment.py \
        --l2-mode shared --num-cores 4 \
        --l2-size-per-core 512KiB --binary jl-tutorials/ch2/igemm

    # 私有 L2（每核 512KiB，合计同样 2MiB）
    ./build/ARM/gem5.opt --outdir=m5out/private \
        jl-tutorials/ch2/chi_l2_experiment.py \
        --l2-mode private --num-cores 4 \
        --l2-size-per-core 512KiB --binary jl-tutorials/ch2/igemm

随后对比两个 m5out/*/stats.txt 中的 DRAM 字节数（见 2.4.5）。
"""

import argparse

from gem5.coherence_protocol import CoherenceProtocol
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.chi.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.memory import SingleChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

from chi_shared_l2_hierarchy import PrivateL1SharedL2CacheHierarchy


def parse_size(s: str) -> int:
    """把 '512KiB'/'2MiB' 之类的字符串解析成字节数，用于换算共享 L2 容量。"""
    s = s.strip()
    units = {"KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "B": 1}
    for u in ("KiB", "MiB", "GiB", "B"):
        if s.endswith(u):
            return int(float(s[: -len(u)]) * units[u])
    return int(s)


parser = argparse.ArgumentParser(description="CHI 共享/私有 L2 带宽对比实验")
parser.add_argument(
    "--l2-mode", choices=["shared", "private"], default="shared"
)
parser.add_argument("--num-cores", type=int, default=4)
parser.add_argument(
    "--l2-size-per-core",
    type=str,
    default="512KiB",
    help="每核 L2 容量预算；共享模式下共享 L2 = 核数 x 该值",
)
parser.add_argument("--l2-assoc", type=int, default=8)
parser.add_argument("--l1d-size", type=str, default="32KiB")
parser.add_argument("--l1i-size", type=str, default="32KiB")
parser.add_argument("--l1-assoc", type=int, default=8)
parser.add_argument("--mem-size", type=str, default="512MiB")
parser.add_argument(
    "--binary",
    type=str,
    required=True,
    help="静态链接的 ARM igemm 二进制路径",
)
args = parser.parse_args()

requires(
    isa_required=ISA.ARM,
    coherence_protocol_required=CoherenceProtocol.CHI,
)

# ── 缓存层级：根据 l2-mode 选择，并保持 L2 总容量一致 ──────────
if args.l2_mode == "shared":
    shared_l2_bytes = parse_size(args.l2_size_per_core) * args.num_cores
    cache_hierarchy = PrivateL1SharedL2CacheHierarchy(
        l1i_size=args.l1i_size,
        l1i_assoc=args.l1_assoc,
        l1d_size=args.l1d_size,
        l1d_assoc=args.l1_assoc,
        l2_size=f"{shared_l2_bytes}B",
        l2_assoc=args.l2_assoc,
    )
else:
    cache_hierarchy = PrivateL1PrivateL2CacheHierarchy(
        l1i_size=args.l1i_size,
        l1i_assoc=args.l1_assoc,
        l1d_size=args.l1d_size,
        l1d_assoc=args.l1_assoc,
        l2_size=args.l2_size_per_core,
        l2_assoc=args.l2_assoc,
    )

# ── 内存：单通道 DDR4-2400 ────────────────────────────────────
memory = SingleChannelDDR4_2400(size=args.mem_size)

# ── 处理器：多核 Timing CPU（SE 模式 + pthreads 多线程）──────
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    isa=ISA.ARM,
    num_cores=args.num_cores,
)

# ── 板级 ──────────────────────────────────────────────────────
board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# ── 工作负载：本地交叉编译的 igemm，传入线程数 = 核数 ─────────
board.set_se_binary_workload(
    binary=BinaryResource(local_path=args.binary),
    arguments=[str(args.num_cores)],
)

simulator = Simulator(board=board)
simulator.run()

print("=" * 64)
print(f"L2 模式: {args.l2_mode}  核数: {args.num_cores}")
print(f"仿真 Tick 数: {simulator.get_current_tick()}")
print("查看 DRAM 字节数: grep -E 'dramBytesRead|dramBytesWritten' "
      "<outdir>/stats.txt")
print("=" * 64)
