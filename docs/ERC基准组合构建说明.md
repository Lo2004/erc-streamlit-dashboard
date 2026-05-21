---
title: "ERC 风险平价组合构建说明"
subtitle: "基准 ERC 组合的构建过程、数学原理与实现细节"
author: "ERC 看板项目"
date: "2026年5月"
documentclass: ctexart
geometry: "left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm"
fontsize: 11pt
linestretch: 1.3
toc: true
toc-depth: 2
numbersections: true
header-includes:
  - \usepackage{amsmath}
  - \usepackage{amssymb}
  - \usepackage{booktabs}
  - \usepackage{longtable}
  - \usepackage{xcolor}
  - \definecolor{codebg}{rgb}{0.95,0.95,0.95}
---

# 组合架构概述

基准 ERC（Equal Risk Contribution，等风险贡献）组合由三个核心资产构成，每个资产在组合中贡献相等的风险：

| 资产代码 | 资产名称 | 角色 |
|----------|----------|------|
| H20955.CSI | 红利低波100全收益 | 权益类 |
| CBA00661.CS | 中债国债总财富(10年以上) | 利率类 |
| CI005213.WI | 黄金(中信) | 另类资产 |

黄金在纳入组合前，先对沪深300 beta 进行对冲处理，以剥离权益市场系统性风险，得到纯化的黄金 alpha 收益。

对比基准为 **60% 沪深300 + 40% 中债10年以上国债** 的传统股债组合，同时给出纯沪深300指数作为二级参考。

---

# 数据准备

## Wind 标准化数据表

数据源为 Wind 终端导出的多行表头收盘价 Excel 文件，解析过程如下：

1. 前 4 行为表头：第 3 行为资产名称，第 4 行为 Wind 代码
2. 第 5 行起为数据行，第一列为日期（`Date` 列）
3. 按代码提取价格序列，构建以日期为索引、代码为列的价格矩阵 $\mathbf{P}$

设价格矩阵为 $\mathbf{P} \in \mathbb{R}^{T \times N}$，其中 $T$ 为交易日数，$N$ 为资产数。

## 所需数据

| 代码 | 用途 |
|------|------|
| H20955.CSI | ERC 权益资产 |
| CBA00661.CS | ERC 债券资产 |
| CI005213.WI | ERC 黄金资产（待对冲） |
| H00300.CSI | 沪深300（对冲回归 + 基准构建） |
| AU9999.SGE | 现货黄金（对冲回归自变量） |

---

# 黄金对冲：剥离沪深300 Beta

## 目的

中信黄金指数（CI005213.WI）本身包含权益市场联动成分。为了将黄金作为真正独立的另类资产纳入 ERC 组合，需先对冲其与沪深300的系统性关联，保留与现货黄金价格和自身特有波动相关的暴露。

## 回归模型

采用对数收益率的三因子回归：

$$\ln\left(\frac{P_t^{\text{gold}}}{P_{t-1}^{\text{gold}}}\right) = \alpha + \beta_{\text{equity}} \cdot \ln\left(\frac{P_t^{\text{csi300}}}{P_{t-1}^{\text{csi300}}}\right) + \beta_{\text{spot}} \cdot \ln\left(\frac{P_t^{\text{AU9999}}}{P_{t-1}^{\text{AU9999}}}\right) + \varepsilon_t$$

其中：

- $P_t^{\text{gold}}$：黄金指数（CI005213.WI）在 $t$ 日的收盘价
- $P_t^{\text{csi300}}$：沪深300指数（H00300.CSI）在 $t$ 日的收盘价
- $P_t^{\text{AU9999}}$：现货黄金（AU9999.SGE）在 $t$ 日的收盘价
- $\alpha, \beta_{\text{equity}}, \beta_{\text{spot}}$：待估参数

回归使用全部共同可用的历史数据，通过最小二乘法（OLS）求解。

## 对冲价格序列构建

对冲后的对数收益率为：

$$r_t^{\text{hedged}} = \ln\left(\frac{P_t^{\text{gold}}}{P_{t-1}^{\text{gold}}}\right) - \hat{\beta}_{\text{equity}} \cdot \ln\left(\frac{P_t^{\text{csi300}}}{P_{t-1}^{\text{csi300}}}\right)$$

对冲后价格序列由累积收益重建：

$$P_t^{\text{hedged}} = P_0^{\text{gold}} \cdot \exp\left(\sum_{s=1}^{t} r_s^{\text{hedged}}\right)$$

其中 $P_0^{\text{gold}}$ 为对冲收益序列起始日的黄金原始价格，作为对齐基准。

## 最终资产面板

$$\mathbf{X} = \begin{bmatrix} P^{\text{stock}} & P^{\text{bond10}} & P^{\text{hedged}} & P^{\text{csi300}} \end{bmatrix}$$

前三列进入 ERC 组合，第四列用于构建 60/40 基准和纯沪深300基准。

---

# ERC 权重求解

## 等风险贡献原理

对于 $N$ 个资产，设权重向量 $\mathbf{w} \in \mathbb{R}^N$（$\sum_i w_i = 1$，$w_i \geq 0$），协方差矩阵 $\boldsymbol{\Sigma} \in \mathbb{R}^{N \times N}$，组合波动率为：

$$\sigma(\mathbf{w}) = \sqrt{\mathbf{w}^\top \boldsymbol{\Sigma} \mathbf{w}}$$

第 $i$ 个资产的边际风险贡献（Marginal Risk Contribution）为：

$$\text{MRC}_i = \frac{\partial \sigma}{\partial w_i} = \frac{(\boldsymbol{\Sigma}\mathbf{w})_i}{\sqrt{\mathbf{w}^\top \boldsymbol{\Sigma}\mathbf{w}}}$$

