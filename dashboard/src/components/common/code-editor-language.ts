/**
 * Map Monaco {@link https://microsoft.github.io/monaco-editor/monarch.html} language ids to Ace `mode` names.
 * Unsupported ids fall back to `plain_text`.
 */
export function monacoLanguageToAceMode(monacoId: string | undefined): string {
  const id = (monacoId ?? 'plaintext').toLowerCase()
  const map: Record<string, string> = {
    json: 'json',
    yaml: 'yaml',
    javascript: 'javascript',
    typescript: 'typescript',
    javascriptreact: 'javascript',
    typescriptreact: 'typescript',
    html: 'html',
    css: 'css',
    scss: 'scss',
    less: 'less',
    markdown: 'markdown',
    xml: 'xml',
    python: 'python',
    shell: 'sh',
    sh: 'sh',
    bash: 'sh',
    powershell: 'powershell',
    sql: 'sql',
    graphql: 'graphqlschema',
    dockerfile: 'dockerfile',
    ini: 'ini',
    ruby: 'ruby',
    php: 'php',
    golang: 'golang',
    go: 'golang',
    rust: 'rust',
    java: 'java',
    csharp: 'csharp',
    c: 'c_cpp',
    cpp: 'c_cpp',
    'c++': 'c_cpp',
    plaintext: 'plain_text',
    text: 'plain_text',
  }
  return map[id] ?? 'plain_text'
}
