- [项目初始化 — 完整前端界面搭建](2026-06-25-project-init.md) — 8页面SPA，暖色调玻璃态UI
- [成长记录页改造为数据看板](2026-06-26-profile-stats-page.md) — 5模块统计面板
- [行动页面完整改造](2026-06-27-action-center.md) — 侧边栏3子板块 + 开始行动重构 + 行动中心5模块 + 行动历史独立页面
- [属性面板改造 + SVG图标系统](2026-06-27-attribute-icon-system.md) — 编号替换复选框 + 属性介绍卡片 + 6维→8维升级 + emoji→SVG矢量图标全面替换
- [目标页面全面改造](2026-06-28-goals-page-redesign.md) — 统一深色卡片风格 + 属性筛选 + 删除模式 + 里程碑备注 + 奖励EXP
- [任务页面拆分改造](2026-06-28-tasks-page-redesign.md) — 本日任务/本周任务子板块 + EXP手动领取 + 筛选/删除模式
- [任务板块历史任务+刷新机制+仪表盘图标+对数滑块](2026-06-29-tasks-history-dashboard-icons.md) — 历史任务子板块 + 凌晨3点自动刷新 + 任务描述展开收起 + SVG图标替换仪表盘 + 时长log滑块
- [定时任务+每周任务+行动页SVG图标+目标卡片改造](2026-06-30-scheduled-tasks-and-weekly-templates.md) — 定时任务模板+每周任务模板+凌晨自动创建；行动页13个SVG图标替换emoji；行动中心目标数据统一+AI图案预留；仪表盘删除快速行动；热力图按EXP深浅；习惯页面全面改造5模块
- [习惯奖励成长记录三轮改造](2026-07-01-habit-rewards-history-improvements.md) — 习惯EXP凌晨结算+弹窗介绍/AI按钮+删除模式；奖励商城解锁/领取双条件+图片导入；成长记录11个SVG图标替换；日期计算bug修复；统计卡片逻辑修复
- [大标题图标替换+习惯重置+奖励商城改造](2026-07-02-header-icons-and-rewards-redesign.md) — 7页面标题SVG图标替换（58×58圆形）；习惯每天默认未打卡修复；奖励商城去EXP改为条件解锁/领取+双筛选+编辑删除模式+条件自动检测对勾
- [等级系统+仪表盘待打卡+侧边栏改造+奖励条件模糊检测+手动确认](2026-07-06-level-system-and-dashboard.md) — 二次公式200级10段位配色系统；仪表盘八维雷达图替换为待打卡习惯列表；侧边栏footer等级动态渲染；Lv.188模拟数据；7类模糊正则自动检测；手动确认弹窗+温馨提示；习惯/目标模糊名称查找+歧义红字提示；unlocked自动设置Bug修复；后端迁移文档v3全量扫描
- [工作记录 2026-07-07](2026-07-07-work-session.md) — 技能树功能实现基础
- [工作记录 2026-07-08](2026-07-08-work-session.md) — 技能树嵌入主项目 + 项目目录整理
- [技能树嵌入方案](2026-07-08-skill-tree-embed-plan.md) — 双模式（编辑器+查看器）+ localStorage数据共享
- [2026-07-09 工作记录](2026-07-09-work-session.md) — 后端迁移 P0-P3（用户/行动/目标任务）、技能树编辑器重构/查看器修复/清理优化、性能优化（懒加载+并行化）、路由修复
- [2026-07-10 P6奖励商城+定时任务](2026-07-10-p6-rewards-and-cron-jobs.md) — P6奖励商城后端迁移完成、前端mock清理、后端定时任务基础设施搭建、Chart.js 修复、后端迁移完成度确认（~95%）、用户数据修复（total_exp/维度语义/120级上限）、history.js硬编码user_id修复、技能板块用户隔离（4文件）、action.js删除~200行残留mock代码
- [2026-07-10 P7全端联调+文档更新](2026-07-10-p7-fullstack-integration.md) — P7全端联调完成（6项修复）、README.md/CLAUDE.md/后端迁移模块.md 全面更新
- [2026-07-10 后端模块化重构](2026-07-10-backend-refactor.md) — 后端从2个单体文件拆分为36个模块文件
- [2026-07-11 首次 Git 提交 + 项目开发规划](2026-07-11-work.md) — 推送到 Gitee、后端迁移模块重命名、P0-P6 完成度确认
- [2026-07-12 工作记录](2026-07-12-work.md) — 3个UI bug修复（进度条EXP/动态播报undefined/表格对齐）+ 技能树存储迁移到后端 + 奖励弹窗多项优化（暂存草稿/条件移除/弹窗关闭/图片图标合并/下拉修复）
- [2026-07-13 工作记录](2026-07-13-work.md) — AI提示词整合 + 统一调用层 + AI图标设计 + 魅力改名 + 维度计分规则重构 + 今日统计三层叠加莫兰迪进度条 + 分类局部刷新 + 提交确认弹窗 + EXP预览显示维度→全局 + AI行动解析多轮对话 + 奖励商城默认奖励清空
- [2026-07-14 工作记录](2026-07-14-work.md) — 1.0审查修复17条 + 桌面打包 + 睡眠记录数据持久化+展示修复 + 规律作息EXP系统完整实现 + 技能空状态SVG插图 + 睡眠每日限制 + 今日统计排除睡眠 + 财务半月复盘 + 学习EXP显示0修复 + 拖拽条EXP实时更新
- [2026-07-19 工作记录](2026-07-19-work.md) — 修复技能页API请求路径+SQLite WAL模式P0优化+压测脚本修复+手机版部署方案文档+侧边栏扩展架构+AI Agent页面占位
- [2026-07-20 工作记录](2026-07-20-work.md) — 行动历史 CSV 导出功能（后端API+前端对话框+浏览器下载）
- [2026-07-21 工作记录](2026-07-21-work.md) — 表达训练系统完整实现：AI出题+答题+评分+提示生成+填充词检测V2
- [2026-07-22 工作记录](2026-07-22-work.md) — 表达训练历史记录完整实现 + 多项体验修复 + 用户数据隔离 + 空数据状态修复
- [2026-07-23 工作记录](2026-07-23-work.md) — 表达训练语音识别集成：DashScope paraformer 实时语音替代打字输入 + 修复页面崩溃 + 麦克风诊断弹窗（双标签） + 回答记录创建时机修复 + 草稿续答完善
- [2026-07-24 工作记录](2026-07-24-work.md) — 语音识别修复（倒计时时机/文本重复/同步显示/降采样/去重）
- [2026-07-25 工作记录](2026-07-25-work.md) — 表达训练多项修复 + 任务板块数据污染/看板同步/completed_at修复 + 动态播报 + 侧边栏经验同步
- [2026-07-26 工作记录](2026-07-26-work.md) — 任务板块重构（source_type 分离 + task_history 归档）+ 行动板块审查修复 + 习惯/目标板块审查修复 + user_monthly_stats 月度统计持久化
- [2026-07-27 工作记录](2026-07-27-work.md) — 仪表板/成长记录/属性面板代码审查 7项修复 + 技能树板块代码审查 7项修复（同名节点红色光圈+禁止发布、历史栈 index 修复、delete 存在性检查等）
- [2026-07-28 工作记录](2026-07-28-work.md) — 奖励商城全面审查修复（10项/增量快照机制）+ 全项目代码大清理 + 删除打包相关文件 + .gitignore完善 + Docker部署方案文档

