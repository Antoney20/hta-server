import re
from html import escape
from html.parser import HTMLParser

# formatting tags the editor can emit — everything else is unwrapped
ALLOWED_HTML_TAGS = {
    "p", "br", "div", "span",
    "strong", "b", "em", "i", "u",
    "h2", "h3", "h4",
    "ul", "ol", "li",
    "blockquote", "a",
}
VOID_HTML_TAGS = {"br"}
ALLOWED_HTML_ATTRS = {"a": {"href", "title", "target"}}

# tags whose CONTENTS are discarded entirely, not just unwrapped
DROP_CONTENT_TAGS = {
    "script", "style", "iframe", "object", "embed", "noscript",
    "template", "svg", "math", "head", "title", "meta", "link", "base", "form",
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*):", re.IGNORECASE)


def _safe_url(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    m = _SCHEME_RE.match(value)
    if not m:
        return True  # relative URL (no scheme) is fine
    return m.group(1).lower() in ALLOWED_URL_SCHEMES


class _HTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)  # entities -> unicode, we re-escape on output
        self.out = []
        self._skip_depth = 0  # > 0 while inside a drop-content tag

    def _clean_attrs(self, tag, attrs):
        allowed = ALLOWED_HTML_ATTRS.get(tag, set())
        kept = []
        for name, value in attrs:
            name = (name or "").lower()
            value = value or ""
            if name not in allowed or name.startswith("on"):
                continue
            if name == "href" and not _safe_url(value):
                continue
            kept.append((name, value))
        return kept

    @staticmethod
    def _render_attrs(attrs):
        return "".join(' %s="%s"' % (n, escape(v, quote=True)) for n, v in attrs)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth:
            if tag in DROP_CONTENT_TAGS:
                self._skip_depth += 1
            return
        if tag in DROP_CONTENT_TAGS:
            self._skip_depth = 1
            return
        if tag not in ALLOWED_HTML_TAGS:
            return  # unwrap: drop the tag, keep its children
        clean = self._clean_attrs(tag, attrs)
        if tag == "a":
            clean.append(("rel", "noopener noreferrer nofollow"))
        if tag in VOID_HTML_TAGS:
            self.out.append("<%s />" % tag)
        else:
            self.out.append("<%s%s>" % (tag, self._render_attrs(clean)))

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth or tag in DROP_CONTENT_TAGS or tag not in ALLOWED_HTML_TAGS:
            return
        clean = self._clean_attrs(tag, attrs)
        if tag == "a":
            clean.append(("rel", "noopener noreferrer nofollow"))
        self.out.append("<%s%s />" % (tag, self._render_attrs(clean)))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._skip_depth:
            if tag in DROP_CONTENT_TAGS:
                self._skip_depth -= 1
            return
        if tag in ALLOWED_HTML_TAGS and tag not in VOID_HTML_TAGS:
            self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if not self._skip_depth:
            self.out.append(escape(data, quote=False))

    def handle_comment(self, data):
        return  # drop comments (could hide IE conditionals)


def sanitize_html(value: str) -> str:
    """Allowlist-clean rich text: keep known formatting tags, unwrap unknown
    ones, discard scripts/styles/handlers and non-http(s)/mailto URLs."""
    if not value:
        return value
    parser = _HTMLSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.out).strip()

def sanitize_email(value: str) -> str:
    """
    Sanitize email input safely.

    - trims whitespace
    - converts to lowercase
    - removes control/invisible characters
    - limits length to 100 chars
    """

    if not value:
        return ""

    # ensure string
    value = str(value)

    # remove leading/trailing whitespace
    value = value.strip().lower()

    # remove control characters 
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # collapse internal spaces (rare but safe)
    value = re.sub(r'\s+', '', value)

    # enforce max length
    value = value[:50]

    return value



def sanitize_text(value: str, max_length: int = 100) -> str:
    """
    Sanitize general text input.

    - converts to string
    - trims whitespace
    - removes control characters
    - normalizes spaces
    - enforces max length
    """

    if not value:
        return ""

    # ensure string
    value = str(value)

    # strip leading/trailing whitespace
    value = value.strip()

    # remove control / invisible characters
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # normalize multiple spaces
    value = re.sub(r'\s+', ' ', value)

    # enforce max length
    value = value[:max_length]

    return value