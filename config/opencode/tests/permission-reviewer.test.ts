import { afterEach, expect, mock, spyOn, test } from "bun:test"
import plugin from "../plugins/permission-reviewer"

const user = { id: "msg_user", type: "user", text: "Fix the parser and run its tests. Do not push." }
const tool = { type: "tool", id: "call_1", name: "shell", state: { status: "running", input: { command: "npm test" } } }
const assistant = { id: "msg_tool", type: "assistant", content: [tool] }

async function harness(options: any = {}) {
  let evaluate: any
  const dispose = mock(async () => {})
  const generate = mock(options.generate ?? (async () => ({ text: JSON.stringify({ effect: "allow", reason: "依頼されたテストの実行です。" }) })))
  const context = mock(options.context ?? (async () => [user, assistant]))
  const ctx: any = {
    provider: { get: async () => ({ location: { directory: "/tmp/project" }, data: { settings: { baseURL: options.baseURL ?? "https://chatgpt.com/backend-api/codex" } } }) },
    permission: { hook: async (name: string, fn: any) => { expect(name).toBe("evaluate"); evaluate = fn; return { dispose } } },
    generate: { text: generate },
    session: {
      get: options.get ?? (async () => ({ location: { directory: "/tmp/project" } })),
      context,
    },
  }
  const cleanup = await plugin.setup(ctx)
  return { evaluate, generate, context, cleanup, dispose }
}

const operation = (overrides = {}) => ({ sessionID: "ses_test", action: "shell", resources: ["npm test"], effect: "allow", source: { type: "tool", messageID: "msg_tool", id: "call_1" }, ...overrides })
afterEach(() => mock.restore())

test("leaves configured deny and allowed reads alone, but reviews sensitive reads", async () => {
  const h = await harness()
  await h.evaluate(operation({ effect: "deny" }))
  await h.evaluate(operation({ action: "read" }))
  expect(h.generate).not.toHaveBeenCalled()
  await h.evaluate(operation({ action: "read", effect: "ask" }))
  expect(h.generate).toHaveBeenCalledTimes(1)
})

test("uses Sol medium, exact tool arguments and user restrictions, without tool results or reasoning", async () => {
  const h = await harness({ context: async () => [user, { ...assistant, content: [tool, { type: "reasoning", text: "PRIVATE_REASONING" }, { type: "tool", id: "old", state: { status: "completed", content: [{ text: "SECRET_OUTPUT" }] } }] }] })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("allow")
  const [request] = h.generate.mock.calls[0]
  expect(request.model).toEqual({ providerID: "openai", id: "gpt-5.6-sol", variant: "medium" })
  expect(request.prompt).toContain('"command":"npm test"')
  expect(request.prompt).toContain("Do not push.")
  expect(request.prompt).not.toContain("SECRET_OUTPUT")
  expect(request.prompt).not.toContain("PRIVATE_REASONING")
})

test("includes root user authorization when evaluating a delegated child", async () => {
  const h = await harness({
    get: async ({ sessionID }: any) => ({ parentID: sessionID === "ses_child" ? "ses_root" : undefined, location: { directory: "/tmp/project" } }),
    context: async ({ sessionID }: any) => sessionID === "ses_child" ? [{ ...user, text: "Push the branch" }, assistant] : [user],
  })
  await h.evaluate(operation({ sessionID: "ses_child" }))
  expect(h.generate.mock.calls[0][0].prompt).toContain('"parentID":"ses_root"')
  expect(h.generate.mock.calls[0][0].prompt).toContain("Do not push.")
})

test.each(["ask", "deny"])("applies a valid %s decision with its explanation", async (effect) => {
  const h = await harness({ generate: async () => ({ text: JSON.stringify({ effect, reason: "ユーザーの許可範囲を超えています。" }) }) })
  const event: any = operation()
  await h.evaluate(event)
  expect(event.effect).toBe(effect)
  expect(event.message).toContain("ユーザーの許可範囲")
})

test.each(["not JSON", '{"effect":"allow"}', '{"effect":"always","reason":"ok"}', "null", '{"effect":"allow","reason":""}'])("asks on invalid model output: %s", async (text) => {
  const h = await harness({ generate: async () => ({ text }) })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("ask")
})

test("asks on generation failures and missing exact tool input", async () => {
  const h = await harness({ generate: async () => { throw new Error("offline") } })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("ask")
  const missing = await harness({ context: async () => [user] })
  const missingEvent = operation()
  await missing.evaluate(missingEvent)
  expect(missingEvent.effect).toBe("ask")
  expect(missing.generate).not.toHaveBeenCalled()
})

test("does not fall back to an API-key endpoint", async () => {
  const h = await harness({ baseURL: "https://api.openai.com/v1" })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("ask")
  expect(h.generate).not.toHaveBeenCalled()
})

test("asks instead of truncating an oversized operation or missing ancestry", async () => {
  const h = await harness({ context: async () => [{ ...user, text: "x".repeat(81_000) }, assistant] })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("ask")
  expect(h.generate).not.toHaveBeenCalled()
  const loop = await harness({ get: async () => ({ parentID: "ses_test", location: { directory: "/tmp" } }) })
  const loopEvent = operation()
  await loop.evaluate(loopEvent)
  expect(loopEvent.effect).toBe("ask")
})

test("times out, aborts the request, and ignores a late allow response", async () => {
  const actualTimeout = globalThis.setTimeout
  spyOn(globalThis, "setTimeout").mockImplementation(((fn: any) => actualTimeout(fn, 5)) as any)
  let release: any
  let signal: AbortSignal | undefined
  const h = await harness({ generate: (_: any, options: any) => { signal = options.signal; return new Promise((resolve) => { release = resolve }) } })
  const event = operation()
  await h.evaluate(event)
  expect(event.effect).toBe("ask")
  expect(signal?.aborted).toBe(true)
  release({ text: '{"effect":"allow","reason":"late"}' })
  await new Promise((resolve) => actualTimeout(resolve, 10))
  expect(event.effect).toBe("ask")
})

test("disposes the hook when the plugin unloads", async () => {
  const h = await harness()
  await h.cleanup?.()
  expect(h.dispose).toHaveBeenCalledTimes(1)
})
