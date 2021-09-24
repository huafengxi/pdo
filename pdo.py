#!/usr/bin/env python2
'''
# why not use xags?
# xargs do not support timeout, do not support dispatch stdin
# what about gnu parallel?
# gnu parallel is much more powerful, but it is a perl script and very complex.

# multi column args file
ARGS=a.list ./pdo.py 'echo $k1 $k2'
# single column args file, from stdin
cat ip.list | ./pdo.py rsync -avz ~/.ssh @stdin:  # ssh get through
# args from file, dup stdin
./pdo.py ssh -T @hosts.list hostname
cat a.sh | ./pdo.py ssh -T @hosts.list
# specify timeout
echo date |timeout=1 par=1 ./pdo.py ssh -T root@@hosts.list # par=-1 to print cmd without execute
# dispatch stdin
cat a.sh | ./pdo.py bash
par=-1 ./pdo.py @a.list
'''

import logging
import sys
import os
import stat
import re
import string
import time
from threading import Thread, Semaphore
from Queue import Queue
try:
    from mysubprocess32 import call,Popen,PIPE,STDOUT,TimeoutExpired
    popen_support_timeout = True
except ImportError:
    popen_support_timeout = False
    from subprocess import call,Popen,PIPE,STDOUT
    class TimeoutExpired(Exception):
        pass
import signal

import platform
DEVNULL=open('/dev/null', 'wb')
def is_executable_file(p):
    if platform.platform().startswith('Linux'):
        return call(['/usr/bin/which', '--skip-alias', p], stdout=DEVNULL) == 0
    else:
        return call(['/usr/bin/which', p], stdout=DEVNULL) == 0

def help():
    print __doc__

import copy
def dict_updated(d, **kw):
    nd = copy.copy(d)
    nd.update(kw)
    return nd

def cfgi(k, v):
    return int(os.getenv(k) or v)

def is_pipe(fd):
    return stat.S_ISFIFO(os.fstat(fd).st_mode)

def is_file(path):
    if path == 'stdin':
        return True
    try:
        os.stat(path)
        return True
    except:
        return False

def read_file(path):
    if path == 'stdin':
        return sys.stdin.readlines()
    with open(path) as f:
        return f.readlines()

def plog(color, msg):
    if sys.stdout.isatty():
        print '\033[%dm%s\033[0m' %(color, msg)
    else:
        print msg
    sys.stdout.flush()
def pinfo(msg):
    if log_level != 'error':
        plog(32, msg)
def perror(msg):
    plog(31, msg)
    sys.stderr.write(msg + '\n')

def wait_child(p):
    if p.returncode == None:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except OSError, e:
            pass
        return -1
    return p.returncode

if popen_support_timeout:
    def popen_communicate(p, input, timeout):
        return p.communicate(input, timeout)
else:
    def popen_communicate(p, input, timeout):
        return p.communicate(input)
def popen(cmd, input, pipe_output=False, timeout=-1):
    env = dict_updated(os.environ, BASH_ENV='~/.env')
    if not is_executable_file(cmd[0]):
        cmd = ['/bin/bash', '-c', ' '.join(cmd)]
    p = Popen(cmd, env=env, stdin=input and PIPE or None, stdout=pipe_output and PIPE or None, stderr=pipe_output and STDOUT or None, preexec_fn=os.setsid)
    logging.debug('input: %s pipe_output: %s'%(input, pipe_output))
    try:
        output = popen_communicate(p, input or None, timeout=timeout)[0]
    except TimeoutExpired:
        output = 'cmd timeout'
    finally:
        err = wait_child(p)
    if err:
        output = 'CmdError: %s err=%d output=%s'%(cmd, err, output)
    return output

def par_map(func, seq, n_thread=1):
    q = Queue()
    result = [None] * len(seq)
    def do_work():
        while True:
            idx, arg = q.get()
            result[idx] = func(*arg)
            pinfo('popen: %s done'%(arg,))
            q.task_done()
    for i in range(n_thread):
        t = Thread(target=do_work)
        t.daemon = True
        t.start()
    for item in enumerate(seq):
        q.put(item)
    q.join()
    return result

def print_result(result):
    for cmd, output in result:
        pinfo(cmd)
        if type(output) == str and 'CmdError' not in output:
            print output.strip()
        else:
            perror(output)

def format_cmd(cmd, input):
    return '%s %s'%(cmd, repr(input and input[:100] or ''))
def mpopen(cmd_list, timeout, par):
    if par == -1:
        for cmd, input in cmd_list:
            print ' '.join(cmd)
    elif par == 1:
        for cmd, input in cmd_list:
            pinfo(format_cmd(cmd, input))
            errmsg = popen(cmd, input, pipe_output=False, timeout=timeout)
            if errmsg:
                perror(errmsg)
    else:
        result = par_map(lambda cmd, input: popen(cmd, input, pipe_output=True, timeout=timeout), cmd_list, par)
        print_result(zip([format_cmd(cmd, input) for cmd, input in cmd_list], result))

def get_file_to_iter(argv):
    f = os.getenv('ARGS')
    if f: return f, argv
    for f in re.findall('@([_./a-zA-Z0-9-]+)', ' '.join(argv)):
        if is_file(f):
            return f, [re.sub('@%s'%(f,), '$k0', i) for i in argv]

def iter_file(path):
    if not path: return ['']
    return [line for line in read_file(path) if not line.startswith('#')]

def construct_cmd(argv, line):
    kv = dict(('k%d'%(i + 1), v) for i, v in enumerate(line.split()))
    kv.update(k0=line)
    return [string.Template(i).safe_substitute(kv) for i in argv]

def get_cmds(argv):
    file_to_iter, argv = get_file_to_iter(argv)
    return file_to_iter, [construct_cmd(argv, line.strip()) for line in iter_file(file_to_iter)]

def get_inputs(args_file):
    if not is_pipe(sys.stdin.fileno()):
        return [None]
    elif args_file == None:
        return [line for line in sys.stdin]
    elif args_file == 'stdin':
        return [None]
    else:
        return [sys.stdin.read()]

def stop(sig, stack):
    print 'sig handler'
    os._exit(1)

if os.getenv('par') == '-1' and not os.getenv('log'):
   os.putenv('log', 'error')
log_level = os.getenv('log') or 'info'
logging.basicConfig(level=getattr(logging, log_level.upper(), None), format="%(asctime)s %(levelname)s %(message)s")
signal.signal(signal.SIGINT, stop)
len(sys.argv) > 1 or help() or sys.exit(1)
args_file, cmds = get_cmds(sys.argv[1:])
inputs = get_inputs(args_file)
timeout, par = cfgi("timeout", "1000"), cfgi('par', '1')
mpopen([(cmd,input) for cmd in cmds for input in inputs], timeout, par)
