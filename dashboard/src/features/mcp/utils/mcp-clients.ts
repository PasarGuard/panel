export const MCP_KEY_PLACEHOLDER = 'YOUR_API_KEY'
export const MCP_SERVER_ID = 'pasarguard'

export type McpClientId = 'claude-web' | 'chatgpt' | 'claude-code' | 'claude-desktop' | 'cursor' | 'vscode' | 'windsurf' | 'gemini-cli' | 'codex' | 'cline' | 'zed' | 'http'

export interface McpClientSnippet {
  id: McpClientId
  labelKey: string
  hintKey: string
  content: string
  oauth?: boolean
}

export const buildMcpUrl = (endpointPath: string): string => {
  if (typeof window === 'undefined') return endpointPath
  return `${window.location.origin}${endpointPath}`
}

const json = (value: unknown) => JSON.stringify(value, null, 2)

export const buildMcpClientSnippets = (mcpUrl: string): McpClientSnippet[] => {
  const bearer = `Bearer ${MCP_KEY_PLACEHOLDER}`
  const authHeader = `Authorization: ${bearer}`

  return [
    {
      id: 'claude-web',
      labelKey: 'mcp.clients.claudeWeb',
      hintKey: 'mcp.clients.claudeWebHint',
      content: mcpUrl,
      oauth: true,
    },
    {
      id: 'chatgpt',
      labelKey: 'mcp.clients.chatgpt',
      hintKey: 'mcp.clients.chatgptHint',
      content: mcpUrl,
      oauth: true,
    },
    {
      id: 'claude-code',
      labelKey: 'mcp.clients.claudeCode',
      hintKey: 'mcp.clients.claudeCodeHint',
      content: `claude mcp add --transport http ${MCP_SERVER_ID} ${mcpUrl} --header "${authHeader}"`,
    },
    {
      id: 'claude-desktop',
      labelKey: 'mcp.clients.claudeDesktop',
      hintKey: 'mcp.clients.claudeDesktopHint',
      content: json({
        mcpServers: {
          [MCP_SERVER_ID]: { command: 'npx', args: ['-y', 'mcp-remote', mcpUrl, '--header', authHeader] },
        },
      }),
    },
    {
      id: 'cursor',
      labelKey: 'mcp.clients.cursor',
      hintKey: 'mcp.clients.cursorHint',
      content: json({ mcpServers: { [MCP_SERVER_ID]: { url: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'vscode',
      labelKey: 'mcp.clients.vscode',
      hintKey: 'mcp.clients.vscodeHint',
      content: json({ servers: { [MCP_SERVER_ID]: { type: 'http', url: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'windsurf',
      labelKey: 'mcp.clients.windsurf',
      hintKey: 'mcp.clients.windsurfHint',
      content: json({ mcpServers: { [MCP_SERVER_ID]: { serverUrl: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'gemini-cli',
      labelKey: 'mcp.clients.geminiCli',
      hintKey: 'mcp.clients.geminiCliHint',
      content: json({ mcpServers: { [MCP_SERVER_ID]: { httpUrl: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'codex',
      labelKey: 'mcp.clients.codex',
      hintKey: 'mcp.clients.codexHint',
      content: [`[mcp_servers.${MCP_SERVER_ID}]`, `url = "${mcpUrl}"`, '', `[mcp_servers.${MCP_SERVER_ID}.http_headers]`, `Authorization = "${bearer}"`].join('\n'),
    },
    {
      id: 'cline',
      labelKey: 'mcp.clients.cline',
      hintKey: 'mcp.clients.clineHint',
      content: json({ mcpServers: { [MCP_SERVER_ID]: { type: 'streamableHttp', url: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'zed',
      labelKey: 'mcp.clients.zed',
      hintKey: 'mcp.clients.zedHint',
      content: json({ context_servers: { [MCP_SERVER_ID]: { source: 'custom', url: mcpUrl, headers: { Authorization: bearer } } } }),
    },
    {
      id: 'http',
      labelKey: 'mcp.clients.http',
      hintKey: 'mcp.clients.httpHint',
      content: [`POST ${mcpUrl}`, authHeader, 'Accept: application/json, text/event-stream', 'Content-Type: application/json', '', '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'].join('\n'),
    },
  ]
}
