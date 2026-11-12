import { io, Socket } from 'socket.io-client'
import type {
  FileChangedEvent,
  FileDeletedEvent,
  ScanProgressEvent,
  ScanCompletedEvent,
  ThumbnailReadyEvent,
} from '../types'
import { getApiBaseUrl, getSessionToken, resolveApiBaseUrl } from './baseUrl'

class WebSocketClient {
  private workspacePaths: string[] = []
  private recovering = false
  private socket: Socket | null = null
  private eventHandlers: Map<string, Set<(data: unknown) => void>> = new Map()

  connect(): void {
    if (this.socket) return

    // 每次 connect 时取最新 baseUrl；启动竞速时若仍未解析，
    // socket.io-client 接受空串（连相对路径，走 vite 代理）。
    const wsUrl = getApiBaseUrl() || window.location.origin
    this.socket = io(wsUrl, {
      auth: (callback) => callback({ token: getSessionToken() }),
      transports: ['websocket', 'polling'],  // 允许降级到 polling
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 60000,  // 连接超时 60 秒
    })

    this.socket.on('connect', () => {
      this.socket?.emit('subscribe_workspace', { paths: this.workspacePaths })
      console.log('WebSocket connected')
      this.emit('connected', {})
    })

    this.socket.on('connect_error', async () => {
      if (this.recovering) return
      this.recovering = true
      try {
        await resolveApiBaseUrl(true)
        this.disconnect()
        this.connect()
      } catch (error) { this.emit('error', { message: String(error) }) }
      finally { this.recovering = false }
    })

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
      this.emit('disconnected', {})
    })

    this.socket.on('error', (error: unknown) => {
      console.error('WebSocket error:', error)
      this.emit('error', error)
    })

    // 文件变更事件
    this.socket.on('file_changed', (data: FileChangedEvent) => {
      this.emit('file_changed', data)
    })

    this.socket.on('file_deleted', (data: FileDeletedEvent) => {
      this.emit('file_deleted', data)
    })

    // 扫描事件
    this.socket.on('scan_started', (data: { path: string }) => {
      this.emit('scan_started', data)
    })

    this.socket.on('scan_progress', (data: ScanProgressEvent) => {
      this.emit('scan_progress', data)
    })

    this.socket.on('scan_completed', (data: ScanCompletedEvent) => {
      this.emit('scan_completed', data)
    })

    this.socket.on('scan_error', (error: { message: string }) => {
      this.emit('scan_error', error)
    })

    // 缩略图异步生成完成
    this.socket.on('thumbnail_ready', (data: ThumbnailReadyEvent) => {
      this.emit('thumbnail_ready', data)
    })

    // 文件夹结构变化（创建/删除目录、移动/复制/导入文件等）
    this.socket.on('folder_tree_changed', (data: { workspace: string }) => {
      this.emit('folder_tree_changed', data)
    })
  }

  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
  }

  subscribeWorkspace(path: string): void { this.subscribeWorkspaces([path]) }

  subscribeWorkspaces(paths: string[]): void {
    this.workspacePaths = [...paths]
    if (this.socket?.connected) this.socket.emit('subscribe_workspace', { paths })
  }

  unsubscribeWorkspace(): void {
    this.workspacePaths = []
    this.socket?.emit('unsubscribe_workspace', {})
  }

  startScan(path: string): void {
    this.socket?.emit('start_scan', { path })
  }

  on<T>(event: string, handler: (data: T) => void): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set())
    }
    this.eventHandlers.get(event)!.add(handler as (data: unknown) => void)

    // 返回取消订阅函数
    return () => {
      this.eventHandlers.get(event)?.delete(handler as (data: unknown) => void)
    }
  }

  private emit(event: string, data: unknown): void {
    const handlers = this.eventHandlers.get(event)
    if (handlers) {
      handlers.forEach(handler => handler(data))
    }
  }

  cancelScan(): void { this.socket?.emit('cancel_scan', {}) }

  isConnected(): boolean {
    return this.socket?.connected ?? false
  }
}

export const wsClient = new WebSocketClient()
