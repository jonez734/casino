from . import lib

def init(args, **kw:dict) -> bool:
    return True

def access(args, op:str, **kw:dict) -> bool:
    return True

def buildargs(args, **kw:dict) -> bool:
    return None

def main(args, **kw):
    lib.runmodule(args, "main", **kw)
    return True
