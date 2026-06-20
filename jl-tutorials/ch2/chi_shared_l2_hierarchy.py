"""
第二章 2.4 配套用例：基于 CHI 协议的"私有 L1 + 共享 L2"缓存层级

gem5 v25.1 的 stdlib 自带 CHI 层级只有
``PrivateL1PrivateL2CacheHierarchy``（每核私有 L2）。
为对比"共享 L2"的收益，本模块复用 stdlib 提供的 CHI 节点
（L1CacheController / L2CacheController / SimpleDirectory /
MemoryController），把"每核一个 L2"改为"全体核心共享一个 L2"。

与私有版本（参见
src/python/gem5/components/cachehierarchies/chi/
private_l1_private_l2_cache_hierarchy.py）的唯一结构差异：

    私有版： L1d/L1i --> cluster.l2(每核一个) --> directory
    共享版： L1d/L1i --> self.l2(全局唯一)   --> directory

下游连接（downstream_destinations）决定了 CHI 请求的转发路径，
因此把所有核心 L1 的 downstream 指向同一个 L2 控制器即可。
"""

from itertools import chain
from typing import List

from m5.objects import (
    NULL,
    RubyPortProxy,
    RubySequencer,
    RubySystem,
)
from m5.objects.SubSystem import SubSystem
from m5.params import AllMemory

from gem5.coherence_protocol import CoherenceProtocol
from gem5.utils.requires import requires

requires(coherence_protocol_required=CoherenceProtocol.CHI)

from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.abstract_cache_hierarchy import (
    AbstractCacheHierarchy,
)
from gem5.components.cachehierarchies.abstract_two_level_cache_hierarchy import (
    AbstractTwoLevelCacheHierarchy,
)
from gem5.components.cachehierarchies.ruby.abstract_ruby_cache_hierarchy import (
    AbstractRubyCacheHierarchy,
)
from gem5.components.cachehierarchies.ruby.topologies.simple_pt2pt import (
    SimplePt2Pt,
)
from gem5.components.cachehierarchies.chi.nodes.directory import SimpleDirectory
from gem5.components.cachehierarchies.chi.nodes.dma_requestor import (
    DMARequestor,
)
from gem5.components.cachehierarchies.chi.nodes.l1_cache import (
    L1CacheController,
)
from gem5.components.cachehierarchies.chi.nodes.l2_cache import (
    L2CacheController,
)
from gem5.components.cachehierarchies.chi.nodes.memory_controller import (
    MemoryController,
)
from gem5.components.processors.abstract_core import AbstractCore
from gem5.isas import ISA
from gem5.utils.override import overrides


class PrivateL1SharedL2CacheHierarchy(
    AbstractRubyCacheHierarchy, AbstractTwoLevelCacheHierarchy
):
    """CHI 两级缓存：每核私有 split L1 + 全体核心共享的单个 L2。

    单一目录（HNF），内存通道对应若干 SNF，网络为点对点。
    """

    def __init__(
        self,
        l1i_size: str,
        l1i_assoc: int,
        l1d_size: str,
        l1d_assoc: int,
        l2_size: str,
        l2_assoc: int,
    ):
        AbstractRubyCacheHierarchy.__init__(self=self)
        AbstractTwoLevelCacheHierarchy.__init__(
            self,
            l1i_size=l1i_size,
            l1i_assoc=l1i_assoc,
            l1d_size=l1d_size,
            l1d_assoc=l1d_assoc,
            l2_size=l2_size,
            l2_assoc=l2_assoc,
        )

    @overrides(AbstractCacheHierarchy)
    def get_coherence_protocol(self):
        return CoherenceProtocol.CHI

    @overrides(AbstractCacheHierarchy)
    def incorporate_cache(self, board: AbstractBoard) -> None:
        super().incorporate_cache(board)
        self.ruby_system = RubySystem()

        # 全局网络：点对点
        self.ruby_system.network = SimplePt2Pt(self.ruby_system)
        # CHI 使用 4 条虚拟网络：0=request 1=snoop 2=response 3=data
        self.ruby_system.number_of_virtual_networks = 4
        self.ruby_system.network.number_of_virtual_networks = 4

        # 单一集中式目录（HNF）
        self.directory = SimpleDirectory(
            self.ruby_system.network,
            cache_line_size=board.get_cache_line_size(),
            clk_domain=board.get_clock_domain(),
            addr_ranges=[AllMemory],
        )
        self.directory.ruby_system = self.ruby_system

        # ★ 关键差异：创建唯一的共享 L2，供所有核心共用
        self.l2 = L2CacheController(
            size=self._l2_size,
            assoc=self._l2_assoc,
            network=self.ruby_system.network,
            cache_line_size=board.get_cache_line_size(),
            clk_domain=board.get_clock_domain(),
        )
        self.l2.ruby_system = self.ruby_system
        self.l2.downstream_destinations = [self.directory]

        # 每核一个 cluster：split I/D L1，下游统一指向共享 L2
        self.core_clusters = [
            self._create_core_cluster(core, i, board)
            for i, core in enumerate(board.get_processor().get_cores())
        ]

        # 内存控制器（SNF）
        self.memory_controllers = self._create_memory_controllers(board)
        self.directory.downstream_destinations = self.memory_controllers

        # DMA（SE 模式通常没有）
        if board.has_dma_ports():
            self.dma_controllers = self._create_dma_controllers(board)
            self.ruby_system.num_of_sequencers = len(
                self.core_clusters
            ) * 2 + len(self.dma_controllers)
        else:
            self.ruby_system.num_of_sequencers = len(self.core_clusters) * 2

        # 把所有控制器接入网络：注意 L2 只有一个（self.l2）
        self.ruby_system.network.connectControllers(
            list(
                chain.from_iterable(
                    [
                        (cluster.dcache, cluster.icache)
                        for cluster in self.core_clusters
                    ]
                )
            )
            + [self.l2]
            + self.memory_controllers
            + [self.directory]
            + (self.dma_controllers if board.has_dma_ports() else [])
        )

        self.ruby_system.network.setup_buffers()

        # 用于加载二进制等功能性访问的代理端口
        self.ruby_system.sys_port_proxy = RubyPortProxy(
            ruby_system=self.ruby_system
        )
        board.connect_system_port(self.ruby_system.sys_port_proxy.in_ports)

    def _create_core_cluster(
        self, core: AbstractCore, core_num: int, board: AbstractBoard
    ) -> SubSystem:
        cluster = SubSystem()
        cluster.dcache = L1CacheController(
            size=self._l1d_size,
            assoc=self._l1d_assoc,
            network=self.ruby_system.network,
            requires_send_evicts=core.requires_send_evicts(),
            cache_line_size=board.get_cache_line_size(),
            target_isa=board.get_processor().get_isa(),
            clk_domain=board.get_clock_domain(),
        )
        cluster.icache = L1CacheController(
            size=self._l1i_size,
            assoc=self._l1i_assoc,
            network=self.ruby_system.network,
            requires_send_evicts=core.requires_send_evicts(),
            cache_line_size=board.get_cache_line_size(),
            target_isa=board.get_processor().get_isa(),
            clk_domain=board.get_clock_domain(),
        )

        cluster.icache.sequencer = RubySequencer(
            version=core_num,
            dcache=NULL,
            clk_domain=cluster.icache.clk_domain,
            ruby_system=self.ruby_system,
        )
        cluster.dcache.sequencer = RubySequencer(
            version=core_num,
            dcache=cluster.dcache.cache,
            clk_domain=cluster.dcache.clk_domain,
            ruby_system=self.ruby_system,
        )

        if board.has_io_bus():
            cluster.dcache.sequencer.connectIOPorts(board.get_io_bus())

        cluster.dcache.ruby_system = self.ruby_system
        cluster.icache.ruby_system = self.ruby_system

        core.connect_icache(cluster.icache.sequencer.in_ports)
        core.connect_dcache(cluster.dcache.sequencer.in_ports)
        core.connect_walker_ports(
            cluster.dcache.sequencer.in_ports,
            cluster.icache.sequencer.in_ports,
        )

        if board.get_processor().get_isa() == ISA.X86:
            int_req_port = cluster.dcache.sequencer.interrupt_out_port
            int_resp_port = cluster.dcache.sequencer.in_ports
            core.connect_interrupt(int_req_port, int_resp_port)
        else:
            core.connect_interrupt()

        # ★ 所有核心的 L1 下游都指向同一个共享 L2
        cluster.dcache.downstream_destinations = [self.l2]
        cluster.icache.downstream_destinations = [self.l2]

        return cluster

    def _create_memory_controllers(
        self, board: AbstractBoard
    ) -> List[MemoryController]:
        memory_controllers = []
        for rng, port in board.get_mem_ports():
            mc = MemoryController(self.ruby_system.network, rng, port)
            mc.ruby_system = self.ruby_system
            memory_controllers.append(mc)
        return memory_controllers

    def _create_dma_controllers(
        self, board: AbstractBoard
    ) -> List[DMARequestor]:
        dma_controllers = []
        for i, port in enumerate(board.get_dma_ports()):
            ctrl = DMARequestor(
                self.ruby_system.network,
                board.get_cache_line_size(),
                board.get_clock_domain(),
            )
            version = len(board.get_processor().get_cores()) + i
            ctrl.sequencer = RubySequencer(
                version=version,
                in_ports=port,
                ruby_system=self.ruby_system,
            )
            ctrl.sequencer.dcache = NULL
            ctrl.ruby_system = self.ruby_system
            ctrl.sequencer.ruby_system = self.ruby_system
            ctrl.downstream_destinations = [self.directory]
            dma_controllers.append(ctrl)
        return dma_controllers

    @overrides(AbstractRubyCacheHierarchy)
    def _reset_version_numbers(self):
        from gem5.components.cachehierarchies.chi.nodes.abstract_node import (
            AbstractNode,
        )

        AbstractNode._version = 0
        MemoryController._version = 0
