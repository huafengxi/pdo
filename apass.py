#!/usr/bin/env python2
'''
APF=~/.apf ./autopass.py ...
'''
import pexpect
import sys
import os

def autopass(cmd_list, passwd):
    p = pexpect.spawn(cmd_list[0], cmd_list[1:])
    if p.expect(['[Pp]assword[^:]+:', pexpect.EOF], timeout=None) == 0:
        p.sendline(passwd.strip())
    print p.before
    p.interact()

if __name__ == '__main__':
    def help(): print __doc__
    len(sys.argv) > 1 or help() or sys.exit()
    autopass(sys.argv[1:], file(os.getenv('APF', os.path.expanduser('~/.apf'))).read())
