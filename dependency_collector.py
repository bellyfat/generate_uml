import ast
from collections import ChainMap
from types import MappingProxyType as readonlydict


class ModuleUseCollector(ast.NodeVisitor):
    def __init__(self, modulename, package=''):
        """initialize the class ModuleUseCollector, inherited from ast.NodeVisitor.

        Arguments:
            ast {object} -- ast inheritance
            modulename {str} -- name of the module for which we want to compute its usage.

        Keyword Arguments:
            package {str} -- Python package where the search for this module's
                             usage should occur. (default: {''})
        """
        self.modulename = modulename
        # used to resolve from ... import ... references
        self.package = package
        self.modulepackage, _, self.modulestem = modulename.rpartition('.')
        # track scope namespaces, with a mapping of imported names (bound name to original)
        # If a name references None it is used for a different purpose in that scope
        # and so masks a name in the global namespace.
        self.scopes = ChainMap()
        self.used_at = []  # list of (name, alias, line) entries

    def visit_FunctionDef(self, node):
        """visit the function's definition for tracing usage.
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        self.scopes = self.scopes.new_child()
        self.generic_visit(node)
        self.scopes = self.scopes.parents

    def visit_Lambda(self, node):
        """visit lambda type of functions' usage.
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        # lambdas are just functions, albeit with no statements
        self.visit_Function(node)

    def visit_ClassDef(self, node):
        """class scope is a special local scope that is re-purposed to form
        the class attributes. By using a read-only dict proxy here this code
        we can expect an exception when a class body contains an import
        statement or uses names that'd mask an imported name.
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        # 
        self.scopes = self.scopes.new_child(readonlydict({}))
        self.generic_visit(node)
        self.scopes = self.scopes.parents

    def visit_Import(self, node):
        """visit import declarations
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        self.scopes.update({
            a.asname or a.name: a.name
            for a in node.names
            if a.name == self.modulename
        })

    def visit_ImportFrom(self, node):
        """resolve relative imports; from . import <name>, from ..<name> import <name>
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        source = node.module  # can be None
        if node.level:
            package = self.package
            if node.level > 1:
                # go up levels as needed
                package = '.'.join(self.package.split('.')[:-(node.level - 1)])
            source = f'{package}.{source}' if source else package
        if self.modulename == source:
            # names imported from our target module
            self.scopes.update({
                a.asname or a.name: f'{self.modulename}.{a.name}'
                for a in node.names
            })
        elif self.modulepackage and self.modulepackage == source:
            # from package import module import, where package.module is what we want
            self.scopes.update({
                a.asname or a.name: self.modulename
                for a in node.names
                if a.name == self.modulestem
            })

    def visit_Name(self, node):
        """ #TODO
        
        Arguments:
            node {str} -- name of the node where we want to check the usage.
        """
        if not isinstance(node.ctx, ast.Load):
            # store or del operation, means the name is masked in the current scope
            try:
                self.scopes[node.id] = None
            except TypeError:
                # class scope, which we made read-only. These names can't mask
                # anything so just ignore these.
                pass
            return
        # find scope this name was defined in, starting at the current scope
        imported_name = self.scopes.get(node.id)
        if imported_name is None:
            return
        self.used_at.append((imported_name, node.id, node.lineno))
