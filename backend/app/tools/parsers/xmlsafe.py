"""XML from a tool, read without trusting it.

No entity is expanded, no DTD is loaded, nothing is fetched over the network, and a document that
is huge or deeply nested is refused. A DOCTYPE line alone (nmap writes one) is fine.
"""

from lxml import etree
from lxml.etree import _Element  # pyright: ignore[reportPrivateUsage]

from app.tools.parsers.base import ParseError, check_size

Element = _Element
_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
    remove_comments=True,
    remove_pis=True,
)


def parse_xml(data: bytes) -> Element:
    """The root element of an XML document, or a `ParseError`."""
    check_size(data)
    if b"<!ENTITY" in data:
        raise ParseError("The output declares an XML entity, which is not allowed")
    try:
        root = etree.fromstring(data.strip(), _PARSER)  # the parser is hardened above
    except etree.XMLSyntaxError, ValueError:
        raise ParseError("The output is not valid XML") from None
    return root
