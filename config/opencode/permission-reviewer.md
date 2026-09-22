# OpenCode permission reviewer

`plugins/permission-reviewer.ts` registers the official OpenCode 2
[`permission.hook("evaluate")`](https://opencode.ai/v2/docs/build/plugins#permissions-1).
The global plugin directory is discovered automatically; no package installation
or additional provider credentials are required.

- Model: `openai/gpt-5.6-sol#medium`, using the active ChatGPT Pro/Plus connection.
- Existing explicit `deny` rules remain final.
- Already allowed reads, searches, web retrieval, questions, skills, and subagent
  launches retain their existing decision. Child tool operations are still reviewed.
- Other actions, including shell commands, edits, and every existing `ask`, are reviewed.
- The model returns `allow`, `ask`, or `deny`. An `ask` continues through the normal
  OpenCode permission prompt and the existing Moshi notification hook.
- Invalid output, missing context, an unavailable subscription connection, or a
  30-second timeout produces `ask`. The reviewer never switches to API-key billing.

The evidence contains the proposed tool input, permission metadata, user requests,
assistant text, and compaction summaries. Parent conversations are included for
subagents. Attachments, reasoning, and tool outputs are omitted. Context beyond
80,000 characters or five session levels requires human confirmation rather than
silently truncating authorization or operation details.

The review policy allows necessary routine work under an existing user request.
Publishing, messages, pushes, deployment, purchases, system installs, destructive
operations, and sending private data to new destinations require explicit authorization.
Uncertain cases ask; clearly malicious or user-forbidden actions are denied.

The `MODEL` constant near the top of the plugin selects the model and reasoning
variant. The current choice favors judgment quality for permission decisions.
Logs contain the session ID, action, decision, and latency, without command or
conversation contents. AI decisions do not replace filesystem or network sandboxing.

Run the behavior checks with:

```sh
bun test tests/permission-reviewer.test.ts
```

To disable this plugin, add `"-local.permission-reviewer"` to the V2 `plugins`
array in `opencode.json`, or move the plugin file out of `plugins/`.
