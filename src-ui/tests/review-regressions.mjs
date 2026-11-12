// 使用现有 Vite SSR 执行真实 Pinia actions，网络接口以可控延迟替换。
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createPinia, getActivePinia, setActivePinia } from 'pinia'
import { createSSRApp, effectScope, ssrContextKey, nextTick } from 'vue'
import { renderToString } from 'vue/server-renderer'
import ElementPlus, { ElMessage, ElMessageBox, ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } from 'element-plus'

const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
}
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
const results = []
try {
  const { useFileStore } = await server.ssrLoadModule('/src/stores/files.ts')
  const { useAppStore } = await server.ssrLoadModule('/src/stores/app.ts')
  const { useTagStore } = await server.ssrLoadModule('/src/stores/tags.ts')
  const { fileApi } = await server.ssrLoadModule('/src/api/files.ts')
  const { folderApi } = await server.ssrLoadModule('/src/api/folders.ts')
  const { tagApi } = await server.ssrLoadModule('/src/api/tags.ts')
  const { toPersisted, fromPersisted } = await server.ssrLoadModule('/src/stores/browserTabs.ts')
  const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
  const response = name => ({ files: [{ id: name === 'new' ? 2 : 1, name, tag_ids: [] }], total: 1, has_more: false })
  const test = async (name, run) => { storage.clear(); setActivePinia(createPinia()); await run(); results.push({ name, passed: true }); console.log(`PASS ${name}`) }
  tagApi.getAll = async () => []

  await test('F08: delayed old search cannot replace new search', async () => {
    const store = useFileStore(), app = useAppStore()
    app.workspaces = ['A']; store.activeTab.workspace = 'A'
    const old = deferred(), current = deferred()
    fileApi.search = query => query.text === 'old' ? old.promise : current.promise
    store.activeTab.searchText = 'old'; const one = store.search()
    store.activeTab.searchText = 'new'; const two = store.search()
    current.resolve(response('new')); await two
    old.resolve(response('old')); await one
    assert.equal(store.files[0].name, 'new')
    assert.equal(store.isLoading, false)
  })
  await test('F08: delayed folder response cannot replace newer folder', async () => {
    const store = useFileStore(); store.activeTab.browseMode = 'explorer'
    const old = deferred(), current = deferred()
    folderApi.getContents = path => path === 'A' ? old.promise : current.promise
    const one = store.loadFolderContents('A'), two = store.loadFolderContents('B')
    current.resolve({ ...response('new'), dirs: [] }); await two
    old.resolve({ ...response('old'), dirs: [] }); await one
    assert.equal(store.currentFolderPath, 'B'); assert.equal(store.files[0].name, 'new')
  })
  await test('F08: stale pagination cannot append to replaced query', async () => {
    const store = useFileStore(), page = deferred()
    store.activeTab.searchText = 'old'; store.activeTab.hasMore = true
    fileApi.search = query => query.offset ? page.promise : Promise.resolve(response('new'))
    store.activeTab.files = response('old').files
    const loading = store.loadMore()
    store.activeTab.searchText = 'new'; await store.search()
    page.resolve(response('old')); await loading
    assert.deepEqual(store.files.map(file => file.name), ['new'])
  })
  await test('F09/F18: filters compose per tab and use registered roots', async () => {
    const store = useFileStore(), app = useAppStore(); app.workspaces = ['A', 'B']; app.activeWorkspace = 'B'
    const tab = store.activeTab; tab.workspace = 'A'; tab.browseMode = 'all'
    tab.searchText = 'photo'; tab.searchType = 'image'
    let captured
    fileApi.search = async query => { captured = query; return response('new') }
    await store.filterByTags([7])
    assert.equal(captured.root, 'A'); assert.equal(captured.text, 'photo')
    assert.deepEqual(captured.types, ['image']); assert.deepEqual(captured.tags, [7])
    tab.browseMode = 'explorer'; tab.currentFolderPath = 'A/sub'; await store.reloadCurrentView()
    assert.equal(captured.root, 'A/sub'); assert.deepEqual(captured.tags, [7])
    tab.isGlobalView = true; tab.browseMode = 'all'; await store.search()
    assert.deepEqual(captured.roots, ['A', 'B'])
    app.workspaces = ['A']; await store.search(); assert.deepEqual(captured.roots, ['A'])
    app.workspaces = []; await store.search(); assert.deepEqual(captured.roots, [])
  })
  await test('F09: text, type and tags survive tab persistence', async () => {
    const tab = useFileStore().activeTab
    tab.searchText = 'photo'; tab.searchType = 'image'; tab.searchQuery = { tags: [4, 8] }
    const restored = fromPersisted(toPersisted(tab))
    assert.equal(restored.searchText, 'photo'); assert.equal(restored.searchType, 'image')
    assert.deepEqual(restored.searchQuery.tags, [4, 8])
  })
  await test('F06: preexisting cyclic tags cannot loop descendant traversal', async () => {
    const tags = useTagStore(); tags.tags = [{ id: 1, parent_id: 2 }, { id: 2, parent_id: 1 }]
    assert.deepEqual(tags.getDescendantIds(1), [2])
  })
  await test('R01: query scope clears selection while paging preserves it', async () => {
    const store = useFileStore(); store.activeTab.workspace = 'A'
    fileApi.search = async () => response('old')
    await store.search(); store.selectFile(1)
    await store.search(); assert.equal(store.selectedIds.has(1), true)
    const pending = deferred(); fileApi.search = () => pending.promise
    store.activeTab.searchText = 'changed'; const changing = store.search()
    store.selectFile(1); store.selectAll(); assert.equal(store.selectedCount, 0)
    pending.resolve(response('new')); await changing
    assert.equal(store.selectedCount, 0); assert.equal(store.activeId, null)
  })
  await test('R07: rejected query keeps last results and exposes retry state', async () => {
    const store = useFileStore(); fileApi.search = async () => response('old')
    await store.search(); const applied = store.activeTab.appliedQuery
    fileApi.search = async () => { throw new Error('offline') }
    store.activeTab.searchText = 'changed'; await store.search()
    assert.equal(store.files[0].name, 'old'); assert.match(store.activeTab.queryError, /搜索失败/)
    assert.equal(store.activeTab.appliedQuery, applied)
    store.selectFile(1); store.selectAll()
    assert.equal(store.selectedCount, 0)
    fileApi.search = async () => response('new'); await store.search()
    assert.equal(store.activeTab.queryError, ''); assert.equal(store.files[0].name, 'new')
  })
  await test('R18: refresh keeps loaded depth and ignores unrelated workspaces', async () => {
    const store = useFileStore(); const tab = store.activeTab; tab.workspace = 'A'
    let calls = 0, limit = 0, restored = 0
    fileApi.search = async query => { calls++; limit = query.limit; return { files: Array.from({length: query.limit ?? 500}, (_, i) => ({id: i + 1, name: String(i), tag_ids: []})), total: 2000, has_more: true } }
    await store.search(); tab.files = Array.from({length: 1500}, (_, i) => ({id: i + 1, name: String(i), tag_ids: []}))
    store.registerScrollHooks({ capture: () => 7200, restore: value => { restored = value } })
    await store.refreshChangedPaths(['B/photo.jpg']); assert.equal(calls, 1)
    await store.refreshChangedPaths(['A/photo.jpg']); assert.equal(calls, 2)
    assert.equal(limit, 1500); assert.equal(restored, 7200); assert.equal(tab.files.length, 1500)
  })
  await test('R12: rename validates literal file names before submission', async () => {
    const { fileNameError } = await server.ssrLoadModule('/src/utils/fileNames.ts')
    for (const name of ['../x', 'a/b', 'C:bad', 'NUL.png', 'a.', ' a', 'x\u0000y']) assert.ok(fileNameError(name))
    for (const name of ['.gitignore', '设计参考.png', 'photo-01.JPG']) assert.equal(fileNameError(name), '')
  })
  await test('R01/R08: sorting retains names and tags of selections beyond the loaded page', async () => {
    const store = useFileStore()
    fileApi.search = async () => ({ files: [{ id: 1, name: 'original', tag_ids: [3] }], total: 1000, has_more: true })
    await store.search(); store.selectFile(1)
    fileApi.search = async () => ({ files: [{ id: 2, name: 'sorted-first', tag_ids: [] }], total: 1000, has_more: true })
    await store.search({ sort_by: 'size' })
    assert.equal(store.selectedFiles[0].name, 'original')
    assert.equal(store.hiddenSelectedCount, 1)
    store.addTagsToFile(1, [5]); assert.deepEqual(store.selectedFiles[0].tag_ids, [3, 5])
    store.removeFile(1); assert.equal(store.selectedCount, 0)
    assert.equal(store.activeTab.selectedRecords.size, 0)
  })
  // 直接运行 Vue SFC 的实际 setup/actions；SSR 上下文不挂载 UI，不访问真实文件。
  const setupActions = async path => {
    const { default: component } = await server.ssrLoadModule(path)
    const app = createSSRApp({}); app.provide(ssrContextKey, { modules: new Set() })
    const scope = effectScope(), previousWarn = console.warn
    let state
    try { console.warn = () => {}; state = app.runWithContext(() => scope.run(() => component.setup({}, { expose() {} }))) }
    finally { console.warn = previousWarn }
    return { state, stop: () => scope.stop() }
  }
  const silentSuccess = ElMessage.success, silentWarning = ElMessage.warning
  ElMessage.success = () => {}; ElMessage.warning = () => {}
  await test('detail follows the last clicked file during multi-selection, including media and tags', async () => {
    const store = useFileStore(), tags = useTagStore()
    store.activeTab.files = [
      { id: 1, name: 'first.jpg', path: '', size: 1024, type: 'image', tag_ids: [1] },
      { id: 2, name: 'second.mp4', path: '', size: 2048, type: 'video', tag_ids: [2] },
      { id: 3, name: 'third.mp4', path: '', size: 4096, type: 'video', tag_ids: [3] },
    ]
    tags.tags = [1, 2, 3].map(id => ({ id, name: `file-tag-${id}` }))
    tags.reloadTags = async () => {}
    const previousMediaInfo = fileApi.getMediaInfo
    const second = deferred(), third = deferred()
    fileApi.getMediaInfo = id => id === 2 ? second.promise : third.promise
    store.selectFile(1)
    const { state, stop } = await setupActions('/src/views/DetailPanel.vue')
    try {
      store.selectFile(2, true); await nextTick()
      assert.equal(store.selectedCount, 2); assert.equal(state.selectedFile.value.id, 2)
      assert.equal(state.mediaLoading.value, true)
      store.selectFile(3, true); await nextTick()
      second.resolve({ file_id: 2, duration: 22, width: 1920, height: 1080 }); await nextTick()
      assert.equal(state.mediaInfo.value, null)
      third.resolve({ file_id: 3, duration: 33, width: 1080, height: 1920 }); await nextTick()
      assert.equal(state.mediaInfo.value.file_id, 3)
      const { default: component } = await server.ssrLoadModule('/src/views/DetailPanel.vue')
      const app = createSSRApp(component).use(getActivePinia()).use(ElementPlus)
      app.provide(ID_INJECTION_KEY, { prefix: 1, current: 0 })
      app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
      app.config.warnHandler = () => {}
      const markup = await renderToString(app)
      assert.match(markup, /third\.mp4/); assert.match(markup, /1080 × 1920/)
      assert.match(markup, /\/api\/files\/3\/preview/); assert.match(markup, /file-tag-3/)
      assert.doesNotMatch(markup, /已选择 3 个文件|共同标签|部分文件拥有/)
      state.openTagDialog(); state.selectedTagIds.value = [5]
      let submitted
      fileApi.updateTags = async (id, update) => { submitted = { id, tags: [...update.tag_ids] } }
      await state.saveTags()
      assert.deepEqual(submitted, { id: 3, tags: [5] })
      assert.equal(store.selectedCount, 3); assert.deepEqual(store.files[0].tag_ids, [1])
    } finally { stop(); fileApi.getMediaInfo = previousMediaInfo }
  })
  await test('R02: detail save freezes file and tag IDs across selection changes', async () => {
    const store = useFileStore(), tags = useTagStore()
    store.activeTab.files = [{ id: 1, name: 'a', type: 'image', tag_ids: [1] }, { id: 2, name: 'b', type: 'image', tag_ids: [2] }]
    store.selectFile(1); tags.reloadTags = async () => {}
    const { state, stop } = await setupActions('/src/views/DetailPanel.vue')
    try {
      state.openTagDialog(); state.selectedTagIds.value = [5]
      const request = deferred(); let submitted
      fileApi.updateTags = async (id, update) => { submitted = { id, tags: [...update.tag_ids] }; await request.promise }
      const saving = state.saveTags()
      store.selectFile(2); state.selectedTagIds.value = [8]; await nextTick()
      request.resolve(); await saving
      assert.deepEqual(submitted, { id: 1, tags: [5] })
      assert.deepEqual(store.files[0].tag_ids, [5]); assert.deepEqual(store.files[1].tag_ids, [2])
    } finally { stop() }
  })
  await test('R02: remove confirmation keeps the original file target', async () => {
    const store = useFileStore(), tags = useTagStore()
    store.activeTab.files = [{ id: 1, name: 'a', type: 'image', tag_ids: [1, 3] }, { id: 2, name: 'b', type: 'image', tag_ids: [2] }]
    store.selectFile(1); tags.reloadTags = async () => {}
    const { state, stop } = await setupActions('/src/views/DetailPanel.vue')
    const confirmation = deferred(), previousConfirm = ElMessageBox.confirm
    try {
      ElMessageBox.confirm = () => confirmation.promise
      let submitted
      fileApi.updateTags = async (id, update) => { submitted = { id, tags: [...update.tag_ids] } }
      const removing = state.confirmRemoveTag({ id: 1, name: 'one' })
      store.selectFile(2); confirmation.resolve(); await removing
      assert.deepEqual(submitted, { id: 1, tags: [3] })
      assert.deepEqual(store.files[1].tag_ids, [2])
    } finally { ElMessageBox.confirm = previousConfirm; stop() }
  })
  await test('R08: batch delete continues after failure and retries only failures', async () => {
    const store = useFileStore()
    store.activeTab.files = [1,2,3,4].map(id => ({ id, name: String(id), type: 'image', tag_ids: [] }))
    store.selectFile(1); store.selectFile(2, true); store.selectFile(3, true)
    const { state, stop } = await setupActions('/src/components/BatchOperations.vue')
    try {
      state.confirmDelete(); store.selectFile(4); await nextTick()
      const calls = []; let fail = true
      fileApi.delete = async id => { calls.push(id); if (id === 2 && fail) throw new Error('blocked') }
      await state.deleteSelectedFiles()
      assert.deepEqual(calls, [1,2,3]); assert.deepEqual(state.targets.value.map(f => f.id), [2])
      assert.equal(state.failures.value.length, 1); assert.equal(state.submitting.value, false)
      fail = false; await state.deleteSelectedFiles()
      assert.deepEqual(calls, [1,2,3,2]); assert.equal(store.files[0].id, 4)
    } finally { stop() }
  })
  ElMessage.success = silentSuccess; ElMessage.warning = silentWarning
  console.log(JSON.stringify({ tests: results.length, results }))
} finally {
  await server.close()
}
