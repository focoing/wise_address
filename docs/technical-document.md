# wise_address 技术文档

## 1. 项目概述

`wise_address` 是一个面向商业选址与门店经营分析的前后端分离系统，核心目标是把“地图选点、周边 POI 聚合、结构化评分、大模型建议”串成一条可解释、可追溯、可复用的分析链路。

系统支持四类典型场景：

- 品牌新店精准选址
- 存量门店诊断与优化
- 商业生态规划
- 区域商业潜力评估

当前技术栈如下：

- 前端：Vue 3 + Vite + TypeScript + Pinia + Vue Router
- 后端：FastAPI + Pydantic + SQLite
- 外部能力：高德地图 API、智谱 GLM API

---

## 2. 总体架构

系统采用“三层分析 + 一层记忆”的设计：

1. 交互层
   - 负责地图选点、场景参数配置、问题输入、结果展示、历史浏览。
2. 结构化分析层
   - 负责坐标校验、逆地理编码、POI 聚合、场景评分、风险识别、建议生成。
3. 大模型生成层
   - 负责将结构化分析结果转写为自然语言结论，并给出可读性更强的策略建议。
4. 历史记忆层
   - 负责将每次问答与分析快照写入 SQLite，支持会话级追踪与复盘。

### 请求主链路

1. 用户在前端地图上选点，得到经纬度。
2. 前端调用 `/api/geo/reverse` 获取地址与行政区信息。
3. 用户发起分析后，前端将模块、位置、场景参数、问题文本和门店指标封装为 `AnalysisRequest`。
4. 后端通过高德 API 拉取周边 POI。
5. 后端基于 POI 聚合与场景参数生成结构化评分 `AnalysisResponse`。
6. 后端将结构化结果交给 智谱 GLM，生成自然语言回答。
7. 结果写入 SQLite 历史库。
8. 前端展示分析结论，并可跳转历史列表和历史详情页。

---

## 3. 数据处理流程

这一部分是系统最核心的流程，整个设计的重点不是“直接问大模型”，而是先把地图空间信息转成稳定的结构化特征，再让模型做解释与建议生成。

### 3.1 输入数据

输入由 `AnalysisRequest` 统一承载，定义在 [`backend/app/models.py`](../backend/app/models.py)：

- `module`
  - 分析模块，四选一：`site_selection`、`store_diagnosis`、`ecosystem_planning`、`regional_potential`
- `location`
  - 经纬度，支持附带地址和区县信息
- `scenario`
  - 场景参数，包括业态、半径、预算等级、租金敏感度、竞品容忍度、目标客群
- `question`
  - 用户自然语言问题
- `storeMetrics`
  - 仅在门店诊断场景下使用，用于补充经营数据

### 3.2 业态识别与归一化

当用户直接输入自然语言问题时，后端会先做一层轻量业态抽取，入口位于 [`backend/app/main.py`](../backend/app/main.py) 的 `_infer_business_type()`。

这一步的目标不是做完整的 NLP，而是通过规则优先识别常见表达，例如：

- “适合开一家咖啡店吗”
- “这里适合开餐厅吗”
- “帮我分析做服装生意是否合适”

抽取后的业态会回填到 `request.scenario.businessType`，如果识别不到，则保留用户原始输入或表单值。

这一层的作用有两个：

- 减少前端手动填写业态的成本
- 让后续 POI 检索关键词与评分逻辑更贴近用户意图

### 3.3 逆地理编码补全

如果请求中没有地址信息，后端会先调用高德逆地理编码接口，自动补全：

- formatted address
- province
- city
- district
- township

实现位于 [`backend/app/services/amap.py`](../backend/app/services/amap.py) 的 `reverse_geocode()`。

这一步有三个作用：

- 增强结果可读性
- 为历史记录提供更稳定的地点标签
- 让前端无需等待用户手动填写详细地址

### 3.4 周边 POI 拉取与聚合

后端以当前位置和分析半径为中心调用高德周边检索接口，默认取 25 条结果，并将返回的 POI 转换成统一的 `PoiItem` 结构。

核心实现同样位于 [`backend/app/services/amap.py`](../backend/app/services/amap.py)：

- `nearby_pois()` 负责拉取原始 POI
- `_category_name()` 负责将高德返回的复杂行业类型映射为业务可用类别
- `PoiSummary` 负责承载聚合结果

当前 POI 聚合类别做了业务化归并，重点保留如下几类：

- 餐饮
- 零售
- 交通
- 办公
- 社区生活
- 教育
- 医疗

聚合输出包括：

- `total`
  - 半径内 POI 总数
- `byCategory`
  - 按业务类别统计的数量分布
- `topPois`
  - 代表性 POI 列表
- `radius`
  - 查询半径
- `estimated`
  - 当前实现为 `false`，表示来自真实接口而非估算数据

### 3.5 结构化评分

结构化评分位于 [`backend/app/services/analysis.py`](../backend/app/services/analysis.py)，核心函数是 `build_analysis()`。

它的思路不是做复杂机器学习，而是把 POI 分布、场景参数和门店经营信息转成一组可解释的维度分数，再综合生成总分与建议。

#### 核心维度

当前输出的维度包括：

- 客流强度
- 交通便利
- 竞品压力
- 租金健康
- 消费潜力
- 业态匹配
- 生态完整

#### 打分逻辑

评分主要由以下信息驱动：

- 周边交通类 POI 数量影响交通便利
- 办公、社区、零售等 POI 数量影响客流和消费潜力
- 餐饮类 POI 数量影响竞品压力
- POI 类别多样性影响生态完整度
- `rentSensitivity`、`competitorTolerance` 等场景参数影响租金健康和竞品压力
- 门店诊断场景下，月营收、月租金、转化率会进一步修正结果

总分由各维度平均得到，再裁剪到 `0~100` 区间。

#### 输出内容

`AnalysisResponse` 会返回：

- `score`
  - 综合评分
- `dimensions`
  - 各维度分数
- `poiSummary`
  - 周边 POI 汇总
- `charts`
  - 雷达图、柱状图、趋势图等前端图表数据
- `recommendation`
  - 一段可直接展示的结论
- `actions`
  - 建议动作
- `risks`
  - 风险提示
- `evidence`
  - 证据说明
- `alternatives`
  - 替代方案或转型建议

### 3.6 大模型生成

大模型能力位于 [`backend/app/services/llm.py`](../backend/app/services/llm.py)。

调用方式是：

1. 组装系统提示词，按模块指定角色
2. 将用户问题、位置、场景参数和结构化分析结果打包成 JSON
3. 调用 智谱 GLM Chat Completions 接口
4. 生成自然语言答案

如果 智谱 GLM 不可用，系统会自动回退为本地模板回答，保证接口稳定返回。

### 3.7 历史写入

历史记录在 [`backend/app/services/history.py`](../backend/app/services/history.py) 中使用 SQLite 持久化。

数据结构分为两张表：

- `sessions`
  - 记录会话摘要，包括模块、位置、标题、最新问题、最新分数、轮次、更新时间
- `turns`
  - 记录每一轮问答的完整请求体、分析结果、回答内容、模型名称与回退标记

会话匹配规则基于：

- `module`
- 经纬度归一化后的 `location_key`

这意味着同一地点、同一模块的多轮分析会合并到同一会话中，便于持续追踪。

---

## 4. 模型与工具设计思路

这一项目的“模型”不只是大模型，还包括结构化数据模型、评分模型和工具模型。

### 4.1 数据模型设计

所有请求与响应都通过 Pydantic 模型定义，位置见 [`backend/app/models.py`](../backend/app/models.py)。

#### 请求模型

- `AnalysisRequest`
  - 统一承载一次分析所需的全部输入
- `Location`
  - 位置坐标与地址信息
- `Scenario`
  - 业务场景与约束参数
- `StoreMetrics`
  - 存量门店经营指标

#### 响应模型

- `AnalysisResponse`
  - 结构化分析主结果
- `AgentResponse`
  - 在 `AnalysisResponse` 基础上附加大模型回答、模型名、回退标识、会话信息
- `HistorySessionSummary`
  - 历史会话摘要
- `HistorySessionDetail`
  - 历史会话详情与轮次列表
- `HistoryTurn`
  - 每一轮分析记录

