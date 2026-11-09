import test from 'node:test'
import assert from 'node:assert/strict'
import { renderMarkdown } from '../src/utils/markdown.js'

const derivative = String.raw`\frac{d}{dx}\int_{1}^{\cos x} e^{-t^2}\,dt`
const displayCount = html => (html.match(/class="katex-display"/g) || []).length

test('display formulas immediately after prose render without a blank line', () => {
  const html = renderMarkdown(`分子求导：\n\\[\n${derivative}\n\\]\n分母求导：\n\\[\n\\frac{d}{dx}\\ln(\\cos x)=-\\tan x\n\\]`)
  assert.equal(displayCount(html), 2)
  assert.match(html, /<p>分子求导：<\/p>/)
  assert.match(html, /<p>分母求导：<\/p>/)
  assert.doesNotMatch(html, /katex-error/)
})

test('all supported display delimiters can interrupt paragraphs', () => {
  for (const formula of [String.raw`\[x^2\]`, '$$x^2$$', String.raw`\begin{align}x^2 &= y\end{align}`]) {
    assert.equal(displayCount(renderMarkdown(`公式\n${formula}\n正文`)), 1)
  }
})

test('formulas render in blockquotes and list items with their nesting preserved', () => {
  const quote = renderMarkdown('> 求导：\n> \\[\n> x^2\n> \\]')
  const list = renderMarkdown('1. 求导：\n   \\[\n   x^2\n   \\]\n2. 核对答案')
  assert.equal(displayCount(quote), 1)
  assert.match(quote, /<blockquote>/)
  assert.equal(displayCount(list), 1)
  assert.match(list, /<ol>/)
  assert.match(list, /<li>核对答案<\/li>/)
})

test('inline math and standard Markdown formatting remain available', () => {
  const html = renderMarkdown('# 解答\n\n**步骤**与 *说明*，行内 \\(x^2\\) 和 $y$。\n\n- 列表\n\n| 项目 | 内容 |\n| --- | --- |\n| 结果 | 1 |\n\n[教材](https://example.com)')
  assert.match(html, /<h1>解答<\/h1>/)
  assert.match(html, /<strong>步骤<\/strong>/)
  assert.match(html, /<em>说明<\/em>/)
  assert.match(html, /<ul>/)
  assert.match(html, /<table>/)
  assert.match(html, /href="https:\/\/example.com"/)
  assert.equal((html.match(/class="katex"/g) || []).length, 2)
})

test('code samples and escaped delimiters stay literal', () => {
  for (const source of ['```latex\n\\[x^2\\]\n```', '`\\[x^2\\]`', String.raw`\\[x^2\\]`]) {
    assert.equal(displayCount(renderMarkdown(source)), 0)
  }
  assert.match(renderMarkdown('```js\nconst n = 1\n```'), /<pre><code class="language-js">/)
})

test('incomplete or invalid math preserves surrounding answer text', () => {
  const incomplete = renderMarkdown('求导\n\\[\nx^2\n核对原题')
  assert.equal(displayCount(incomplete), 0)
  assert.match(incomplete, /核对原题/)
  const invalid = renderMarkdown('求导\n\\[\\unknowncommand{x}\\]\n核对原题')
  assert.match(invalid, /核对原题/)
})

test('raw HTML and dangerous Markdown or TeX links cannot create active elements', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[链接](javascript:alert%281%29)\n\n\\(\\href{javascript:alert(1)}{x}\\)')
  assert.doesNotMatch(html, /<script|<img|href="javascript:/)
})
