# 商枢智能体

商铺潜力选址分析系统，采用 Vue 3 前端和 FastAPI 后端。系统围绕地图选点、真实高德 POI 数据聚合、多场景参数模拟和 智谱 GLM 智能体建议生成，支持品牌新店选址、存量门店诊断、商业生态规划、区域商业潜力评估四类工作流。

## 项目结构

```text
.
├── backend/     # FastAPI 服务，高德代理、评分模型、智谱 GLM 智能体
├── frontend/    # Vue 3 + Vite + TypeScript 工作台
├── .env         # 本地真实密钥，不提交
└── .env.example # 环境变量模板
```

## 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端默认读取项目根目录 `.env`。

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。

## 核心接口

- `GET /api/config/public`：返回前端加载高德 JS API 所需配置。
- `GET /api/geo/reverse`：逆地理编码。
- `GET /api/poi/nearby`：周边 POI 聚合。
- `POST /api/analysis/site-selection`：品牌新店精准选址。
- `POST /api/analysis/store-diagnosis`：存量门店优化诊断。
- `POST /api/analysis/ecosystem-planning`：商业生态规划。
- `POST /api/analysis/regional-potential`：区域商业潜力评估。
- `POST /api/agent/chat`：地图上下文联动智能体问答。

## 说明

高德提供真实空间与 POI 数据。客流、租金、消费能力等无法由高德直接提供的商业指标，在首版中由 POI 密度、交通便利度、竞品密度、业态丰富度和场景参数估算，结果会标记为模型估算。

