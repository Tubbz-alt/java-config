# -*- coding: UTF-8 -*-

# Copyright 2005 Gentoo Foundation
# Distributed under the terms of the GNU General Public license v2
# $Header: $

import sys
sys.path.append("/usr/lib/portage/pym")

import re
from string import upper

import VM, Errors 
from java_config_2.FileParser import *
import os, glob, re
import os.path


# Does not handle deps correctly
# Does however do the right thing for the only types of deps we should see
# Ignore blockers: portage doesn't support them in a way that is usefull for us
class VersionManager:
    """
    Used to parse dependency strings, and find the best/prefered vm to use.
    """
    atom_parser = re.compile(r"([<>=]*)virtual/(jre|jdk)[-:]([0-9\.*]+)")
    virtuals_parser = re.compile(r"([<>=~]+)?java-virtuals/([\w\-\.:]+)")
    package_parser = re.compile(r"([\w\-]+)/([\w\-]+)(?:\:(\d+))?")
    pref_files = ['/etc/java-config-2/build/jdk.conf', '/usr/share/java-config-2/config/jdk-defaults.conf']
    _prefs = None

    def __init__(self):
        pass

    def get_prefs(self):
        if self._prefs:
            return self._prefs
        else:
            self._prefs = []
            for file in self.pref_files:
                if os.path.exists(file):
                    self._prefs += PrefsFileParser(file).get_config()
            return self._prefs

    def parse_depend(self, atoms):
        """Filter the dependency string for useful information"""
      
        #pkg_name, highest_pkg_target = self.get_target_from_pkg_deps(self.parse_depend_packages(atoms))
        matched_atoms = []
        atoms = self.filter_depend(atoms)
        matches = self.atom_parser.findall(atoms)
       
        if len(matches) >  0:
            for match in matches:
                #if highest_pkg_target and self.version_cmp(match[2], highest_pkg_target) < 0:
                #    continue
                matched_atoms.append({'equality':match[0], 'type':match[1], 'version':match[2]})

        #if len(matched_atoms) == 0 and pkg_name and highest_pkg_target:
        #    raise Exception("Couldn't find a suitable VM due to dependency %s having a required target of %s" % (pkg_name, highest_pkg_target))

        matched_atoms.sort()
        matched_atoms.reverse()

        return matched_atoms

    def parse_depend_packages(self, atoms):
        """ Parse atoms for possible packages. This excludes virtual/[jdk|jre] but includes java-virtuals"""

        matched_atoms = []
        atoms = self.filter_depend(atoms)
        matches = self.package_parser.findall(atoms)

        if len(matches) > 0:
            for match in matches:
                if not (match[0] == 'virtual' and (match[1] == 'jdk-1' or match[1] == 'jre-1' or match[1] == 'jdk' or match[1] == 'jre' )):
                        matched_atoms.append({'equality':'=', 'cat':match[0], 'pkg':match[1], 'slot':match[2]})
        
        return matched_atoms

    def filter_depend( self, atoms ):
        """Filter the dependency string for useful information"""

        import os
        # gjl does not use use flags
        try:
            use = os.environ["USE"]

            # Local import to avoid initializing portage elsewhere
            try:
                from portage.dep import use_reduce,paren_reduce
            except ImportError:
                from portage_dep import use_reduce,paren_reduce
            from portage import flatten

            # Normalize white space for Portage
            atoms = " ".join(atoms.split())

            # Remove conditional depends that are not turned on
            atoms = " ".join(flatten(use_reduce(paren_reduce(atoms),uselist=use)))
        except KeyError:
            pass
        return atoms

    def parse_depend_virtuals(self, atoms):
        """Filter the dependency string for useful information"""
        atoms=self.filter_depend(atoms)
        virtuals_matches = self.virtuals_parser.findall(atoms)
        matched_virtuals = ""

        for match in virtuals_matches:
            matched_virtuals += " " + match[1].replace(':0', '').replace(':', '-')

        return matched_virtuals[1:]

    def matches(self, version_a, version_b, operator):
        val = self.version_cmp(version_a, version_b)
        
        #now assuming that if no operator we are
        #doing an '=' comparision. Used to handle cases like virtual/jdk:1.5
        if operator == '>=': return val >= 0
        elif operator == '<=': return val <= 0
        elif operator == '>':  return val > 0
        elif operator == '<':  return val < 0
        else:                  return val == 0
                
    def version_satisfies(self, atoms, vm):
        version = vm.version()
        matched_atoms = self.parse_depend(atoms)

        for atom in matched_atoms:
            if vm.is_type(atom['type']):
                if self.matches(version, atom['version'], atom['equality']):
                    return True
        return False

    def get_lowest_atom(self, atoms):
        lowest = None
        for atom in atoms:
            if not lowest:
                lowest = atom
            else:
                if self.version_cmp(lowest['version'], atom['version']) > 0:
                    lowest = atom

        if lowest:
            return atom
        else:
            raise Exception("Couldn't find a VM dep")

    def get_lowest(self, atoms):
        atoms = self.parse_depend(atoms)
        lowest = self.get_lowest_atom(atoms)
        lowest = lowest['version']

        if lowest:
            return '.'.join(lowest.strip('*').split('.')[0:2])
        else:
            raise Exception("Couldn't find a VM dep")

    def get_target_from_pkg_deps(self, matches):
        """ Get the lowest virtual machine version from a packages dependencies."""
        from java_config_2.EnvironmentManager import EnvironmentManager
        manager = EnvironmentManager()
        highest = None
        pkg_name = None

        pkgs=[]

        for match in matches:
            pkg_name = match['pkg']
            if match['slot'] and match['slot'] != '0':
                pkg_name += '-' + match['slot']
            try:
                pkg = manager.get_package(pkg_name)
                pkgs.append(pkg)
            except Exception, e:
                pass

        deep_pkgs = get_needed_packages(*pkgs)

        for pkg in deep_pkgs:
            try:
                target = pkg.target()
                if not highest:
                    highest = target
                    pkg_name = pkg.name()
                if self.version_cmp(highest, target) < 0:
                    highest = target
                    pkg_name = pkg.name()
            except:
                pass
        
        return pkg_name, highest

    def get_vm(self, atoms, allow_build_only = False):
        from java_config_2.EnvironmentManager import EnvironmentManager

        pkg_name, highest_pkg_target = self.get_target_from_pkg_deps(self.parse_depend_packages(atoms))

        matched_atoms = self.parse_depend(atoms)
        matched_virtuals = self.parse_depend_virtuals(atoms)
        need_virtual = None
        
        if not len(matched_virtuals) == 0:
            need_virtual = matched_virtuals

        prefs = self.get_prefs()
        # first try to find vm based on preferences
        low = self.get_lowest(atoms) # Lowest vm version we can use

        for atom in matched_atoms: 
            for pref in prefs:
                if pref[0] == low or pref[0] == "*": # We have a configured preference for this version
                    for vmProviderString in pref[1]: # Loop over the prefered once, and check if they are valid
                        for gvm in self.find_vm(vmProviderString, atom, highest_pkg_target, allow_build_only):
                            if need_virtual: # Package we are finding a vm for needs a virtual
                                # New, correct way of searching for virtuals
                                if EnvironmentManager().have_provider(need_virtual, gvm, self): # We have a package available that provides it, will use that
                                    return gvm
                            else:
                                return gvm          # use it!
       
        # no match in preferences, find anything we have
        # Support for virtuals too here
        for atom in matched_atoms:
            for gvm in self.find_vm("", atom, highest_pkg_target, allow_build_only):
                if need_virtual:         # Package we are finding a vm for needs a virtual
                    if EnvironmentManager().have_provider(need_virtual, gvm, self):
                        return gvm
                else:
                    return gvm
        # nothing found
        raise Exception("Couldn't find suitable VM. Possible invalid dependency string.")


    def find_vm(self, vmProviderString, atom, min_package_target, allow_build_only = True):
        from java_config_2.EnvironmentManager import EnvironmentManager
        vm_list = EnvironmentManager().find_vm(vmProviderString)
        vm_list.sort()
        vm_list.reverse()
        for vm in vm_list:
            if min_package_target and self.version_cmp(vm.version(), min_package_target) < 0:
                continue
            if not allow_build_only and vm.is_build_only():
                continue
            if vm.is_type(atom['type']):
                if self.matches(vm.version(), atom['version'], atom['equality']):
                    yield vm

    def version_cmp(self, version1, version2):
        #Parly stolen from portage.py
        if version1 == version2:
            return 0

        version1 = version1.split('.')
        version2 = version2.split('.')

        check_len = None
        for x in range(1, len(version1)):
            if version1[x][-1] == '*':
                version1[x] = version1[x][:-1]
                check_len = x
            if version1[x][0] == '0':
                version1[x]='.' + version1[x]

        for x in range(1, len(version2)):
            if version2[x][-1] == '*':
                version2[x] = version2[x][:-1]
                if (not check_len) or (check_len and check_len > x):
                    check_len = x
            if version2[x][0] == '0':
                version2[x]='.' + version2[x]

       
        if len(version2) < len(version1):
            version2.extend(["0"]*(len(version1)-len(version2)))
        elif len(version1) < len(version2):
            version1.extend(["0"]*(len(version2)-len(version1)))

        for x in range(0, len(version1)):
            if check_len and x > check_len:
                return 0
            ret = float(version1[x]) - float(version2[x])
            if ret != 0:
                return ret
        return 0


