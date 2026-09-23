# -*- coding: utf-8 -*-
"""用 Word COM 打开 docx：
1) 统一设置样式字体（标题黑体、正文宋体、TOC 宋体、超链接黑色无下划线）
2) 更新全部域（目录、页码）
3) 保存
"""
import win32com.client

PATH = r'E:\问题求解实战\期末周别慌_系统需求分析.docx'

STYLE_FONTS = [
    ('Normal', '宋体'), ('Heading 1', '黑体'), ('Heading 2', '黑体'),
    ('Heading 3', '黑体'), ('Heading 4', '黑体'),
    ('TOC 1', '宋体'), ('TOC 2', '宋体'), ('TOC 3', '宋体'),
    ('目录 1', '宋体'), ('目录 2', '宋体'), ('目录 3', '宋体'),
]

word = win32com.client.Dispatch('Word.Application')
word.Visible = False
try:
    doc = word.Documents.Open(PATH)
    for sname, far in STYLE_FONTS:
        try:
            st = doc.Styles(sname)
            st.Font.Name = 'Times New Roman'
            st.Font.NameFarEast = far
        except Exception:
            pass
    try:  # 目录超链接改黑色、无下划线，避免目录发蓝
        hs = doc.Styles('Hyperlink')
        hs.Font.Color = 0
        hs.Font.Underline = 0
    except Exception:
        pass
    for toc in doc.TablesOfContents:
        toc.Update()
    for s in doc.Sections:
        for f in s.Footers(1).Range.Fields:
            try:
                f.Update()
            except Exception:
                pass
    doc.Save()
    doc.Close()
    print('样式字体与目录域已更新并保存')
finally:
    word.Quit()