### 4.2 工具设计

#### 高德地图工具

[`backend/app/services/amap.py`](../backend/app/services/amap.py) 将地图能力封装成独立客户端，便于替换和测试。

工具职责：

- 逆地理编码
- 周边 POI 检索
- POI 类别归并
- 异常统一转换为 FastAPI HTTPException

这种设计的好处是：

- 主业务逻辑不直接依赖 HTTP 协议细节
- 外部服务异常不会污染分析代码
- 测试时可以更容易 mock 客户端行为

#### 智谱 GLM 工具

[`backend/app/services/llm.py`](../backend/app/services/llm.py) 提供两种调用方式：

- `ask_deepseek()`
  - 一次性返回完整回答
- `stream_deepseek()`
  - 支持 SSE 风格增量输出

同一份输入会分别用于普通问答与流式问答，保证输出风格一致。

#### 历史工具

[`backend/app/services/history.py`](../backend/app/services/history.py) 负责：

- 初始化数据库
- 保存会话
- 列出会话
- 获取会话详情
- 删除会话

### 4.3 接口层设计

后端入口位于 [`backend/app/main.py`](../backend/app/main.py)。

接口分为四类：

- 健康检查
- 地理和 POI 能力
- 结构化分析
- 智能问答与历史管理

其中 `/api/agent/chat/stream` 采用 SSE 事件流返回，事件类型包括：

- `analysis`
  - 先返回结构化分析结果
- `delta`
  - 增量返回大模型文本
- `done`
  - 返回最终结果并附带会话 ID

这使前端可以先展示“结构化结论”，再逐步呈现大模型话术，显著改善等待体验。

---

## 5. 关键创新点

### 5.1 结构化分析与自然语言生成解耦

项目没有把“分析结果”完全交给大模型自由发挥，而是先通过规则与 POI 数据生成可解释的结构化结论，再让 智谱 GLM 做语言润色和策略化表达。

优点：

- 可控性更强
- 结果更稳定
- 方便单独测试评分逻辑
- 便于历史对比和复盘

### 5.2 业态识别的轻量前置化

系统会从用户问题中抽取业态关键词，并回填到场景参数中。

这一步看起来简单，但对真实交互很重要，因为很多用户不会先填规范表单，而是直接问一句“这里适不适合开奶茶店”。

该设计减少了用户操作成本，也提高了 POI 检索与评分的相关性。

### 5.3 POI 类别业务化归并

高德原始类型码很细，直接使用会导致分析维度过碎，不利于商业决策。

因此系统将 POI 归并为少量业务类目，再按类目进行加权评分与图表展示。

这是一个典型的“数据产品化”处理：

- 原始数据适合检索
- 业务类目适合决策

### 5.4 结构化结论带替代方案

当综合评分偏低时，系统不只给出“不建议”，还会输出替代方案，例如：

- 调整业态
- 降低固定成本
- 更换位置条件
- 先做低成本验证

这让分析结果更接近真实选址决策场景，而不是单纯打分。

### 5.5 SSE 流式返回

流式接口把“结构化分析”和“文本生成”拆成两个阶段输出，前端可以先看到关键结论，再等待完整回答。

对长文本、复杂分析尤其有帮助：

- 减少空白等待感
- 提高交互反馈速度
- 更容易做渐进式展示

### 5.6 历史会话按地点与模块复用

历史会话不是简单按时间堆叠，而是按 `module + location_key` 聚合。

这意味着同一地点、同一分析模块的多轮问答会自然沉淀到同一会话里，更符合“持续调研同一位置”的实际业务流程。

---

## 6. 实验验证过程

项目当前没有独立的离线训练实验，因为它本质上是一个“地图数据 + 规则评分 + 大模型生成”的工程系统。验证重点放在代码级可重复测试与场景正确性检查。

### 6.1 验证目标

验证分为四个方向：

1. 结构化评分是否稳定输出
2. 业态识别是否能从自然语言中抽取关键业务词
3. 历史记录是否能正确写入、查询与删除
4. 低分和高分场景下的替代建议是否符合预期

### 6.2 单元测试覆盖

测试文件位于 [`backend/tests`](../backend/tests)。

#### `test_analysis.py`

