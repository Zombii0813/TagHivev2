"""生成分阶段优化结果 HTML，内嵌截图并保留验证边界。"""

import base64
import hashlib
import html
import json
from pathlib import Path

from ui_module_registry import MODULE_GROUPS, NAMING_RULES, REQUEST_EXAMPLES

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = REPORTS / "taghive-optimization-results-2026-11-12.html"
UI_DOC = ROOT / "UI-MODULES.md"

# 编号沿用原报告；结果描述针对最终实施方案，未实测的验收条件单列。
ITEMS = [
    ("R01", "A", "查询变化与选择范围", "切换范围、目录、关键词、类型或标签时清空选择；分页、排序和同范围刷新保留；移出加载页的选中项保留名称与标签，明确显示未显示项数量。新查询未成功应用期间禁止重新选择旧结果。", "Pinia 延迟请求、范围切换与跨页回归。", "src-ui/src/stores/files.ts", "function prepareQuery"),
    ("R02", "A", "异步标签操作固定目标", "详情保存和确认移除在 await 前固定文件及标签；批量对话框在打开当下同步固定清单，提交期间防重复。", "实际 Vue setup/actions：保存及确认期间切换选择，后端与本地均只更新原文件。", "src-ui/src/views/DetailPanel.vue", "async function saveTags"),
    ("R03", "A", "静态统计路由", "将 /api/thumbnails/stats 注册在 /{file_id} 之前，恢复统计接口。", "真实路由请求返回 200。", "src-python/app/api/thumbnails.py", '@router.get("/stats")'),
    ("R04", "A", "扫描与监听共用忽略规则", "只匹配工作区相对路径的完整段或文件名 glob；工作区自身及 design.git-assets、.github 不再被子串误伤。", "工作区根含 company.github.io，精确 .git、普通相似名称的隔离用例。", "src-python/app/utils/ignore.py", "def should_ignore"),
    ("R05", "A", "缩略图 pending / 失败 / 重试", "卡片和详情共用状态；1×1 占位保持等待，按尺寸接收就绪/失败事件，使用文件版本 URL 和有限重取兜底。", "独立缓存首次选图、实际卡片图片尺寸与就绪状态检查；失败状态和重试分支经源码核对。", "src-ui/src/composables/useThumbnail.ts", "export function useThumbnail"),
    ("R07", "A", "查询失败保留并标记旧结果", "保存 appliedQuery 和错误；不提前清空文件，提示上次成功结果并提供重试；错误状态阻止重新选择和打开批量操作。", "失败保留旧数据、重试恢复、禁止选择的 Pinia 回归。", "src-ui/src/stores/files.ts", "async function search"),
    ("R11", "A", "字面子串搜索", "长短词统一子串语义，转义 %、_、!；SQLite 支持时用 trigram 子查询加速，FTS 由触发器维护，不再物化 ID 清单。", "port / por、中文子串和通配符用例；不支持 trigram 时退回 LIKE。未补做 4 万命中专门基准。", "src-python/app/db/repo.py", "def _search_statement"),
    ("R12", "A", "文件名校验与重命名", "重命名、新建目录共用后端校验，拒绝路径和系统保留名称；Windows 允许同一文件的大小写修改。前端即时提示，默认仅选主文件名，扩展名变化需确认。", "后端 7 组拒绝用例、前端字面名称回归；浏览器验证 F2、选区和无效名称禁用提交。", "src-python/app/utils/file_names.py", "def validate_name"),
    ("R13", "A", "EXIF 方向与统一渲染", "同步/异步渲染共用 EXIF 转正、透明处理、居中缩放和原子保存；缓存身份升级 v3，旧方向缓存自然失效。", "同一 EXIF 旋转样本验证两条渲染路径。JPEG draft / 编码参数未作性能调参。", "src-python/app/utils/thumbnail_render.py", "def fit_and_save"),
    ("R15", "A", "数据库连接与版本化迁移", "启用 WAL、外键、NORMAL 同步和 30 秒 busy timeout；user_version v2 事务迁移，保留标签层级、修复孤儿关联，file_tags 级联删除；失败中止启动。", "连接 PRAGMA、旧库迁移、重复初始化、孤儿修复与级联测试。网络盘 WAL 回退尚未专门验证。", "src-python/app/db/session.py", "def _ensure_schema"),
    ("L01", "A", "窄窗保留搜索空间", "按主内容可用宽度切换工具栏为两行，低频显隐/主题入口折叠；窄窗详情使用抽屉。", "1000×700、1280×800、1680×900：搜索输入约 409px，工具栏均无横向溢出。", "src-ui/src/views/MainLayout.vue", ".toolbar.compact"),
    ("R06", "B", "隐藏详情释放播放器", "隐藏或无选择时卸载详情；销毁时暂停并清除 src/load。多选时仍预览并探测最后点选的活动文件。", "生命周期源码检查与布局验证；多选时的媒体信息及旧请求丢弃回归通过。未完成真实长视频/转码播放验证，播放进度跨卸载恢复未新增。", "src-ui/src/views/DetailPanel.vue", "onBeforeUnmount"),
    ("R08", "B", "明确全选范围与逐项删除结果", "菜单/按钮明确全选已加载；工具栏、右键和 Delete 复用固定名称清单。删除不中断后续项，失败清单留待重试，文案明确系统回收站。", "实际组件 actions 验证选择变化、首轮失败后继续及仅重试失败项。沿用逐文件 API，未新增整批删除端点或全结果选择。", "src-ui/src/components/BatchOperations.vue", "async function deleteSelectedFiles"),
    ("R10", "B", "缩略图结果保留上限", "保留兼容轮询，结果队列固定 256，满时丢最旧结果；WebSocket 照常广播，统计返回 retained_results。", "合成完成事件超过容量后仍仅保留 256 条；未进行长时 RSS 稳态压测。", "src-python/app/core/async_thumbnail.py", "self.result_queue: Queue"),
    ("R14", "B", "缩略图优先级与去重", "仅在有空闲 worker 时派发；按文件版本和尺寸去重、提升优先级；视口外 medium 排队请求淘汰，失败缓存 30 秒且有上限。", "阻塞 worker 测优先级、去重、视口淘汰、负缓存。未补做连续滚过 2000 项的就绪 P95。", "src-python/app/core/async_thumbnail.py", "def _process_queue"),
    ("R16", "B", "扫描串行、取消与跳过未变更", "未变化文件零 UPDATE；手动扫描全局串行、去重排队、UUID 标识、限频进度和 remaining 余量；支持取消并跳过过期索引清理。", "零 UPDATE、取消保留索引、队列串行/余量/取消测试。保留快速计数预遍历，尚未合并为单遍；未测 10 万真实文件首扫/重扫。", "src-python/app/api/websocket.py", "async def start_scan"),
    ("R18", "B", "刷新保留加载深度与滚动", "变更路径仅标脏相关工作区标签页，非活动页惰性刷新；500ms 合并事件，成功后替换结果，按已加载条数重新取数并恢复滚动。", "无关工作区不请求；1500 条加载深度及 7200px 滚动恢复回归。未改为逐行增量协议。", "src-ui/src/stores/files.ts", "async function refreshChangedPaths"),
    ("L02", "B", "筛选、浏览与选择分层", "主工具栏按空间换行；内容区显示范围/关键词/类型/标签摘要及清除入口，选择操作放在文件区上方，底栏显示统计。", "三档布局与浏览模式切换检查；保留可见重扫和卡片大小入口，以两行布局解决拥挤。", "src-ui/src/views/MainLayout.vue", 'class="filter-summary"'),
    ("L03", "B", "侧栏偏好与窗口恢复", "可访问分隔条支持拖动、方向键和双击恢复；宽度/显隐持久化。路径可展开复制；窗口保存正常尺寸、位置、最大化，恢复时适配当前工作区和缩放。", "浏览器分隔条 240→224→240；Rust 检查和 3 个边界测试覆盖小屏、断开显示器及负坐标。原生重启、多屏及 125%/150% DPI 仍需实机验收。", "src-tauri/src/window_state.rs", "pub fn restore"),
    ("L04", "B", "多选时显示最后点选的文件详情", "按用户偏好，多选时右侧显示最后点选文件的预览、属性和标签；右侧标签编辑仅作用于该文件。上方操作条处理批量标签和删除，底栏保留加载量与总数。", "实际组件渲染和 actions 验证连续多选、媒体信息、旧请求丢弃及单文件标签保存；保留全部选择。", "src-ui/src/views/DetailPanel.vue", "const selectedFile"),
    ("L05", "B", "文件与标签页键盘操作", "标签页采用 tablist/tab、方向/Home/End/新增原生按钮；文件 roving focus、方向/Space/Enter，补齐 F2/Delete/Esc，快捷键避开输入框及弹窗。", "浏览器验证标签切换、方向键、F2、Delete 确认、Esc；未以读屏工具及长距离虚拟滚动完成整套验收。", "src-ui/src/composables/useFileNavigation.ts", "export function useFileNavigation"),
    ("R09", "C", "稳定排序与自然排序索引", "统一排序白名单和 ID 同值次序，未知时长始终末尾；schema v2 增加自然名称及 parent_dir+名称索引。保留 OFFSET 接口。", "10k/100k 合成库首屏与深页对照；100k 深页 P95 1172.02→148.66ms。现有游标接口未整体迁移。", "src-python/app/db/sorting.py", "def file_order"),
    ("R17", "C", "目录封面在 SQL 内限量", "每个直接子目录查询稳定的前 4 个 image/video ID，取消整棵子树媒体候选在 Python 中物化和自然排序。", "源码确保每目录 LIMIT 4；当前未取得 10k/100k 资源管理器根目录打开 P95，目录较多时需观察逐目录查询成本。", "src-python/app/api/routes.py", "cover_map = {"),
    ("R19", "C", "时长覆盖率与主动补探测", "时长排序显示已知/总媒体数及未知末尾说明；提供用户主动补探测，固定最多 1000 项、单线程、进度与取消，写入前重查文件签名。", "覆盖率、固定快照、取消和旧版本不写回用例；浏览器验证入口。提取器以桩隔离，真实视频批次吞吐未测。", "src-python/app/api/media.py", "def start_probe"),
    ("L06", "C", "稳定选中态与紧凑密度", "移除卡片位移/选中脉冲，统一语义选中态，增加紧凑密度及 prefers-reduced-motion；虚拟列表尺寸跟随偏好。", "布局和构建验证；未实测 GPU/滚动帧耗时，未据此进一步削减模糊效果。", "src-ui/src/styles/index.css", "/* 密度与虚拟列表行高保持同步。 */"),
]


