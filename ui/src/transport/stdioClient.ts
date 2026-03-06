import { spawn, type ChildProcessByStdio } from "node:child_process"
import type { Readable, Writable } from "node:stream"
import { randomUUID } from "node:crypto"
import { delimiter, dirname, resolve } from "node:path"
import { createInterface } from "node:readline"
import { fileURLToPath } from "node:url"

type RpcEvent = {
  type: "event"
  event: string
  data: Record<string, unknown>
}

type RpcResponse = {
  type: "response"
  id: string
  ok: boolean
  result?: unknown
  error?: { code: number; message: string; data?: unknown }
}

export type EventHandler = (event: RpcEvent) => void
export type ErrorOutputHandler = (line: string) => void

function projectRootFromCurrentFile() {
  const here = dirname(fileURLToPath(import.meta.url))
  return resolve(here, "../../..")
}

export class StdioRpcClient {
  private proc: ChildProcessByStdio<Writable, Readable, Readable> | null = null
  private readonly pending = new Map<
    string,
    {
      resolve: (value: unknown) => void
      reject: (reason?: unknown) => void
    }
  >()
  private readonly eventHandlers = new Set<EventHandler>()
  private readonly errorHandlers = new Set<ErrorOutputHandler>()

  constructor(
    private readonly pythonCmd: string =
      process.env.PYTHON_BIN ?? process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3"),
    private readonly projectRoot: string = process.env.IZTEAMSLOTS_ROOT ?? projectRootFromCurrentFile(),
  ) {}

  start() {
    if (this.proc) return

    this.proc = spawn(this.pythonCmd, ["-m", "backend"], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: this.projectRoot,
      shell: process.platform === "win32",
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH
          ? `${this.projectRoot}${delimiter}${process.env.PYTHONPATH}`
          : this.projectRoot,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
    })

    const proc = this.proc
    if (!proc) {
      throw new Error("RPC process did not start")
    }

    proc.on("error", (err) => {
      this.proc = null
      for (const [, p] of this.pending) {
        p.reject(new Error(`RPC spawn error: ${err.message}`))
      }
      this.pending.clear()
    })

    const rl = createInterface({ input: proc.stdout })
    const stderr = createInterface({ input: proc.stderr })

    stderr.on("line", (line) => {
      const message = line.trim()
      if (!message) return
      for (const handler of this.errorHandlers) handler(message)
    })

    rl.on("line", (line) => {
      if (!line.trim()) return
      let payload: RpcEvent | RpcResponse
      try {
        payload = JSON.parse(line) as RpcEvent | RpcResponse
      } catch {
        return
      }

      if (payload.type === "event") {
        for (const handler of this.eventHandlers) handler(payload)
        return
      }

      const entry = this.pending.get(payload.id)
      if (!entry) return
      this.pending.delete(payload.id)
      if (payload.ok) {
        entry.resolve(payload.result)
      } else {
        entry.reject(new Error(payload.error?.message ?? "RPC error"))
      }
    })

    proc.on("exit", (code, signal) => {
      this.proc = null
      const suffix = signal ? `signal ${signal}` : `code ${String(code ?? "unknown")}`
      for (const handler of this.errorHandlers) handler(`RPC backend остановлен (${suffix})`)
      for (const [id, p] of this.pending) {
        p.reject(new Error(`RPC process exited before response: ${id}`))
      }
      this.pending.clear()
    })
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.add(handler)
    return () => this.eventHandlers.delete(handler)
  }

  onErrorOutput(handler: ErrorOutputHandler): () => void {
    this.errorHandlers.add(handler)
    return () => this.errorHandlers.delete(handler)
  }

  async request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    this.start()
    const id = randomUUID()
    const message = JSON.stringify({ id, method, params })

    if (!this.proc) {
      throw new Error("RPC process is not running")
    }

    return await new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: (value) => resolve(value as T),
        reject,
      })
      if (!this.proc) {
        reject(new Error("RPC process is not running"))
        return
      }
      this.proc.stdin.write(message + "\n")
    })
  }

  async shutdown() {
    try {
      await this.request("shutdown")
    } catch {
      // no-op
    }
    if (this.proc) {
      this.proc.kill()
      this.proc = null
    }
  }
}
