import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'

const delimiters = ['brackets', 'dollars', 'beg_end']
const markdown = new MarkdownIt({ html: false, breaks: true }).use(texmath, {
  engine: katex,
  delimiters,
  katexOptions: { trust: false, throwOnError: false, maxExpand: 1000, maxSize: 20 },
})

// texmath 的块规则默认不能中断段落，导致紧接正文的 \[ 先被当作 Markdown 转义。
// 复用同一组公式规则作为段落终止规则，同时保留代码块和嵌套列表的解析方式。
const blockMathRules = texmath.mergeDelimiters(delimiters).block.map(rule => texmath.block(rule))
markdown.block.ruler.before('fence', 'math_block_interrupt', (state, start, end, silent) =>
  blockMathRules.some(rule => rule(state, start, end, silent)), { alt: ['paragraph'] })

// 输出在 MarkdownContent 中统一净化后插入 DOM。
export function renderMarkdown(content) {
  return markdown.render(content)
}
