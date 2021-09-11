from pathlib import Path

USER_DIR = Path('data/genshin/calculator')
USER_CHARA_DIR = USER_DIR.joinpath('chara')
USER_ART_DIR = USER_DIR.joinpath('artifact_set')
 
if not USER_DIR.exists():
    USER_DIR.mkdir()

if not USER_CHARA_DIR.exists():
    USER_CHARA_DIR.mkdir()

if not USER_ART_DIR.exists():
    USER_ART_DIR.mkdir()