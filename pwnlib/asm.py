from . import context, log

__all__ = ['asm', 'disasm']

def asm(shellcode, arch = None):
    """asm(code, arch = None) -> assembled

    Assembles a piece of code, represented as a multi-line string."""

    import tempfile, subprocess, os.path, shutil

    # Lookup in context if not found
    if arch == None and context.arch:
        arch = context.arch
    else:
        raise ValueError("asm() needs to get 'arch' through an argument or the context")

    #TODO: constants module should be used to lookup constants
    tmpdir = tempfile.mkdtemp(prefix = 'pwn-asm-')
    def path(s):
        return os.path.join(tmpdir, s)
    try:
        code = []
        asm_extra = []

        if arch not in ['i386', 'amd64']:
            code += ['.section .shellcode,"ax"']

        if arch == 'arm':
            code += ['.syntax unified']
            code += ['.arch armv7-a']
            code += ['.arm']
        elif arch == 'thumb':
            code += ['.syntax unified']
            code += ['.arch armv7-a']
            code += ['.thumb']
            arch = 'arm'
        elif arch == 'i386':
            code += ['bits 32']
        elif arch == 'amd64':
            code += ['bits 64']
        elif arch in ['mips', 'mipsel']:
            code += ['.set mips2']
            code += ['.set noreorder']
            if arch == 'mips':
                asm_extra += ['--EB']
            else:
                asm_extra += ['--EL']
            arch = 'mips'

        code = '\n'.join(code) + shellcode

        if arch in ['i386', 'amd64']:
            assembler = ['nasm', '-Ox'] + asm_extra
            objcopy = ['objcopy']
        else:
            assembler = [os.path.join(pwn.installpath, 'binutils', arch + '-as')] + asm_extra
            if not os.path.isfile(assembler[0]):
                raise Exception('Could not find the gnu assembler for this architecture: %s' % arch)
            objcopy = [os.path.join(pwn.installpath, 'binutils', 'promisc-objcopy')]
        objcopy += ['-j.shellcode', '-Obinary']

        with open(path('step1'), 'w') as fd:
            fd.write(code)

        _run(assembler + ['-o', path('step2'), path('step1')])

        if arch in ['i386', 'amd64']:
            with open(path('step2')) as fd:
                return fd.read()

        # Sanity check for seeing if the output has relocations
        relocs = subprocess.check_output(['readelf', '-r', path('step2')]).strip()
        if len(relocs.split('\n')) > 1:
            raise Exception('There were relocations in the shellcode:\n\n%s' % relocs)

        _run(objcopy + [path('step2'), path('step3')])

        with open(path('step3')) as fd:
            return fd.read()
    finally:
        try:
            shutil.rmtree(tmpdir)
        except:
            pass

def disasm(data, arch = None):
    """disasm(code, arch = None) -> disassembled

    Disassembles a binary piece of shellcode into assembler."""

    import os.path, tempfile, subprocess, shutil
    # Lookup in context if not found
    if arch == None and context.arch:
        arch = context.arch
    else:
        raise ValueError("disasm() needs to get 'arch' through an argument or the context")

    tmpdir = tempfile.mkdtemp(prefix = 'pwn-disasm-')
    def path(s):
        return os.path.join(tmpdir, s)
    try:
        bfdarch = arch
        extra = ['-w', '-N', '*']

        if arch == 'i386':
            bfdname = 'elf32-i386'
        elif arch == 'amd64':
            bfdname = 'elf64-x86-64'
            bfdarch = 'i386:x86-64'
        elif arch == 'arm':
            bfdname = 'elf32-littlearm'
        elif arch == 'thumb':
            bfdname = 'elf32-littlearm'
            bfdarch = 'arm'
            extra = ['--prefix-symbol=$t.']
        elif arch == 'mips':
            bfdname = 'elf32-bigmips'
        elif arch == 'mipsel':
            bfdname = 'elf32-littlemips'
        elif arch == 'alpha':
            bfdname = 'elf64-alpha'
        elif arch == 'cris':
            bfdname = 'elf32-cris'
        elif arch == 'ia64':
            bfdname = 'elf64-ia64-little'
            bfdarch = 'ia64-elf64'
        elif arch == 'm68k':
            bfdname = 'elf32-m68k'
        elif arch == 'powerpc':
            bfdname = 'elf32-powerpc'
        elif arch == 'vax':
            bfdname = 'elf32-vax'

        if arch in ['i386', 'amd64']:
            objcopy = ['objcopy']
            objdump = ['objdump', '-Mintel']
        else:
            objcopy = [os.path.join(pwn.installpath, 'binutils', 'promisc-objcopy')]
            objdump = [os.path.join(pwn.installpath, 'binutils', 'promisc-objdump')]

        objcopy += ['-I', 'binary',
                    '-O', bfdname,
                    '-B', bfdarch,
                    '--set-section-flags', '.data=code',
                    '--rename-section', '.data=.text',
                    ]

        objdump += ['-d']

        with open(path('step1'), 'w') as fd:
            fd.write(data)
        _run(objcopy + extra + [path('step1'), path('step2')])

        output0 = subprocess.check_output(objdump + [path('step2')])
        output1 = output0.split('<.text>:\n')
        if len(output1) != 2:
            raise Exception('Something went wrong with objdump:\n\n%s' % output0)
        else:
            return output1[1].strip('\n')
    finally:
        try:
            shutil.rmtree(tmpdir)
        except:
            pass

def _run(cmd):
    import subprocess, errno
    try:
        p = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout, stderr = p.communicate()
        exitcode = p.wait()
    except OSError as e:
        if e.errno == errno.ENOENT:
            log.die('%s is not installed' % cmd[0])
        else:
            raise
    if exitcode != 0 or stdout != '' or stderr != '':
        err = 'There was a problem running %s.\n' % ' '.join(cmd)
        if exitcode != 0:
            err += 'It had the exitcode %d.\n' % exitcode
        if stdout != '':
            err += 'It had this on stdout:\n%s\n' % stdout
        if stderr != '':
            err += 'It had this on stdout:\n%s\n' % stderr
        raise Exception(err)