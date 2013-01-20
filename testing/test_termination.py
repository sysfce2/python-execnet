
import sys, os
import execnet
import time
import subprocess
import py
from execnet.threadpool import WorkerPool
queue = py.builtin._tryimport('queue', 'Queue')
from testing.test_gateway import TESTTIMEOUT
execnetdir = py.path.local(execnet.__file__).dirpath().dirpath()

def test_exit_blocked_slave_execution_gateway(anypython, makegateway):
    gateway = makegateway('popen//python=%s' % anypython)
    channel = gateway.remote_exec("""
        import time
        time.sleep(10.0)
    """)
    def doit():
        gateway.exit()
        return 17

    pool = WorkerPool()
    reply = pool.dispatch(doit)
    x = reply.get(timeout=5.0)
    assert x == 17

def test_endmarker_delivery_on_remote_killterm(makegateway):
    gw = makegateway('popen')
    q = queue.Queue()
    channel = gw.remote_exec(source='''
        import os, time
        channel.send(os.getpid())
        time.sleep(100)
    ''')
    pid = channel.receive()
    py.process.kill(pid)
    channel.setcallback(q.put, endmarker=999)
    val = q.get(TESTTIMEOUT)
    assert val == 999
    err = channel._getremoteerror()
    assert isinstance(err, EOFError)

def test_termination_on_remote_channel_receive(monkeypatch, makegateway):
    if not py.path.local.sysfind('ps'):
        py.test.skip("need 'ps' command to externally check process status")
    monkeypatch.setenv('EXECNET_DEBUG', '2')
    gw = makegateway("popen")
    pid = gw.remote_exec("import os ; channel.send(os.getpid())").receive()
    gw.remote_exec("channel.receive()")
    gw._group.terminate()
    command = ["ps", "-p", str(pid)]
    popen = subprocess.Popen(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    out, err = popen.communicate()
    out = py.builtin._totext(out, 'utf8')
    assert str(pid) not in out, out

@py.test.mark.xfail(reason="non-resolved race/wait/interrupt_main/thread-loop "
 "isdue with some Python interpreters")
def test_close_initiating_remote_no_error(testdir, anypython):
    p = testdir.makepyfile("""
        import sys
        sys.path.insert(0, %r)
        import execnet
        gw = execnet.makegateway("popen")
        print ("remoteinitthreads")
        gw.remote_init_threads(num=2)
        print ("remote_exec1")
        ch1 = gw.remote_exec("channel.receive()")
        print ("remote_exec1")
        ch2 = gw.remote_exec("channel.receive()")
        print ("termination")
        execnet.default_group.terminate()
    """ % str(execnetdir))
    popen = subprocess.Popen([str(anypython), str(p)],
            stdout=None, stderr=subprocess.PIPE,)
    out, err = popen.communicate()
    print (err)
    err = err.decode('utf8')
    lines = [x for x in err.splitlines()
               if '*sys-package' not in x]
    print (lines)
    assert not lines

def test_terminate_implicit_does_trykill(testdir, anypython, capfd):
    p = testdir.makepyfile("""
        import sys
        sys.path.insert(0, %r)
        import execnet
        group = execnet.Group()
        gw = group.makegateway("popen")
        ch = gw.remote_exec("import time ; channel.send(1) ; time.sleep(100)")
        ch.receive() # remote execution started
        sys.stdout.write("1\\n")
        sys.stdout.flush()
        sys.stdout.close()
        class FlushNoOp(object):
            def flush(self):
                pass
        #replace stdout since some python implementations flush and print errors (for example 3.2)
        # see Issue #5319 (from the release notes of 3.2 Alpha 2)
        sys.stdout = FlushNoOp()

        #  use process at-exit group.terminate call
    """ % str(execnetdir))
    popen = subprocess.Popen([str(anypython), str(p)], stdout=subprocess.PIPE)
    # sync with start-up
    line = popen.stdout.readline()
    reply = WorkerPool(1).dispatch(popen.communicate)
    reply.get(timeout=50)
    out, err = capfd.readouterr()
    lines = [x for x in err.splitlines()
               if '*sys-package' not in x]
    assert not lines or "Killed" in err
