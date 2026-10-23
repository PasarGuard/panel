import ace from 'ace-builds/src-noconflict/ace'
import 'ace-builds/src-noconflict/mode-json'

type AceRequire = (name: string) => unknown
type AceExports = Record<string, unknown>
type AceRule = { token: string; start: string; end: string }
type HighlightRules = { $rules: Record<string, AceRule[]>; normalizeRules: () => void }
type Constructor = { call: (self: unknown) => void }
type Oop = { inherits: (child: unknown, parent: unknown) => void }

// `define` exists on the Ace global but not in its typings.
const aceDefine = (ace as unknown as { define: (name: string, deps: string[], factory: (require: AceRequire, exports: AceExports) => void) => void }).define

// Ace's counterpart of the `json-jinja` Monaco language: JSON plus Jinja2 tags, also inside strings.
aceDefine('ace/mode/json_jinja_highlight_rules', ['require', 'exports', 'module', 'ace/lib/oop', 'ace/mode/json_highlight_rules'], (require, exports) => {
  const oop = require('ace/lib/oop') as Oop
  const { JsonHighlightRules } = require('ace/mode/json_highlight_rules') as { JsonHighlightRules: Constructor }

  const JsonJinjaHighlightRules = function (this: HighlightRules) {
    JsonHighlightRules.call(this)
    // Rules are rewritten in place when normalized, so each state gets its own copies.
    const jinja = (): AceRule[] => [
      { token: 'comment', start: '\\{#', end: '#\\}' },
      { token: 'support.function', start: '\\{\\{-?', end: '-?\\}\\}' },
      { token: 'keyword', start: '\\{%-?', end: '-?%\\}' },
    ]
    this.$rules.start.unshift(...jinja())
    this.$rules.string.unshift(...jinja())
    this.normalizeRules()
  }
  oop.inherits(JsonJinjaHighlightRules, JsonHighlightRules)
  exports.JsonJinjaHighlightRules = JsonJinjaHighlightRules
})

aceDefine('ace/mode/json_jinja', ['require', 'exports', 'module', 'ace/lib/oop', 'ace/mode/json', 'ace/mode/json_jinja_highlight_rules'], (require, exports) => {
  const oop = require('ace/lib/oop') as Oop
  const { Mode: JsonMode } = require('ace/mode/json') as { Mode: Constructor }
  const { JsonJinjaHighlightRules } = require('ace/mode/json_jinja_highlight_rules') as { JsonJinjaHighlightRules: unknown }

  const Mode = function (this: { HighlightRules: unknown }) {
    JsonMode.call(this)
    this.HighlightRules = JsonJinjaHighlightRules
  }
  oop.inherits(Mode, JsonMode)
  exports.Mode = Mode
})
