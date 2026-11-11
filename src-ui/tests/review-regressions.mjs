// 使用现有 Vite SSR 执行真实 Pinia actions，网络接口以可控延迟替换。
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createPinia, setActivePinia } from 'pinia'

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
  console.log(JSON.stringify({ tests: results.length, results }))
} finally {
  await server.close()
}