def esc(value):
    """转义文本，返回可安全嵌入的 HTML。"""
    return html.escape(str(value))


def image(name, caption):
    """内嵌现有截图并按实际格式标注；缺图时明确提示。

    Args:
        name: 证据截图文件名。
        caption: 图注。

    Returns:
        独立可读的图像或缺图提示。
    """
    path = REPORTS / "optimization-results-assets" / name
    if not path.exists():
        return f'<p class="note">缺少截图：{esc(name)}</p>'
    raw = path.read_bytes()
    mime = "image/jpeg" if raw.startswith(b"\xff\xd8") else "image/png"
    data = base64.b64encode(raw).decode("ascii")
    return f'<figure><img src="data:{mime};base64,{data}" alt="{esc(caption)}" loading="lazy"><figcaption>{esc(caption)}</figcaption></figure>'


def source(path, needle):
    """读取最终源码锚点及摘要，便于与后续代码变化核对。

    Args:
        path: 仓库相对文件路径。
        needle: 必须存在的源码锚点。

    Returns:
        含行号和 SHA256 的源码片段。
    """
    data = (ROOT / path).read_bytes()
    lines = data.decode("utf-8-sig").splitlines()
    index = next(i for i, line in enumerate(lines) if needle in line)
    excerpt = "\n".join(f"{i + 1:4} {lines[i]}" for i in range(index, min(index + 12, len(lines))))
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f'<details><summary>源码 · {esc(path)}:{index + 1}</summary><small>生成时 SHA256 前 16 位：{digest}</small><pre>{esc(excerpt)}</pre></details>'


