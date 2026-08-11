"""Static-analysis adapters."""

from eea_adapters.static_analysis.cpp_syntax import TreeSitterCppSourceAnalyzer
from eea_adapters.static_analysis.cppcheck import CppcheckAdapter

__all__ = ["CppcheckAdapter", "TreeSitterCppSourceAnalyzer"]
