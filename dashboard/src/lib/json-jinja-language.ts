import type * as Monaco from 'monaco-editor'

export const JSON_JINJA_LANGUAGE_ID = 'json-jinja'

const JINJA_KEYWORDS = [
  'if',
  'elif',
  'else',
  'endif',
  'for',
  'endfor',
  'in',
  'is',
  'not',
  'and',
  'or',
  'set',
  'endset',
  'with',
  'endwith',
  'macro',
  'endmacro',
  'call',
  'endcall',
  'filter',
  'endfilter',
  'block',
  'endblock',
  'include',
  'import',
  'from',
  'as',
  'raw',
  'endraw',
  'true',
  'false',
  'none',
  'True',
  'False',
  'None',
]

/**
 * JSON with Jinja2 `{{ }}`, `{% %}` and `{# #}` tags, also inside strings.
 * Unlike the `json` language it has no diagnostics, since a Jinja'd document is not JSON until rendered.
 */
export const jsonJinjaLanguage: Monaco.languages.IMonarchLanguage = {
  keywords: JINJA_KEYWORDS,
  tokenizer: {
    root: [{ include: '@jinja' }, [/"/, 'string', '@string'], [/-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/, 'number'], [/\b(?:true|false|null)\b/, 'keyword'], [/[{}[\],:]/, 'delimiter'], [/\s+/, 'white']],
    string: [{ include: '@jinja' }, [/[^"\\{]+/, 'string'], [/\\./, 'string.escape'], [/\{/, 'string'], [/"/, 'string', '@pop']],
    jinja: [
      [/\{#/, 'comment', '@jinjaComment'],
      [/\{\{-?/, 'tag', '@jinjaExpression'],
      [/\{%-?/, 'tag', '@jinjaStatement'],
    ],
    jinjaComment: [
      [/#\}/, 'comment', '@pop'],
      [/[^#]+|#/, 'comment'],
    ],
    jinjaExpression: [[/-?\}\}/, 'tag', '@pop'], { include: '@jinjaCode' }],
    jinjaStatement: [[/-?%\}/, 'tag', '@pop'], { include: '@jinjaCode' }],
    jinjaCode: [
      [/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/, 'string'],
      [/\d+(?:\.\d+)?/, 'number'],
      [/[A-Za-z_]\w*/, { cases: { '@keywords': 'keyword', '@default': 'variable' } }],
      [/\s+/, 'white'],
      [/./, 'operator'],
    ],
  },
}

export function registerJsonJinjaLanguage(monaco: typeof Monaco) {
  monaco.languages.register({ id: JSON_JINJA_LANGUAGE_ID })
  monaco.languages.setMonarchTokensProvider(JSON_JINJA_LANGUAGE_ID, jsonJinjaLanguage)
}
