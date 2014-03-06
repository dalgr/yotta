# standard library modules, , ,
import string
import os
import logging

# fsutils, , misc filesystem utils, internal
import fsutils

CMakeLists_Template = string.Template(
'''#
#
# NOTE: This file is generated by yotta: changes will be overwritten!
#
#
cmake_minimum_required(VERSION 2.8)

# toolchain file for $target_name
set(CMAKE_TOOLCHAIN_FILE $toolchain_file)

project($component_name)

# include own root directory
$include_own_dir

# include root directories of all components we depend on (directly and
# indirectly)
$include_root_dirs

# recurse into dependencies that aren't built elsewhere
$add_depend_subdirs


# Some components (I'm looking at you, libc), need to export system header
# files with no prefix, these directories are listed in the component
# description files:
$include_sys_dirs

# And others (typically CMSIS implementations) need to export non-system header
# files. Please don't use this facility. Please. It's much, much better to fix
# implementations that import these headers to import them using
# #include "modname/headername.h" instead
$include_other_dirs

# Components may defined additional preprocessor definitions: use this at your
# peril, this support WILL go away! (it's here to bridge toolchain component ->
# target package switchover)
get_property(EXTRA_DEFINITIONS GLOBAL PROPERTY YOTTA_GLOBAL_DEFINITIONS)
add_definitions($${EXTRA_DEFINITIONS})

# !!! FIXME: actually the target can just add these to the toolchain, no need
# for repitition in every single cmake list
# Build targets may define additional preprocessor definitions for all
# components to use (such as chip variant information)
#$yotta_target_definitions


# recurse into subdirectories for this component, using the two-argument
# add_subdirectory because the directories referred to here exist in the source
# tree, not the working directory
$add_own_subdirs

'''
)

Ignore_Subdirs = set(('build',))

class CMakeGen(object):
    def __init__(self, directory, target):
        super(CMakeGen, self).__init__()
        self.buildroot = directory
        logging.info("generate for target: %s" % target)
        self.target = target

    def generateRecursive(self, component, all_components, builddir=None, processed_components=None):
        ''' generate top-level CMakeLists for this component and its
            dependencies: the CMakeLists are all generated in self.buildroot,
            which MUST be out-of-source

            !!! NOTE: experimenting with a slightly different way of doing
            things here, this function is a generator that yields any errors
            produced, so the correct use is:

            for error in gen.generateRecursive(...):
                print error
        '''
        if builddir is None:
            builddir = self.buildroot
        if processed_components is None:
            processed_components = dict()
        if not self.target:
            yield 'Target "%s" is not a valid build target' % self.target
    
        logging.debug('generate build files: %s (target=%s)' % (component, self.target))
        # because of the way c-family language includes work we need to put the
        # public header directories of all components that this component
        # depends on (directly OR indirectly) into the search path, which means
        # we need to first enumerate all the direct and indirect dependencies
        recursive_deps = component.getDependenciesRecursive(
            available_components = all_components,
                          target = self.target,
                  available_only = True
        )
        dependencies = component.getDependencies(
                  all_components,
                          target = self.target,
                  available_only = True
        )

        for name, dep in dependencies.items():
            if not dep:
                yield 'Required dependency "%s" of "%s" is not installed.' % (name, component)
        new_dependencies = {name:c for name,c in dependencies.items() if c and not name in processed_components}
        self.generate(builddir, component, new_dependencies, recursive_deps)

        logging.debug('recursive deps of %s:' % component)
        for d in recursive_deps.values():
            logging.debug('    %s' % d)

        processed_components.update(new_dependencies)
        for name, c in new_dependencies.items():
            for error in self.generateRecursive(c, all_components, os.path.join(builddir, name), processed_components):
                yield error


    def generate(self, builddir, component, active_dependencies, all_dependencies):
        ''' active_dependencies is the dictionary of components that need to be
            built for this component, but will not already have been built for
            another component.
        '''

        include_own_dir = string.Template(
            'include_directories("$path")\n'
        ).substitute(path=component.path)

        include_root_dirs = ''
        include_sys_dirs = ''
        include_other_dirs = ''
        for name, c in all_dependencies.items():
            include_root_dirs += string.Template(
                'include_directories("$path")\n'
            ).substitute(path=c.path)
            dep_sys_include_dirs = c.getExtraSysIncludes()
            for d in dep_sys_include_dirs:
                include_sys_dirs += string.Template(
                    'include_directories(SYSTEM "$path")\n'
                ).substitute(path=os.path.join(c.path, d))
            dep_extra_include_dirs = c.getExtraIncludes()
            for d in dep_extra_include_dirs:
                include_other_dirs += string.Template(
                    'include_directories("$path")\n'
                ).substitute(path=os.path.join(c.path, d))

        add_depend_subdirs = ''
        for name, c in active_dependencies.items():
            add_depend_subdirs += string.Template(
                'add_subdirectory("$working_dir/$component_name")\n'
            ).substitute(
                working_dir=builddir,
                component_name=name
            )

        add_own_subdirs = ''
        for f in os.listdir(component.path):
            if f in Ignore_Subdirs:
                continue
            if os.path.isfile(os.path.join(component.path, f, 'CMakeLists.txt')):
                add_own_subdirs += string.Template(
                    '''add_subdirectory(
    "$component_source_dir/$subdir_name"
    "$working_dir/$subdir_name"
)
'''
                ).substitute(
                    component_source_dir=component.path,
                    working_dir=builddir,
                    subdir_name=f
                )

        file_contents = CMakeLists_Template.substitute(
                         target_name = self.target.getName(),
                      toolchain_file = self.target.getToolchainFile(),
                      component_name = component.getName(),
                     include_own_dir = include_own_dir,
                   include_root_dirs = include_root_dirs,
                    include_sys_dirs = include_sys_dirs,
                  include_other_dirs = include_other_dirs,
                  add_depend_subdirs = add_depend_subdirs,
                     add_own_subdirs = add_own_subdirs,
            yotta_target_definitions = '' # TODO
        )
        fsutils.mkDirP(builddir)
        with open(os.path.join(builddir, 'CMakeLists.txt'), 'w') as f:
            f.write(file_contents)


        