def card(item):
    """生成带审查勾选及代码证据的单项结果卡片。"""
    ident, phase, title, change, proof, path, needle = item
    return f'''<article id="{ident}" data-phase="{phase}" data-search="{esc(' '.join(item).lower())}">
      <div class="meta"><span class="pill">阶段 {phase}</span><b>{ident}</b><span>已实施 · 验证范围见下</span></div>
      <h3>{esc(title)}</h3><p>{esc(change)}</p><p class="evidence"><strong>验证与边界：</strong>{esc(proof)}</p>
      {source(path, needle)}<label class="review"><input type="checkbox" data-review="{ident}"> 我已审阅此项</label></article>'''


def module_reference():
    """从同一命名表生成布局图、HTML 索引及 Markdown 文档。

    Returns:
        HTML 模块章节、Markdown 文档及模块数量。

    Raises:
        AssertionError: 编号、名称重复，父模块缺失或源码锚点失效。
    """
    modules = [row for _, rows in MODULE_GROUPS for row in rows]
    lookup = {row[0]: row for row in modules}
    labels = {ident: f"{ident} {row[1]}" for ident, row in lookup.items()}
    assert len(lookup) == len(modules), "模块编号重复"
    assert len({row[1] for row in modules}) == len(modules), "模块名称重复"
    source_lines = {}

    def link(ident):
        """返回指向固定模块编号的布局图链接。"""
        return f'<a href="#{ident}"><b>{ident}</b> {esc(lookup[ident][1])}</a>'

    layout = f'''<figure class="module-figure"><div class="table-scroll" tabindex="0" role="region" aria-label="界面模块位置示意图，可横向滚动">
      <div class="module-map">
        <div class="module-map-menu">{link('UI-01')}</div>
        <div class="module-map-sidebar"><div>{link('UI-02')}</div>{link('UI-02-01')}{link('UI-02-02')}{link('UI-02-03')}<span>标签搜索 · 筛选模式 · 标签树</span>{link('UI-02-08')}<small>折叠时显示捷径</small></div>
        <div class="module-map-grip">{link('UI-12-01')}</div>
        <div class="module-map-center">
          <div>{link('UI-03')}<small>文件搜索 · 类型 · 排序 · 浏览模式 · 视图 · 密度</small></div>
          <div>{link('UI-04')}</div><div class="conditional">{link('UI-05')} · 按需</div>
          <div class="conditional">{link('UI-06')} · 按需</div><div class="conditional">{link('UI-07')} · 有选择时</div>
          <div class="module-map-browser">{link('UI-08')}<p>{link('UI-08-01')} / {link('UI-08-02')}</p><p>{link('UI-08-05')} · {link('UI-08-06')}</p><p>{link('UI-08-07')} / {link('UI-08-08')}</p><small>路径与目录卡片用于资源管理器模式；导航窗按模式悬浮显示。</small></div>
          <div class="conditional">{link('UI-10')} · 失败时</div><div>{link('UI-11')}</div>
        </div>
        <div class="module-map-grip">{link('UI-12-02')}</div>
        <div class="module-map-detail"><div>{link('UI-09')}</div>{link('UI-09-01')}{link('UI-09-02')}{link('UI-09-03')}<small>多选跟随最后点选文件；窄窗使用抽屉。</small></div>
      </div></div><figcaption>点击区域名称跳至模块索引。虚线区域按状态显示；布局图表示位置关系，浮动导航不占固定列。UI-12 为两侧面板调节条。</figcaption></figure>'''
    markdown = [
        "# TagHive 界面模块命名索引", "",
        "命名版本：1 · 2026-11-12。后续修改可直接指定本页的固定编号或中文名称。", "",
        "本页与 HTML 审查报告由 `scripts/ui_module_registry.py` 共用命名源数据生成。修改命名表后运行 `src-python/.venv/Scripts/python.exe scripts/build_optimization_results.py`，不要单独修改生成结果。源码行号为生成时定位。", "",
        "## 使用约定", "", *[f"- {rule}" for rule in NAMING_RULES], "",
        "## 布局位置速查", "", "```text",
        labels["UI-01"],
        f"├─ {labels['UI-02']}",
        f"│  ├─ {labels['UI-02-01']}",
        f"│  ├─ {labels['UI-02-02']}",
        f"│  └─ {labels['UI-02-03']} / {labels['UI-02-08']}",
        f"├─ {labels['UI-12-01']}",
        "├─ 中央内容列（从上到下）",
        f"│  ├─ {labels['UI-03']}",
        f"│  ├─ {labels['UI-04']}",
        f"│  ├─ {labels['UI-05']}（按需）",
        f"│  ├─ {labels['UI-06']}（按需）",
        f"│  ├─ {labels['UI-07']}（有选择时）",
        f"│  ├─ {labels['UI-08']}",
        f"│  ├─ {labels['UI-10']}（失败时）",
        f"│  └─ {labels['UI-11']}",
        f"├─ {labels['UI-12-02']}",
        f"└─ {labels['UI-09']}（窄窗为抽屉）",
        f"   ├─ {labels['UI-09-01']}",
        f"   ├─ {labels['UI-09-02']}",
        f"   └─ {labels['UI-09-03']}",
        "```", "", "布局示意和完整条件请结合下表；并非所有区域同时出现。", "",
    ]
    tables = []
    for title, rows in MODULE_GROUPS:
        table_rows = []
        markdown.extend([f"## {title}", "", "| 编号 | 名称 | 位置、职责与显示条件 | 代码定位 |", "| --- | --- | --- | --- |"])
        for ident, name, purpose, visibility, refs in rows:
            if ident.startswith("UI-") and ident.count("-") == 2:
                assert ident.rsplit("-", 1)[0] in lookup, f"缺少父模块：{ident}"
            html_refs, md_refs = [], []
            for path, needle in refs:
                if path not in source_lines:
                    source_lines[path] = (ROOT / path).read_text(encoding="utf-8-sig").splitlines()
                matches = [i + 1 for i, line in enumerate(source_lines[path]) if needle in line]
                assert matches, f"模块 {ident} 源码锚点失效：{path} / {needle}"
                line = matches[0]
                html_refs.append(f'<code>{esc(path)}:{line}</code><small>锚点：{esc(needle)}</small>')
                md_refs.append(f'[{path}]({path}) L{line} · `{needle}`')
            table_rows.append(f'<tr id="{ident}"><td><code>{ident}</code></td><th scope="row">{esc(name)}</th><td>{esc(purpose)}<small>显示：{esc(visibility)}</small></td><td>{"<br>".join(html_refs)}</td></tr>')
            markdown.append(f'| {ident} | {name} | {purpose}<br>显示：{visibility} | {"<br>".join(md_refs)} |')
        tables.append(f'<div class="module-group"><h3>{esc(title)}</h3><div class="table-scroll"><table class="module-table"><caption>{esc(title)} · 固定名称与代码定位</caption><thead><tr><th>编号</th><th>名称</th><th>位置、职责与显示条件</th><th>代码定位</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table></div></div>')
        markdown.append("")
    markdown.extend(["## 需求表达示例", "", *[f"- {example}" for example in REQUEST_EXAMPLES], ""])
    rules = "".join(f'<li>{esc(rule)}</li>' for rule in NAMING_RULES)
    examples = "".join(f'<li>{esc(example)}</li>' for example in REQUEST_EXAMPLES)
    section = f'''<section id="modules" class="panel"><h2>界面模块命名与位置索引</h2><p>共 {len(modules)} 个区域、子模块及交互浮层，采用固定编号和中文名称。后续可直接指定模块名称或编号。</p>
      {layout}<h3>使用约定与名称区分</h3><ul>{rules}</ul>{''.join(tables)}
      <h3>需求表达示例</h3><ul>{examples}</ul><p class="evidence">仓库索引：UI-MODULES.md。命名源：scripts/ui_module_registry.py；与本报告同时生成，源码路径和锚点在生成时校验。</p></section>'''
    return section, "\n".join(markdown), len(modules)