def get_needed_packages(*packages):
    from java_config_2.EnvironmentManager import EnvironmentManager

    manager = EnvironmentManager()

    unresolved = set()
    for package in packages:
        unresolved.add(package)

    resolved = set()

    while len(unresolved) > 0:
        pkg = unresolved.pop()
        resolved.add(pkg)
        # dep is in the form of (jar, pkg)
        for dep in manager.get_pkg_deps(pkg):
            dep_pkg = dep[-1]
            p = manager.get_package(dep_pkg)
            if p is None:
                if ',' in dep_pkg:
                    msg = """
Package %s has a broken DEPEND entry in package.env. Please reinstall it.
If this does not fix it, please report this to http://bugs.gentoo.org
"""
                    msg = msg % pkg
                else:
                    msg = """
Package %s not found in the system. This package is listed as a
dependency of %s. Please run emerge -1Da %s and if it does not bring in the
needed dependency, report this to http://bugs.gentoo.org.
"""
                    msg = msg % (dep_pkg,pkg,pkg)
                abort(msg)

            if p not in resolved:
                unresolved.add(p)

    return resolved

#vator=VersionManager()
#for i in [  
#            ">=virtual/jdk-1.3",
#            ">=virtual/jdk-1.4",
#            ">=virtual/jdk-1.5",
#            "|| ( =virtual/jdk-1.4* =virtual/jdk-1.3* )",
#            "|| ( =virtual/jdk-1.3* =virtual/jdk-1.4* )",
#            "=virtual/jdk-1.5*",
#            "=virtual/jdk-1.4*",
#            "=virtual/jdk-1.3*",
#        ]:
#    print i
#    try:
#    print vator.get_vm(i)
#    except Exception, ex:
#        print ex
#    print

# vim:set expandtab tabstop=4 shiftwidth=4 softtabstop=4 nowrap:
