from pydantic import BaseModel

class Target(BaseModel):
    name: str = None
    pyro: float = 0.1
    level: int = 0.1
    hydro: float = 0.1
    dendro: float = 0.1
    eletro: float = 0.1
    anemo: float = 0.1
    cryo: float = 0.1
    physical: float = 0.1

    @classmethod
    def create():
        pass

xiaobao = Target(level = 87, name='85级独眼小宝')

