# -*- coding: UTF-8 -*-

# Copyright 2004-2005 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

from Package import Package
from VM import VM
from Errors import *

from os.path import basename, dirname
from glob import glob
import os, re


class EnvironmentManager:
    virtual_machines = None
    packages = None
    active = None

    vms_path = '/etc/env.d/java/'
    pkg_path = '/usr/share/*/package.env'

    def __init__(self):
        pass

    def load_vms(self):
        self.virtual_machines = {} 
        
        if os.path.isdir(self.vms_path):
            count = 1
            for file in os.listdir(self.vms_path):
                conf = os.path.join(self.vms_path, file)

                if file.startswith("20"):
                    vm = None

                    try:
                        vm = VM(conf)
                    except InvalidConfigError:
                        pass
                    except PermissionError:
                        pass

                    self.virtual_machines[count] = vm
                    count += 1
         
    def load_packages(self):
        self.packages = []
        for package in iter(glob(pkg_path)):
            self.packages.append(Package(package, basename(dirname(package))))

    def load_active_vm(self):
        environ_path = [
                                os.path.join(os.environ.get('HOME'), '.gentoo', 'java'),
                                os.path.join('/', 'etc', 'env.d', '20java')
                            ]

        java_home = None

        for file in environ_path:
            try:
                stream = open(file, 'r')
            except IOError:
                continue
            
            read = stream.readline()
            while read:
                if read.strip().startswith('JAVA_HOME'):
                    stream.close()
                    java_home = read.split('=', 1)[-1].strip()
                    break
                else:
                    read = stream.readline()
            stream.close()        

        for vm in self.get_virtual_machines().itervalues():
            if vm.query('JAVA_HOME') == java_home:
                self.active = vm
                return vm

        raise InvalidVMError

    def set_active_vm(self, vm):
        self.active = vm
 
    def get_active_vm(self):
        if self.active is None:
            self.load_active_vm()
        return self.active

    def get_virtual_machines(self):
        if self.virtual_machines is None:
            self.load_vms()
        return self.virtual_machines

    def find_vm(self, name):
        found = []
        for id, vm in self.get_virtual_machines().iteritems():
            if vm.name().startswith(name):
                found.append(vm)
        return found

    def get_packages(self):
        if self.packages is None:
            self.load_packages()
        return self.packages

    def query_packages(self, packages, query):
        results = []

        for package in iter(self.get_packages()):
            if package.name() in packages:
                value = package.query(query)
                if value:
                    results.append(value)
                packages.remove(package.name())

        return results

    def get_vm(self, machine):
        vm_list = self.get_virtual_machines()
        selected = None

        for count in iter(vm_list):
            vm = vm_list[count]

            if str(machine).isdigit():
                if int(machine) is count:
                    return vm
            else:
                # Check if the vm is specified via env file
                if machine == vm.filename():
                    return vm 

                # Check if the vm is specified by name 
                elif machine == vm.name():
                    return vm

                # Check if the vm is specified via JAVA_HOME
                elif machine == vm.query('JAVA_HOME'):
                    return vm

                # Check if vm is specified by partial name 
                elif vm.name().startswith(machine):
                    selected = vm

        if selected:
            return selected
        else:
            return None

    def create_env_entry(self, vm, stream, render="%s=%s\n"):
        stream.write("# Autogenerated by java-config\n")
        stream.write("# Java Virtual Machine: %s\n\n" % vm.query('VERSION'))

        try:
            ENV_VARS = vm.query('ENV_VARS')
            for (item, value) in vm.get_config().iteritems():
                if item in ENV_VARS:
                    stream.write(render % (item, value))
        except IOError:
            raise PermissionError
        except EnvironmentUndefinedError:
            raise EnvironmentUndefinedError

    def set_vm(self, vm, sh_env_file, csh_env_file=None):

        # Create the SH environment file
        if sh_env_file is not None:
            try:
                stream = open(sh_env_file, 'w')
            except IOError:
                raise PermissionError

            try:
                self.create_env_entry(vm, stream, "%s=%s\n")
            except IOError:
                stream.close()
                raise PermissionError
            except EnvironmentUndefinedError:
                stream.close();
                raise EnvironmentUndefinedError

            stream.close()

        # Create the CSH environment file
        if csh_env_file is not None:
            try:
                stream = open(csh_env_file, 'w')
            except IOError:
                raise PermissionError

            try:
                self.create_env_entry(vm, stream, "setenv %s %s\n")
            except IOError:
                stream.close()
                raise PermissionError

            stream.close()

    def clean_classpath(self, env_file):
        if os.path.isfile(env_file):
            try:
                os.remove(env_file)
            except IOError:
                raise PermissionError

    def set_classpath(self, env_file, pkgs):
        classpath = self.query_packages(pkgs, "CLASSPATH")
        classpath = re.sub(':+', ':', ':'.join(classpath)).strip(':')

        self.clean_classpath(env_file)

        self.write_classpath(env_file, classpath)

    def append_classpath(self, env_file, pkgs):
        classpath = self.query_packages(pkgs, "CLASSPATH")
        classpath = re.sub(':+', ':', ':'.join(classpath)).strip(':')

        oldClasspath = ''
        if os.path.isfile(env_file):
            try:
                stream = open(env_file, 'r')
            except IOError:
                raise PermissionError

            read = stream.readline()
            while read:
                if read.strip().startswith('CLASSPATH'):
                    stream.close()
                    oldClasspath = read.split('=', 1)[-1].strip()
                    break
                else:
                    read = stream.readline()
            stream.close()

        classpath = oldClasspath + ':' + classpath

        self.clean_classpath(env_file)

        self.write_classpath(env_file, classpath)

    def write_classpath(self, env_file, classpath):
        try:
            stream = open(env_file, 'w')
        except IOError:
            raise PermissionError

        stream.write("CLASSPATH=%s\n" % (classpath))
        stream.close()

# vim:set expandtab tabstop=4 shiftwidth=4 softtabstop=4 nowrap:
