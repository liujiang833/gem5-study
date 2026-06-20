# jl-tutorials

本目录收录《gem5 深度教程》各章的**可运行实验**。书本式的讲解内容在配套教程仓库的 `chXX/README.md` 中；这里只放能在本 gem5 仓库内直接编译、运行的配置脚本与工作负载。

> 分支：`gem5-tutorial-dev`。学习者 clone 本 fork、切到该分支后即可运行下列用例。

## 目录结构

```
jl-tutorials/
├── ch0/   第零章 · gem5 仿真框架概述
│   └── arm_o3_simple.py            ARM O3CPU + 私有 L1（classic）
└── ch2/   第二章 · Ruby 内存子系统
    ├── ruby_mesi_two_level.py      2.1/2.3：Ruby(MESI_Two_Level) 两级缓存
    ├── igemm.c                     2.4：多线程整数 GEMM 工作负载
    ├── chi_shared_l2_hierarchy.py  2.4：自定义 CHI 共享 L2 层级
    └── chi_l2_experiment.py        2.4：共享 vs 私有 L2 的 DDR 带宽对比
```

## 运行约定

所有命令均假定**工作目录为本 gem5 仓库根目录**：

```bash
# 构建（ARM 默认即 CHI 协议）
scons build/ARM/gem5.opt -j$(nproc)

# 运行某个用例
./build/ARM/gem5.opt jl-tutorials/ch0/arm_o3_simple.py
```

各脚本头部的 docstring 给出了该用例所需的构建协议与完整运行/分析命令。
