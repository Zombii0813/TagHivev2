import { io, Socket } from 'socket.io-client'
import type {
  FileChangedEvent,
  FileDeletedEvent,
  ScanProgressEvent,
  ScanCompletedEvent,
} from '../types'

const WS_URL = import.meta.env.VITE_WS_URL || 'http://127.0.0.1:8721'

class WebSocketClient {
  private socket: Socket | null = null
  private eventHandlers: Map<string, Set<(data: unknown) => void>> = new Map()

  connect(): void {
    if (this.socket?.connected) return

    this.socket = io(WS_URL, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    })

    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.emit('connected', {})
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
  }

  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
  }

  subscribeWorkspace(path: string): void {
    this.socket?.emit('subscribe_workspace', { path })
  }

  unsubscribeWorkspace(): void {
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

  isConnected(): boolean {
    return this.socket?.connected ?? false
  }
}

export const wsClient = new WebSocketClient()
