"""
第三章 3.1 配套用例：DDR4 DRAM 控制器行为扫描

用一个合成流量发生器（Traffic Generator）直接压测单通道 DDR4-2400，
把 CPU/缓存完全撇开，从而干净地隔离出 **DRAM 控制器 + 器件时序** 本身的行为。

可扫描的三个维度：
  * --pattern   linear | random
        linear  = 顺序地址流 → 极高的 row-buffer 命中率（同一行连续访问）
        random  = 随机地址流 → 几乎每次访问都要 precharge+activate 换行
  * --page-policy   open_adaptive | open | close | close_adaptive
        决定一次 burst 之后是否立即关闭（precharge）row buffer。
  * --addr-mapping  RoRaBaCoCh | RoRaBaChCo | RoCoRaBaCh
        决定物理地址如何切分成 rank/bank/row/col —— 影响 bank 级并行度。
  * --rd-perc   读请求百分比（100=纯读，0=纯写，50=读写混合观察总线掉头）

生成器以远高于 DDR4 峰值的速率（默认 100GiB/s）注入请求，因此瓶颈必然落在
DRAM 上，stats.txt 里的 avgRdBWSys / readRowHits 就直接反映器件行为。

用法（DDR4 实验与协议无关，任何 ARM 二进制均可；此处用合成流量，无需工作负载）：
    scons build/ARM/gem5.opt -j$(nproc)

    # 顺序 vs 随机，观察 open_adaptive 下 row-buffer 命中率的天壤之别
    ./build/ARM/gem5.opt --outdir=m5out/ddr_lin \
        jl-tutorials/ch3/dram_sweep.py --pattern linear
    ./build/ARM/gem5.opt --outdir=m5out/ddr_rnd \
        jl-tutorials/ch3/dram_sweep.py --pattern random

    # 随机流量下对比 open vs close 页策略
    ./build/ARM/gem5.opt --outdir=m5out/ddr_rnd_close \
        jl-tutorials/ch3/dram_sweep.py --pattern random --page-policy close

关键统计量（见 3.1.8）：
    grep -E 'avgRdBWSys|avgWrBWSys|readRowHitRate|pageHitRate|bytesPerActivate' \
        <outdir>/stats.txt
    # readRowHitRate = readRowHits / readBursts，直接反映 row-buffer 局部性
"""

import argparse

from gem5.components.boards.test_board import TestBoard
from gem5.components.memory.dram_interfaces.ddr4 import DDR4_2400_8x8
from gem5.components.memory.memory import ChanneledMemory
from gem5.components.processors.linear_generator import LinearGenerator
from gem5.components.processors.random_generator import RandomGenerator
from gem5.simulate.simulator import Simulator

parser = argparse.ArgumentParser(description="DDR4-2400 控制器行为扫描")
parser.add_argument(
    "--pattern", choices=["linear", "random"], default="linear"
)
parser.add_argument(
    "--page-policy",
    choices=["open_adaptive", "open", "close", "close_adaptive"],
    default="open_adaptive",
)
parser.add_argument(
    "--addr-mapping",
    choices=["RoRaBaCoCh", "RoRaBaChCo", "RoCoRaBaCh"],
    default="RoRaBaCoCh",
)
parser.add_argument("--rd-perc", type=int, default=100)
parser.add_argument("--rate", type=str, default="100GiB/s")
parser.add_argument("--duration", type=str, default="0.5ms")
parser.add_argument("--mem-size", type=str, default="1GiB")
args = parser.parse_args()

# ── 内存：单通道 DDR4-2400（8x8 DIMM），可指定地址映射 ──────────
# ChanneledMemory(interface_class, num_channels=1, interleaving_size=64B)
memory = ChanneledMemory(
    DDR4_2400_8x8,
    1,
    64,
    size=args.mem_size,
    addr_mapping=args.addr_mapping,
)

# 逐个 DRAMInterface 覆盖页管理策略（3.1.4）
for dram in memory.get_mem_interfaces():
    dram.page_policy = args.page_policy

# ── 流量发生器：直接挂到内存端口（无缓存层级）────────────────
# max_addr 必须落在内存范围内，否则请求越界。
max_addr = memory.get_size()
if args.pattern == "linear":
    generator = LinearGenerator(
        duration=args.duration,
        rate=args.rate,
        block_size=64,
        max_addr=max_addr,
        rd_perc=args.rd_perc,
    )
else:
    generator = RandomGenerator(
        duration=args.duration,
        rate=args.rate,
        block_size=64,
        max_addr=max_addr,
        rd_perc=args.rd_perc,
    )

# TestBoard：cache_hierarchy=None 时把生成器直连到唯一的内存端口
board = TestBoard(
    clk_freq="3GHz",  # 对合成生成器无意义，仅占位
    generator=generator,
    memory=memory,
    cache_hierarchy=None,
)

simulator = Simulator(board=board)
simulator.run()

print("=" * 64)
print(f"pattern={args.pattern}  page_policy={args.page_policy}  "
      f"addr_mapping={args.addr_mapping}  rd_perc={args.rd_perc}")
print("查看带宽与行命中：grep -E "
      "'avgRdBWSys|readRowHitRate|pageHitRate' <outdir>/stats.txt")
print("=" * 64)
