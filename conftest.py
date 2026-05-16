"""Root conftest: install sgmllib stub so feedparser can be imported in Python 3.11+.

feedparser 6.0.x requires sgmllib3k which fails to build on this platform.
We inject a compatible stub before any test module triggers the import.
"""
import re
import sys
import types

if "sgmllib" not in sys.modules:
    _sgml = types.ModuleType("sgmllib")
    _sgml.interesting = re.compile("[&<]")
    _sgml.incomplete = re.compile("&[a-zA-Z#]")
    _sgml.entityref = re.compile("&([a-zA-Z][-.a-zA-Z0-9]*)[^a-zA-Z0-9]")
    _sgml.starttagopen = re.compile("<[>a-zA-Z]")
    _sgml.shorttagopen = re.compile("<[a-zA-Z][a-zA-Z0-9]*/")
    _sgml.shorttag = re.compile("<([a-zA-Z][a-zA-Z0-9]*)/([^/]*)")

    class _SGMLParser:
        """Minimal stub satisfying feedparser's html.py metaclass introspection.

        feedparser.html copies __code__ / func_code from goahead and
        parse_starttag at class-definition time, and calls parse_declaration
        at runtime.  The stubs only need to have the right attributes.
        """

        def goahead(self, end):
            pass

        def parse_starttag(self, i):
            return -1

        def parse_declaration(self, i):
            return -1

    # feedparser assigns func_code (Python 2 name) on the function objects.
    _SGMLParser.goahead.func_code = _SGMLParser.goahead.__code__  # type: ignore[attr-defined]
    _SGMLParser.parse_starttag.func_code = _SGMLParser.parse_starttag.__code__  # type: ignore[attr-defined]
    _sgml.SGMLParser = _SGMLParser
    sys.modules["sgmllib"] = _sgml
