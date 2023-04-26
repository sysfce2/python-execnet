import pathlib
import shutil
import subprocess
import sys
import tempfile

import execnet
import pytest

MINOR_VERSIONS = {"3": "543210", "2": "76"}


TEMPDIR = None
_py3_wrapper = None


def setup_module(mod):
    mod.TEMPDIR = pathlib.Path(tempfile.mkdtemp())
    mod._py3_wrapper = PythonWrapper(pathlib.Path(sys.executable))


def teardown_module(mod):
    shutil.rmtree(TEMPDIR)


# we use the execnet folder in order to avoid triggering a missing apipkg
pyimportdir = str(pathlib.Path(execnet.__file__).parent)


class PythonWrapper:
    def __init__(self, executable):
        self.executable = executable

    def dump(self, obj_rep):
        script_file = TEMPDIR.joinpath("dump.py")
        script_file.write_text(
            """
import sys
sys.path.insert(0, %r)
import gateway_base as serializer
# Need binary output
sys.stdout = sys.stdout.detach()
sys.stdout.write(serializer.dumps_internal(%s))
"""
            % (pyimportdir, obj_rep)
        )
        popen = subprocess.Popen(
            [str(self.executable), str(script_file)],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, stderr = popen.communicate()
        ret = popen.returncode
        if ret:
            raise Exception(
                "ExecutionFailed: %d  %s\n%s" % (ret, self.executable, stderr)
            )
        return stdout

    def load(self, data, option_args="__class__"):
        script_file = TEMPDIR.joinpath("load.py")
        script_file.write_text(
            r"""
import sys
sys.path.insert(0, %r)
import gateway_base as serializer
sys.stdin = sys.stdin.detach()
loader = serializer.Unserializer(sys.stdin)
loader.%s
obj = loader.load()
sys.stdout.write(type(obj).__name__ + "\n")
sys.stdout.write(repr(obj))"""
            % (pyimportdir, option_args)
        )
        popen = subprocess.Popen(
            [str(self.executable), str(script_file)],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, stderr = popen.communicate(data)
        ret = popen.returncode
        if ret:
            raise Exception(
                "ExecutionFailed: %d  %s\n%s" % (ret, self.executable, stderr)
            )
        return [s.decode("ascii") for s in stdout.splitlines()]

    def __repr__(self):
        return f"<PythonWrapper for {self.executable}>"


@pytest.fixture
def py3(request):
    return _py3_wrapper


@pytest.fixture
def dump(py3):
    return py3.dump


@pytest.fixture
def load(py3):
    return py3.load


simple_tests = [
    # expected before/after repr
    ("int", "4"),
    ("float", "3.25"),
    ("complex", "(1.78+3.25j)"),
    ("list", "[1, 2, 3]"),
    ("tuple", "(1, 2, 3)"),
    ("dict", "{(1, 2, 3): 32}"),
]


@pytest.mark.parametrize(["tp_name", "repr"], simple_tests)
def test_simple(tp_name, repr, dump, load):
    p = dump(repr)
    tp, v = load(p)
    assert tp == tp_name
    assert v == repr


def test_set(load, dump):
    p = dump("set((1, 2, 3))")

    tp, v = load(p)
    assert tp == "set"
    # assert v == "{1, 2, 3}" # ordering prevents this assertion
    assert v.startswith("{") and v.endswith("}")
    assert "1" in v and "2" in v and "3" in v
    p = dump("set()")
    tp, v = load(p)
    assert tp == "set"
    assert v == "set()"


def test_frozenset(load, dump):
    p = dump("frozenset((1, 2, 3))")
    tp, v = load(p)
    assert tp == "frozenset"
    assert v == "frozenset({1, 2, 3})"


def test_long(load, dump):
    really_big = "9223372036854775807324234"
    p = dump(really_big)
    tp, v = load(p)
    assert tp == "int"
    assert v == really_big


def test_bytes(dump, load):
    p = dump("b'hi'")
    tp, v = load(p)
    assert tp == "bytes"
    assert v == "b'hi'"


def test_str(dump, load):
    p = dump("'xyz'")
    tp, s = load(p)
    assert tp == "str"
    assert s == "'xyz'"


def test_unicode(load, dump):
    p = dump("u'hi'")
    tp, s = load(p)
    assert tp == "str"
    assert s == "'hi'"


def test_bool(dump, load):
    p = dump("True")
    tp, s = load(p)
    assert s == "True"
    assert tp == "bool"


def test_none(dump, load):
    p = dump("None")
    tp, s = load(p)
    assert s == "None"


def test_tuple_nested_with_empty_in_between(dump, load):
    p = dump("(1, (), 3)")
    tp, s = load(p)
    assert tp == "tuple"
    assert s == "(1, (), 3)"