- [2026-07-30 工作记录](2026-07-30-work.md) — 表达训练AI美化 + 历史任务重构纯后端分页 + 睡眠输入修复 + AI习惯图标持久化（SVG替代emoji）+ API Key加载修复

- [2026-07-31 工作记录](2026-07-31-work.md) — 任务历史板块代码审查修复 + 启动时补归档机制 + 习惯AI图标安全审查9项修复（SVG提取/校验/消毒/循环依赖）

- [2026-08-01 工作记录](2026-08-01-work.md) — AI 习惯分析性能排查（推理模型max_tokens含思考空间）+ 代码清理（删除分析功能留"更新中"占位）+ ai_client 配置优化（timeout/单例/流式接口）

- [2026-08-16 工作记录](2026-08-16-work.md) — 统一协调Agent设计方案v2改写：单一Agent→主/次Agent多智能体架构 + 反问题队列(滑动窗口2) + 上下文上移主Agent；代码实施(M1)待启动

- [2026-08-23 工作记录](2026-08-23-work.md) — 统一协调Agent全栈实施：后端6个子Agent(action/query/goal/task/habit/reward) + 主图LLM路由 + 前端悬浮球对话框 + API端点(chat/resume/stream)；测试遇到LLM API配额问题待解决

- [2026-08-25 工作记录](2026-08-25-work.md) — Coordinator Agent反问机制实现：公共ask_user工具 + 6子Agent接入 + dispatch interrupt检测 + 前端FIFO队列(max2卡片+域名标签+跳过+输入框) + resume端点改造

- [2026-08-27 工作记录](2026-08-27-work.md) — 协调Agent三段式重构(ask_user替代interrupt) + 上下文管理(近5条记录/3轮反问窗口/sessionStorage) + 经验计算修复(exp键bug+sub_type) + 工具参数完善(ID查询/category枚举/exp必填) + 前端修复(拖拽方向/反问卡片/request_id污染)

- [2026-09-01 工作记录](2026-09-01-work.md) — MCP插件(24业务工具暴露+Literal约束+参数校验) + 经验幂等bug修复 + 用户中心(基础信息/多模型管理) + 模型配置持久化与动态生效(git版本号)

- [2026-09-03 工作记录](2026-09-03-work.md) — 技能树编辑器8项bug修复(跨树撤销污染/连线残留/参考线失效/redo时机等) + 技能树AI审查发现双轨架构 + 技能树AI重写为LangGraph全栈改造(thread_id隔离/checkpointer防累积/确认卡片/旧/api/chat无鉴权端点下线) + CLAUDE.md/README.md按实际架构全面重写

- [2026-09-08 工作记录](2026-09-08-work.md) — 面试展示缺口分析：实测0截图/无Dockerfile/仅2测试/远程在Gitee，输出四道门槛模型 + P0-P2分级清单 + 两周排期 + 速赢8件事（docs/面试展示待补充清单.md）

- [2026-09-09 工作记录](2026-09-09-work.md) — backend/services 代码学习顺序文档：按依赖拓扑排6阶段路线(exp_service→ai_client→旧范式httpx→coordinator→skill_tree_ai)，含读完自测、三条并行主线、通关6题

- [2026-09-10 工作记录](2026-09-10-work.md) — 登录鉴权方案选型：9种登录方式适配度评级(JWT推荐/Session否决/OAuth不做) + MCP与技能树为何不能用Session + JWT四层落地方案 + 面试话术（docs/登录鉴权方案选型.md）

- [2026-09-11 工作记录](2026-09-11-work.md) — 技能树编辑器权限管控落地(仅管理员可进入、普通用户无入口；三道防线 + require_admin + /api/auth/me + 11个权限测试) + 技能树剩余6项bug修复(点击节点全量重绘改updateNodeVisual/连线模式点空白取消/详情面板残留清理等)

- [2026-09-12 工作记录](2026-09-12-work.md) — 技能树AI(Agent)专项复查修复7项：AI生成树叠在(0,0)加自动布局 / resume用旧树覆盖手动改动 / 纯聊天误刷画布 / AI改动不落盘 / 连线样式丢失 / 确认后参数被改写 / 会话失效兜底 + 新增9个工具测试(78 passed)

- [2026-09-13 工作记录](2026-09-13-work.md) — JWT登录鉴权全栈落地S1~S6(101 passed)：passlib换bcrypt踩坑 / refresh_tokens+api_keys表 / auth_service(密钥强制校验·token_version·refresh轮换·API Key) / deps凭证解析链(73端点零改动) / routers/auth.py八个端点 / 前端auth.js包装window.fetch覆盖52处调用 / refresh双通道应对SameSite / CORS从*收紧 / 登录页密码表单+用户中心账户安全 / MCP HTTP传输加ApiKeyMiddleware(发现原HTTP模式裸奔)+ContextVar多用户身份 / docs/安全设计说明.md(威胁模型+已知风险10条)

- [2026-09-14 工作记录](2026-09-14-work.md) — 鉴权上线后的启动排障与文档同步：favicon 404清理 / 点0.0.0.0打不开三原因(监听地址·根路由404·JWT密钥缺失→改为启动即校验) / CORS漏3000端口导致登录页误报"后端未启动"→改allow_origin_regex放行本机任意端口且登录页报错展示真实原因 / README(763行)+CLAUDE.md(275行)按实测全面重写(22表·102端点·101 passed)

- [2026-09-15 工作记录](2026-09-15-work.md) — 首次真正跑上服务器：Docker镜像首次构建成功(567MB/100秒)+端到端冒烟 / 砍掉apt装tzdata(Debian required包,slim自带)构建从4分钟到100秒 / MCP服务补进compose并修init_db缺失bug(23表) / Nginx反代补齐(缺/mcp块·证书挂载三处不一致·服务整段被注释) / **生产事故:config.js写死127.0.0.1导致前端连不上**(改为按请求Host反推) / 新库7维显示"Lv1·5625XP·需要150·100%"根因(migrate写死level=1/xp_to_next=150违约)→seed改真实数据+normalize_dimension_rows自愈迁移 / **全项目时间口径统一为本地时间naive**(修一族UTC混用bug:行动时间早8h·最近行动恒显示8小时前·前端今天用UTC日期)+12用例

