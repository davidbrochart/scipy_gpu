import os
from numpy.f2py.crackfortran import crackfortran

def get_magma_types(magma_src, fname):
    with open(f'{magma_src}/{fname}.cpp') as f:
        txt = f.read()
    i0 = txt.find(f'magma_{fname}')
    i0 = txt[i0:].find('(') + i0 + 1
    i1 = txt[i0:].find(')') + i0
    params = txt[i0:i1].split(',')
    types = []
    names = []
    for param in params:
        p = param.split()
        t = p[0]
        n = p[1]
        if t == 'magma_int_t':
            t = 'int'
        elif t == 'magmaFloat_ptr':
            t = 'float*'
        elif t == 'magmaDouble_ptr':
            t = 'double*'
        if n.startswith('*'):
            t += '*'
            n = n[1:]
        types.append(t)
        names.append(n)
    return types, names

def to_magma(fin, module, magma_src, ignore_func):
    if magma_src:
        magma_impl = [f[:-4] for f in os.listdir(magma_src) if f.endswith('.cpp')]
    else:
        magma_impl = []

    ignores = []
    blocks = crackfortran([fin])
    cfile = []
    cfile.append('#include <cuda.h>')
    cfile.append('#include "magma_v2.h"')
    cfile.append('#ifdef SCIPY_GPU_DEBUG')
    cfile.append('#include <stdio.h>')
    cfile.append('#endif')
    for func in blocks[0]['body'][0]['body']:
        name = func['name']
        ignore = False
        for func_name in ignore_func:
            startswith = False
            endswith = False
            if func_name[0] == '*':
                endsswith = True
                func_name = func_name[1:]
            if func_name[-1] == '*':
                startswith = True
                func_name = func_name[:-1]
            if startswith:
                if name.startswith(func_name):
                    ignore = True
            if endswith:
                if name.endswith(func_name):
                    ignore = True
            if name == func_name:
                ignore = True
        if name not in magma_impl:
            ignore = True
        if not ignore:
            types = func['f2pyenhancements']['callprotoargument'].split(',')
            magma_types, params = get_magma_types(magma_src, name)
            if len(types) != len(magma_types):
                # not the same number of parameters, ignore this function
                ignore = True
        if ignore:
            ignores.append(name)
        else:
            cwrap = []
            proto = []
            proto.append(f'void _magma_{name}(')
            proto.append(', '.join([f'{t} {p}' for t, p in zip(types, params)]))
            proto.append(') {')
            cwrap.append(''.join(proto))
            cwrap.append('#ifdef SCIPY_GPU_DEBUG')
            cwrap.append(f'    fprintf(stderr, "GPU {name}\\n");')
            cwrap.append('#endif')
            # MAGMA function call
            margs = []
            for p, t, mt in zip(params, types, magma_types):
                if t == mt:
                    ma = p
                else:
                    ma = f'*{p}'
                margs.append(ma)
            margs = ', '.join(margs)
            cwrap.append(f'    magma_{name}({margs});')
            cwrap.append('}')
            cwrap = '\n'.join(cwrap)
            cfile.append(cwrap)
    
    with open(f'to_magma.c', 'wt') as f:
        f.write('\n'.join(cfile))

    with open(module) as f:
        clines = f.readlines()
    
    new_clines = []
    for l in clines:
        line_done = False
        if not line_done:
            s = 'extern void F_FUNC('
            if (s in l) and not l.startswith('/*'):
                i0 = l.find(s) + len(s)
                i1 = l.find(',')
                name = l[i0:i1]
                i2 = l.find(')')
                if name not in ignores:
                    line_done = True
                    new_l = f'extern void _magma_{name}' + l[i2+1:]
                    new_clines.append(new_l)
        if not line_done:
            s = 'F_FUNC('
            if (s in l) and ('f2py_init_func') in l:
                i0 = l.find(s)
                i1 = i0 + len(s)
                i2 = l[i1:].find(',') + i1
                name = l[i1:i2]
                i3 = l[i1:].find(')') + i1
                if name not in ignores:
                    line_done = True
                    new_l = l[:i0] + f'_magma_{name}' + l[i3+1:]
                    new_clines.append(new_l)
        if not line_done:
            s = 'import_array'
            if s in l:
                line_done = True
                new_l = l + ' magma_init();'
                new_clines.append(new_l)
        if not line_done:
            new_clines.append(l)
    
    with open(module, 'wt') as f:
        f.write(''.join(new_clines))

if __name__ == '__main__':
    to_magma('build/src.linux-x86_64-3.6/flapack.pyf', 'build/src.linux-x86_64-3.6/build/src.linux-x86_64-3.6/_flapackmodule.c', '../magma/magma-2.4.0/src', ignore_func=['c*', 'z*'])