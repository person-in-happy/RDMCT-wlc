from shared_source import load_shared
load_shared(globals())

if __name__=="__main__":
    if sys.argv[1:2]==["trial"]:
        trial(Path(sys.argv[2]))
    else:
        check()
