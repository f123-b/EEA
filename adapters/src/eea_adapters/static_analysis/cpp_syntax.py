"""Tree-sitter C/C++ syntax adapter for deterministic firmware rules."""

from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import tree_sitter_c as tree_sitter_c_language
import tree_sitter_cpp as tree_sitter_cpp_language
from eea_ports.cpp_syntax import CppCall, CppFunction, CppSourceAnalysis
from tree_sitter import Language, Node, Parser


class TreeSitterCppSourceAnalyzer:
    """Resolve C/C++ calls and function definitions from a real syntax tree."""

    name = "tree-sitter-c-cpp/v1"
    _CPP_SUFFIXES: ClassVar[set[str]] = {".cc", ".cpp", ".cxx", ".hh", ".hpp"}

    def analyze(self, path: Path | str, source: str) -> CppSourceAnalysis:
        source_path = Path(path)
        try:
            source_bytes = source.encode("utf-8")
            language = Language(
                tree_sitter_cpp_language.language()
                if source_path.suffix.lower() in self._CPP_SUFFIXES
                else tree_sitter_c_language.language()
            )
            parser = Parser(language)
            tree = parser.parse(source_bytes)
        except (UnicodeError, TypeError, ValueError) as exc:
            return CppSourceAnalysis(
                path=source_path.as_posix(),
                parse_ok=False,
                diagnostics=(f"parser initialization or encoding failed: {type(exc).__name__}",),
                calls=(),
                functions=(),
            )

        if tree.root_node.has_error:
            return CppSourceAnalysis(
                path=source_path.as_posix(),
                parse_ok=False,
                diagnostics=("syntax tree contains parse errors",),
                calls=(),
                functions=(),
            )

        calls = tuple(
            CppCall(name=self._call_name(node, source_bytes), line=node.start_point[0] + 1)
            for node in self._descendants(tree.root_node, "call_expression")
        )
        functions = tuple(
            self._function(node, source_bytes)
            for node in self._descendants(tree.root_node, "function_definition")
        )
        return CppSourceAnalysis(
            path=source_path.as_posix(),
            parse_ok=True,
            diagnostics=(),
            calls=calls,
            functions=functions,
        )

    @classmethod
    def _function(cls, node: Node, source: bytes) -> CppFunction:
        declarator = node.child_by_field_name("declarator")
        body = node.child_by_field_name("body")
        calls = (
            ()
            if body is None
            else tuple(
                CppCall(name=cls._call_name(call, source), line=call.start_point[0] + 1)
                for call in cls._descendants(body, "call_expression")
            )
        )
        return CppFunction(
            name=cls._declarator_name(declarator, source) if declarator is not None else "",
            line=node.start_point[0] + 1,
            calls=calls,
        )

    @classmethod
    def _call_name(cls, node: Node, source: bytes) -> str:
        function = node.child_by_field_name("function")
        if function is None:
            return ""
        return cls._node_text(function, source)

    @classmethod
    def _declarator_name(cls, node: Node | None, source: bytes) -> str:
        if node is None:
            return ""
        if node.type in {
            "identifier",
            "field_identifier",
            "qualified_identifier",
            "scoped_identifier",
        }:
            return cls._node_text(node, source)
        for child in node.children:
            name = cls._declarator_name(child, source)
            if name:
                return name
        return ""

    @staticmethod
    def _node_text(node: Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @classmethod
    def _descendants(cls, node: Node, node_type: str) -> Iterator[Node]:
        for child in node.children:
            if child.type == node_type:
                yield child
            yield from cls._descendants(child, node_type)


__all__ = ["TreeSitterCppSourceAnalyzer"]