验证内容：

- `build_analysis()` 能返回完整结构化结果
- 总分位于 `0~100`
- 维度分数、行动建议、证据说明都能正常生成
- 低分场景会产生 `alternatives`
- 高分场景不会输出替代方案

#### `test_business_type_extraction.py`

验证内容：

- 自然语言中的“开一家某某店”句式能被识别
- 不包含业态信息的提问不会误判

#### `test_history.py`

验证内容：

- 首次写入会创建新会话
- 同一地点同一模块的后续写入会复用同一会话
- 轮次计数会累加
- 会话详情能正确返回每一轮分析
- 删除会话后列表为空

### 6.3 当前环境复现记录

我在当前工作区实际尝试过运行：

```bash
pytest -q
python -m pytest -q
```

结果显示当前环境缺少后端依赖，报错集中在：

- `pydantic`
- `fastapi`

这说明测试代码本身已经存在，但当前 Python 环境未完成依赖安装，因此无法在这台机器上做完整跑通。

### 6.4 推荐的可复现实验流程

建议按以下步骤复现验证：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
```

如果依赖安装完成，测试应覆盖上述三类核心路径。

---

## 7. 后端接口概览

### 7.1 健康检查

- `GET /api/health`

### 7.2 公共配置

- `GET /api/config/public`

用于前端初始化地图配置。

### 7.3 地理能力

- `GET /api/geo/reverse?lng=...&lat=...`
- `GET /api/poi/nearby?lng=...&lat=...&radius=...`

### 7.4 结构化分析

- `POST /api/analysis/site-selection`
- `POST /api/analysis/store-diagnosis`
- `POST /api/analysis/ecosystem-planning`
- `POST /api/analysis/regional-potential`

### 7.5 智能问答

- `POST /api/agent/chat`
- `POST /api/agent/chat/stream`

### 7.6 历史记录

- `GET /api/history/sessions`
- `GET /api/history/sessions/{session_id}`
- `DELETE /api/history/sessions/{session_id}`

---

## 8. 前端协同设计

前端入口位于 [`frontend/src/main.ts`](../frontend/src/main.ts)，并由 Pinia 与 Vue Router 组织全局状态与页面切换。

### 8.1 状态管理

[`frontend/src/store.ts`](../frontend/src/store.ts) 维护：

- 当前分析模块
- 当前坐标与地址
- 场景参数
- 门店经营参数
- 对话消息
- 最近一次分析结果
- 当前会话 ID
- 加载与错误状态

### 8.2 请求封装

[`frontend/src/api.ts`](../frontend/src/api.ts) 对后端接口做统一封装：

- 普通请求使用 `axios`
- 流式接口使用 `fetch + ReadableStream`

前端在接收到 SSE 后，按事件类型更新视图：

- `analysis`
  - 先展示结构化结果
- `delta`
  - 逐步追加文本
- `done`
  - 完成会话落盘和状态更新

---

## 9. 环境变量

项目通过 `.env` 加载配置，主要字段如下：

- `AMAP_KEY`
  - 高德地图服务 Key
- `DEEPSEEK_API_KEY`
  - 智谱 GLM API Key
- `DEEPSEEK_BASE_URL`
  - 智谱 GLM 接口地址
- `DEEPSEEK_MODEL`
  - 默认模型名
- `CORS_ORIGINS`
  - 允许跨域访问的前端地址

配置读取逻辑位于 [`backend/app/config.py`](../backend/app/config.py)。

---

## 10. 本地启动

### 10.1 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 10.2 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：

- `http://localhost:5173`

### 10.3 生产构建

```bash
cd frontend
npm run build
```

后端会在检测到 `frontend/dist` 存在时自动挂载静态资源，适合简单的一体化部署场景。

---

## 11. 总结

这个系统的核心价值不在于单点模型能力，而在于把地图数据、POI 结构化处理、规则评分和大模型解释组合成一条稳定链路。

它的设计特点可以概括为：

- 先结构化，再生成化
- 先可解释，再自然语言化
- 先稳定输出，再增强智能表达
- 先保底可用，再追求体验提升

这使得系统既适合真实业务分析，也便于后续持续扩展更多选址与经营决策模块。