- [2026-09-16 工作记录](2026-09-16-work.md) — 四条主线：①修AppData.profile缓存永不失效(5个写钩子调refreshProfileCache) ②测试连通性支持留空Key(回落已存Key·防越权) ③修MCP query_action_history字段名bug(从上线起就没成功过)+25项全量体检 ④**8个AI端点全部SSE化**(services/sse.py·ContextVar发射器穿透router→graph→agent→tool·心跳保活·前端sse.js零依赖·删2个假端点·21用例) ⑤端到端验SSE穿Nginx(89秒长任务不中断;发现X-Accel-Buffering会被Nginx消费掉属正确行为) ⑥**反问并发复现出四个缺陷**(重复执行子图/静默吞掉/清空另一卡片输入/跳过导致总结为空)→会话锁409+skip语义+前端串行队列+假DOM测试当场抓到'idle'真值bug / 113→134→144 passed

- [2026-09-17 工作记录](2026-09-17-work.md) — 推送18个提交+README同步(数端点必须用app.openapi,别遍历app.routes) / **全代码审查删净死代码**(45文件 +175/-1120行:6死端点·viewer.html 649行·68条废弃CSS;核心原则"假阳性比漏报危险得多",调用方语料必须覆盖仓库根) / 抓到两个静默真bug(agent.js的formatDate覆盖utils.js同名全局函数·DEFAULT_DIMENSIONS的xp_to_next写死150) / 常量改为从CATEGORIES单一来源派生 / README端点表双向核对B组8→0 / **多智能体token实测**(单体每轮6659 vs 子Agent平均1382)并修正归因:真省token的是"按域装载工具与提示词"而非"多Agent" / 挖出4个独特设计(反问做成工具·动态改工具集约束LLM·防幻觉兜底·自己解多Agent引入的竞态与事件串扰)

- [2026-09-18 工作记录](2026-09-18-work.md) — 由用户两个提问引出的提示词与工具定义治理：清掉"预留工具"残留注释(search_hot_events已删;**给LLM声明工具≠前端留TODO**,模型会真去调、白烧一整轮往返10~30s) / 讲清项目里两套工具挂载方式并存的合法性(@tool+bind_tools vs 手写OpenAI schema+bind(tools=);判据是工具背后有没有真实本地函数) / **ACTION_PARSE_TOOLS.category_id补上enum约束**(从CATEGORIES派生,原来只在description里手写ID) / 未修:sub_type 12个子类型无单一来源·mcp_server的CategoryId=Literal只能手写(可加运行时断言) / 150 passed

- [2026-09-19 工作记录](2026-09-19-work.md) — **SQLite/MySQL双后端迁移完成**(项目最大一次架构改造)：先侦察改动面(151个get_conn调用点·150处?占位符·36处TEXT DEFAULT是头号坑·18个FOREIGN KEY)出方案文档 / 新增db/backend.py(PooledDB+连接代理)·db/dialect.py(方言自动转换)·db/testing.py·迁移脚本 / **151个调用点与150处占位符一行没改** / 10个"跑起来才炸"的坑(反引号与DDL转换顺序·幂等标记不能含VARCHAR(·TEXT进键1170三种位置·保留字需保护ORDER BY DESC·池太小死锁无超时·date()返回类型不同) / 验证:SQLite 150 passed / MySQL 141+9 skipped / 22表逐字段核对一致·时区偏差0秒

- [2026-09-20 工作记录](2026-09-20-work.md) — 迁移后收尾三件事+两处加固：①compose加mysql服务(不发布端口·mysqladmin ping healthcheck因初始化期有临时server·$$转义·depends_on健康门控) ②🐛真bug:派生表缺别名→MySQL 1248(全库扫出2处,第二处是f-string拼接grep搜不到)→固化为test_sql_dialect_lint.py(含灵敏度自检,因为"永远返回0的检查器比没有更危险") ③⚠️隐患:MySQL lock_wait_timeout默认一年+DBUtils无限等待→整站静默挂死(无任何日志)→连接层设30秒 ④TRUNCATE重置测试库实测卡死已回退 ⑤README/CLAUDE.md数据库表述全面同步(新增"双后端"一节) / SQLite 167 passed,MySQL 158+9 skipped

- [2026-09-21 工作记录](2026-09-21-work.md) — 推送7个提交(按主题拆分) / **推送前扫出两个含明文API Key的未跟踪文件**(bocha.py/gitsearch.py,确认从未进过git历史→加gitignore并建议吊销重发) / remote从HTTPS改SSH(非交互环境凭据助手弹不出窗)并双向验证(rev-list 0 0 + ls-tree查敏感文件无命中) / 协作笔记MEMORY.md涨到22KB被注入截断→拆为核心(9.8KB)+细节(13.9KB)两份
