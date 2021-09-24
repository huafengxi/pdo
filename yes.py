#!/usr/bin/env python2
'''
./yes.py ./a.sh
'''
import sys
import pexpect

def help(): print __doc__
len(sys.argv) > 1 or help() or sys.exit(1)

p = pexpect.spawn(' '.join(sys.argv[1:])) 
while p.expect([pexpect.EOF, '\(y/N\)']):
    print p.before
    p.send('y')
print p.before
p.interact()
