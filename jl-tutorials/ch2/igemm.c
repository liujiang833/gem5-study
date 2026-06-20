/*
 * 第二章 2.4 配套用例：多线程整数矩阵乘法（igemm）
 *
 * 计算 C = A x B，其中 A、B、C 均为 N x N 的 int32 方阵。
 * 工作按 C 的行划分给 NTHREADS 个线程；每个线程负责一个水平条带。
 *
 * 关键访存特征（用于演示共享 L2 的收益）：
 *   - 采用 i-k-j 循环顺序，内层对 B 的整行做顺序流式访问；
 *   - 外层 i 每推进一行，都会把"整个 B"重新读一遍；
 *   - 4 个线程读的是同一个 B —— B 是被多核反复复用的共享数据。
 *
 * 因此：若 B 能整体放进（共享的）L2，则 B 只需从 DRAM 取一次，
 * 之后命中 L2；若每核私有 L2 装不下 B，则 B 会被反复从 DRAM 重取，
 * 造成大量冗余 DRAM 读带宽。这正是本实验要量化的对比。
 *
 * 默认 N=512 时：单个矩阵 = 512*512*4 B = 1 MiB，A/B/C 合计约 3 MiB。
 *
 * 交叉编译（静态链接，供 gem5 SE 模式使用）：
 *   aarch64-linux-gnu-gcc -O2 -static -pthread \
 *       -DN=512 -DNTHREADS=4 igemm.c -o igemm
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef N
#define N 512
#endif

#ifndef NTHREADS
#define NTHREADS 4
#endif

static int *A;
static int *B;
static int *C;

typedef struct {
    int tid;
    int nthreads;
} targ_t;

static void *worker(void *p)
{
    targ_t *a = (targ_t *)p;
    int rows = N / a->nthreads;
    int r0 = a->tid * rows;
    int r1 = (a->tid == a->nthreads - 1) ? N : (r0 + rows);

    /* i-k-j 顺序：内层顺序读 B 的整行，最大化 B 的复用 */
    for (int i = r0; i < r1; i++) {
        for (int k = 0; k < N; k++) {
            int aik = A[i * N + k];
            const int *Brow = &B[k * N];
            int *Crow = &C[i * N];
            for (int j = 0; j < N; j++) {
                Crow[j] += aik * Brow[j];
            }
        }
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int nthreads = NTHREADS;
    if (argc > 1) {
        nthreads = atoi(argv[1]);
        if (nthreads <= 0) nthreads = NTHREADS;
    }

    A = (int *)malloc((size_t)N * N * sizeof(int));
    B = (int *)malloc((size_t)N * N * sizeof(int));
    C = (int *)malloc((size_t)N * N * sizeof(int));
    if (!A || !B || !C) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }

    /* 确定性初始化，避免被优化掉 */
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            A[i * N + j] = (i + j) & 0xFF;
            B[i * N + j] = (i ^ j) & 0xFF;
            C[i * N + j] = 0;
        }
    }

    pthread_t th[NTHREADS];
    targ_t args[NTHREADS];
    for (int t = 0; t < nthreads; t++) {
        args[t].tid = t;
        args[t].nthreads = nthreads;
        pthread_create(&th[t], NULL, worker, &args[t]);
    }
    for (int t = 0; t < nthreads; t++) {
        pthread_join(th[t], NULL);
    }

    /* 计算校验和，防止死代码消除并便于核对结果 */
    long long checksum = 0;
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++)
            checksum += C[i * N + j];

    printf("igemm done: N=%d threads=%d checksum=%lld\n",
           N, nthreads, checksum);
    return 0;
}
