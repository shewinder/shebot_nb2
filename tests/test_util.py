from hoshino.util.sutil import get_md5

def test_get_md():
    s = 'hello world'
    assert(get_md5(s) == '5eb63bbbe01eeed093cb22bb8f5acdc3')
    assert(get_md5('') == 'd41d8cd98f00b204e9800998ecf8427e')
    assert(get_md5(bytes(2)) == 'c4103f122d27677c9db144cae1394a66')



