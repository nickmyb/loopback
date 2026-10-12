"""模型写的 SVG：先当成不可信输入消毒，再放进课件（docs/decisions.md D8）。

- 必须是合法的 XML，根元素必须是 <svg>；写坏了抛 ToolError，模型会看到错误并重写（自我修正）。
- 删掉能执行代码或外连的东西：<script>、<foreignObject>、<iframe> 等元素，on* 事件属性，
  指向外部的 href，以及 javascript: / 外部 url(...)。动画（<animate>、CSS keyframes）保留。
- 不解析外部实体、不联网（防 XXE）。
"""

from __future__ import annotations

from lxml import etree

from loopback.tools import ToolError

MAX_SVG_CHARS = 200_000
_DENY_TAGS = {"script", "foreignObject", "iframe", "object", "embed", "audio", "video", "image"}
_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, remove_comments=True, remove_pis=True
)


def sanitize_svg(svg: str) -> str:
    """校验并清洗一段 SVG，返回可以直接内嵌进 HTML 的安全版本。"""
    if len(svg) > MAX_SVG_CHARS:
        raise ToolError(f"SVG 太大（{len(svg)} 字符，上限 {MAX_SVG_CHARS}），请简化")
    try:
        root = etree.fromstring(svg.strip().encode("utf-8"), _PARSER)
    except etree.XMLSyntaxError as e:
        raise ToolError(f"SVG 不是合法的 XML：{e}。请修正后重新调用") from None
    if etree.QName(root).localname != "svg":
        raise ToolError("SVG 的根元素必须是 <svg>")
    # 1) 先收集再删除危险元素（边遍历边删会漏掉节点）
    doomed = [
        el
        for el in root.iter()
        if isinstance(el.tag, str) and etree.QName(el).localname in _DENY_TAGS
    ]
    for el in doomed:
        el.getparent().remove(el)
    # 2) 清理每个元素上的危险属性
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            name, value = etree.QName(attr).localname.lower(), el.attrib[attr].strip().lower()
            external = "javascript:" in value or "url(http" in value or "url(//" in value
            if name.startswith("on") or (name == "href" and not value.startswith("#")) or external:
                del el.attrib[attr]
    # 3) <style> 里的外部资源（@import、远程 url）也去掉
    for style in root.iter("{*}style", "style"):
        if style.text and ("@import" in style.text or "url(http" in style.text):
            style.text = ""
    return etree.tostring(root, encoding="unicode")