第 $i$ 个资产的绝对风险贡献为：

$$\text{RC}_i = w_i \cdot \text{MRC}_i = w_i \cdot \frac{(\boldsymbol{\Sigma}\mathbf{w})_i}{\sqrt{\mathbf{w}^\top \boldsymbol{\Sigma}\mathbf{w}}}$$

ERC 的目标是使所有资产的风险贡献相等：

$$\text{RC}_i = \text{RC}_j, \quad \forall i, j$$

## 优化问题

等价于最小化风险贡献的方差：

$$\min_{\mathbf{w}} \sum_{i=1}^{N} \left( \text{RC}_i - \frac{1}{N} \sum_{j=1}^{N} \text{RC}_j \right)^2$$

$$\text{s.t.} \quad \sum_{i=1}^{N} w_i = 1, \quad w_i \geq 10^{-6}$$

使用 SLSQP（序列最小二乘规划）求解器，最大迭代 200 次，容差 $10^{-12}$。若优化失败，回退为等权 $\frac{1}{N}$。

## 滚动窗口与调仓日程

在每个调仓日 $t$，使用过去 $L$ 个交易日（回看窗口，默认为 60 日）的收益率计算协方差矩阵：

$$\boldsymbol{\Sigma}_t = \text{Cov}\left(\{\mathbf{r}_s\}_{s=t-L+1}^{t}\right)$$

收益率由价格对数差分计算：$r_{i,t} = \ln(P_{i,t} / P_{i,t-1})$。

支持三种调仓频率：

| 频率 | 调仓日规则 |
|------|-----------|
| 日度（D） | 每个交易日更新权重 |
| 周度（W） | 每周第 $d$ 个交易日（默认 $d=1$，即周一） |
| 月度（M） | 每月第 $d$ 个交易日（默认 $d=1$，即月初首个交易日） |

权重在调仓日计算，次一交易日生效（即权重序列整体前移 1 日）。

---

# 回测引擎

## 组合收益与净值

设第 $t$ 日生效的权重为 $\mathbf{w}_t$，当日的资产收益率为 $\mathbf{r}_t$，则：

$$r_t^{\text{ERC}} = \mathbf{w}_t^\top \mathbf{r}_t = \sum_{i=1}^{N} w_{i,t} \cdot r_{i,t}$$

ERC 组合净值：

$$\text{NAV}_t^{\text{ERC}} = \prod_{s=1}^{t} (1 + r_s^{\text{ERC}}), \quad \text{NAV}_0^{\text{ERC}} = 1$$

## 基准组合

**60/40 基准**（传统股债配置）：

$$r_t^{\text{60/40}} = 0.6 \cdot r_t^{\text{csi300}} + 0.4 \cdot r_t^{\text{bond10}}$$

$$\text{NAV}_t^{\text{60/40}} = \prod_{s=1}^{t} (1 + r_s^{\text{60/40}})$$

**沪深300基准**（纯权益参考）：

$$\text{NAV}_t^{\text{csi300}} = \prod_{s=1}^{t} (1 + r_s^{\text{csi300}})$$

## 换手率

第 $t$ 期的双边换手率为权重变化绝对值的半数：

$$\text{TO}_t = \frac{1}{2} \sum_{i=1}^{N} |w_{i,t} - w_{i,t-1}|$$

---

# 绩效指标

## 年化收益率

$$\text{AnnRet} = \left(\frac{\text{NAV}_T}{\text{NAV}_0}\right)^{\frac{f}{T}} - 1$$

其中 $f$ 为年化频率（日频数据 $f=252$，周频 $f=52$，月频 $f=12$），$T$ 为样本长度。

## 年化波动率

$$\text{AnnVol} = \sigma_r \cdot \sqrt{f}$$

其中 $\sigma_r$ 为日收益率标准差。

## 夏普比率

使用中债-总财富(1年以下)指数（CBA00311.CS）的日收益率作为无风险利率 $r_t^f$：

$$\text{Sharpe} = \frac{\overline{r - r^f}}{\sigma_r} \cdot \sqrt{f}$$

## 最大回撤

$$\text{MDD} = \min_{0 \leq s < t \leq T} \left( \frac{\text{NAV}_t}{\text{NAV}_s} - 1 \right)$$

同时记录最大回撤的起止日期和最长修复天数。

## 卡玛比率

$$\text{Calmar} = \frac{\text{AnnRet}}{|\text{MDD}|}$$

## 胜率

- **日胜率**：$r_t > 0$ 的比例
- **月胜率**：月末净值环比上涨的月份比例
- **月均换手率**：换手率的月度合计均值

## 多区间统计

所有指标在六个时间区间上分别计算：全样本、近 10 年、近 5 年、近 2 年、近 1 年、近 6 个月。

---

# 实现模块索引

| 模块 | 文件 | 核心功能 |
|------|------|----------|
| 数据加载 | `src/data_loader.py` | Wind 多行表头解析、无风险利率加载 |
| 黄金对冲与ERC | `src/erc.py` | 三因子 OLS 对冲、SLSQP 权重优化、回测引擎 |
| 基准编排 | `src/baseline.py` | 基准组合流程编排、基准构建、调仓日计算 |
| 绩效指标 | `src/metrics.py` | 年化指标、最大回撤、胜率、多区间报表 |
| 交易日历 | `src/trading_calendar.py` | A股交易日历加载、调仓日推算 |
| 前端看板 | `app.py` | Streamlit 交互界面 |

---

*本文档基于项目 `erc-streamlit-dashboard` 的实际代码逻辑生成，所有公式与流程均与实现严格对应。*