def main():
    """生成 HTML 并检查编号完整性，不运行或修改应用数据。"""
    expected = {f"R{i:02}" for i in range(1, 20)} | {f"L{i:02}" for i in range(1, 7)}
    assert {item[0] for item in ITEMS} == expected and len(ITEMS) == 25
    modules_html, modules_md, module_count = module_reference()
    benchmark_path = REPORTS / "optimization-benchmark-2026-11-12.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8")) if benchmark_path.exists() else None
    performance = '<p class="note">未找到基准 JSON，请先运行 scripts/benchmark_review.py。</p>'
    if benchmark:
        rows = benchmark["results"]
        pairs = []
        for count in [10000, 100000]:
            for offset in [0, count - 500]:
                before = next(r for r in rows if r["count"] == count and r["offset"] == offset and not r["natural_index"])
                after = next(r for r in rows if r["count"] == count and r["offset"] == offset and r["natural_index"])
                pairs.append(f'<tr><td>{count:,}</td><td>{offset:,}</td><td>{before["p50_ms"]:.2f} / {before["p95_ms"]:.2f}</td><td>{after["p50_ms"]:.2f} / {after["p95_ms"]:.2f}</td><td>{before["first_request_ms"]:.2f} → {after["first_request_ms"]:.2f}</td></tr>')
        performance = f'''<div class="table-scroll"><table><thead><tr><th>文件数</th><th>偏移</th><th>无索引 P50 / P95 ms</th><th>有索引 P50 / P95 ms</th><th>首次请求 ms</th></tr></thead><tbody>{''.join(pairs)}</tbody></table></div>
        <p>环境：Python {esc(benchmark['python'])}，{esc(benchmark['platform'])}。独立临时合成库；500 条一页，包含 COUNT、DTO 构造与标签查询；每组首次请求单列，之后 7 次取 P50/P95。进程和 OS 缓存为热态，未包含 HTTP 序列化、真实磁盘文件和端到端 UI 耗时。</p>'''
    screenshots = "".join(image(name, caption) for name, caption in [
        ("layout-1000.png", "1000×700：搜索不再被压到 0px，详情使用抽屉。"),
        ("layout-1280.png", "1280×800：详情停靠，可用空间驱动工具栏布局。"),
        ("layout-1680.png", "1680×900 大窗口档（截图内容为 1664×900）：文件区、标签页与停靠详情。三档截图为布局阶段记录；后续补齐了路径操作及快捷键。"),
        ("keyboard-delete.png", "最终快捷键补验：Delete 展示原目标名称清单；验证后取消，未删除样本。"),
    ])
    counts = {phase: sum(item[1] == phase for item in ITEMS) for phase in "ABC"}
    body = TEMPLATE.replace("__CARDS__", "".join(card(item) for item in ITEMS))
    body = body.replace("__MODULES__", modules_html)
    body = body.replace("__PERFORMANCE__", performance).replace("__SCREENSHOTS__", screenshots)
    for phase, count in counts.items():
        body = body.replace(f"__COUNT_{phase}__", str(count))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    UI_DOC.write_text(modules_md, encoding="utf-8")
    print(f"Generated {OUT} ({OUT.stat().st_size:,} bytes; 25 items)")
    print(f"Generated {UI_DOC} ({module_count} named modules)")


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TagHive · 分阶段优化结果审查 · 2026-11-12</title>
<style>
:root{--bg:#f4f6fa;--ink:#1f2e42;--muted:#5a6879;--line:#dce3ed;--accent:#3154b5;--card:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 system-ui,"Microsoft YaHei",sans-serif}a{color:var(--accent)}
header{background:#132841;color:white;padding:44px max(24px,calc((100vw - 1120px)/2))}header p{max-width:900px;color:#c9d8eb}h1{font-size:32px;line-height:1.4;margin:8px 0 16px}h2{font-size:23px;margin:0 0 18px}h3{font-size:18px;margin:12px 0 6px}p{margin:8px 0}main{max-width:1168px;margin:auto;padding:28px 24px 60px}
nav{display:flex;gap:20px;flex-wrap:wrap;margin-top:20px}header a{color:#d5e2ff}section{margin-bottom:34px;scroll-margin-top:90px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px}.stat{background:white;padding:18px;border:1px solid var(--line);border-radius:12px}.stat b{display:block;font-size:24px;color:var(--accent)}.stat span{color:var(--muted);font-size:13px}
.panel,article{background:var(--card);padding:22px;border:1px solid var(--line);border-radius:12px;margin:14px 0}article{scroll-margin-top:90px}.phases{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.phases .panel{margin:0}.pill{display:inline-block;background:#eaf0ff;color:#254795;padding:2px 9px;border-radius:30px;font-size:12px}.meta{display:flex;gap:12px;align-items:center;color:var(--muted);font-size:13px}.meta b{color:var(--ink)}
.controls{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:14px 0;background:var(--bg)}input[type=search],select,button{font:inherit;padding:8px 12px;border:1px solid #bbc8da;border-radius:7px;background:white;color:var(--ink)}input[type=search]{flex:1;min-width:180px}button{cursor:pointer}.evidence{border-left:3px solid #83a3de;padding-left:12px;color:var(--muted)}.note{background:#fff4dc;border-left:3px solid #cf9b38;padding:12px 16px}.review{display:block;margin-top:14px;font-size:13px}.review input{margin-right:8px}summary{cursor:pointer;color:var(--accent);margin-top:12px}small{color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f8;padding:14px;border-radius:8px;font:12px/1.6 Consolas,monospace}code{overflow-wrap:anywhere}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);white-space:nowrap}th{background:#edf2f9}figure{margin:22px 0}img{width:100%;height:auto;border:1px solid var(--line);border-radius:10px}figcaption{color:var(--muted);font-size:13px;margin-top:8px}.gallery{max-width:1000px;margin:auto}ul{padding-left:22px}li{margin:7px 0}[hidden]{display:none!important}footer{color:var(--muted);font-size:13px}
.module-map{display:grid;grid-template-columns:1fr 26px 2.5fr 26px 1.15fr;min-width:760px;gap:7px;font-size:13px}.module-map a{display:block;text-decoration:none;border-radius:6px;padding:9px 10px;background:#fff;border:1px solid #cbd8ec}.module-map a:hover{border-color:var(--accent);background:#edf3ff}.module-map a:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.module-map small{display:block;font-size:12px}.module-map-menu{grid-column:1/-1}.module-map-menu a{background:#e4ecfa}.module-map-sidebar,.module-map-detail{display:flex;flex-direction:column;gap:10px;padding:10px;background:#edf2f9;border:1px solid var(--line);border-radius:8px}.module-map-center{display:flex;flex-direction:column;gap:7px}.module-map-center>div{border:1px solid var(--line);padding:5px;border-radius:7px;background:#f5f8fc}.module-map-center .conditional{border-style:dashed}.module-map-center small{padding:3px 8px}.module-map-center .module-map-browser{flex:1;min-height:210px;background:#eaf2ff}.module-map-browser p{margin:9px 4px}.module-map-browser p a{display:inline-block;padding:4px;font-size:12px}.module-map-grip{display:flex;align-items:stretch}.module-map-grip a{writing-mode:vertical-rl;text-align:center;padding:8px 3px;background:#e0e7f3}.module-table{table-layout:fixed}.module-table th,.module-table td{white-space:normal;vertical-align:top;overflow-wrap:anywhere}.module-table thead th:nth-child(1){width:12%}.module-table thead th:nth-child(2){width:16%}.module-table thead th:nth-child(3){width:39%}.module-table tbody th{background:transparent}.module-table small{display:block;margin-top:5px;font-size:12px}.module-table code{font-size:12px}.module-table tr{scroll-margin-top:30px}.module-table tr:target{background:#fff0c8;outline:2px solid #ca9a30;outline-offset:-2px}.module-table caption{text-align:left;font-size:12px;color:var(--muted);padding:5px 0}.module-group{margin-top:24px}.module-figure .table-scroll:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
@media(max-width:760px){h1{font-size:25px}.stats,.phases{grid-template-columns:repeat(2,1fr)}.phases .panel:last-child{grid-column:1/-1}.meta{flex-wrap:wrap}main{padding:20px 14px}article,.panel{padding:16px}}
@media(max-width:760px){.module-table{min-width:720px}}
@media print{body{background:white;font-size:11px}header{background:white;color:var(--ink);padding:12px}header p,header a{color:var(--muted)}main{padding:0;max-width:none}.controls,.review,nav,.print{display:none}article,figure{break-inside:avoid}.stats,.phases{gap:6px}section{margin:12px 0}details:not([open]){display:none}article[hidden]{display:block!important}}
</style></head><body>
<header><span class="pill">实施结果 · 2026-11-12</span><h1>TagHive 分阶段优化结果审查</h1><p>依据第二轮报告 R01–R19、L01–L06 完成三阶段核心改动。本文对照最终行为，保留性能取舍、测试证据及尚未实测的验收条件，并提供界面模块固定名称。原审查报告保持不变。</p><nav><a href="#phases">阶段结果</a><a href="#modules">界面模块命名</a><a href="#items">逐项审查</a><a href="#performance">容量数据</a><a href="#screenshots">布局证据</a><a href="#limits">验证边界</a><a href="#commits">提交建议</a></nav></header>
<main><div class="stats"><div class="stat"><b>25 项</b><span>核心改动已实施</span></div><div class="stat"><b>108 + 15</b><span>Python / 前端回归通过</span></div><div class="stat"><b>3 项</b><span>Rust 窗口边界测试通过</span></div><div class="stat"><b>149 ms</b><span>100k 深页 P95（合成库）</span></div></div>
<section id="phases"><h2>三个阶段的实施结果</h2><div class="phases"><div class="panel"><span class="pill">A · __COUNT_A__ 项</span><h3>正确性与可用性</h3><p>查询/选择隔离、异步快照、文件名、搜索语义、数据库迁移及缩略图修正；窄窗搜索恢复可用。</p></div><div class="panel"><span class="pill">B · __COUNT_B__ 项</span><h3>资源与操作流程</h3><p>队列上限与优先级、扫描串行取消、刷新位置保留、逐项删除和活动文件详情、侧栏及窗口偏好、键盘操作。</p></div><div class="panel"><span class="pill">C · __COUNT_C__ 项</span><h3>容量与视觉整理</h3><p>自然排序索引、稳定次序、封面限量、时长覆盖率与主动补探测，以及紧凑密度和减少动画。</p></div></div><p class="note">“已实施”表示下列最终方案已落地，不表示原报告每条建议及所有压力/实机验收均已完成。方案调整和验证缺口逐项列明；发布版本未变，代码未自动提交。</p></section>
__MODULES__
<section id="items"><h2>逐项结果与代码依据</h2><div class="controls"><label>阶段 <select id="phase"><option value="all">全部 25 项</option><option value="A">A 正确性</option><option value="B">B 资源与交互</option><option value="C">C 容量与视觉</option></select></label><input id="search" type="search" placeholder="搜索编号、行为或文件" aria-label="筛选审查条目"><span id="count" aria-live="polite">25 / 25 项</span><button id="print" class="print">打印 / 保存 PDF</button></div>__CARDS__</section>
<section id="performance" class="panel"><h2>容量数据与分页取舍</h2>__PERFORMANCE__<p>100k 深页 P95 降低约 87.3%。本批优先增加与实际自然排序一致的索引并保留 OFFSET；复合游标整体迁移留待真实库再次出现瓶颈后评估。同值使用 ID 兜底，未知时长无论升降序都在末尾。</p></section>
<section id="validation" class="panel"><h2>完成的验证</h2><ul><li>Python 全量：108 passed；721 条既有警告；新增隔离用例覆盖迁移、查询、校验、EXIF、缩略图调度、扫描取消和媒体补探测。</li><li>前端：15 项回归通过；使用真实 Pinia actions 及 Vue setup/actions，并以可控延迟和失败替换网络，验证异步目标与批量失败重试。</li><li>前端生产构建：vue-tsc + Vite 通过；主 JS 约 1235.32kB / gzip 410.65kB。保留现有大包与 Browserslist 数据过期提示，未增加运行依赖。</li><li>Rust：cargo check --offline --locked 通过（既有 9 条警告）；window_bounds 独立测试 3/3。未运行安装包。</li><li>浏览器：独立数据目录和 24 张合成 JPEG，三档尺寸、冷缓存缩略图、标签页、分隔条与文件快捷键；未修改用户实际工作区。</li><li>git diff --check 通过；README 与实施计划同步，用户原有 uv.lock / Cargo.toml 改动保留。</li></ul></section>
<section id="screenshots"><h2>布局与交互证据</h2><p>三档窗口下实际搜索输入宽度约 409px，工具栏横向溢出均为 false。截图嵌入文档，可离线审阅。</p><div class="gallery">__SCREENSHOTS__</div></section>
<section id="limits" class="panel"><h2>仍需实机验收与后续测量</h2><ul><li>原生窗口重启、多屏切换和 Windows 125%/150% 缩放；目前验证了边界算法和编译，未以 Tauri 安装包实测。</li><li>真实长视频播放/转码中隐藏、切换与重开；本轮仅核查生命周期代码。主动补探测采用显式单线程批次，不会在扫描后自动启动；取消在当前文件结束后生效。</li><li>10 万真实磁盘文件首扫/重扫、资源管理器根目录打开 P95、连续滚过 2000 项的缩略图就绪 P95、长时 RSS 与滚动帧耗时。</li><li>SQLite 网络盘 WAL 兼容/回退、旧打包环境 trigram 支持，以及读屏工具与长距离虚拟滚动焦点回收。</li><li>全结果选择、后端整批删除端点、逐行刷新协议、播放位置跨卸载恢复等扩展未加入；当前采用明确已加载范围、逐项删除结果与保深度重载。</li></ul></section>
<section id="commits" class="panel"><h2>供审核的 Git 提交信息</h2><pre>[fix] 修复查询选择、文件校验与数据库迁移
[feat] 优化批量操作、扫描调度与响应式布局
[perf] 优化自然排序、目录封面与媒体时长补探测
[docs] 添加界面模块命名与布局索引</pre><p>未创建提交。建议按上述阶段拆分审核；缩略图 v3 与调度修改、数据库迁移与索引修改各自应保持成组，避免只选取依赖的一部分。</p></section>
<footer>本报告由 scripts/build_optimization_results.py 生成。勾选状态仅存在当前浏览器本地，不写入应用数据库；单文件包含所有图像和脚本，无外部依赖。</footer></main>
<script>
const cards=[...document.querySelectorAll('article[data-phase]')],phase=document.querySelector('#phase'),search=document.querySelector('#search');
function filter(){const term=search.value.trim().toLowerCase();let visible=0;for(const card of cards){const show=(phase.value==='all'||card.dataset.phase===phase.value)&&card.dataset.search.includes(term);card.hidden=!show;visible+=show?1:0}document.querySelector('#count').textContent=visible+' / 25 项'}
phase.addEventListener('change',filter);search.addEventListener('input',filter);document.querySelector('#print').addEventListener('click',()=>window.print());
for(const checkbox of document.querySelectorAll('[data-review]')){const key='taghive-results-2026-11-12-'+checkbox.dataset.review;try{checkbox.checked=localStorage.getItem(key)==='1'}catch{}checkbox.addEventListener('change',()=>{try{localStorage.setItem(key,checkbox.checked?'1':'0')}catch{}})}
</script></body></html>'''


if __name__ == "__main__":
    main()
