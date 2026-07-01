"""
第三章 3.2 配套用例：HBM2 vs DDR4 内存带宽对比

同一个合成流量发生器分别压测两种内存，在完全相同的注入负载下对比可达带宽，
凸显 HBM 相对 DDR 的架构差异（伪通道、BL4、更高的通道并行度）。

对比对象（均为"一个物理通道"的口径，各暴露 1 个内存端口，可直连）：
  * ddr4 : 单通道 DDR4-2400（8x8）
           峰值 ≈ 2400 MT/s x 8 B = 19.2 GB/s，1 个 MemCtrl + 1 个 DRAMInterface
  * hbm  : 一个 HBM2 物理通道 = 2 个伪通道
           峰值 ≈ 2 x 64 bit x 2000 MT/s / 8 = 32 GB/s，
           由 HBMCtrl 管理两个 DRAMInterface（dram / dram_2，按地址 bit6 分流）

生成器以远超两者峰值的速率注入（默认 100GiB/s），因此实测带宽 = 各自的
可达上限。random 模式还能顺带对比两者在低局部性下的表现差异。

用法：
    scons build/ARM/gem5.opt -j$(nproc)

    ./build/ARM/gem5.opt --outdir=m5out/ddr4 \
        jl-tutorials/ch3/mem_compare.py --mem ddr4 --pattern linear
    ./build/ARM/gem5.opt --outdir=m5out/hbm \
        jl-tutorials/ch3/mem_compare.py --mem hbm  --pattern linear

    # 对比两个 outdir 的 avgRdBWSys（HBMCtrl 有两个伪通道，需把 pc0/pc1 相加）
    grep -E 'avgRdBWSys|avgWrBWSys' m5out/ddr4/stats.txt m5out/hbm/stats.txt
"""

import argparse

from gem5.components.boards.test_board import TestBoard
from gem5.components.memory import SingleChannelDDR4_2400
from gem5.components.memory.dram_interfaces.hbm import HBM_2000_4H_1x64
from gem5.components.memory.hbm import HighBandwidthMemory
from gem5.components.processors.linear_generator import LinearGenerator
from gem5.components.processors.random_generator import RandomGenerator
from gem5.simulate.simulator import Simulator

parser = argparse.ArgumentParser(description="HBM2 vs DDR4 带宽对比")
parser.add_argument("--mem", choices=["ddr4", "hbm"], default="ddr4")
parser.add_argument(
    "--pattern", choices=["linear", "random"], default="linear"
)
parser.add_argument("--rd-perc", type=int, default=100)
parser.add_argument("--rate", type=str, default="100GiB/s")
parser.add_argument("--duration", type=str, default="0.5ms")
args = parser.parse_args()

# ── 内存：两种口径都是"一个物理通道"，各暴露 1 个内存端口 ──────
if args.mem == "ddr4":
    memory = SingleChannelDDR4_2400(size="1GiB")
else:
    # HighBandwidthMemory(interface, num_channels=1, interleaving=128B)
    # → 1 个物理通道 / 2 个伪通道，由 HBMCtrl 管理
    memory = HighBandwidthMemory(HBM_2000_4H_1x64, 1, 128)

max_addr = memory.get_size()
if args.pattern == "linear":
    generator = LinearGenerator(
        duration=args.duration, rate=args.rate,
        block_size=64, max_addr=max_addr, rd_perc=args.rd_perc,
    )
else:
    generator = RandomGenerator(
        duration=args.duration, rate=args.rate,
        block_size=64, max_addr=max_addr, rd_perc=args.rd_perc,
    )

board = TestBoard(
    clk_freq="3GHz",
    generator=generator,
    memory=memory,
    cache_hierarchy=None,
)

simulator = Simulator(board=board)
simulator.run()

print("=" * 64)
print(f"mem={args.mem}  pattern={args.pattern}  rd_perc={args.rd_perc}")
print("查看带宽：grep -E 'avgRdBWSys|avgWrBWSys' <outdir>/stats.txt")
print("  DDR4 只有一个 dram；HBM 有 mem_ctrl.dram 与 mem_ctrl.dram_2 两个伪通道，"
      "总带宽需把两者相加。")
print("=" * 64)
